import os
from dataclasses import dataclass

from . import converter
from .client import Client
from .config import Config
from .downloadable import Downloadable
from .media import Media, Pending
from .metadata import AlbumMetadata, TrackMetadata
from .progress import get_progress_bar


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
            await self.downloadable.download(
                self.download_path, lambda x: bar.update(x)
            )

    async def postprocess(self):
        await self._tag()
        await self._convert()

    async def _tag(self):
        t = Tagger(self.meta)
        t.tag(self.download_path)

    async def _convert(self):
        CONV_CLASS = {
            "FLAC": converter.FLAC,
            "ALAC": converter.ALAC,
            "MP3": converter.LAME,
            "OPUS": converter.OPUS,
            "OGG": converter.Vorbis,
            "VORBIS": converter.Vorbis,
            "AAC": converter.AAC,
            "M4A": converter.AAC,
        }
        c = self.config.session.conversion
        codec = c.codec
        engine = CONV_CLASS[codec.upper()](
            filename=self.download_path,
            sampling_rate=c.sampling_rate,
            remove_source=True,  # always going to delete the old file
        )
        engine.convert()
        self.download_path = engine.final_fn  # because the extension changed

    def _get_folder(self, parent: str) -> str:
        formatter = self.config.session.filepaths.track_format
        track_path = self.meta.format_track_path(formatter)
        return os.path.join(self.folder, track_path)


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
        return Track(meta, downloadable, self.config, self.folder)
