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

    async def enqueue(self, source: str, album_ids: list[str]) -> list[dict]:
        items = []
        for source_album_id in album_ids:
            album = self.db.get_album_by_source_id(source, source_album_id)
            if album is None:
                logger.warning("Album %s not found in DB", source_album_id)
                continue
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
        """Download an album using PendingAlbum directly (no Main).

        This avoids Main.__init__ creating new un-logged-in clients.
        We pass the already-logged-in client directly to PendingAlbum.
        """
        from streamrip.media import PendingAlbum
        from streamrip.db import build_database
        from .config_bridge import build_streamrip_config

        client = self.clients.get(item["source"])
        if client is None:
            raise ValueError(f"No client for source {item['source']}")

        # Ensure client is logged in — login if needed
        if not getattr(client, 'logged_in', False) or (
            item["source"] == "qobuz" and not getattr(client, 'secret', None)
        ):
            logger.warning(
                "Client %s not ready (logged_in=%s, secret=%s). Attempting login...",
                item["source"],
                getattr(client, 'logged_in', None),
                'set' if getattr(client, 'secret', None) else 'None',
            )
            try:
                await client.login()
                logger.info("Login successful for %s", item["source"])
            except Exception:
                logger.exception("Login failed for %s", item["source"])
                raise ValueError(f"Client {item['source']} failed to login")

        logger.info(
            "Downloading album: %s - %s (id: %s) [logged_in=%s, secret=%s]",
            item["artist"], item["title"], item["source_album_id"],
            client.logged_in,
            "set" if getattr(client, "secret", None) else "None",
        )

        config = build_streamrip_config(self.db)
        if self.download_path:
            config.session.downloads.folder = self.download_path

        database = build_database(config)

        pending = PendingAlbum(item["source_album_id"], client, config, database)

        media = await pending.resolve()
        if media is None:
            raise ValueError(f"Failed to resolve album {item['source_album_id']}")

        await media.rip()

        # Check success using the same 80% threshold as Album.postprocess()
        if hasattr(media, 'successful_tracks') and hasattr(media, 'total_tracks'):
            total = media.total_tracks
            success = media.successful_tracks
            if total > 0:
                success_rate = success / total
                logger.info(
                    "Downloaded %d/%d tracks (%.0f%%) for %s - %s",
                    success, total, success_rate * 100,
                    item["artist"], item["title"],
                )
                if success_rate < 0.8:
                    raise RuntimeError(
                        f"Only {success}/{total} tracks downloaded "
                        f"({success_rate:.0%}), below 80% threshold"
                    )

        logger.info("Download complete: %s - %s", item["artist"], item["title"])
