import asyncio
import logging
import os
from dataclasses import dataclass

from .. import progress
from ..client import Client
from ..config import Config
from ..db import Database
from ..exceptions import NonStreamableError
from ..filepath_utils import clean_filepath
from ..metadata import AlbumMetadata
from ..metadata.util import get_album_track_ids
from .artwork import download_artwork
from .media import Media, Pending
from .track import PendingTrack

logger = logging.getLogger("streamrip")


@dataclass(slots=True)
class Album(Media):
    meta: AlbumMetadata
    tracks: list[PendingTrack]
    config: Config
    # folder where the tracks will be downloaded
    folder: str
    db: Database

    async def preprocess(self):
        progress.add_title(self.meta.album)

    async def download(self):
        async def _resolve_and_download(pending: Pending):
            try:
                track = await pending.resolve()
                if track is None:
                    return None  # Track not available
                await track.rip()
                return True  # Success
            except Exception as e:
                logger.error(f"Error downloading track: {e}")
                return False  # Failed

        results = await asyncio.gather(
            *[_resolve_and_download(p) for p in self.tracks], return_exceptions=True
        )

        # Count successful downloads
        self.successful_tracks = 0
        self.total_tracks = len(self.tracks)
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Album track processing error: {result}")
            elif result is True:
                self.successful_tracks += 1

    async def postprocess(self):
        progress.remove_title(self.meta.album)
        
        # Mark album as downloaded in the database for faster library browsing
        # Only mark as downloaded if at least 80% of tracks succeeded
        success_rate = self.successful_tracks / max(1, self.total_tracks)
        
        if success_rate >= 0.8:  # 80% success threshold
            try:
                source = self.tracks[0].client.source if self.tracks else "unknown"
                album_id = self.meta.info.id or "unknown"
                title = self.meta.album or "Unknown Album"
                artist = (self.meta.albumartist or self.meta.artist) or "Unknown Artist"
                self.db.set_album_downloaded(source, album_id, title, artist)
                logger.debug(f"Marked album as downloaded: {artist} - {title} ({source}:{album_id}) - {self.successful_tracks}/{self.total_tracks} tracks")
            except Exception as e:
                logger.debug(f"Failed to mark album as downloaded: {e}")
        else:
            logger.debug(f"Album not marked as downloaded due to low success rate: {self.successful_tracks}/{self.total_tracks} tracks ({success_rate:.1%})")


@dataclass(slots=True)
class PendingAlbum(Pending):
    id: str
    client: Client
    config: Config
    db: Database

    async def resolve(self) -> Album | None:
        try:
            resp = await self.client.get_metadata(self.id, "album")
        except NonStreamableError as e:
            logger.error(
                f"Album {self.id} not available to stream on {self.client.source} ({e})",
            )
            return None

        try:
            meta = AlbumMetadata.from_album_resp(resp, self.client.source)
        except Exception as e:
            logger.error(f"Error building album metadata for {id=}: {e}")
            return None

        if meta is None:
            logger.error(
                f"Album {self.id} not available to stream on {self.client.source}",
            )
            return None

        tracklist = get_album_track_ids(self.client.source, resp)
        folder = self.config.session.downloads.folder
        album_folder = self._album_folder(folder, meta)
        os.makedirs(album_folder, exist_ok=True)
        embed_cover, _ = await download_artwork(
            self.client.session,
            album_folder,
            meta.covers,
            self.config.session.artwork,
            for_playlist=False,
        )
        pending_tracks = [
            PendingTrack(
                id,
                album=meta,
                client=self.client,
                config=self.config,
                folder=album_folder,
                db=self.db,
                cover_path=embed_cover,
            )
            for id in tracklist
        ]
        logger.debug("Pending tracks: %s", pending_tracks)
        return Album(meta, pending_tracks, self.config, album_folder, self.db)

    def _album_folder(self, parent: str, meta: AlbumMetadata) -> str:
        config = self.config.session
        if config.downloads.source_subdirectories:
            parent = os.path.join(parent, self.client.source.capitalize())
        formatter = config.filepaths.folder_format
        folder = clean_filepath(
            meta.format_folder_path(formatter), config.filepaths.restrict_characters
        )

        return os.path.join(parent, folder)
