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

# Matches text segments between → (U+2192) and / delimiters
_genre_clean = re.compile(r"([^\u2192/]+)")


def _build_track_title(track: Track, raw_track: dict | None = None) -> str:
    """Build title with version appended, matching streamrip behavior."""
    title = track.title
    version = track.version or (raw_track.get("version") if raw_track else None)
    if version and version not in title:
        title = f"{title} ({version})"
    return title


def _build_albumartist(album: Album) -> str:
    """Use the primary artist name for albumartist.

    The Qobuz API provides a primary 'artist' and a list of 'artists'
    with roles. We use the primary artist to match what the UI displays
    and avoid long multi-artist strings in folder names.
    """
    return album.artist.name


def _build_genres(raw_album: dict) -> list[str]:
    """Extract genre list from raw album response, matching streamrip.

    Uses genres_list first, falls back to genre field. Deduplicates.
    """
    genre_raw = raw_album.get("genres_list") or raw_album.get("genre") or []
    if isinstance(genre_raw, dict):
        genre_raw = [genre_raw.get("name", "")]
    if isinstance(genre_raw, str):
        genre_raw = [genre_raw]
    genres = list(set(_genre_clean.findall("/".join(genre_raw))))
    return genres


def _zero_pad(n: int) -> str:
    """Zero-pad a number to at least 2 digits, matching streamrip."""
    return str(n).zfill(2)


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
    skip_downloaded: bool = True  # Skip tracks already in download history
    downloads_db_path: str | None = None  # Path to SQLite downloads DB


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
        self._downloaded_ids: set[str] = set()
        if config.skip_downloaded and config.downloads_db_path:
            self._load_downloaded_ids()

    async def download(self, album_id: str) -> AlbumResult:
        """Download an entire album by ID."""
        # Fetch raw response for goodies, then parse album + tracks
        _, raw_body = await self.client._transport.get(
            "album/get", {"album_id": album_id, "extra": "track_ids"}
        )
        album = Album.from_dict(raw_body)
        raw_track_items = raw_body.get("tracks", {}).get("items", [])
        tracks = [Track.from_dict(t) for t in raw_track_items]
        # Keep raw track dicts for version/metadata parity
        raw_tracks_by_id = {t.get("id"): t for t in raw_track_items}
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
            *[self._download_track(
                i + 1, track, album, album_folder, cover_path,
                raw_album=raw_body, raw_track=raw_tracks_by_id.get(track.id),
              )
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

        album_result = AlbumResult(
            album_id=album.id,
            title=album.title,
            artist=album.artist.name,
            tracks=track_results,
            cover_path=cover_path,
            booklet_paths=booklet_paths,
        )

        # Write metadata file for filesystem-based dedup
        if album_result.successful > 0:
            self._write_metadata_file(album, album_folder, album_result)

        return album_result

    METADATA_FILENAME = ".streamrip.json"

    def _write_metadata_file(self, album: Album, folder: str, result: AlbumResult) -> None:
        """Write a .streamrip.json file in the album folder for filesystem-based dedup."""
        import json
        from datetime import datetime

        metadata = {
            "source": "qobuz",
            "album_id": album.id,
            "title": album.title,
            "artist": album.artist.name,
            "tracks_count": result.total,
            "tracks_downloaded": result.successful,
            "quality": self.config.quality,
            "downloaded_at": datetime.now().isoformat(),
            "tracks": [
                {
                    "id": t.track_id,
                    "title": t.title,
                    "success": t.success,
                    "path": os.path.basename(t.path) if t.path else None,
                }
                for t in result.tracks
            ],
        }

        path = os.path.join(folder, self.METADATA_FILENAME)
        try:
            with open(path, "w") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            logger.info("Wrote metadata file: %s", path)
        except Exception as e:
            logger.warning("Failed to write metadata file: %s", e)

    @staticmethod
    def scan_downloaded_albums(download_dir: str) -> list[dict]:
        """Scan a download directory for .streamrip.json files.

        Returns a list of album metadata dicts from all found metadata files.
        Use this to reconcile the DB with what's actually on disk.
        """
        import json

        albums = []
        for root, dirs, files in os.walk(download_dir):
            if AlbumDownloader.METADATA_FILENAME in files:
                meta_path = os.path.join(root, AlbumDownloader.METADATA_FILENAME)
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)
                    meta["_folder"] = root
                    albums.append(meta)
                except Exception:
                    pass
        return albums

    def _load_downloaded_ids(self) -> None:
        """Load previously downloaded track IDs from SQLite DB."""
        import sqlite3
        path = self.config.downloads_db_path
        if not path or not os.path.exists(path):
            return
        try:
            conn = sqlite3.connect(path)
            rows = conn.execute("SELECT id FROM downloads").fetchall()
            self._downloaded_ids = {str(row[0]) for row in rows}
            conn.close()
            logger.info("Loaded %d downloaded track IDs from %s", len(self._downloaded_ids), path)
        except Exception as e:
            logger.warning("Failed to load downloads DB: %s", e)

    def _mark_downloaded(self, track_id: int) -> None:
        """Mark a track as downloaded in the SQLite DB."""
        path = self.config.downloads_db_path
        if not path:
            return
        try:
            import sqlite3
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE IF NOT EXISTS downloads (id TEXT UNIQUE NOT NULL)")
            conn.execute("INSERT OR IGNORE INTO downloads (id) VALUES (?)", (str(track_id),))
            conn.commit()
            conn.close()
            self._downloaded_ids.add(str(track_id))
        except Exception as e:
            logger.warning("Failed to update downloads DB: %s", e)

    async def _download_track(
        self,
        track_num: int,
        track: Track,
        album: Album,
        album_folder: str,
        cover_path: str | None,
        raw_album: dict | None = None,
        raw_track: dict | None = None,
    ) -> TrackResult:
        """Download, tag, and save a single track."""
        async with self._semaphore:
            # Check dedup — skip if already downloaded
            if self.config.skip_downloaded and str(track.id) in self._downloaded_ids:
                logger.info("Skipping track %d — already downloaded", track.id)
                if self._on_track_complete:
                    self._on_track_complete(track_num, track.title, True)
                return TrackResult(
                    track_id=track.id, title=track.title, success=True,
                    path=None, error="skipped (already downloaded)",
                )

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

                filename = self._build_track_filename(track, album, ext, raw_track=raw_track)
                file_path = os.path.join(disc_folder, filename)

                # Download audio
                await self._download_file(
                    file_url.url, file_path, track_num
                )

                # Tag file
                if self.config.tag_files:
                    await self._tag_file(
                        file_path, track, album, cover_path, file_url,
                        raw_album=raw_album, raw_track=raw_track,
                    )

                self._mark_downloaded(track.id)

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
        self, url: str, path: str, track_num: int, retries: int = 2
    ) -> None:
        """Stream download a file from URL to disk with retry on failure."""
        for attempt in range(retries):
            try:
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
                return  # Success
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning("Download attempt %d failed, retrying in 2s: %s", attempt + 1, e)
                    if os.path.exists(path):
                        os.remove(path)
                    await asyncio.sleep(2)  # Brief pause before retry
                else:
                    raise

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
        raw_album: dict | None = None,
        raw_track: dict | None = None,
    ) -> None:
        """Tag an audio file with metadata using mutagen."""
        ext = path.rsplit(".", 1)[-1].lower()

        if ext == "flac":
            await self._tag_flac(path, track, album, cover_path, raw_album, raw_track)
        elif ext == "mp3":
            await self._tag_mp3(path, track, album, cover_path, raw_album, raw_track)
        elif ext == "m4a":
            await self._tag_m4a(path, track, album, cover_path, raw_album, raw_track)

    async def _tag_flac(
        self, path: str, track: Track, album: Album, cover_path: str | None,
        raw_album: dict | None = None, raw_track: dict | None = None,
    ) -> None:
        from mutagen.flac import FLAC, Picture

        title = _build_track_title(track, raw_track)
        albumartist = _build_albumartist(album)
        genres = _build_genres(raw_album) if raw_album else ([album.genre.name] if album.genre else [])

        # Extract additional metadata from raw responses
        # Composer comes from the TRACK response (per-track), not album
        composer = ""
        if raw_track:
            composer_data = raw_track.get("composer", {})
            if isinstance(composer_data, dict):
                composer = composer_data.get("name", "")
            elif isinstance(composer_data, str):
                composer = composer_data

        copyright_text = ""
        description = ""
        disctotal = 1
        if raw_album:
            copyright_text = raw_album.get("copyright", "")
            description = raw_album.get("description", "")
            disctotal = raw_album.get("media_count", 1) or 1

        audio = FLAC(path)
        audio["title"] = title
        audio["artist"] = track.performer.name
        audio["albumartist"] = albumartist
        audio["album"] = album.title
        audio["tracknumber"] = _zero_pad(track.track_number)
        audio["discnumber"] = _zero_pad(track.disc_number)
        audio["tracktotal"] = str(album.tracks_count)
        audio["disctotal"] = _zero_pad(disctotal)
        if genres:
            audio["genre"] = ", ".join(genres)
        if album.release_date_original:
            audio["date"] = album.release_date_original
            audio["year"] = album.release_date_original[:4]
        if album.label:
            audio["organization"] = album.label.name
        if track.isrc:
            audio["isrc"] = track.isrc
        if album.upc:
            audio["barcode"] = album.upc
        if composer:
            audio["composer"] = composer
        if copyright_text:
            audio["copyright"] = copyright_text
        if description:
            audio["description"] = description

        if cover_path and self.config.embed_cover:
            pic = Picture()
            with open(cover_path, "rb") as f:
                pic.data = f.read()
            pic.type = 3  # front cover
            pic.mime = "image/jpeg"
            audio.add_picture(pic)

        audio.save()

    async def _tag_mp3(
        self, path: str, track: Track, album: Album, cover_path: str | None,
        raw_album: dict | None = None, raw_track: dict | None = None,
    ) -> None:
        from mutagen.id3 import ID3, APIC, TIT2, TPE1, TPE2, TALB, TRCK, TPOS, TDRC, TCON, TSRC

        title = _build_track_title(track, raw_track)
        albumartist = _build_albumartist(album)
        genres = _build_genres(raw_album) if raw_album else ([album.genre.name] if album.genre else [])

        try:
            audio = ID3(path)
        except Exception:
            audio = ID3()

        audio.add(TIT2(encoding=3, text=title))
        audio.add(TPE1(encoding=3, text=track.performer.name))
        audio.add(TPE2(encoding=3, text=albumartist))
        audio.add(TALB(encoding=3, text=album.title))
        audio.add(TRCK(encoding=3, text=f"{_zero_pad(track.track_number)}/{album.tracks_count}"))
        audio.add(TPOS(encoding=3, text=_zero_pad(track.disc_number)))
        if album.release_date_original:
            audio.add(TDRC(encoding=3, text=album.release_date_original[:4]))
        if genres:
            audio.add(TCON(encoding=3, text=", ".join(genres)))
        if track.isrc:
            audio.add(TSRC(encoding=3, text=track.isrc))

        if cover_path and self.config.embed_cover:
            with open(cover_path, "rb") as f:
                audio.add(APIC(encoding=3, mime="image/jpeg", type=3, data=f.read()))

        audio.save(path, v2_version=3)

    async def _tag_m4a(
        self, path: str, track: Track, album: Album, cover_path: str | None,
        raw_album: dict | None = None, raw_track: dict | None = None,
    ) -> None:
        from mutagen.mp4 import MP4, MP4Cover

        title = _build_track_title(track, raw_track)
        albumartist = _build_albumartist(album)
        genres = _build_genres(raw_album) if raw_album else ([album.genre.name] if album.genre else [])

        audio = MP4(path)
        audio["\xa9nam"] = [title]
        audio["\xa9ART"] = [track.performer.name]
        audio["aART"] = [albumartist]
        audio["\xa9alb"] = [album.title]
        audio["trkn"] = [(track.track_number, album.tracks_count)]
        audio["disk"] = [(track.disc_number, 1)]
        if album.release_date_original:
            audio["\xa9day"] = [album.release_date_original[:4]]
        if genres:
            audio["\xa9gen"] = [", ".join(genres)]

        if cover_path and self.config.embed_cover:
            with open(cover_path, "rb") as f:
                audio["covr"] = [MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG)]

        audio.save()

    def _build_album_folder(self, album: Album) -> str:
        """Build the album output folder path from the format template.

        Supports '/' in the format to create nested directories, e.g.
        '{albumartist}/({year}) {title}' → 'Artist/(2024) Album Title'
        """
        base = self.config.output_dir
        if self.config.source_subdirectories:
            base = os.path.join(base, "Qobuz")

        replacements = {
            "albumartist": _safe_value(_build_albumartist(album)),
            "title": _safe_value(album.title),
            "year": album.release_date_original[:4] if album.release_date_original else "Unknown",
            "container": "FLAC" if self.config.quality >= 2 else "MP3",
            "bit_depth": str(album.maximum_bit_depth),
            "sampling_rate": str(album.maximum_sampling_rate).rstrip('0').rstrip('.'),
            "id": album.id,
        }

        try:
            folder_path = self.config.folder_format.format(**replacements)
        except (KeyError, ValueError):
            # Fallback to manual replacement if format() fails
            folder_path = self.config.folder_format
            for key, value in replacements.items():
                folder_path = folder_path.replace(f"{{{key}}}", str(value))
            folder_path = re.sub(r"\{[^}]+\}", "", folder_path).strip()

        # Split on / to create nested directories, clean each segment
        segments = [_safe_filename(seg.strip()) for seg in folder_path.split("/") if seg.strip()]
        return os.path.join(base, *segments)

    def _build_track_filename(
        self, track: Track, album: Album, ext: str,
        raw_track: dict | None = None,
    ) -> str:
        """Build track filename from the format template.

        Uses Python str.format() to handle format specifiers like
        {tracknumber:02} natively, matching streamrip's behavior.
        """
        title = _build_track_title(track, raw_track)
        explicit = " (Explicit)" if track.explicit else ""

        replacements = {
            "tracknumber": track.track_number,
            "artist": _safe_value(track.performer.name),
            "albumartist": _safe_value(_build_albumartist(album)),
            "title": _safe_value(title),
            "explicit": explicit,
        }

        try:
            filename = self.config.track_format.format(**replacements)
        except (KeyError, ValueError):
            # Fallback to manual replacement
            filename = self.config.track_format
            replacements["tracknumber"] = str(track.track_number).zfill(2)
            for key, value in replacements.items():
                filename = filename.replace(f"{{{key}}}", str(value))
            filename = re.sub(r"\{[^}]+\}", "", filename).strip()

        return f"{_safe_filename(filename)}.{ext}"


def _safe_filename(s: str) -> str:
    """Remove or replace characters that are invalid in file/folder names."""
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    s = s.replace("\n", " ").replace("\r", "").strip()
    return s[:200]


def _safe_value(s: str) -> str:
    """Sanitize a metadata value for use in file/folder name templates.

    Removes characters that are invalid in filenames AND path separators,
    so values like 'Eu e Memê / Memê e Eu' don't create nested directories.
    """
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    s = s.replace("/", " - ")  # Replace path separator with dash
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
