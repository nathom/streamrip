"""Sync service — diff streaming library against local downloads."""

import asyncio
import logging

from ..models.database import AppDatabase
from .event_bus import EventBus

logger = logging.getLogger("streamrip")


class SyncService:
    def __init__(
        self,
        db: AppDatabase,
        event_bus: EventBus,
        clients: dict,
        library_service,
        download_service=None,
    ):
        self.db = db
        self.event_bus = event_bus
        self.clients = clients
        self.library_service = library_service
        self.download_service = download_service
        self._auto_sync_task: asyncio.Task | None = None

    async def get_diff(self, source: str) -> dict:
        """Compare streaming library against local database."""
        client = self.clients.get(source)
        # Both SDK clients open their transport via __aenter__ in lifespan
        # and don't expose ``logged_in`` — treat presence of the client as
        # sufficient. If the session is actually down, the SDK call below
        # will surface a proper error.
        if client is None:
            return {"new_albums": [], "removed_albums": [], "source": source, "last_sync": None}

        all_items = await self.library_service.fetch_all_favorites(source, client)

        streaming_ids = set()
        new_albums = []

        for item in all_items:
            parsed = self.library_service._extract_album_data(source, item)
            if parsed is None:
                continue
            source_album_id = parsed["source_album_id"]
            streaming_ids.add(source_album_id)

            existing = self.db.get_album_by_source_id(source, source_album_id)
            if existing is None:
                new_albums.append(parsed)

        # Find removed: albums in DB but not in streaming library
        local_albums = self.db.get_albums(source, limit=10000)
        removed_albums = [a for a in local_albums if a["source_album_id"] not in streaming_ids]

        # Get last sync time
        history = self.db.get_sync_history(source, limit=1)
        last_sync = history[0]["completed_at"] if history else None

        return {
            "new_albums": new_albums,
            "removed_albums": removed_albums,
            "source": source,
            "last_sync": last_sync,
        }

    async def run_sync(self, source: str, download_new: bool = False) -> dict:
        """Run a full sync: refresh library, optionally enqueue new albums.

        When ``download_new=True`` and a ``download_service`` was passed
        to the constructor, the new albums detected by the diff are
        enqueued for download via ``download_service.enqueue``.  The
        returned dict reports how many were queued, but the downloads
        themselves run async in the worker — this method does not block
        on completion.
        """
        run_id = self.db.create_sync_run(source)

        await self.event_bus.publish("sync_started", {"source": source, "run_id": run_id})

        try:
            # Refresh library from streaming API
            refresh_result = await self.library_service.refresh_library(source)

            # Get diff after refresh
            diff = await self.get_diff(source)

            albums_downloaded = 0
            if download_new and self.download_service is not None and diff["new_albums"]:
                new_ids = [a["source_album_id"] for a in diff["new_albums"]]
                logger.info(
                    "Auto-sync enqueueing %d new %s albums for download",
                    len(new_ids), source,
                )
                try:
                    await self.download_service.enqueue(source, new_ids)
                    albums_downloaded = len(new_ids)
                except Exception:
                    logger.exception("Failed to enqueue auto-sync downloads")

            self.db.complete_sync_run(
                run_id,
                albums_found=refresh_result["total"],
                albums_new=refresh_result["new"],
                albums_removed=len(diff["removed_albums"]),
                albums_downloaded=albums_downloaded,
            )

            await self.event_bus.publish("sync_complete", {
                "source": source,
                "run_id": run_id,
                "new_count": refresh_result["new"],
                "removed_count": len(diff["removed_albums"]),
                "downloaded_count": albums_downloaded,
            })

            return {
                "run_id": run_id,
                "albums_found": refresh_result["total"],
                "albums_new": refresh_result["new"],
                "albums_removed": len(diff["removed_albums"]),
                "albums_downloaded": albums_downloaded,
                "status": "complete",
            }
        except Exception as e:
            logger.exception("Sync failed for %s", source)
            return {"run_id": run_id, "status": "failed", "error": str(e)}

    async def get_history(self, source: str, limit: int = 10) -> list[dict]:
        return self.db.get_sync_history(source, limit=limit)

    def start_auto_sync(
        self,
        source: str,
        interval_seconds: int,
        download_new: bool = True,
    ):
        """Start a background auto-sync task.

        ``download_new`` is forwarded to ``run_sync``: when True (default),
        new albums detected by each scheduled diff are enqueued for
        download.  Set to False to refresh the library only without
        kicking off downloads.
        """
        if self._auto_sync_task and not self._auto_sync_task.done():
            self._auto_sync_task.cancel()

        async def _auto_sync_loop():
            while True:
                await asyncio.sleep(interval_seconds)
                try:
                    logger.info(
                        "Auto-sync running for %s (download_new=%s)",
                        source, download_new,
                    )
                    await self.run_sync(source, download_new=download_new)
                except Exception:
                    logger.exception("Auto-sync failed for %s", source)

        self._auto_sync_task = asyncio.create_task(_auto_sync_loop())

    def stop_auto_sync(self):
        if self._auto_sync_task and not self._auto_sync_task.done():
            self._auto_sync_task.cancel()
            self._auto_sync_task = None
