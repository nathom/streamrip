import asyncio
from dataclasses import dataclass

from .artwork import download_artwork
from .client import Client
from .config import Config
from .media import Media, Pending
from .metadata import AlbumMetadata, get_album_track_ids
from .track import PendingTrack, Track


@dataclass(slots=True)
class Album(Media):
    meta: AlbumMetadata
    tracks: list[Track]
    config: Config
    directory: str


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
        album_folder = self._album_folder(folder, meta.album)
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
        tracks: list[Track] = await asyncio.gather(
            *(track.resolve() for track in pending_tracks)
        )
        return Album(meta, tracks, self.config, album_folder)

    def _album_folder(self, parent: str, album_name: str) -> str:
        # find name of album folder
        # create album folder if it doesnt exist
        raise NotImplementedError
