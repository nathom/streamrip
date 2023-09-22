from dataclasses import dataclass

from .client import Client
from .config import Config
from .downloadable import Downloadable
from .media import Media, Pending
from .metadata import AlbumMetadata, TrackMetadata


@dataclass(slots=True)
class Track(Media):
    meta: TrackMetadata
    downloadable: Downloadable
    config: Config
    folder: str


@dataclass(slots=True)
class PendingTrack(Pending):
    id: str
    album: AlbumMetadata
    client: Client
    config: Config
    folder: str

    async def resolve(self) -> Track:
        resp = await self.client.get_metadata(id, "track")
        meta = TrackMetadata.from_resp(self.album, self.client.source, resp)
        quality = getattr(self.config.session, self.client.source).quality
        assert isinstance(quality, int)
        downloadable = await self.client.get_downloadable(self.id, quality)
        return Track(meta, downloadable, self.config, self.directory)
