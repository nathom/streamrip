import asyncio
import base64
import functools
import hashlib
import itertools
import json
import logging
import os
import re
import shutil
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional

import aiofiles
import aiohttp
import m3u8
import requests
from Cryptodome.Cipher import AES, Blowfish
from Cryptodome.Util import Counter

from .. import converter
from ..exceptions import NonStreamableError

logger = logging.getLogger("streamrip")


BLOWFISH_SECRET = "g4el58wc0zvf9na1"


def generate_temp_path(url: str):
    return os.path.join(
        tempfile.gettempdir(),
        f"__streamrip_{hash(url)}_{time.time()}.download",
    )


async def fast_async_download(path, url, headers, callback):
    """Download a file without blocking the event loop.

    Runs the entire synchronous requests download inside a thread via
    asyncio.to_thread so the HTTP connection setup and file I/O never
    stall other concurrent coroutines on the event loop.
    """
    chunk_size: int = 2**17  # 131 KB

    def _sync_download():
        with open(path, "wb") as file:
            with requests.get(
                url,
                headers=headers,
                allow_redirects=True,
                stream=True,
            ) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    file.write(chunk)
                    callback(len(chunk))

    try:
        await asyncio.to_thread(_sync_download)
    except Exception:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        raise


@dataclass
class Downloadable(ABC):
    session: aiohttp.ClientSession
    url: str
    extension: str
    source: str = "Unknown"
    _size: Optional[int] = None

    async def download(self, path: str, callback: Callable[[int], Any]):
        await self._download(path, callback)

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
        raise NotImplementedError


class BasicDownloadable(Downloadable):
    """Just downloads a URL."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        extension: str,
        source: str | None = None,
    ):
        self.session = session
        self.url = url
        self.extension = extension
        self._size = None
        self.source: str = source or "Unknown"

    async def _download(self, path: str, callback):
        await fast_async_download(path, self.url, self.session.headers, callback)


class DeezerDownloadable(Downloadable):
    is_encrypted = re.compile("/m(?:obile|edia)/")

    def __init__(self, session: aiohttp.ClientSession, info: dict):
        logger.debug("Deezer info for downloadable: %s", info)
        self.session = session
        self.url = info["url"]
        self.source: str = "deezer"
        qualities_available = [
            i for i, size in enumerate(info["quality_to_size"]) if size > 0
        ]
        if len(qualities_available) == 0:
            raise NonStreamableError(
                "Missing download info. Skipping.",
            )
        max_quality_available = max(qualities_available)
        self.quality = min(info["quality"], max_quality_available)
        self._size = info["quality_to_size"][self.quality]
        if self.quality <= 1:
            self.extension = "mp3"
        else:
            self.extension = "flac"
        self.id = str(info["id"])

    async def _download(self, path: str, callback):
        async with self.session.get(self.url, allow_redirects=True) as resp:
            resp.raise_for_status()
            self._size = int(resp.headers.get("Content-Length", 0))
            if self._size < 20000 and not self.url.endswith(".jpg"):
                try:
                    info = await resp.json()
                    try:
                        # Usually happens with deezloader downloads
                        raise NonStreamableError(f"{info['error']} - {info['message']}")
                    except KeyError:
                        raise NonStreamableError(info)

                except json.JSONDecodeError:
                    raise NonStreamableError("File not found.")

            if self.is_encrypted.search(self.url) is None:
                logger.debug(f"Deezer file at {self.url} not encrypted.")
                try:
                    async with aiofiles.open(path, "wb") as audio:
                        async for chunk in resp.content.iter_chunked(2**17):
                            await audio.write(chunk)
                            callback(len(chunk))
                except Exception:
                    try:
                        os.remove(path)
                    except FileNotFoundError:
                        pass
                    raise
            else:
                blowfish_key = self._generate_blowfish_key(self.id)
                logger.debug(
                    "Deezer file (id %s) at %s is encrypted. Decrypting with %s",
                    self.id,
                    self.url,
                    blowfish_key,
                )

                buf = bytearray()
                async for data, _ in resp.content.iter_chunks():
                    buf += data
                    callback(len(data))

                encrypt_chunk_size = 3 * 2048
                async with aiofiles.open(path, "wb") as audio:
                    buflen = len(buf)
                    for i in range(0, buflen, encrypt_chunk_size):
                        data = buf[i : min(i + encrypt_chunk_size, buflen)]  # type: ignore[assignment]
                        if len(data) >= 2048:
                            decrypted_chunk = (
                                self._decrypt_chunk(blowfish_key, data[:2048])
                                + data[2048:]
                            )
                        else:
                            decrypted_chunk = data
                        await audio.write(decrypted_chunk)

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
        md5_hash = hashlib.md5(track_id.encode()).hexdigest()
        # good luck :)
        return "".join(
            chr(functools.reduce(lambda x, y: x ^ y, map(ord, t)))
            for t in zip(md5_hash[:16], md5_hash[16:], BLOWFISH_SECRET)
        ).encode()


class TidalDownloadable(Downloadable):
    """A wrapper around BasicDownloadable that includes Tidal-specific
    error messages.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str | None,
        codec: str,
        encryption_key: str | None,
        restrictions,
    ):
        self.session = session
        self.source = "tidal"
        codec = codec.lower()
        if codec in ("flac", "mqa"):
            self.extension = "flac"
        else:
            self.extension = "m4a"

        if url is None:
            # Turn CamelCase code into a readable sentence
            if restrictions:
                words = re.findall(r"([A-Z][a-z]+)", restrictions[0]["code"])
                raise NonStreamableError(
                    words[0] + " " + " ".join(map(str.lower, words[1:])),
                )
            raise NonStreamableError(
                f"Tidal download: dl_info = {url, codec, encryption_key}"
            )
        self.url = url
        self.enc_key = encryption_key
        self.downloadable = BasicDownloadable(session, url, self.extension, "tidal")

    async def _download(self, path: str, callback):
        await self.downloadable._download(path, callback)
        if self.enc_key is not None:
            dec_bytes = await self._decrypt_mqa_file(path, self.enc_key)
            async with aiofiles.open(path, "wb") as audio:
                await audio.write(dec_bytes)

    @property
    def _size(self):
        return self.downloadable._size

    @_size.setter
    def _size(self, v):
        self.downloadable._size = v

    @staticmethod
    async def _decrypt_mqa_file(in_path, encryption_key):
        """Decrypt an MQA file.

        :param in_path:
        :param out_path:
        :param encryption_key:
        """

        # Do not change this
        master_key = "UIlTTEMmmLfGowo/UC60x2H45W6MdGgTRfo/umg4754="

        # Decode the base64 strings to ascii strings
        master_key = base64.b64decode(master_key)
        security_token = base64.b64decode(encryption_key)

        # Get the IV from the first 16 bytes of the securityToken
        iv = security_token[:16]
        encrypted_st = security_token[16:]

        # Initialize decryptor
        decryptor = AES.new(master_key, AES.MODE_CBC, iv)

        # Decrypt the security token
        decrypted_st = decryptor.decrypt(encrypted_st)

        # Get the audio stream decryption key and nonce from the decrypted security token
        key = decrypted_st[:16]
        nonce = decrypted_st[16:24]

        counter = Counter.new(64, prefix=nonce, initial_value=0)
        decryptor = AES.new(key, AES.MODE_CTR, counter=counter)

        async with aiofiles.open(in_path, "rb") as enc_file:
            dec_bytes = decryptor.decrypt(await enc_file.read())
            return dec_bytes


class SoundcloudDownloadable(Downloadable):
    def __init__(self, session, info: dict):
        self.session = session
        self.file_type = info["type"]
        self.source = "soundcloud"
        if self.file_type == "mp3":
            self.extension = "mp3"
        elif self.file_type == "original":
            self.extension = "flac"
        else:
            raise Exception(f"Invalid file type: {self.file_type}")
        self.url = info["url"]
        self._segments = None

    async def _get_segments(self):
        if self._segments is None:
            async with self.session.get(self.url) as resp:
                content = await resp.text("utf-8")
            self._segments = m3u8.loads(content).segments
            self._size = len(self._segments)
        return self._segments

    async def _download(self, path, callback):
        if self.file_type == "mp3":
            await self._download_mp3(path, callback)
        else:
            await self._download_original(path, callback)

    async def _download_original(self, path: str, callback):
        downloader = BasicDownloadable(
            self.session, self.url, "flac", source="soundcloud"
        )
        await downloader.download(path, callback)
        self._size = downloader._size
        engine = converter.FLAC(path)
        await engine.convert(path)

    async def _download_mp3(self, path: str, callback):
        # TODO: make progress bar reflect bytes
        segments = await self._get_segments()
        segment_count = len(segments)
        tasks = [
            asyncio.create_task(self._download_segment(i, segment.uri))
            for i, segment in enumerate(segments)
        ]

        segment_paths: dict[int, str] = {}
        for coro in asyncio.as_completed(tasks):
            index, downloaded_path = await coro
            segment_paths[index] = downloaded_path
            callback(1)

        ordered_paths = [segment_paths[i] for i in range(segment_count)]
        await concat_audio_files(ordered_paths, path, "mp3")

    async def _download_segment(self, index: int, segment_uri: str) -> tuple[int, str]:
        tmp = generate_temp_path(segment_uri)
        async with self.session.get(segment_uri) as resp:
            resp.raise_for_status()
            async with aiofiles.open(tmp, "wb") as file:
                content = await resp.content.read()
                await file.write(content)
        return index, tmp

    async def size(self) -> int:
        if self.file_type == "mp3":
            await self._get_segments()
        return await super().size()


async def concat_audio_files(paths: list[str], out: str, ext: str, max_files_open=128):
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
            tempdir,
            f"__streamrip_ffmpeg_{hash(paths[i*max_files_open])}.{ext}",
        )
        for i in range(num_batches)
    ]

    for p in outpaths:
        try:
            os.remove(p)  # in case of failure
        except FileNotFoundError:
            pass

    proc_futures = []
    for i in range(num_batches):
        command = (
            "ffmpeg",
            "-i",
            f"concat:{'|'.join(itertools.islice(it, max_files_open))}",
            "-acodec",
            "copy",
            "-loglevel",
            "warning",
            outpaths[i],
        )
        fut = asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        proc_futures.append(fut)

    # Create all processes concurrently
    processes = await asyncio.gather(*proc_futures)

    # wait for all of them to finish and capture output for error reporting
    outputs = await asyncio.gather(*[p.communicate() for p in processes])
    for proc, (stdout, stderr) in zip(processes, outputs):
        if proc.returncode != 0:
            stderr_text = stderr.decode(errors="replace") if stderr else ""
            raise Exception(
                f"FFmpeg exited with status {proc.returncode}: {stderr_text}",
            )

    # Recurse on remaining batches
    await concat_audio_files(outpaths, out, ext)
