import asyncio
from dataclasses import dataclass

from ..client import Client
from ..config import Config
from ..db import Database
from ..metadata import LabelMetadata
from .album import PendingAlbum
from .media import Media, Pending


@dataclass(slots=True)
class Label(Media):
    """Represents a list of albums. Used by Artist and Label classes."""

    name: str
    albums: list[PendingAlbum]
    client: Client
    config: Config

    async def preprocess(self):
        pass

    async def download(self):
        # Resolve only 3 albums at a time to avoid
        # initial latency of resolving ALL albums and tracks
        # before any downloads
        album_resolve_chunk_size = 10

        async def _resolve_download(item: PendingAlbum):
            album = await item.resolve()
            if album is None:
                return
            await album.rip()

        batches = self.batch(
            [_resolve_download(album) for album in self.albums],
            album_resolve_chunk_size,
        )
        for batch in batches:
            await asyncio.gather(*batch)

    async def postprocess(self):
        pass

    @staticmethod
    def batch(iterable, n=1):
        total = len(iterable)
        for ndx in range(0, total, n):
            yield iterable[ndx : min(ndx + n, total)]


@dataclass(slots=True)
class PendingLabel(Pending):
    id: str
    client: Client
    config: Config
    db: Database

    async def resolve(self) -> Label:
        resp = await self.client.get_metadata(self.id, "label")
        meta = LabelMetadata.from_resp(resp, self.client.source)
        albums = [
            PendingAlbum(album_id, self.client, self.config, self.db)
            for album_id in meta.album_ids()
        ]
        return Label(meta.name, albums, self.client, self.config)
