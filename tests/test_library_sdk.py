"""Tests for LibraryService with SDK client integration."""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass, field

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


# Mock SDK types
@dataclass
class MockImageSet:
    large: str | None = "https://img.com/large.jpg"
    small: str | None = "https://img.com/small.jpg"
    thumbnail: str | None = "https://img.com/thumb.jpg"


@dataclass
class MockArtist:
    id: int = 1
    name: str = "Test Artist"


@dataclass
class MockArtistRole:
    id: int = 1
    name: str = "Test Artist"
    roles: list[str] = field(default_factory=list)


@dataclass
class MockLabel:
    id: int = 1
    name: str = "Test Label"


@dataclass
class MockGenre:
    id: int = 1
    name: str = "Rock"


@dataclass
class MockAlbum:
    id: str = "album-123"
    title: str = "Test Album"
    artist: MockArtist = field(default_factory=MockArtist)
    artists: list[MockArtistRole] = field(default_factory=lambda: [MockArtistRole()])
    image: MockImageSet = field(default_factory=MockImageSet)
    duration: int = 3600
    tracks_count: int = 10
    maximum_bit_depth: int = 24
    maximum_sampling_rate: float = 96.0
    maximum_channel_count: int = 2
    streamable: bool = True
    downloadable: bool = True
    hires: bool = True
    hires_streamable: bool = True
    release_date_original: str | None = "2024-01-15"
    label: MockLabel | None = field(default_factory=MockLabel)
    genre: MockGenre | None = field(default_factory=MockGenre)
    version: str | None = None
    upc: str | None = None
    description: str | None = None
    awards: list = field(default_factory=list)


@dataclass
class MockTrack:
    id: int = 1
    title: str = "Test Track"
    performer: MockArtist = field(default_factory=MockArtist)
    track_number: int = 1
    disc_number: int = 1
    duration: int = 240
    explicit: bool = False
    isrc: str | None = "USRC12345"
    version: str | None = None
    album: object = None
    audio_info: object = None
    rights: object = None


@dataclass
class MockFavoriteAlbums:
    items: list[MockAlbum] = field(default_factory=list)
    total: int = 0
    limit: int = 500
    offset: int = 0


@dataclass
class MockPaginatedResult:
    items: list[dict] = field(default_factory=list)
    total: int | None = 0
    limit: int = 50
    offset: int = 0
    has_more: bool = False


def make_sdk_client(albums=None, search_results=None, tracks=None):
    """Create a mock SDK client with favorites, catalog, etc."""
    client = MagicMock()

    # favorites
    client.favorites = MagicMock()
    fav_albums = MockFavoriteAlbums(
        items=albums or [],
        total=len(albums) if albums else 0,
    )
    client.favorites.get_albums = AsyncMock(return_value=fav_albums)

    # catalog
    client.catalog = MagicMock()
    search_result = MockPaginatedResult(
        items=search_results or [],
        total=len(search_results) if search_results else 0,
    )
    client.catalog.search_albums = AsyncMock(return_value=search_result)

    if tracks is not None:
        album_obj = albums[0] if albums else MockAlbum()
        client.catalog.get_album_with_tracks = AsyncMock(
            return_value=(album_obj, tracks)
        )

    return client


class TestLibrarySDKRefresh:
    async def test_refresh_with_sdk_client(self, db, event_bus):
        """Should sync favorites using SDK client.favorites.get_albums()."""
        albums = [
            MockAlbum(id="a1", title="Album One"),
            MockAlbum(id="a2", title="Album Two"),
        ]
        client = make_sdk_client(albums=albums)
        service = LibraryService(db, event_bus, clients={"qobuz": client})

        result = await service.refresh_library("qobuz")

        assert result["total"] == 2
        assert result["new"] == 2
        client.favorites.get_albums.assert_called_once()

        # Verify albums in DB
        db_albums = db.get_albums("qobuz")
        assert len(db_albums) == 2

    async def test_refresh_pagination(self, db, event_bus):
        """Should paginate through all favorites."""
        page1 = MockFavoriteAlbums(
            items=[MockAlbum(id="a1", title="A1")],
            total=2, limit=1, offset=0,
        )
        page2 = MockFavoriteAlbums(
            items=[MockAlbum(id="a2", title="A2")],
            total=2, limit=1, offset=1,
        )

        client = MagicMock()
        client.favorites = MagicMock()
        client.favorites.get_albums = AsyncMock(side_effect=[page1, page2])
        client.catalog = MagicMock()

        service = LibraryService(db, event_bus, clients={"qobuz": client})
        result = await service.refresh_library("qobuz")

        assert result["total"] == 2
        assert client.favorites.get_albums.call_count == 2


class TestLibrarySDKSearch:
    async def test_search_with_sdk_client(self, db, event_bus):
        """Should search using SDK client.catalog.search_albums()."""
        search_items = [
            {"id": "s1", "title": "Found Album", "artist": {"name": "Artist"},
             "release_date_original": "2024-01-01", "duration": 3600,
             "tracks_count": 10, "label": {"name": "L"}, "genre": {"name": "R"},
             "maximum_bit_depth": 24, "maximum_sampling_rate": 96.0,
             "image": {"large": "https://img.com/c.jpg"}},
        ]
        client = make_sdk_client(search_results=search_items)
        service = LibraryService(db, event_bus, clients={"qobuz": client})

        results = await service.search("qobuz", "test query")

        assert len(results) == 1
        assert results[0]["source_album_id"] == "s1"
        assert results[0]["in_library"] is False

    async def test_search_enriches_with_library_status(self, db, event_bus):
        """Search results should show in_library=True for known albums."""
        db.upsert_album("qobuz", "existing", "Known", "Artist")

        search_items = [
            {"id": "existing", "title": "Known", "artist": {"name": "Artist"},
             "release_date_original": "2024-01-01", "duration": 3600,
             "tracks_count": 10, "image": {"large": ""},
             "maximum_bit_depth": 16, "maximum_sampling_rate": 44.1},
            {"id": "new", "title": "New", "artist": {"name": "Other"},
             "release_date_original": "2024-06-01", "duration": 2400,
             "tracks_count": 8, "image": {"large": ""},
             "maximum_bit_depth": 16, "maximum_sampling_rate": 44.1},
        ]
        client = make_sdk_client(search_results=search_items)
        service = LibraryService(db, event_bus, clients={"qobuz": client})

        results = await service.search("qobuz", "test")

        known = next(r for r in results if r["source_album_id"] == "existing")
        new = next(r for r in results if r["source_album_id"] == "new")
        assert known["in_library"] is True
        assert new["in_library"] is False


class TestLibrarySDKTracks:
    async def test_fetch_tracks_from_sdk(self, db, event_bus):
        """Should fetch tracks via SDK when album detail is opened."""
        album_id = db.upsert_album("qobuz", "a1", "Album", "Artist")

        tracks = [
            MockTrack(id=101, title="Track 1", track_number=1),
            MockTrack(id=102, title="Track 2", track_number=2),
        ]
        client = make_sdk_client(
            albums=[MockAlbum(id="a1")],
            tracks=tracks,
        )
        service = LibraryService(db, event_bus, clients={"qobuz": client})

        result = await service.get_album_detail(album_id)

        assert result is not None
        assert len(result["tracks"]) == 2
        assert result["tracks"][0]["title"] == "Track 1"
        assert result["tracks"][1]["title"] == "Track 2"
