"""Tests for LibraryService."""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.models.database import AppDatabase
from backend.services.library import LibraryService
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


class TestLibraryServiceGetAlbums:
    async def test_get_albums_returns_paginated(self, db, event_bus):
        db.upsert_album("qobuz", "a1", "Album A", "Artist A")
        db.upsert_album("qobuz", "a2", "Album B", "Artist B")
        service = LibraryService(db, event_bus, clients={})
        result = await service.get_albums("qobuz", page=1, page_size=10)
        assert result["total"] == 2
        assert len(result["albums"]) == 2

    async def test_get_albums_with_search(self, db, event_bus):
        db.upsert_album("qobuz", "a1", "In Rainbows", "Radiohead")
        db.upsert_album("qobuz", "a2", "Blue Train", "John Coltrane")
        service = LibraryService(db, event_bus, clients={})
        result = await service.get_albums("qobuz", page=1, page_size=10, search="Radiohead")
        assert result["total"] == 1
        assert result["albums"][0]["title"] == "In Rainbows"


class TestLibraryServiceSearch:
    async def test_search_enriches_with_library_status(self, db, event_bus):
        db.upsert_album("qobuz", "existing_id", "Known Album", "Artist")
        mock_client = AsyncMock()
        mock_client.source = "qobuz"
        mock_client.logged_in = True
        mock_client.search = AsyncMock(return_value=[{
            "albums": {"items": [
                {"id": "existing_id", "title": "Known Album", "artist": {"name": "Artist"},
                 "release_date_original": "2024-01-01", "duration": 3600, "tracks_count": 10,
                 "label": {"name": "Label"}, "genre": {"name": "Rock"},
                 "maximum_bit_depth": 24, "maximum_sampling_rate": 96.0,
                 "image": {"large": "https://img.com/cover.jpg"}},
                {"id": "new_id", "title": "Unknown Album", "artist": {"name": "Other"},
                 "release_date_original": "2024-06-01", "duration": 2400, "tracks_count": 8,
                 "label": {"name": "Label2"}, "genre": {"name": "Jazz"},
                 "maximum_bit_depth": 16, "maximum_sampling_rate": 44.1,
                 "image": {"large": "https://img.com/cover2.jpg"}},
            ]}
        }])
        service = LibraryService(db, event_bus, clients={"qobuz": mock_client})
        results = await service.search("qobuz", "test query")
        assert len(results) == 2
        known = next(r for r in results if r["source_album_id"] == "existing_id")
        unknown = next(r for r in results if r["source_album_id"] == "new_id")
        assert known["in_library"] is True
        assert unknown["in_library"] is False


class TestExtractItemsFromPages:
    def test_qobuz_paginated_response(self):
        """Should extract album items from Qobuz paginated {albums: {items: [...]}} format."""
        service = LibraryService(None, EventBus(), clients={})
        pages = [
            {"albums": {"items": [
                {"id": "a1", "title": "Album 1", "artist": {"name": "A"}},
                {"id": "a2", "title": "Album 2", "artist": {"name": "B"}},
            ], "total": 4}},
            {"albums": {"items": [
                {"id": "a3", "title": "Album 3", "artist": {"name": "C"}},
                {"id": "a4", "title": "Album 4", "artist": {"name": "D"}},
            ], "total": 4}},
        ]
        result = service._extract_items_from_pages("qobuz", pages)
        assert len(result) == 4
        assert result[0]["id"] == "a1"
        assert result[3]["id"] == "a4"

    def test_tidal_flat_list(self):
        """Should pass through flat list of items (Tidal format)."""
        service = LibraryService(None, EventBus(), clients={})
        items = [
            {"id": 1, "title": "Album 1"},
            {"id": 2, "title": "Album 2"},
        ]
        result = service._extract_items_from_pages("tidal", items)
        assert len(result) == 2

    def test_empty_pages(self):
        """Should return empty list for empty input."""
        service = LibraryService(None, EventBus(), clients={})
        assert service._extract_items_from_pages("qobuz", []) == []
        assert service._extract_items_from_pages("qobuz", None) == []
