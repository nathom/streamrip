"""Tests for SyncService."""
import os
import tempfile
import pytest
from unittest.mock import AsyncMock
from backend.models.database import AppDatabase
from backend.services.sync import SyncService
from backend.services.event_bus import EventBus
from backend.services.library import LibraryService


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


class TestSyncService:
    async def test_get_diff_no_client(self, db, event_bus):
        library_service = LibraryService(db, event_bus, clients={})
        service = SyncService(db, event_bus, clients={}, library_service=library_service)
        diff = await service.get_diff("qobuz")
        assert diff["new_albums"] == []
        assert diff["removed_albums"] == []

    async def test_run_sync_records_history(self, db, event_bus):
        mock_client = AsyncMock(spec=[])  # No SDK attributes
        mock_client.source = "qobuz"
        mock_client.logged_in = True
        mock_client.get_user_favorites = AsyncMock(return_value=[])

        clients = {"qobuz": mock_client}
        library_service = LibraryService(db, event_bus, clients=clients)
        service = SyncService(db, event_bus, clients=clients, library_service=library_service)

        result = await service.run_sync("qobuz")
        assert result["status"] == "complete"

        history = await service.get_history("qobuz")
        assert len(history) == 1
        assert history[0]["status"] == "complete"
