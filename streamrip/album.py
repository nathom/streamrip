import asyncio
import logging
import os
from dataclasses import dataclass

from .artwork import download_artwork
from .client import Client
from .config import Config
from .console import console
from .media import Media, Pending
from .metadata import AlbumMetadata, get_album_track_ids
from .track import PendingTrack, Track

logger = logging.getLogger("streamrip")


@dataclass(slots=True)
class Album(Media):
    meta: AlbumMetadata
    tracks: list[PendingTrack]
    config: Config
    # folder where the tracks will be downloaded
    folder: str

    async def preprocess(self):
        if self.config.session.cli.text_output:
            console.print(
                f"[cyan]Downloading {self.meta.album} by {self.meta.albumartist}"
            )

    async def download(self):
        async def _resolve_and_download(pending):
            track = await pending.resolve()
            await track.rip()

        await asyncio.gather(*[_resolve_and_download(p) for p in self.tracks])

    async def postprocess(self):
        pass


@dataclass(slots=True)
class PendingAlbum(Pending):
    id: str
    client: Client
    config: Config

    async def resolve(self):
        resp = await self.client.get_metadata(self.id, "album")
        meta = AlbumMetadata.from_resp(resp, self.client.source)
        tracklist = get_album_track_ids(self.client.source, resp)
        folder = self.config.session.downloads.folder
        album_folder = self._album_folder(folder, meta)
        os.makedirs(album_folder, exist_ok=True)
        embed_cover, _ = await download_artwork(
            self.client.session, album_folder, meta.covers, self.config.session.artwork
        )
        pending_tracks = [
            PendingTrack(
                id=id,
                album=meta,
                client=self.client,
                config=self.config,
                folder=album_folder,
                cover_path=embed_cover,
            )
            for id in tracklist
        ]
        logger.debug("Pending tracks: %s", pending_tracks)
        return Album(meta, pending_tracks, self.config, album_folder)

    def _album_folder(self, parent: str, meta: AlbumMetadata) -> str:
        formatter = self.config.session.filepaths.folder_format
        folder = meta.format_folder_path(formatter)
        return os.path.join(parent, folder)
