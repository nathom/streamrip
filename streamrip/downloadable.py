import asyncio
import functools
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

import aiofiles
import aiohttp
import m3u8
from Cryptodome.Cipher import Blowfish

from . import converter
from .exceptions import NonStreamable


def generate_temp_path(url: str):
    return os.path.join(
        tempfile.gettempdir(), f"__streamrip_{hash(url)}_{time.time()}.download"
    )


class Downloadable(ABC):
    session: aiohttp.ClientSession
    url: str
    extension: str
    chunk_size = 1024
    _size: Optional[int] = None

    async def download(self, path: str, callback: Callable[[int], Any]):
        tmp = generate_temp_path(self.url)
        await self._download(tmp, callback)
        shutil.move(tmp, path)

    async def size(self) -> int:
        if self._size is not None:
            return self._size
        async with self.session.head(self.url) as response:
            response.raise_for_status()
            content_length = response.headers.get("Content-Length", 0)
            self._size = int(content_length)
            return self._size

    @abstractmethod
    async def _download(self, path: str, callback: Callable[[int], None]):
        raise NotImplemented

    def __repr__(self):
        return f"{self.__class__.__name__}({self.__dict__})"


class BasicDownloadable(Downloadable):
    """Just downloads a URL."""

    def __init__(self, session: aiohttp.ClientSession, url: str, extension: str):
        self.session = session
        self.url = url
        self.extension = extension

    async def _download(self, path: str, callback: Callable[[int], None]):
        async with self.session.get(
            self.url, allow_redirects=True, stream=True
        ) as response:
            response.raise_for_status()
            async with aiofiles.open(path, "wb") as file:
                async for chunk in response.content.iter_chunked(self.chunk_size):
                    await file.write(chunk)
                    # typically a bar.update()
                    callback(self.chunk_size)


class DeezerDownloadable(Downloadable):
    is_encrypted = re.compile("/m(?:obile|edia)/")
    chunk_size = 2048 * 3

    def __init__(self, session: aiohttp.ClientSession, info: dict):
        self.session = session
        self.url = info["url"]
        self.fallback_id = info["fallback_id"]
        self.quality = info["quality"]
        if self.quality <= 1:
            self.extension = "mp3"
        else:
            self.extension = "flac"
        self.id = info["id"]

    async def _download(self, path: str, callback):
        async with self.session.get(
            self.url, allow_redirects=True, stream=True
        ) as resp:
            resp.raise_for_status()
            self._size = int(resp.headers.get("Content-Length", 0))
            if self._size < 20000 and not self.url.endswith(".jpg"):
                try:
                    info = await resp.json()
                    try:
                        # Usually happens with deezloader downloads
                        raise NonStreamable(f"{info['error']} - {info['message']}")
                    except KeyError:
                        raise NonStreamable(info)

                except json.JSONDecodeError:
                    raise NonStreamable("File not found.")

            async with aiofiles.open(path, "wb") as file:
                if self.is_encrypted.search(self.url) is None:
                    async for chunk in resp.content.iter_chunked(self.chunk_size):
                        await file.write(chunk)
                        # typically a bar.update()
                        callback(self.chunk_size)
                else:
                    blowfish_key = self._generate_blowfish_key(self.id)
                    async for chunk in resp.content.iter_chunked(self.chunk_size):
                        if len(chunk) >= 2048:
                            decrypted_chunk = (
                                self._decrypt_chunk(blowfish_key, chunk[:2048])
                                + chunk[2048:]
                            )
                        else:
                            decrypted_chunk = chunk
                        await file.write(decrypted_chunk)
                        callback(self.chunk_size)

    @staticmethod
    def _decrypt_chunk(key, data):
        """Decrypt a chunk of a Deezer stream.

        :param key:
        :param data:
        """
        return Blowfish.new(
            key,
            Blowfish.MODE_CBC,
            b"\x00\x01\x02\x03\x04\x05\x06\x07",
        ).decrypt(data)

    @staticmethod
    def _generate_blowfish_key(track_id: str) -> bytes:
        """Generate the blowfish key for Deezer downloads.

        :param track_id:
        :type track_id: str
        """
        SECRET = "g4el58wc0zvf9na1"
        md5_hash = hashlib.md5(track_id.encode()).hexdigest()
        # good luck :)
        return "".join(
            chr(functools.reduce(lambda x, y: x ^ y, map(ord, t)))
            for t in zip(md5_hash[:16], md5_hash[16:], SECRET)
        ).encode()


class TidalDownloadable(Downloadable):
    """A wrapper around BasicDownloadable that includes Tidal-specific
    error messages."""

    def __init__(self, session: aiohttp.ClientSession, info: dict):
        self.session = session
        url = info.get("url")
        if self.url is None:
            if restrictions := info["restrictions"]:
                # Turn CamelCase code into a readable sentence
                words = re.findall(r"([A-Z][a-z]+)", restrictions[0]["code"])
                raise NonStreamable(
                    words[0] + " " + " ".join(map(str.lower, words[1:])) + "."
                )

            raise NonStreamable(f"Tidal download: dl_info = {info}")

        assert isinstance(url, str)
        self.downloadable = BasicDownloadable(session, url, "m4a")

    async def _download(self, path: str, callback):
        await self.downloadable._download(path, callback)


class SoundcloudDownloadable(Downloadable):
    def __init__(self, session, info: dict):
        self.session = session
        self.file_type = info["type"]
        if self.file_type == "mp3":
            self.extension = "mp3"
        elif self.file_type == "original":
            self.extension = "flac"
        else:
            raise Exception(f"Invalid file type: {self.file_type}")
        self.url = info["url"]

    async def _download(self, path, callback):
        if self.file_type == "mp3":
            await self._download_mp3(path, callback)
        else:
            await self._download_original(path, callback)

    async def _download_original(self, path: str, callback):
        downloader = BasicDownloadable(self.session, self.url, "flac")
        await downloader.download(path, callback)
        engine = converter.FLAC(path)
        engine.convert(path)

    async def _download_mp3(self, path: str, callback):
        async with self.session.get(self.url) as resp:
            content = await resp.text("utf-8")

        parsed_m3u = m3u8.loads(content)
        self._size = len(parsed_m3u.segments)
        tasks = [
            asyncio.create_task(self._download_segment(segment.uri))
            for segment in parsed_m3u.segments
        ]

        segment_paths = []
        for coro in asyncio.as_completed(tasks):
            segment_paths.append(await coro)
            callback(1)

        concat_audio_files(segment_paths, path, "mp3")

    async def _download_segment(self, segment_uri: str) -> str:
        tmp = generate_temp_path(segment_uri)
        async with self.session.get(segment_uri) as resp:
            resp.raise_for_status()
            async with aiofiles.open(tmp, "wb") as file:
                content = await resp.content.read()
                await file.write(content)
        return tmp


def concat_audio_files(paths: list[str], out: str, ext: str, max_files_open=128):
    """Concatenate audio files using FFmpeg. Batched by max files open.

    Recurses log_{max_file_open}(len(paths)) times.
    """

    if shutil.which("ffmpeg") is None:
        raise Exception("FFmpeg must be installed.")

    # Base case
    if len(paths) == 1:
        shutil.move(paths[0], out)
        return

    it = iter(paths)
    num_batches = len(paths) // max_files_open + (
        1 if len(paths) % max_files_open != 0 else 0
    )
    tempdir = tempfile.gettempdir()
    outpaths = [
        os.path.join(
            tempdir, f"__streamrip_ffmpeg_{hash(paths[i*max_files_open])}.{ext}"
        )
        for i in range(num_batches)
    ]

    for p in outpaths:
        try:
            os.remove(p)  # in case of failure
        except FileNotFoundError:
            pass

    for i in range(num_batches):
        proc = subprocess.run(
            (
                "ffmpeg",
                "-i",
                f"concat:{'|'.join(itertools.islice(it, max_files_open))}",
                "-acodec",
                "copy",
                "-loglevel",
                "panic",
                outpaths[i],
            ),
            # capture_output=True,
        )
        if proc.returncode != 0:
            raise Exception(f"FFMPEG returned with this error: {proc.stderr}")

    # Recurse on remaining batches
    concat_audio_files(outpaths, out, ext)
