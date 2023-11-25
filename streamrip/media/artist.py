from dataclasses import dataclass

from ..client import Client
from ..config import Config
from ..db import Database
from ..metadata import ArtistMetadata
from .album import PendingAlbum
from .album_list import AlbumList
from .media import Pending


class Artist(AlbumList):
    pass


@dataclass(slots=True)
class PendingArtist(Pending):
    id: str
    client: Client
    config: Config
    db: Database

    async def resolve(self) -> Artist:
        resp = await self.client.get_metadata(self.id, "artist")
        meta = ArtistMetadata.from_resp(resp, self.client.source)
        albums = [
            PendingAlbum(album_id, self.client, self.config, self.db)
            for album_id in meta.album_ids()
        ]
        return Artist(meta.name, albums, self.client, self.config)
