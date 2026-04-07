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
        """Download an album using the existing streamrip pipeline."""
        from streamrip.config import Config
        from streamrip.rip.main import Main

        client = self.clients.get(item["source"])
        if client is None:
            raise ValueError(f"No client for source {item['source']}")

        logger.info("Downloading album: %s - %s (id: %s)",
                     item["artist"], item["title"], item["source_album_id"])

        # Build a Config from the stored settings
        config_path = os.environ.get(
            "STREAMRIP_CONFIG_PATH",
            os.path.expanduser("~/.config/streamrip/config.toml"),
        )
        if os.path.exists(config_path):
            config = Config(config_path)
        else:
            config = Config.defaults()

        # Override download path
        if self.download_path:
            config.session.downloads.folder = self.download_path

        # Create a Main instance and inject the already-logged-in client
        main = Main(config)
        main.clients[item["source"]] = client

        # Use the existing pipeline: add by ID → resolve → rip
        main._add_by_id_client(client, "album", item["source_album_id"])
        await main.resolve()
        await main.rip()

        logger.info("Download complete: %s - %s", item["artist"], item["title"])
