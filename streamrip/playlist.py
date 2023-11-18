import asyncio
import logging
import os
from dataclasses import dataclass

from .artwork import download_artwork
from .client import Client
from .config import Config
from .filepath_utils import clean_filename
from .media import Media, Pending
from .metadata import AlbumMetadata, Covers, PlaylistMetadata, TrackMetadata
from .track import Track

logger = logging.getLogger("streamrip")


@dataclass(slots=True)
class PendingPlaylistTrack(Pending):
    id: str
    client: Client
    config: Config
    folder: str

    async def resolve(self) -> Track:
        resp = await self.client.get_metadata(self.id, "track")
        album = AlbumMetadata.from_resp(resp["album"], self.client.source)
        meta = TrackMetadata.from_resp(album, self.client.source, resp)
        quality = getattr(self.config.session, self.client.source).quality
        assert isinstance(quality, int)
        embedded_cover_path, downloadable = await asyncio.gather(
            self._download_cover(album.covers, self.folder),
            self.client.get_downloadable(self.id, quality),
        )
        return Track(meta, downloadable, self.config, self.folder, embedded_cover_path)

    async def _download_cover(self, covers: Covers, folder: str) -> str | None:
        embed_path, _ = await download_artwork(
            self.client.session,
            folder,
            covers,
            self.config.session.artwork,
            for_playlist=True,
        )
        return embed_path


@dataclass(slots=True)
class Playlist(Media):
    name: str
    config: Config
    client: Client
    tracks: list[PendingPlaylistTrack]

    async def preprocess(self):
        pass

    async def download(self):
        async def _resolve_and_download(pending):
            track = await pending.resolve()
            await track.rip()

        await asyncio.gather(*[_resolve_and_download(p) for p in self.tracks])

    async def postprocess(self):
        pass


@dataclass(slots=True)
class PendingPlaylist(Pending):
    id: str
    client: Client
    config: Config

    async def resolve(self):
        resp = await self.client.get_metadata(self.id, "playlist")
        meta = PlaylistMetadata.from_resp(resp, self.client.source)
        name = meta.name
        parent = self.config.session.downloads.folder
        folder = os.path.join(parent, clean_filename(name))
        tracks = [
            PendingPlaylistTrack(id, self.client, self.config, folder)
            for id in meta.ids()
        ]
        return Playlist(name, self.config, self.client, tracks)
