from .album import Album, PendingAlbum
from .client import Client
from .config import Config
from .media import Media, Pending


class Artist(Media):
    name: str
    albums: list[PendingAlbum]
    config: Config


class PendingArtist(Pending):
    id: str
    client: Client
