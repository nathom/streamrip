import os
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
    download_path: str = ""

    async def preprocess(self):
        folder = self._get_folder(self.folder)
        os.makedirs(folder, exist_ok=True)
        # Run in background while track downloads?
        # Don't download again if part of album
        await self._download_cover()

    async def download(self):
        async with get_progress_bar(self.config, self.downloadable.size()) as bar:
            self.downloadable.download(self.download_path, lambda x: bar.update(x))

    async def postprocess(self):
        await self.tag()
        await self.convert()


@dataclass(slots=True)
class PendingTrack(Pending):
    id: str
    album: AlbumMetadata
    client: Client
    config: Config
    folder: str

    async def resolve(self) -> Track:
        resp = await self.client.get_metadata({"id": self.id}, "track")
        meta = TrackMetadata.from_resp(self.album, self.client.source, resp)
        quality = getattr(self.config.session, self.client.source).quality
        assert isinstance(quality, int)
        downloadable = await self.client.get_downloadable(self.id, quality)
        return Track(meta, downloadable, self.config, self.directory)
