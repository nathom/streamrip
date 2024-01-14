import asyncio
import logging
import os
from dataclasses import dataclass

from .. import progress
from ..client import Client
from ..config import Config
from ..db import Database
from ..filepath_utils import clean_filename
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
            track = await pending.resolve()
            if track is None:
                return
            await track.rip()

        await asyncio.gather(*[_resolve_and_download(p) for p in self.tracks])

    async def postprocess(self):
        progress.remove_title(self.meta.album)


@dataclass(slots=True)
class PendingAlbum(Pending):
    id: str
    client: Client
    config: Config
    db: Database

    async def resolve(self) -> Album | None:
        resp = await self.client.get_metadata(self.id, "album")
        meta = AlbumMetadata.from_album_resp(resp, self.client.source)
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
        folder = clean_filename(
            meta.format_folder_path(formatter), config.filepaths.restrict_characters
        )

        return os.path.join(parent, folder)
