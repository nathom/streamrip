import asyncio
import logging
import os
from dataclasses import dataclass

from . import progress
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
    playlist_name: str
    position: int

    async def resolve(self) -> Track | None:
        resp = await self.client.get_metadata(self.id, "track")

        album = AlbumMetadata.from_track_resp(resp, self.client.source)
        meta = TrackMetadata.from_resp(album, self.client.source, resp)
        if meta is None:
            logger.error(
                f"Track ({self.id}) not available for stream on {self.client.source}"
            )
            return None

        c = self.config.session.metadata
        if c.renumber_playlist_tracks:
            meta.tracknumber = self.position
        if c.set_playlist_to_album:
            album.album = self.playlist_name

        quality = self.config.session.get_source(self.client.source).quality
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
        progress.add_title(self.name)

        async def _resolve_and_download(pending: PendingPlaylistTrack):
            track = await pending.resolve()
            if track is None:
                return
            await track.rip()

        await asyncio.gather(*[_resolve_and_download(p) for p in self.tracks])
        progress.remove_title(self.name)

    async def postprocess(self):
        pass


@dataclass(slots=True)
class PendingPlaylist(Pending):
    id: str
    client: Client
    config: Config

    async def resolve(self) -> Playlist | None:
        resp = await self.client.get_metadata(self.id, "playlist")
        meta = PlaylistMetadata.from_resp(resp, self.client.source)
        name = meta.name
        parent = self.config.session.downloads.folder
        folder = os.path.join(parent, clean_filename(name))
        tracks = [
            PendingPlaylistTrack(
                id, self.client, self.config, folder, name, position + 1
            )
            for position, id in enumerate(meta.ids())
        ]
        return Playlist(name, self.config, self.client, tracks)
