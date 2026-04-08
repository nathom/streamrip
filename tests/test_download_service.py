"""Tests for DownloadService.

Test Plan: DownloadService

Scenario: Enqueue albums adds items to queue with pending status
  Given a database with a known album
  When enqueue is called with that album's source ID
  Then the returned item has the correct source_album_id and status "pending"

Scenario: Get queue returns all enqueued items
  Given a database with two albums
  When both are enqueued
  Then get_queue returns a list of length 2

Scenario: Cancel marks a pending item as cancelled
  Given a service with one pending item in the queue
  When cancel is called with that item's ID
  Then the item's status is "cancelled"
"""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock
from backend.models.database import AppDatabase
from backend.services.download import DownloadService
from backend.services.event_bus import EventBus


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = AppDatabase(path)
    yield database
    os.unlink(path)


@pytest.fixture
def event_bus():
    return EventBus()


class TestDownloadServiceQueue:
    async def test_enqueue_adds_items(self, db, event_bus):
        db.upsert_album("qobuz", "a1", "Album A", "Artist A")
        service = DownloadService(db, event_bus, clients={}, download_path="/tmp")
        items = await service.enqueue("qobuz", ["a1"])
        assert len(items) == 1
        assert items[0]["source_album_id"] == "a1"
        assert items[0]["status"] == "pending"

    async def test_get_queue(self, db, event_bus):
        db.upsert_album("qobuz", "a1", "Album A", "Artist A")
        db.upsert_album("qobuz", "a2", "Album B", "Artist B")
        service = DownloadService(db, event_bus, clients={}, download_path="/tmp")
        await service.enqueue("qobuz", ["a1", "a2"])
        queue = service.get_queue()
        assert len(queue) == 2

    async def test_cancel_removes_from_queue(self, db, event_bus):
        db.upsert_album("qobuz", "a1", "Album A", "Artist A")
        service = DownloadService(db, event_bus, clients={}, download_path="/tmp")
        items = await service.enqueue("qobuz", ["a1"])
        item_id = items[0]["id"]
        await service.cancel([item_id])
        queue = service.get_queue()
        cancelled = [q for q in queue if q["id"] == item_id]
        assert cancelled[0]["status"] == "cancelled"


class TestDownloadQueue:
    async def test_cancel_all(self, db, event_bus):
        db.upsert_album("qobuz", "a1", "Album A", "Artist A")
        db.upsert_album("qobuz", "a2", "Album B", "Artist B")
        service = DownloadService(db, event_bus, clients={}, download_path="/tmp")
        await service.enqueue("qobuz", ["a1", "a2"])
        await service.cancel_all()
        queue = service.get_queue()
        assert all(q["status"] == "cancelled" for q in queue)

    async def test_enqueue_skips_unknown_album(self, db, event_bus):
        service = DownloadService(db, event_bus, clients={}, download_path="/tmp")
        items = await service.enqueue("qobuz", ["nonexistent"])
        assert len(items) == 0

    async def test_force_flag_preserved(self, db, event_bus):
        db.upsert_album("qobuz", "a1", "Album", "Artist")
        service = DownloadService(db, event_bus, clients={}, download_path="/tmp")
        items = await service.enqueue("qobuz", ["a1"], force=True)
        assert items[0]["force"] is True


class TestDownloadAlbumIntegration:
    async def test_download_album_raises_without_client(self, db, event_bus):
        """_download_album should raise ValueError when no client for source."""
        service = DownloadService(db, event_bus, clients={}, download_path="/tmp")
        item = {
            "id": "test-id",
            "album_db_id": 1,
            "source": "qobuz",
            "source_album_id": "123",
            "title": "Test",
            "artist": "Test Artist",
            "track_count": 10,
            "status": "downloading",
        }
        with pytest.raises(ValueError, match="No client for source"):
            await service._download_album(item)
