import asyncio
import logging
import os
from dataclasses import dataclass

from .. import converter
from ..client import Client, Downloadable
from ..config import Config
from ..db import Database
from ..exceptions import NonStreamableError
from ..filepath_utils import clean_filename
from ..metadata import AlbumMetadata, Covers, TrackMetadata, tag_file
from ..progress import add_title, get_progress_callback, remove_title
from .artwork import download_artwork
from .media import Media, Pending
from .semaphore import global_download_semaphore

logger = logging.getLogger("streamrip")


@dataclass(slots=True)
class Track(Media):
    meta: TrackMetadata
    downloadable: Downloadable
    config: Config
    folder: str
    # Is None if a cover doesn't exist for the track
    cover_path: str | None
    db: Database
    # change?
    download_path: str = ""
    is_single: bool = False

    async def preprocess(self):
        self._set_download_path()
        os.makedirs(self.folder, exist_ok=True)
        if self.is_single:
            add_title(self.meta.title)

    async def download(self):
        # TODO: progress bar description
        async with global_download_semaphore(self.config.session.downloads):
            with get_progress_callback(
                self.config.session.cli.progress_bars,
                await self.downloadable.size(),
                f"Track {self.meta.tracknumber}",
            ) as callback:
                try:
                    await self.downloadable.download(self.download_path, callback)
                    retry = False
                except Exception as e:
                    logger.error(
                        f"Error downloading track '{self.meta.title}', retrying: {e}"
                    )
                    retry = True

            if not retry:
                return

            with get_progress_callback(
                self.config.session.cli.progress_bars,
                await self.downloadable.size(),
                f"Track {self.meta.tracknumber} (retry)",
            ) as callback:
                try:
                    await self.downloadable.download(self.download_path, callback)
                except Exception as e:
                    logger.error(
                        f"Persistent error downloading track '{self.meta.title}', skipping: {e}"
                    )
                    self.db.set_failed(
                        self.downloadable.source, "track", self.meta.info.id
                    )

    async def postprocess(self):
        if self.is_single:
            remove_title(self.meta.title)

        await tag_file(self.download_path, self.meta, self.cover_path)
        if self.config.session.conversion.enabled:
            await self._convert()

        self.db.set_downloaded(self.meta.info.id)

    async def _convert(self):
        c = self.config.session.conversion
        engine_class = converter.get(c.codec)
        engine = engine_class(
            filename=self.download_path,
            sampling_rate=c.sampling_rate,
            bit_depth=c.bit_depth,
            remove_source=True,  # always going to delete the old file
        )
        await engine.convert()
        self.download_path = engine.final_fn  # because the extension changed

    def _set_download_path(self):
        c = self.config.session.filepaths
        formatter = c.track_format
        track_path = clean_filename(
            self.meta.format_track_path(formatter),
            restrict=c.restrict_characters,
        )
        if c.truncate_to > 0 and len(track_path) > c.truncate_to:
            track_path = track_path[: c.truncate_to]

        self.download_path = os.path.join(
            self.folder,
            f"{track_path}.{self.downloadable.extension}",
        )


@dataclass(slots=True)
class PendingTrack(Pending):
    id: str
    album: AlbumMetadata
    client: Client
    config: Config
    folder: str
    db: Database
    # cover_path is None <==> Artwork for this track doesn't exist in API
    cover_path: str | None

    async def resolve(self) -> Track | None:
        if self.db.downloaded(self.id):
            logger.info(
                f"Skipping track {self.id}. Marked as downloaded in the database.",
            )
            return None

        source = self.client.source
        try:
            resp = await self.client.get_metadata(self.id, "track")
        except NonStreamableError as e:
            logger.error(f"Track {self.id} not available for stream on {source}: {e}")
            return None

        try:
            meta = TrackMetadata.from_resp(self.album, source, resp)
        except Exception as e:
            logger.error(f"Error building track metadata for {self.id}: {e}")
            return None

        if meta is None:
            logger.error(f"Track {self.id} not available for stream on {source}")
            self.db.set_failed(source, "track", self.id)
            return None

        quality = self.config.session.get_source(source).quality
        try:
            downloadable = await self.client.get_downloadable(self.id, quality)
        except NonStreamableError as e:
            logger.error(
                f"Error getting downloadable data for track {meta.tracknumber} [{self.id}]: {e}"
            )
            return None

        downloads_config = self.config.session.downloads
        if downloads_config.disc_subdirectories and self.album.disctotal > 1:
            folder = os.path.join(self.folder, f"Disc {meta.discnumber}")
        else:
            folder = self.folder

        return Track(
            meta,
            downloadable,
            self.config,
            folder,
            self.cover_path,
            self.db,
        )


@dataclass(slots=True)
class PendingSingle(Pending):
    """Whereas PendingTrack is used in the context of an album, where the album metadata
    and cover have been resolved, PendingSingle is used when a single track is downloaded.

    This resolves the Album metadata and downloads the cover to pass to the Track class.
    """

    id: str
    client: Client
    config: Config
    db: Database

    async def resolve(self) -> Track | None:
        if self.db.downloaded(self.id):
            logger.info(
                f"Skipping track {self.id}. Marked as downloaded in the database.",
            )
            return None

        try:
            resp = await self.client.get_metadata(self.id, "track")
        except NonStreamableError as e:
            logger.error(f"Error fetching track {self.id}: {e}")
            return None
        # Patch for soundcloud
        try:
            album = AlbumMetadata.from_track_resp(resp, self.client.source)
        except Exception as e:
            logger.error(f"Error building album metadata for track {id=}: {e}")
            return None

        if album is None:
            self.db.set_failed(self.client.source, "track", self.id)
            logger.error(
                f"Cannot stream track (am) ({self.id}) on {self.client.source}",
            )
            return None

        try:
            meta = TrackMetadata.from_resp(album, self.client.source, resp)
        except Exception as e:
            logger.error(f"Error building track metadata for track {id=}: {e}")
            return None

        if meta is None:
            self.db.set_failed(self.client.source, "track", self.id)
            logger.error(
                f"Cannot stream track (tm) ({self.id}) on {self.client.source}",
            )
            return None

        config = self.config.session
        quality = getattr(config, self.client.source).quality
        assert isinstance(quality, int)
        parent = config.downloads.folder
        if config.filepaths.add_singles_to_folder:
            folder = os.path.join(parent, self._format_folder(album))
        else:
            folder = parent

        os.makedirs(folder, exist_ok=True)

        embedded_cover_path, downloadable = await asyncio.gather(
            self._download_cover(album.covers, folder),
            self.client.get_downloadable(self.id, quality),
        )
        return Track(
            meta,
            downloadable,
            self.config,
            folder,
            embedded_cover_path,
            self.db,
            is_single=True,
        )

    def _format_folder(self, meta: AlbumMetadata) -> str:
        c = self.config.session
        parent = c.downloads.folder
        formatter = c.filepaths.folder_format
        if c.downloads.source_subdirectories:
            parent = os.path.join(parent, self.client.source.capitalize())

        return os.path.join(parent, meta.format_folder_path(formatter))

    async def _download_cover(self, covers: Covers, folder: str) -> str | None:
        embed_path, _ = await download_artwork(
            self.client.session,
            folder,
            covers,
            self.config.session.artwork,
            for_playlist=False,
        )
        return embed_path
