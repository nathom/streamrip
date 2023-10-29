import asyncio
import os
from dataclasses import dataclass

from . import converter
from .artwork import download_artwork
from .client import Client
from .config import Config
from .downloadable import Downloadable
from .filepath_utils import clean_filename
from .media import Media, Pending
from .metadata import AlbumMetadata, Covers, TrackMetadata
from .progress import get_progress_bar
from .tagger import tag_file


@dataclass(slots=True)
class Track(Media):
    meta: TrackMetadata
    downloadable: Downloadable
    config: Config
    folder: str
    # Is None if a cover doesn't exist for the track
    cover_path: str | None
    # change?
    download_path: str = ""

    async def preprocess(self):
        self._set_download_path()
        os.makedirs(self.folder, exist_ok=True)

    async def download(self):
        # TODO: progress bar description
        with get_progress_bar(
            self.config,
            await self.downloadable.size(),
            f"Track {self.meta.tracknumber}",
        ) as bar:
            await self.downloadable.download(
                self.download_path, lambda x: bar.update(x)
            )

    async def postprocess(self):
        await self._tag()
        if self.config.session.conversion.enabled:
            await self._convert()

        # if self.cover_path is not None:
        #     os.remove(self.cover_path)

    async def _tag(self):
        await tag_file(self.download_path, self.meta, self.cover_path)

    async def _convert(self):
        CONV_CLASS = {
            "FLAC": converter.FLAC,
            "ALAC": converter.ALAC,
            "MP3": converter.LAME,
            "OPUS": converter.OPUS,
            "OGG": converter.Vorbis,
            "VORBIS": converter.Vorbis,
            "AAC": converter.AAC,
            "M4A": converter.AAC,
        }
        c = self.config.session.conversion
        codec = c.codec
        engine = CONV_CLASS[codec.upper()](
            filename=self.download_path,
            sampling_rate=c.sampling_rate,
            remove_source=True,  # always going to delete the old file
        )
        engine.convert()
        self.download_path = engine.final_fn  # because the extension changed

    def _set_download_path(self):
        c = self.config.session.filepaths
        formatter = c.track_format
        track_path = clean_filename(
            self.meta.format_track_path(formatter), restrict=c.restrict_characters
        )
        if c.truncate_to > 0 and len(track_path) > c.truncate_to:
            track_path = track_path[: c.truncate_to]

        self.download_path = os.path.join(
            self.folder, f"{track_path}.{self.downloadable.extension}"
        )


@dataclass(slots=True)
class PendingTrack(Pending):
    id: str
    album: AlbumMetadata
    client: Client
    config: Config
    folder: str
    cover_path: str | None

    async def resolve(self) -> Track:
        resp = await self.client.get_metadata(self.id, "track")
        meta = TrackMetadata.from_resp(self.album, self.client.source, resp)
        quality = getattr(self.config.session, self.client.source).quality
        assert isinstance(quality, int)
        downloadable = await self.client.get_downloadable({"id": self.id}, quality)
        return Track(meta, downloadable, self.config, self.folder, self.cover_path)


@dataclass(slots=True)
class PendingSingle(Pending):
    """Whereas PendingTrack is used in the context of an album, where the album metadata
    and cover have been resolved, PendingSingle is used when a single track is downloaded.

    This resolves the Album metadata and downloads the cover to pass to the Track class.
    """

    id: str
    client: Client
    config: Config

    async def resolve(self) -> Track:
        resp = await self.client.get_metadata(self.id, "track")
        album = AlbumMetadata.from_resp(resp["album"], self.client.source)
        meta = TrackMetadata.from_resp(album, self.client.source, resp)

        quality = getattr(self.config.session, self.client.source).quality
        assert isinstance(quality, int)
        folder = os.path.join(
            self.config.session.downloads.folder, self._format_folder(album)
        )
        os.makedirs(folder, exist_ok=True)

        embedded_cover_path, downloadable = await asyncio.gather(
            self._download_cover(album.covers, folder),
            self.client.get_downloadable({"id": self.id}, quality),
        )
        return Track(meta, downloadable, self.config, folder, embedded_cover_path)

    def _format_folder(self, meta: AlbumMetadata) -> str:
        c = self.config.session
        parent = c.downloads.folder
        formatter = c.filepaths.folder_format
        return os.path.join(parent, meta.format_folder_path(formatter))

    async def _download_cover(self, covers: Covers, folder: str) -> str | None:
        embed_path, _ = await download_artwork(
            self.client.session, folder, covers, self.config.session.artwork
        )
        return embed_path
