import os
import shutil
import time
from abc import ABC, abstractmethod
from tempfile import gettempdir
from typing import Callable, Optional

import aiofiles
import aiohttp


def generate_temp_path(url: str):
    return os.path.join(gettempdir(), f"__streamrip_{hash(url)}_{time.time()}.download")


class Downloadable(ABC):
    session: aiohttp.ClientSession
    url: str
    chunk_size = 1024
    _size: Optional[int] = None

    async def download(self, path: str, callback: Callable[[], None]):
        tmp = generate_temp_path(self.url)
        await self._download(tmp, callback)
        shutil.move(tmp, path)

    async def size(self) -> int:
        if self._size is not None:
            return self._size
        async with self.session.head(self.url) as response:
            response.raise_for_status()
            content_length = response.headers["Content-Length"]
            self._size = int(content_length)
            return self._size

    @abstractmethod
    async def _download(self, path: str, callback: Callable[[], None]):
        raise NotImplemented


class BasicDownloadable(Downloadable):
    """Just downloads a URL."""

    def __init__(self, session: aiohttp.ClientSession, url: str):
        self.session = session
        self.url = url

    async def _download(self, path: str, callback: Callable[[int], None]):
        async with self.session.get(self.url) as response:
            response.raise_for_status()
            async with aiofiles.open(path, "wb") as file:
                async for chunk in response.content.iter_chunked(self.chunk_size):
                    await file.write(chunk)
                    # typically a bar.update()
                    callback(self.chunk_size)


class DeezerDownloadable(Downloadable):
    def __init__(self, resp: dict):
        self.resp = resp

    async def _download(self, path: str):
        raise NotImplemented


class TidalDownloadable(Downloadable):
    def __init__(self, info: dict):
        self.info = info

    async def _download(self, path: str):
        raise NotImplemented


class SoundcloudDownloadable(Downloadable):
    def __init__(self, info: dict):
        self.info = info

    async def _download(self, path: str):
        raise NotImplemented
