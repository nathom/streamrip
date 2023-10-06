import asyncio
from dataclasses import dataclass

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
    folder: str

    async def resolve(self):
        resp = self.client.get_metadata({"id": self.id}, "album")
        meta = AlbumMetadata.from_resp(self.client.source, resp)
        tracklist = get_album_track_ids(self.client.source, resp)
        album_folder = self._album_folder(self.folder, meta.album)
        pending_tracks = [
            PendingTrack(
                id=id,
                album=meta,
                client=self.client,
                config=self.config,
                folder=album_folder,
            )
            for id in tracklist
        ]
        tracks: list[Track] = await asyncio.gather(
            *(track.resolve() for track in pending_tracks)
        )
        return Album(meta, tracks, self.config)

    def _album_folder(self, parent: str, album_name: str) -> str:
        # find name of album folder
        # create album folder if it doesnt exist
        pass
