"""Album downloader — fetches tracks, tags, and organizes files."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import aiohttp

from qobuz.client import QobuzClient
from qobuz.types import Album, FileUrl, Track

logger = logging.getLogger("qobuz.downloader")

ProgressCallback = Callable[[int], None]  # called with bytes downloaded


@dataclass
class DownloadConfig:
    """Configuration for the download pipeline."""
    output_dir: str = "."
    quality: int = 3  # 1-4
    folder_format: str = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
    track_format: str = "{tracknumber:02d}. {artist} - {title}"
    max_connections: int = 6
    embed_cover: bool = True
    cover_size: str = "large"  # thumbnail, small, large
    source_subdirectories: bool = False
    disc_subdirectories: bool = True
    tag_files: bool = True
    download_booklets: bool = True


@dataclass
class TrackResult:
    """Result of downloading a single track."""
    track_id: int
    title: str
    success: bool
    path: str | None = None
    error: str | None = None


@dataclass
class AlbumResult:
    """Result of downloading an entire album."""
    album_id: str
    title: str
    artist: str
    tracks: list[TrackResult] = field(default_factory=list)
    cover_path: str | None = None
    booklet_paths: list[str] = field(default_factory=list)

    @property
    def successful(self) -> int:
        return sum(1 for t in self.tracks if t.success)

    @property
    def total(self) -> int:
        return len(self.tracks)

    @property
    def success_rate(self) -> float:
        return self.successful / max(1, self.total)


class AlbumDownloader:
    """Downloads a complete album from Qobuz.

    Usage::

        async with QobuzClient(app_id="...", user_auth_token="...", app_secret="...") as client:
            dl = AlbumDownloader(client, DownloadConfig(output_dir="/music"))
            result = await dl.download("album_id_123")
            print(f"Downloaded {result.successful}/{result.total} tracks")
    """

    def __init__(
        self,
        client: QobuzClient,
        config: DownloadConfig,
        on_track_start: Callable[[int, str], None] | None = None,
        on_track_progress: Callable[[int, int, int], None] | None = None,
        on_track_complete: Callable[[int, str, bool], None] | None = None,
    ):
        self.client = client
        self.config = config
        self._on_track_start = on_track_start  # (track_num, title)
        self._on_track_progress = on_track_progress  # (track_num, bytes_done, bytes_total)
        self._on_track_complete = on_track_complete  # (track_num, title, success)
        self._semaphore = asyncio.Semaphore(config.max_connections)

    async def download(self, album_id: str) -> AlbumResult:
        """Download an entire album by ID."""
        # Fetch raw response for goodies, then parse album + tracks
        _, raw_body = await self.client._transport.get(
            "album/get", {"album_id": album_id, "extra": "track_ids"}
        )
        album = Album.from_dict(raw_body)
        tracks = [Track.from_dict(t) for t in raw_body.get("tracks", {}).get("items", [])]
        goodies = raw_body.get("goodies", [])

        logger.info("Resolved: %s — %s (%d tracks, %d booklets)",
                     album.artist.name, album.title, len(tracks), len(goodies))

        album_folder = self._build_album_folder(album)
        os.makedirs(album_folder, exist_ok=True)

        cover_path = await self._download_cover(album, album_folder)

        # Download booklet PDFs
        booklet_paths = []
        if self.config.download_booklets and goodies:
            booklet_paths = await self._download_booklets(goodies, album_folder)

        # Download all tracks with concurrency limit
        results = await asyncio.gather(
            *[self._download_track(i + 1, track, album, album_folder, cover_path)
              for i, track in enumerate(tracks)],
            return_exceptions=True,
        )

        track_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Track %d failed: %s", i + 1, result)
                track_results.append(TrackResult(
                    track_id=tracks[i].id if i < len(tracks) else 0,
                    title=tracks[i].title if i < len(tracks) else "Unknown",
                    success=False,
                    error=str(result),
                ))
            else:
                track_results.append(result)

        return AlbumResult(
            album_id=album.id,
            title=album.title,
            artist=album.artist.name,
            tracks=track_results,
            cover_path=cover_path,
            booklet_paths=booklet_paths,
        )

    async def _download_track(
        self,
        track_num: int,
        track: Track,
        album: Album,
        album_folder: str,
        cover_path: str | None,
    ) -> TrackResult:
        """Download, tag, and save a single track."""
        async with self._semaphore:
            if self._on_track_start:
                self._on_track_start(track_num, track.title)

            try:
                # Get stream URL
                file_url = await self.client.streaming.get_file_url(
                    track.id, quality=self.config.quality
                )

                # Determine file extension
                ext = _mime_to_ext(file_url.mime_type)

                # Build file path
                disc_folder = album_folder
                if self.config.disc_subdirectories and album.tracks_count > 0 and track.disc_number > 1:
                    disc_folder = os.path.join(album_folder, f"Disc {track.disc_number}")
                    os.makedirs(disc_folder, exist_ok=True)

                filename = self._build_track_filename(track, album, ext)
                file_path = os.path.join(disc_folder, filename)

                # Download audio
                await self._download_file(
                    file_url.url, file_path, track_num
                )

                # Tag file
                if self.config.tag_files:
                    await self._tag_file(file_path, track, album, cover_path, file_url)

                if self._on_track_complete:
                    self._on_track_complete(track_num, track.title, True)

                return TrackResult(
                    track_id=track.id,
                    title=track.title,
                    success=True,
                    path=file_path,
                )

            except Exception as e:
                logger.error("Failed to download track '%s': %s", track.title, e, exc_info=True)
                if self._on_track_complete:
                    self._on_track_complete(track_num, track.title, False)
                return TrackResult(
                    track_id=track.id,
                    title=track.title,
                    success=False,
                    error=str(e),
                )

    async def _download_file(
        self, url: str, path: str, track_num: int
    ) -> None:
        """Stream download a file from URL to disk."""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0

                with open(path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if self._on_track_progress:
                            self._on_track_progress(track_num, downloaded, total)

    async def _download_booklets(self, goodies: list[dict], folder: str) -> list[str]:
        """Download PDF booklets from the goodies list."""
        paths = []
        for i, goodie in enumerate(goodies):
            url = goodie.get("url") or goodie.get("original_url")
            if not url:
                continue
            name = goodie.get("name", f"booklet_{i + 1}")
            ext = url.rsplit(".", 1)[-1] if "." in url.rsplit("/", 1)[-1] else "pdf"
            filename = f"{_safe_filename(name)}.{ext}"
            path = os.path.join(folder, filename)

            if os.path.exists(path):
                paths.append(path)
                continue

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        with open(path, "wb") as f:
                            async for chunk in resp.content.iter_chunked(8192):
                                f.write(chunk)
                paths.append(path)
                logger.info("Downloaded booklet: %s", filename)
            except Exception as e:
                logger.warning("Failed to download booklet '%s': %s", name, e)

        return paths

    async def _download_cover(self, album: Album, folder: str) -> str | None:
        """Download album cover art."""
        cover_url = getattr(album.image, self.config.cover_size, None) or album.image.large
        if not cover_url:
            return None

        cover_path = os.path.join(folder, "cover.jpg")
        if os.path.exists(cover_path):
            return cover_path

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(cover_url) as resp:
                    resp.raise_for_status()
                    with open(cover_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
            return cover_path
        except Exception as e:
            logger.warning("Failed to download cover: %s", e)
            return None

    async def _tag_file(
        self,
        path: str,
        track: Track,
        album: Album,
        cover_path: str | None,
        file_url: FileUrl,
    ) -> None:
        """Tag an audio file with metadata using mutagen."""
        ext = path.rsplit(".", 1)[-1].lower()

        if ext == "flac":
            await self._tag_flac(path, track, album, cover_path)
        elif ext == "mp3":
            await self._tag_mp3(path, track, album, cover_path)
        elif ext == "m4a":
            await self._tag_m4a(path, track, album, cover_path)

    async def _tag_flac(
        self, path: str, track: Track, album: Album, cover_path: str | None
    ) -> None:
        from mutagen.flac import FLAC, Picture

        audio = FLAC(path)
        audio["title"] = track.title
        audio["artist"] = track.performer.name
        audio["albumartist"] = album.artist.name
        audio["album"] = album.title
        audio["tracknumber"] = str(track.track_number)
        audio["discnumber"] = str(track.disc_number)
        audio["tracktotal"] = str(album.tracks_count)
        if album.genre:
            audio["genre"] = album.genre.name
        if album.release_date_original:
            audio["date"] = album.release_date_original
            audio["year"] = album.release_date_original[:4]
        if album.label:
            audio["organization"] = album.label.name
        if track.isrc:
            audio["isrc"] = track.isrc
        if album.upc:
            audio["barcode"] = album.upc

        if cover_path and self.config.embed_cover:
            pic = Picture()
            with open(cover_path, "rb") as f:
                pic.data = f.read()
            pic.type = 3  # front cover
            pic.mime = "image/jpeg"
            audio.add_picture(pic)

        audio.save()

    async def _tag_mp3(
        self, path: str, track: Track, album: Album, cover_path: str | None
    ) -> None:
        from mutagen.id3 import ID3, APIC, TIT2, TPE1, TPE2, TALB, TRCK, TPOS, TDRC, TCON, TSRC

        try:
            audio = ID3(path)
        except Exception:
            audio = ID3()

        audio.add(TIT2(encoding=3, text=track.title))
        audio.add(TPE1(encoding=3, text=track.performer.name))
        audio.add(TPE2(encoding=3, text=album.artist.name))
        audio.add(TALB(encoding=3, text=album.title))
        audio.add(TRCK(encoding=3, text=f"{track.track_number}/{album.tracks_count}"))
        audio.add(TPOS(encoding=3, text=str(track.disc_number)))
        if album.release_date_original:
            audio.add(TDRC(encoding=3, text=album.release_date_original[:4]))
        if album.genre:
            audio.add(TCON(encoding=3, text=album.genre.name))
        if track.isrc:
            audio.add(TSRC(encoding=3, text=track.isrc))

        if cover_path and self.config.embed_cover:
            with open(cover_path, "rb") as f:
                audio.add(APIC(encoding=3, mime="image/jpeg", type=3, data=f.read()))

        audio.save(path, v2_version=3)

    async def _tag_m4a(
        self, path: str, track: Track, album: Album, cover_path: str | None
    ) -> None:
        from mutagen.mp4 import MP4, MP4Cover

        audio = MP4(path)
        audio["\xa9nam"] = [track.title]
        audio["\xa9ART"] = [track.performer.name]
        audio["aART"] = [album.artist.name]
        audio["\xa9alb"] = [album.title]
        audio["trkn"] = [(track.track_number, album.tracks_count)]
        audio["disk"] = [(track.disc_number, 1)]
        if album.release_date_original:
            audio["\xa9day"] = [album.release_date_original[:4]]
        if album.genre:
            audio["\xa9gen"] = [album.genre.name]

        if cover_path and self.config.embed_cover:
            with open(cover_path, "rb") as f:
                audio["covr"] = [MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG)]

        audio.save()

    def _build_album_folder(self, album: Album) -> str:
        """Build the album output folder path from the format template."""
        base = self.config.output_dir
        if self.config.source_subdirectories:
            base = os.path.join(base, "Qobuz")

        replacements = {
            "albumartist": _safe_filename(album.artist.name),
            "title": _safe_filename(album.title),
            "year": album.release_date_original[:4] if album.release_date_original else "Unknown",
            "container": "FLAC" if self.config.quality >= 2 else "MP3",
            "bit_depth": str(album.maximum_bit_depth),
            "sampling_rate": str(album.maximum_sampling_rate),
            "id": album.id,
        }

        folder_name = self.config.folder_format
        for key, value in replacements.items():
            folder_name = folder_name.replace(f"{{{key}}}", value)
        # Clean any remaining unresolved placeholders
        folder_name = re.sub(r"\{[^}]+\}", "", folder_name).strip()

        return os.path.join(base, _safe_filename(folder_name))

    def _build_track_filename(self, track: Track, album: Album, ext: str) -> str:
        """Build track filename from the format template."""
        replacements = {
            "tracknumber": str(track.track_number).zfill(2),
            "artist": _safe_filename(track.performer.name),
            "albumartist": _safe_filename(album.artist.name),
            "title": _safe_filename(track.title),
        }

        filename = self.config.track_format
        # Handle {tracknumber:02d} format
        filename = re.sub(r"\{tracknumber:\d+d\}", replacements["tracknumber"], filename)
        for key, value in replacements.items():
            filename = filename.replace(f"{{{key}}}", value)

        explicit = " (Explicit)" if track.explicit else ""
        filename = filename.replace("{explicit}", explicit)
        filename = re.sub(r"\{[^}]+\}", "", filename).strip()

        return f"{filename}.{ext}"


def _safe_filename(s: str) -> str:
    """Remove or replace characters that are invalid in file/folder names."""
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    s = s.replace("\n", " ").replace("\r", "").strip()
    return s[:200]


def _mime_to_ext(mime: str) -> str:
    """Map MIME type to file extension."""
    mapping = {
        "audio/flac": "flac",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/x-flac": "flac",
        "audio/aac": "m4a",
    }
    return mapping.get(mime.lower(), "flac")
