"""Download service — queue management and download execution."""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Any

from ..models.database import AppDatabase
from .event_bus import EventBus

logger = logging.getLogger("streamrip")


class DownloadService:
    def __init__(self, db: AppDatabase, event_bus: EventBus, clients: dict,
                 download_path: str, max_connections: int = 6):
        self.db = db
        self.event_bus = event_bus
        self.clients = clients
        self.download_path = download_path
        self.max_connections = max_connections
        self._queue: list[dict[str, Any]] = []
        self._cancel_requested: set[str] = set()
        self._worker_task: asyncio.Task | None = None

    async def _fetch_album_metadata(self, source: str, source_album_id: str) -> dict:
        """Fetch real album metadata from the streaming service.

        Used when enqueueing a download for an album that's not yet in
        the local DB (typically a search result).  Falls back to a
        placeholder name if the SDK call fails — we still want the
        download to be attempted, just with an ugly queue entry.
        """
        fallback = {
            "title": f"Album {source_album_id}",
            "artist": "Unknown",
            "cover_url": None,
            "track_count": None,
            "release_date": None,
        }
        client = self.clients.get(source)
        if client is None or not hasattr(client, "catalog"):
            return fallback

        try:
            album, tracks = await client.catalog.get_album_with_tracks(source_album_id)
        except Exception:
            logger.exception(
                "Failed to fetch metadata for %s/%s; using placeholder",
                source, source_album_id,
            )
            return fallback

        # The two SDKs return slightly different shapes — both have
        # `title` and `artist.name`, but `cover` (Tidal) vs `image.large`
        # (Qobuz raw dicts). The typed Qobuz Album also has helpers.
        title = getattr(album, "title", None) or fallback["title"]
        artist_obj = getattr(album, "artist", None)
        artist = (
            getattr(artist_obj, "name", None)
            if artist_obj is not None
            else None
        ) or fallback["artist"]

        # Cover URL — Tidal exposes a bare cover ID, Qobuz a full URL.
        cover_url: str | None = None
        if source == "tidal":
            cover_id = getattr(album, "cover", None)
            if cover_id:
                cover_url = (
                    f"https://resources.tidal.com/images/"
                    f"{cover_id.replace('-', '/')}/640x640.jpg"
                )
        else:
            image = getattr(album, "image", None)
            if isinstance(image, dict):
                cover_url = image.get("large") or image.get("small")
            elif image is not None:
                cover_url = (
                    getattr(image, "large", None) or getattr(image, "small", None)
                )
            if cover_url is None:
                cover_url = getattr(album, "cover_url", None) or getattr(album, "cover", None)

        track_count = (
            getattr(album, "tracks_count", None)
            or getattr(album, "number_of_tracks", None)
            or len(tracks)
        )
        release_date = (
            getattr(album, "release_date_original", None)
            or getattr(album, "release_date", None)
        )

        return {
            "title": title,
            "artist": artist,
            "cover_url": cover_url,
            "track_count": track_count,
            "release_date": release_date,
        }

    async def enqueue(self, source: str, album_ids: list[str], force: bool = False) -> list[dict]:
        items = []
        for source_album_id in album_ids:
            album = self.db.get_album_by_source_id(source, source_album_id)
            if album is None:
                # Search results aren't in the local DB yet — fetch the real
                # title/artist/cover from the streaming service so the queue
                # row doesn't show "Album <id>" + "Unknown".
                meta = await self._fetch_album_metadata(source, source_album_id)
                album_id = self.db.upsert_album(
                    source=source,
                    source_album_id=source_album_id,
                    title=meta["title"],
                    artist=meta["artist"],
                    cover_url=meta.get("cover_url"),
                    track_count=meta.get("track_count"),
                    release_date=meta.get("release_date"),
                    added_to_library_at=datetime.now().isoformat(),
                )
                album = self.db.get_album(album_id)
                if album is None:
                    logger.warning("Failed to create album entry for %s", source_album_id)
                    continue
                logger.info(
                    "Auto-created album entry for %s: %s — %s",
                    source_album_id, meta["artist"], meta["title"],
                )
            item = {
                "id": str(uuid.uuid4()),
                "album_db_id": album["id"],
                "source": source,
                "source_album_id": source_album_id,
                "title": album["title"],
                "artist": album["artist"],
                "cover_url": album.get("cover_url"),
                "track_count": album.get("track_count", 0),
                "tracks_done": 0,
                "bytes_done": 0,
                "bytes_total": 0,
                "speed": 0.0,
                "status": "pending",
                "force": force,
            }
            self._queue.append(item)
            self.db.update_album_status(album["id"], "queued")
            items.append(item)

        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue())
        return items

    def get_queue(self) -> list[dict]:
        return list(self._queue)

    async def cancel(self, item_ids: list[str]):
        for item_id in item_ids:
            self._cancel_requested.add(item_id)
            for item in self._queue:
                if item["id"] == item_id and item["status"] in ("pending", "downloading"):
                    item["status"] = "cancelled"
                    self.db.update_album_status(item["album_db_id"], "not_downloaded")

    async def cancel_all(self):
        ids = [item["id"] for item in self._queue if item["status"] in ("pending", "downloading")]
        await self.cancel(ids)

    async def _process_queue(self):
        while True:
            pending = [item for item in self._queue if item["status"] == "pending"]
            if not pending:
                break
            item = pending[0]
            if item["id"] in self._cancel_requested:
                item["status"] = "cancelled"
                self._cancel_requested.discard(item["id"])
                continue

            item["status"] = "downloading"
            self.db.update_album_status(item["album_db_id"], "downloading")
            await self.event_bus.publish("download_progress", {
                "item_id": item["id"], "status": "downloading",
                "tracks_done": 0, "track_count": item["track_count"],
            })

            try:
                await self._download_album(item)
                item["status"] = "complete"
                self.db.update_album_status(item["album_db_id"], "complete", downloaded_at=datetime.now().isoformat())
                await self.event_bus.publish("download_complete", {"item_id": item["id"], "title": item["title"], "artist": item["artist"]})
            except Exception as e:
                logger.exception("Download failed for %s", item["title"])
                item["status"] = "failed"
                self.db.update_album_status(item["album_db_id"], "not_downloaded")
                await self.event_bus.publish("download_failed", {"item_id": item["id"], "error": str(e)})

    async def _download_album(self, item: dict):
        """Download an album using the appropriate source SDK.

        Dispatches to the Qobuz or Tidal SDK based on ``item["source"]``.
        Both SDKs use the same ``AlbumDownloader``/``DownloadConfig`` shape
        and the same callback protocol, so the progress-reporting wiring
        below is identical for either path.
        """
        source = item["source"]
        sdk_client = self.clients.get(source)
        if sdk_client is None:
            raise ValueError(f"No client for source {source}")

        if source == "qobuz":
            from qobuz import AlbumDownloader, DownloadConfig
        elif source == "tidal":
            from tidal import AlbumDownloader, DownloadConfig
        else:
            raise ValueError(f"Unsupported source: {source}")

        # Quality is per-source (each streaming service has its own tier scale).
        quality_key = f"{source}_quality"
        quality = 3
        q_val = self.db.get_config(quality_key)
        if q_val:
            quality = int(q_val)

        # Per-source dedup DB so track IDs from different services never collide.
        # Qobuz keeps the legacy name to preserve existing dedup state on disk.
        downloads_db = None
        if not item.get("force"):
            db_dir = os.path.dirname(
                os.environ.get("STREAMRIP_DB_PATH", "data/streamrip.db")
            ) or "data"
            db_filename = "downloads.db" if source == "qobuz" else f"downloads-{source}.db"
            downloads_db = os.path.join(db_dir, db_filename)

        config_kwargs: dict = {
            "output_dir": self.download_path or "/music",
            "quality": quality,
            "folder_format": self.db.get_config("folder_format") or "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]",
            "track_format": self.db.get_config("track_format") or "{tracknumber:02d}. {artist} - {title}",
            "max_connections": self.max_connections,
            "embed_cover": self.db.get_config("embed_artwork") != "false",
            "cover_size": self.db.get_config("artwork_size") or "large",
            "source_subdirectories": self.db.get_config("source_subdirectories") in ("true", "1"),
            "disc_subdirectories": self.db.get_config("disc_subdirectories") != "false",
            "skip_downloaded": not item.get("force", False),
            "downloads_db_path": downloads_db,
        }
        # Qobuz-only settings — the Tidal SDK's DownloadConfig doesn't model them.
        if source == "qobuz":
            config_kwargs["download_booklets"] = (
                self.db.get_config("qobuz_download_booklets") != "false"
            )

        dl_config = DownloadConfig(**config_kwargs)

        import time as _time

        event_bus = self.event_bus
        queue_item = item
        # Track status keyed by track number — tracks download concurrently
        # via asyncio.gather, so [-1] indexing is racy and clobbers the
        # wrong track on every callback.  Keep a dict, render to a sorted
        # list at emit time.
        track_statuses_by_num: dict[int, dict] = {}
        last_emit = [0.0]
        # Per-track download start time, for per-track speed calculations
        track_start_times: dict[int, float] = {}

        def _render_statuses() -> list[dict]:
            return [
                dict(track_statuses_by_num[k])
                for k in sorted(track_statuses_by_num)
            ]

        def _emit_progress():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(event_bus.publish("download_progress", {
                        "item_id": queue_item["id"],
                        "status": "downloading",
                        "tracks_done": queue_item.get("tracks_done", 0),
                        "track_count": queue_item.get("track_count", 0),
                        "bytes_done": queue_item.get("bytes_done", 0),
                        "bytes_total": queue_item.get("bytes_total", 0),
                        "speed": queue_item.get("speed", 0),
                        "current_track": queue_item.get("current_track", ""),
                        "track_statuses": _render_statuses(),
                    }))
            except Exception:
                pass

        def on_track_start(num: int, title: str):
            queue_item["current_track"] = f"Track {num}: {title}"
            track_statuses_by_num[num] = {
                "num": num,
                "name": title,
                "status": "downloading",
                "progress": 0,
            }
            track_start_times[num] = _time.monotonic()
            _emit_progress()

        def on_track_progress(num: int, bytes_done: int, bytes_total: int):
            queue_item["bytes_done"] = bytes_done
            queue_item["bytes_total"] = bytes_total

            status = track_statuses_by_num.get(num)
            if status is not None and bytes_total > 0:
                status["progress"] = min(100, round(bytes_done / bytes_total * 100))

            # Speed for *this* track (per-track, not the album-wide last call)
            start = track_start_times.get(num, _time.monotonic())
            elapsed = _time.monotonic() - start
            speed = (bytes_done / elapsed / (1024 * 1024)) if elapsed > 0 else 0
            queue_item["speed"] = round(speed, 2)

            # Throttle WebSocket events to every 0.5s
            now = _time.monotonic()
            if now - last_emit[0] < 0.5:
                return
            last_emit[0] = now
            _emit_progress()

        def on_track_complete(num: int, title: str, success: bool):
            status = track_statuses_by_num.get(num)
            if status is not None:
                status["status"] = "complete" if success else "failed"
                if success:
                    status["progress"] = 100
            if success:
                queue_item["tracks_done"] = queue_item.get("tracks_done", 0) + 1
            _emit_progress()

        logger.info("Downloading album: %s - %s (id: %s)",
                     item["artist"], item["title"], item["source_album_id"])

        downloader = AlbumDownloader(
            sdk_client,
            dl_config,
            on_track_start=on_track_start,
            on_track_progress=on_track_progress,
            on_track_complete=on_track_complete,
        )

        result = await downloader.download(item["source_album_id"])

        item["track_count"] = result.total
        item["tracks_done"] = result.successful

        # Update album metadata in DB with resolved data from download
        if result.title and result.artist:
            self.db.upsert_album(
                source=item["source"],
                source_album_id=item["source_album_id"],
                title=result.title,
                artist=result.artist,
                track_count=result.total,
            )
            item["title"] = result.title
            item["artist"] = result.artist

        # Update track statuses in web DB
        self._update_track_statuses_from_result(item, result)

        # Check 80% success threshold
        if result.total > 0 and result.success_rate < 0.8:
            raise RuntimeError(
                f"Only {result.successful}/{result.total} tracks downloaded "
                f"({result.success_rate:.0%}), below 80% threshold"
            )

        logger.info("Download complete: %s - %s (%d/%d tracks)",
                     item["artist"], item["title"], result.successful, result.total)

    def _update_track_statuses_from_result(self, item: dict, result):
        """Update track download_status in the web DB from AlbumResult."""
        album = self.db.get_album_by_source_id(item["source"], item["source_album_id"])
        if not album:
            return

        tracks = self.db.get_tracks(album["id"])
        if not tracks:
            return

        downloaded_ids = {str(t.track_id) for t in result.tracks if t.success}
        for track in tracks:
            if track["source_track_id"] in downloaded_ids:
                self.db.update_track_status(track["id"], "complete")
