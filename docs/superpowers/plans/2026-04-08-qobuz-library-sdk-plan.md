# Qobuz Library SDK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python async client for the Qobuz API covering favorites, playlists, catalog, discovery, and streaming — validated from real API captures.

**Architecture:** Namespace-based client (`client.favorites`, `client.playlists`, etc.) built on a shared HTTP transport with rate limiting. Each namespace is an independent module with its own tests. Response models are typed dataclasses parsed from raw JSON via `from_dict()` class methods.

**Tech Stack:** Python 3.10+, aiohttp, aiolimiter, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-08-qobuz-library-sdk-design.md`

---

## File Map

```
qobuz-api/
├── clients/python/
│   ├── pyproject.toml
│   ├── qobuz/
│   │   ├── __init__.py         # Public API exports
│   │   ├── errors.py           # Exception hierarchy
│   │   ├── types.py            # All dataclass models + from_dict parsers
│   │   ├── _http.py            # HTTP transport: _get, _post, headers, rate limiter
│   │   ├── favorites.py        # FavoritesAPI: add, remove, list, get_ids
│   │   ├── playlists.py        # PlaylistsAPI: create, update, delete, add_tracks, get, list
│   │   ├── catalog.py          # CatalogAPI: album/artist/track get, search, batch, suggest
│   │   ├── discovery.py        # DiscoveryAPI: index, new_releases, playlists, genres
│   │   ├── streaming.py        # StreamingAPI: file_url (signed), session, reports
│   │   └── client.py           # QobuzClient: facade tying all namespaces together
│   └── tests/
│       ├── conftest.py         # Shared fixtures: mock transport, sample responses
│       ├── test_errors.py
│       ├── test_types.py
│       ├── test_http.py
│       ├── test_favorites.py
│       ├── test_playlists.py
│       ├── test_catalog.py
│       ├── test_discovery.py
│       ├── test_streaming.py
│       └── test_client.py
└── README.md
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `qobuz-api/clients/python/pyproject.toml`
- Create: `qobuz-api/clients/python/qobuz/__init__.py`
- Create: `qobuz-api/clients/python/tests/conftest.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p qobuz-api/clients/python/qobuz
mkdir -p qobuz-api/clients/python/tests
```

- [ ] **Step 2: Write pyproject.toml**

```toml
# qobuz-api/clients/python/pyproject.toml
[project]
name = "qobuz"
version = "0.1.0"
description = "Async Python client for the Qobuz API"
requires-python = ">=3.10"
dependencies = [
    "aiohttp>=3.9",
    "aiolimiter>=1.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "aioresponses>=0.7",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Write empty __init__.py**

```python
# qobuz-api/clients/python/qobuz/__init__.py
"""Async Python client for the Qobuz API."""
```

- [ ] **Step 4: Write conftest.py with shared fixtures**

```python
# qobuz-api/clients/python/tests/conftest.py
"""Shared test fixtures for Qobuz client tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_transport():
    """Mock HTTP transport that returns configurable responses."""
    transport = AsyncMock()
    transport.app_id = "304027809"
    transport.user_auth_token = "test-token"
    return transport


# --- Sample API responses (from Proxyman captures) ---

SAMPLE_ALBUM = {
    "id": "p0d55tt7gv3lc",
    "title": "Virgin Lake",
    "version": None,
    "maximum_bit_depth": 24,
    "maximum_sampling_rate": 44.1,
    "maximum_channel_count": 2,
    "duration": 3487,
    "tracks_count": 14,
    "parental_warning": True,
    "release_date_original": "2026-04-03",
    "upc": "0067003183055",
    "streamable": True,
    "downloadable": True,
    "hires": True,
    "hires_streamable": True,
    "image": {
        "small": "https://static.qobuz.com/images/covers/lc/v3/p0d55tt7gv3lc_230.jpg",
        "thumbnail": "https://static.qobuz.com/images/covers/lc/v3/p0d55tt7gv3lc_50.jpg",
        "large": "https://static.qobuz.com/images/covers/lc/v3/p0d55tt7gv3lc_600.jpg",
    },
    "artist": {"id": 11162390, "name": "Philine Sonny", "albums_count": 25},
    "artists": [{"id": 11162390, "name": "Philine Sonny", "roles": ["main-artist"]}],
    "label": {"id": 2367808, "name": "Nettwerk Music Group"},
    "genre": {"id": 113, "name": "Alternativ und Indie", "path": [112, 113]},
    "description": "Album description text",
    "awards": [],
}

SAMPLE_TRACK = {
    "id": 33967376,
    "title": "Blitzkrieg Bop",
    "version": "40th Anniversary",
    "isrc": "USWA10100001",
    "duration": 133,
    "parental_warning": False,
    "performer": {"id": 47434, "name": "Ramones"},
    "album": {
        "id": "0603497873012",
        "title": "Ramones - 40th Anniversary",
        "image": {"small": "https://example.com/230.jpg", "thumbnail": "https://example.com/50.jpg", "large": "https://example.com/600.jpg"},
    },
    "audio_info": {"maximum_bit_depth": 24, "maximum_channel_count": 2, "maximum_sampling_rate": 96},
    "physical_support": {"media_number": 1, "track_number": 1},
    "rights": {"streamable": True, "downloadable": True, "hires_streamable": True, "purchasable": True, "previewable": True, "sampleable": True},
}

SAMPLE_PLAYLIST = {
    "id": 61997651,
    "name": "New Private Playlist",
    "description": "This is the name",
    "tracks_count": 0,
    "users_count": 0,
    "duration": 0,
    "public_at": False,
    "created_at": 1775635602,
    "updated_at": 1775635602,
    "is_public": False,
    "is_collaborative": False,
    "owner": {"id": 2113276, "name": "arthursoares"},
}

SAMPLE_GENRE = {"id": 112, "color": "#5eabc1", "name": "Pop/Rock", "path": [112], "slug": "pop-rock"}

SAMPLE_ARTIST_SUMMARY = {"id": 38895, "name": "Talk Talk"}

SAMPLE_FAVORITE_IDS = {
    "albums": ["0724386649553", "xetru34w7hkdv"],
    "tracks": [77158728, 12345678],
    "artists": [38895, 2414834],
    "labels": [7812847],
    "awards": [215],
    "articles": [],
}

SAMPLE_LAST_UPDATE = {
    "last_update": {
        "favorite": 1775473221,
        "favorite_album": 1775473221,
        "favorite_artist": 1657790773,
        "favorite_track": 1773822437,
        "favorite_label": 1756417638,
        "favorite_award": 1775208126,
        "playlist": 1775208266,
        "purchase": 1663572155,
    }
}
```

- [ ] **Step 5: Install dev dependencies and verify**

```bash
cd qobuz-api/clients/python && pip install -e ".[dev]"
pytest --co -q  # Should show "no tests ran"
```

- [ ] **Step 6: Commit**

```bash
git add qobuz-api/
git commit -m "feat(qobuz-sdk): scaffold Python client project"
```

---

### Task 2: Error Hierarchy

**Files:**
- Create: `qobuz-api/clients/python/qobuz/errors.py`
- Create: `qobuz-api/clients/python/tests/test_errors.py`

- [ ] **Step 1: Write failing test**

```python
# qobuz-api/clients/python/tests/test_errors.py
from qobuz.errors import (
    QobuzError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    InvalidAppError,
    NonStreamableError,
)


def test_qobuz_error_has_status_and_message():
    err = QobuzError(status=401, message="Unauthorized")
    assert err.status == 401
    assert err.message == "Unauthorized"
    assert "401" in str(err)


def test_authentication_error_is_qobuz_error():
    err = AuthenticationError(status=401, message="Bad token")
    assert isinstance(err, QobuzError)
    assert err.status == 401


def test_raise_for_status_maps_codes():
    from qobuz.errors import raise_for_status

    import pytest

    with pytest.raises(AuthenticationError):
        raise_for_status(401, {"status": "error", "code": 401, "message": "Auth required"})

    with pytest.raises(ForbiddenError):
        raise_for_status(403, {"status": "error", "code": 403, "message": "Forbidden"})

    with pytest.raises(NotFoundError):
        raise_for_status(404, {"status": "error", "code": 404, "message": "Not found"})

    with pytest.raises(RateLimitError):
        raise_for_status(429, {"status": "error", "code": 429, "message": "Too many"})

    with pytest.raises(InvalidAppError):
        raise_for_status(400, {"status": "error", "code": 400, "message": "Bad app"})

    # 200 should not raise
    raise_for_status(200, {"status": "success"})
    raise_for_status(201, {"status": "success"})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qobuz-api/clients/python && pytest tests/test_errors.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'qobuz.errors'`

- [ ] **Step 3: Implement errors.py**

```python
# qobuz-api/clients/python/qobuz/errors.py
"""Qobuz API error hierarchy."""

from __future__ import annotations


class QobuzError(Exception):
    """Base exception for all Qobuz API errors."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"[{status}] {message}")


class AuthenticationError(QobuzError):
    """401 — Invalid or expired token."""


class ForbiddenError(QobuzError):
    """403 — Insufficient permissions (e.g., free account)."""


class NotFoundError(QobuzError):
    """404 — Resource not found."""


class RateLimitError(QobuzError):
    """429 — Too many requests."""


class InvalidAppError(QobuzError):
    """400 — Invalid app_id or bad request."""


class NonStreamableError(QobuzError):
    """Track has streaming restrictions."""


_STATUS_MAP: dict[int, type[QobuzError]] = {
    400: InvalidAppError,
    401: AuthenticationError,
    403: ForbiddenError,
    404: NotFoundError,
    429: RateLimitError,
}


def raise_for_status(status: int, body: dict) -> None:
    """Raise the appropriate QobuzError if status indicates failure."""
    if status < 400:
        return
    exc_cls = _STATUS_MAP.get(status, QobuzError)
    message = body.get("message", f"HTTP {status}")
    raise exc_cls(status=status, message=message)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd qobuz-api/clients/python && pytest tests/test_errors.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add qobuz-api/clients/python/qobuz/errors.py qobuz-api/clients/python/tests/test_errors.py
git commit -m "feat(qobuz-sdk): add error hierarchy with raise_for_status"
```

---

### Task 3: Response Types (Dataclass Models)

**Files:**
- Create: `qobuz-api/clients/python/qobuz/types.py`
- Create: `qobuz-api/clients/python/tests/test_types.py`

- [ ] **Step 1: Write failing test for model parsing**

```python
# qobuz-api/clients/python/tests/test_types.py
from conftest import SAMPLE_ALBUM, SAMPLE_TRACK, SAMPLE_PLAYLIST, SAMPLE_GENRE, SAMPLE_FAVORITE_IDS
from qobuz.types import Album, Track, Playlist, Genre, FavoriteIds, ImageSet, ArtistSummary, Label


class TestAlbumParsing:
    def test_from_dict_parses_capture_data(self):
        album = Album.from_dict(SAMPLE_ALBUM)
        assert album.id == "p0d55tt7gv3lc"
        assert album.title == "Virgin Lake"
        assert album.maximum_bit_depth == 24
        assert album.maximum_sampling_rate == 44.1
        assert album.tracks_count == 14
        assert album.streamable is True
        assert album.hires is True
        assert album.image.large.endswith("600.jpg")
        assert album.artist.name == "Philine Sonny"
        assert album.label.name == "Nettwerk Music Group"
        assert album.genre.id == 113

    def test_version_can_be_none(self):
        album = Album.from_dict(SAMPLE_ALBUM)
        assert album.version is None


class TestTrackParsing:
    def test_from_dict_parses_capture_data(self):
        track = Track.from_dict(SAMPLE_TRACK)
        assert track.id == 33967376
        assert track.title == "Blitzkrieg Bop"
        assert track.duration == 133
        assert track.track_number == 1
        assert track.disc_number == 1
        assert track.performer.name == "Ramones"
        assert track.audio_info.maximum_bit_depth == 24


class TestPlaylistParsing:
    def test_from_dict_parses_capture_data(self):
        pl = Playlist.from_dict(SAMPLE_PLAYLIST)
        assert pl.id == 61997651
        assert pl.name == "New Private Playlist"
        assert pl.is_public is False
        assert pl.owner.name == "arthursoares"
        assert pl.tracks_count == 0


class TestGenreParsing:
    def test_from_dict_parses_capture_data(self):
        genre = Genre.from_dict(SAMPLE_GENRE)
        assert genre.id == 112
        assert genre.name == "Pop/Rock"
        assert genre.slug == "pop-rock"
        assert genre.path == [112]


class TestFavoriteIds:
    def test_from_dict_parses_capture_data(self):
        fav = FavoriteIds.from_dict(SAMPLE_FAVORITE_IDS)
        assert len(fav.albums) == 2
        assert len(fav.tracks) == 2
        assert len(fav.artists) == 2
        assert "xetru34w7hkdv" in fav.albums
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd qobuz-api/clients/python && pytest tests/test_types.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'qobuz.types'`

- [ ] **Step 3: Implement types.py**

```python
# qobuz-api/clients/python/qobuz/types.py
"""Typed response models for the Qobuz API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImageSet:
    small: str | None = None
    thumbnail: str | None = None
    large: str | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> ImageSet:
        if not d:
            return cls()
        return cls(small=d.get("small"), thumbnail=d.get("thumbnail"), large=d.get("large"))


@dataclass
class ArtistSummary:
    id: int
    name: str

    @classmethod
    def from_dict(cls, d: dict) -> ArtistSummary:
        name = d.get("name", "Unknown")
        # artist/page uses {"name": {"display": "..."}}
        if isinstance(name, dict):
            name = name.get("display", "Unknown")
        return cls(id=d["id"], name=name)


@dataclass
class ArtistRole:
    id: int
    name: str
    roles: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> ArtistRole:
        return cls(id=d["id"], name=d.get("name", "Unknown"), roles=d.get("roles", []))


@dataclass
class Label:
    id: int
    name: str

    @classmethod
    def from_dict(cls, d: dict | None) -> Label | None:
        if not d:
            return None
        return cls(id=d["id"], name=d.get("name", "Unknown"))


@dataclass
class Genre:
    id: int
    name: str
    color: str = ""
    path: list[int] = field(default_factory=list)
    slug: str = ""

    @classmethod
    def from_dict(cls, d: dict | None) -> Genre | None:
        if not d:
            return None
        return cls(
            id=d["id"], name=d.get("name", ""), color=d.get("color", ""),
            path=d.get("path", []), slug=d.get("slug", ""),
        )


@dataclass
class AudioInfo:
    maximum_bit_depth: int = 16
    maximum_channel_count: int = 2
    maximum_sampling_rate: float = 44.1

    @classmethod
    def from_dict(cls, d: dict | None) -> AudioInfo:
        if not d:
            return cls()
        return cls(
            maximum_bit_depth=d.get("maximum_bit_depth", 16),
            maximum_channel_count=d.get("maximum_channel_count", 2),
            maximum_sampling_rate=d.get("maximum_sampling_rate", 44.1),
        )


@dataclass
class Rights:
    streamable: bool = False
    downloadable: bool = False
    hires_streamable: bool = False
    purchasable: bool = False

    @classmethod
    def from_dict(cls, d: dict | None) -> Rights:
        if not d:
            return cls()
        return cls(
            streamable=d.get("streamable", False),
            downloadable=d.get("downloadable", False),
            hires_streamable=d.get("hires_streamable", False),
            purchasable=d.get("purchasable", False),
        )


@dataclass
class AlbumSummary:
    id: str
    title: str
    image: ImageSet = field(default_factory=ImageSet)

    @classmethod
    def from_dict(cls, d: dict) -> AlbumSummary:
        return cls(id=str(d["id"]), title=d.get("title", ""), image=ImageSet.from_dict(d.get("image")))


@dataclass
class UserSummary:
    id: int
    name: str

    @classmethod
    def from_dict(cls, d: dict) -> UserSummary:
        return cls(id=d["id"], name=d.get("name", d.get("display_name", "")))


@dataclass
class Award:
    id: int
    name: str
    awarded_at: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Award:
        return cls(id=d["id"], name=d.get("name", ""), awarded_at=d.get("awarded_at"))


@dataclass
class Album:
    id: str
    title: str
    version: str | None
    artist: ArtistSummary
    artists: list[ArtistRole]
    image: ImageSet
    duration: int
    tracks_count: int
    maximum_bit_depth: int
    maximum_sampling_rate: float
    maximum_channel_count: int
    streamable: bool
    downloadable: bool
    hires: bool
    hires_streamable: bool
    release_date_original: str | None = None
    upc: str | None = None
    label: Label | None = None
    genre: Genre | None = None
    description: str | None = None
    awards: list[Award] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Album:
        return cls(
            id=str(d["id"]),
            title=d.get("title", ""),
            version=d.get("version"),
            artist=ArtistSummary.from_dict(d.get("artist", {"id": 0, "name": "Unknown"})),
            artists=[ArtistRole.from_dict(a) for a in d.get("artists", [])],
            image=ImageSet.from_dict(d.get("image")),
            duration=d.get("duration", 0),
            tracks_count=d.get("tracks_count", 0),
            maximum_bit_depth=d.get("maximum_bit_depth", 16),
            maximum_sampling_rate=d.get("maximum_sampling_rate", 44.1),
            maximum_channel_count=d.get("maximum_channel_count", 2),
            streamable=d.get("streamable", False),
            downloadable=d.get("downloadable", False),
            hires=d.get("hires", False),
            hires_streamable=d.get("hires_streamable", False),
            release_date_original=d.get("release_date_original"),
            upc=d.get("upc"),
            label=Label.from_dict(d.get("label")),
            genre=Genre.from_dict(d.get("genre")),
            description=d.get("description"),
            awards=[Award.from_dict(a) for a in d.get("awards", [])],
        )


@dataclass
class Track:
    id: int
    title: str
    version: str | None
    duration: int
    track_number: int
    disc_number: int
    explicit: bool
    performer: ArtistSummary
    album: AlbumSummary
    audio_info: AudioInfo
    rights: Rights
    isrc: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Track:
        phys = d.get("physical_support", {})
        return cls(
            id=d["id"],
            title=d.get("title", ""),
            version=d.get("version"),
            duration=d.get("duration", 0),
            track_number=phys.get("track_number", d.get("track_number", 0)),
            disc_number=phys.get("media_number", d.get("media_number", 1)),
            explicit=d.get("parental_warning", False),
            performer=ArtistSummary.from_dict(d.get("performer", {"id": 0, "name": "Unknown"})),
            album=AlbumSummary.from_dict(d.get("album", {"id": "", "title": ""})),
            audio_info=AudioInfo.from_dict(d.get("audio_info")),
            rights=Rights.from_dict(d.get("rights")),
            isrc=d.get("isrc"),
        )


@dataclass
class Playlist:
    id: int
    name: str
    description: str
    tracks_count: int
    users_count: int
    duration: int
    is_public: bool
    is_collaborative: bool
    public_at: int | bool
    created_at: int
    updated_at: int
    owner: UserSummary

    @classmethod
    def from_dict(cls, d: dict) -> Playlist:
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            description=d.get("description", ""),
            tracks_count=d.get("tracks_count", 0),
            users_count=d.get("users_count", 0),
            duration=d.get("duration", 0),
            is_public=d.get("is_public", False),
            is_collaborative=d.get("is_collaborative", False),
            public_at=d.get("public_at", False),
            created_at=d.get("created_at", 0),
            updated_at=d.get("updated_at", 0),
            owner=UserSummary.from_dict(d.get("owner", {"id": 0, "name": ""})),
        )


@dataclass
class FavoriteIds:
    albums: list[str] = field(default_factory=list)
    tracks: list[int] = field(default_factory=list)
    artists: list[int] = field(default_factory=list)
    labels: list[int] = field(default_factory=list)
    awards: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> FavoriteIds:
        return cls(
            albums=[str(a) for a in d.get("albums", [])],
            tracks=d.get("tracks", []),
            artists=d.get("artists", []),
            labels=d.get("labels", []),
            awards=d.get("awards", []),
        )


@dataclass
class LastUpdate:
    favorite: int = 0
    favorite_album: int = 0
    favorite_artist: int = 0
    favorite_track: int = 0
    favorite_label: int = 0
    playlist: int = 0
    purchase: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> LastUpdate:
        lu = d.get("last_update", d)
        return cls(
            favorite=lu.get("favorite", 0),
            favorite_album=lu.get("favorite_album", 0),
            favorite_artist=lu.get("favorite_artist", 0),
            favorite_track=lu.get("favorite_track", 0),
            favorite_label=lu.get("favorite_label", 0),
            playlist=lu.get("playlist", 0),
            purchase=lu.get("purchase", 0),
        )


@dataclass
class FileUrl:
    track_id: int
    format_id: int
    mime_type: str
    sampling_rate: int
    bits_depth: int
    duration: float
    url_template: str
    n_segments: int
    key_id: str | None = None
    key: str | None = None
    blob: str | None = None
    restrictions: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> FileUrl:
        return cls(
            track_id=d["track_id"],
            format_id=d["format_id"],
            mime_type=d.get("mime_type", ""),
            sampling_rate=d.get("sampling_rate", 0),
            bits_depth=d.get("bits_depth", 0),
            duration=d.get("duration", 0),
            url_template=d.get("url_template", ""),
            n_segments=d.get("n_segments", 0),
            key_id=d.get("key_id"),
            key=d.get("key"),
            blob=d.get("blob"),
            restrictions=d.get("restrictions", []),
        )


@dataclass
class Session:
    session_id: str
    profile: str
    expires_at: int

    @classmethod
    def from_dict(cls, d: dict) -> Session:
        return cls(session_id=d["session_id"], profile=d.get("profile", ""), expires_at=d.get("expires_at", 0))


@dataclass
class PaginatedResult:
    """Wraps a paginated API response."""
    items: list[dict]
    total: int | None  # None for has_more-style pagination
    limit: int
    offset: int
    has_more: bool

    @classmethod
    def from_dict(cls, d: dict, key: str | None = None) -> PaginatedResult:
        """Parse paginated response.

        Two styles:
        - {key: {items: [...], total, limit, offset}}  (most endpoints)
        - {has_more: bool, items: [...]}                (discovery, releases)
        """
        if key and key in d:
            container = d[key]
            return cls(
                items=container.get("items", []),
                total=container.get("total"),
                limit=container.get("limit", 500),
                offset=container.get("offset", 0),
                has_more=container.get("offset", 0) + container.get("limit", 500) < container.get("total", 0),
            )
        if "items" in d:
            return cls(
                items=d["items"],
                total=None,
                limit=len(d["items"]),
                offset=0,
                has_more=d.get("has_more", False),
            )
        return cls(items=[], total=0, limit=0, offset=0, has_more=False)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd qobuz-api/clients/python && pytest tests/test_types.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add qobuz-api/clients/python/qobuz/types.py qobuz-api/clients/python/tests/test_types.py
git commit -m "feat(qobuz-sdk): add typed response models with from_dict parsers"
```

---

### Task 4: HTTP Transport Layer

**Files:**
- Create: `qobuz-api/clients/python/qobuz/_http.py`
- Create: `qobuz-api/clients/python/tests/test_http.py`

- [ ] **Step 1: Write failing tests**

```python
# qobuz-api/clients/python/tests/test_http.py
import pytest
from aioresponses import aioresponses

from qobuz._http import HttpTransport
from qobuz.errors import AuthenticationError


class TestHttpTransport:
    async def test_get_sends_app_id_header(self):
        transport = HttpTransport(app_id="123", user_auth_token="tok")
        with aioresponses() as m:
            m.get("https://www.qobuz.com/api.json/0.2/test/endpoint", payload={"ok": True})
            async with transport:
                status, body = await transport.get("test/endpoint", {})
            assert status == 200
            assert body == {"ok": True}
            req = m.requests[("GET", "https://www.qobuz.com/api.json/0.2/test/endpoint")][0]
            assert req.kwargs["headers"]["X-App-Id"] == "123"
            assert req.kwargs["headers"]["X-User-Auth-Token"] == "tok"

    async def test_post_form_sends_correct_content_type(self):
        transport = HttpTransport(app_id="123", user_auth_token="tok")
        with aioresponses() as m:
            m.post("https://www.qobuz.com/api.json/0.2/favorite/create", payload={"status": "success"})
            async with transport:
                status, body = await transport.post_form("favorite/create", {"album_ids": "abc"})
            assert status == 200
            assert body["status"] == "success"

    async def test_post_json_sends_json_body(self):
        transport = HttpTransport(app_id="123", user_auth_token="tok")
        with aioresponses() as m:
            m.post("https://www.qobuz.com/api.json/0.2/track/getList", payload={"tracks": {"items": []}})
            async with transport:
                status, body = await transport.post_json("track/getList", {"tracks_id": [1, 2]})
            assert status == 200

    async def test_get_raises_on_401(self):
        transport = HttpTransport(app_id="123", user_auth_token="bad")
        with aioresponses() as m:
            m.get(
                "https://www.qobuz.com/api.json/0.2/user/login",
                status=401,
                payload={"status": "error", "code": 401, "message": "Auth required"},
            )
            async with transport:
                with pytest.raises(AuthenticationError):
                    await transport.get("user/login", {}, raise_errors=True)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd qobuz-api/clients/python && pytest tests/test_http.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'qobuz._http'`

- [ ] **Step 3: Implement _http.py**

```python
# qobuz-api/clients/python/qobuz/_http.py
"""HTTP transport layer for the Qobuz API."""

from __future__ import annotations

import contextlib
import logging

import aiohttp
import aiolimiter

from .errors import raise_for_status

logger = logging.getLogger("qobuz")

BASE_URL = "https://www.qobuz.com/api.json/0.2"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class HttpTransport:
    """Low-level HTTP transport with rate limiting and auth headers."""

    def __init__(
        self,
        app_id: str,
        user_auth_token: str | None = None,
        requests_per_minute: int = 30,
    ):
        self.app_id = app_id
        self.user_auth_token = user_auth_token
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter: aiolimiter.AsyncLimiter | contextlib.nullcontext = (
            aiolimiter.AsyncLimiter(requests_per_minute, 60)
            if requests_per_minute > 0
            else contextlib.nullcontext()
        )

    def _headers(self) -> dict[str, str]:
        h = {"User-Agent": USER_AGENT, "X-App-Id": self.app_id}
        if self.user_auth_token:
            h["X-User-Auth-Token"] = self.user_auth_token
        return h

    async def get(
        self, endpoint: str, params: dict, *, raise_errors: bool = True
    ) -> tuple[int, dict]:
        assert self._session is not None, "Transport not started — use 'async with'"
        url = f"{BASE_URL}/{endpoint}"
        logger.debug("GET %s params=%s", endpoint, params)
        async with self._rate_limiter:
            async with self._session.get(url, params=params, headers=self._headers()) as resp:
                body = await resp.json()
                if raise_errors:
                    raise_for_status(resp.status, body)
                return resp.status, body

    async def post_form(
        self, endpoint: str, data: dict, *, raise_errors: bool = True
    ) -> tuple[int, dict]:
        assert self._session is not None, "Transport not started — use 'async with'"
        url = f"{BASE_URL}/{endpoint}"
        logger.debug("POST (form) %s data=%s", endpoint, data)
        async with self._rate_limiter:
            async with self._session.post(url, data=data, headers=self._headers()) as resp:
                body = await resp.json()
                if raise_errors:
                    raise_for_status(resp.status, body)
                return resp.status, body

    async def post_json(
        self, endpoint: str, json_body: dict, *, raise_errors: bool = True
    ) -> tuple[int, dict]:
        assert self._session is not None, "Transport not started — use 'async with'"
        url = f"{BASE_URL}/{endpoint}"
        logger.debug("POST (json) %s", endpoint)
        async with self._rate_limiter:
            async with self._session.post(url, json=json_body, headers=self._headers()) as resp:
                body = await resp.json()
                if raise_errors:
                    raise_for_status(resp.status, body)
                return resp.status, body

    async def __aenter__(self) -> HttpTransport:
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._session:
            await self._session.close()
            self._session = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd qobuz-api/clients/python && pytest tests/test_http.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add qobuz-api/clients/python/qobuz/_http.py qobuz-api/clients/python/tests/test_http.py
git commit -m "feat(qobuz-sdk): add HTTP transport with rate limiting"
```

---

### Task 5: Favorites API

**Files:**
- Create: `qobuz-api/clients/python/qobuz/favorites.py`
- Create: `qobuz-api/clients/python/tests/test_favorites.py`

- [ ] **Step 1: Write failing tests**

```python
# qobuz-api/clients/python/tests/test_favorites.py
import pytest
from unittest.mock import AsyncMock

from conftest import SAMPLE_ALBUM, SAMPLE_FAVORITE_IDS
from qobuz.favorites import FavoritesAPI
from qobuz.types import Album, FavoriteIds


class TestFavoritesAdd:
    async def test_add_album_posts_form(self, mock_transport):
        mock_transport.post_form = AsyncMock(return_value=(200, {"status": "success"}))
        api = FavoritesAPI(mock_transport)
        await api.add_album("abc123")
        mock_transport.post_form.assert_called_once_with(
            "favorite/create", {"album_ids": "abc123", "artist_ids": "", "track_ids": ""}
        )

    async def test_add_tracks_joins_ids(self, mock_transport):
        mock_transport.post_form = AsyncMock(return_value=(200, {"status": "success"}))
        api = FavoritesAPI(mock_transport)
        await api.add_tracks(["1", "2", "3"])
        mock_transport.post_form.assert_called_once_with(
            "favorite/create", {"album_ids": "", "artist_ids": "", "track_ids": "1,2,3"}
        )


class TestFavoritesRemove:
    async def test_remove_artist(self, mock_transport):
        mock_transport.post_form = AsyncMock(return_value=(200, {"status": "success"}))
        api = FavoritesAPI(mock_transport)
        await api.remove_artist("99")
        mock_transport.post_form.assert_called_once_with(
            "favorite/delete", {"album_ids": "", "artist_ids": "99", "track_ids": ""}
        )


class TestFavoritesGet:
    async def test_get_albums_returns_parsed_albums(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"albums": {"items": [SAMPLE_ALBUM], "total": 1, "limit": 500, "offset": 0}}))
        api = FavoritesAPI(mock_transport)
        result = await api.get_albums(limit=500)
        assert len(result.items) == 1
        assert result.items[0].id == "p0d55tt7gv3lc"

    async def test_get_ids_returns_favorite_ids(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, SAMPLE_FAVORITE_IDS))
        api = FavoritesAPI(mock_transport)
        result = await api.get_ids()
        assert isinstance(result, FavoriteIds)
        assert len(result.albums) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd qobuz-api/clients/python && pytest tests/test_favorites.py -v
```

- [ ] **Step 3: Implement favorites.py**

```python
# qobuz-api/clients/python/qobuz/favorites.py
"""Favorites API — add, remove, list, and check favorite albums/tracks/artists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .types import Album, Track, ArtistSummary, FavoriteIds, PaginatedResult

if TYPE_CHECKING:
    from ._http import HttpTransport


@dataclass
class FavoriteAlbums:
    """Paginated list of favorite albums."""
    items: list[Album]
    total: int
    limit: int
    offset: int


class FavoritesAPI:
    """Operations on the user's Qobuz favorites."""

    def __init__(self, transport: HttpTransport):
        self._t = transport

    async def add_album(self, album_id: str) -> None:
        await self._t.post_form("favorite/create", {"album_ids": album_id, "artist_ids": "", "track_ids": ""})

    async def add_albums(self, album_ids: list[str]) -> None:
        await self._t.post_form("favorite/create", {"album_ids": ",".join(album_ids), "artist_ids": "", "track_ids": ""})

    async def add_track(self, track_id: str) -> None:
        await self._t.post_form("favorite/create", {"album_ids": "", "artist_ids": "", "track_ids": track_id})

    async def add_tracks(self, track_ids: list[str]) -> None:
        await self._t.post_form("favorite/create", {"album_ids": "", "artist_ids": "", "track_ids": ",".join(track_ids)})

    async def add_artist(self, artist_id: str) -> None:
        await self._t.post_form("favorite/create", {"album_ids": "", "artist_ids": artist_id, "track_ids": ""})

    async def remove_album(self, album_id: str) -> None:
        await self._t.post_form("favorite/delete", {"album_ids": album_id, "artist_ids": "", "track_ids": ""})

    async def remove_track(self, track_id: str) -> None:
        await self._t.post_form("favorite/delete", {"album_ids": "", "artist_ids": "", "track_ids": track_id})

    async def remove_artist(self, artist_id: str) -> None:
        await self._t.post_form("favorite/delete", {"album_ids": "", "artist_ids": artist_id, "track_ids": ""})

    async def get_albums(self, limit: int = 500, offset: int = 0) -> FavoriteAlbums:
        _, body = await self._t.get("favorite/getUserFavorites", {"type": "albums", "limit": limit, "offset": offset})
        container = body.get("albums", {})
        return FavoriteAlbums(
            items=[Album.from_dict(item) for item in container.get("items", [])],
            total=container.get("total", 0),
            limit=container.get("limit", limit),
            offset=container.get("offset", offset),
        )

    async def get_tracks(self, limit: int = 500, offset: int = 0) -> PaginatedResult:
        _, body = await self._t.get("favorite/getUserFavorites", {"type": "tracks", "limit": limit, "offset": offset})
        return PaginatedResult.from_dict(body, key="tracks")

    async def get_artists(self, limit: int = 100, offset: int = 0) -> PaginatedResult:
        _, body = await self._t.get("favorite/getUserFavorites", {"type": "artists", "limit": limit, "offset": offset})
        return PaginatedResult.from_dict(body, key="artists")

    async def get_ids(self, limit: int = 5000) -> FavoriteIds:
        _, body = await self._t.get("favorite/getUserFavoriteIds", {"limit": limit})
        return FavoriteIds.from_dict(body)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd qobuz-api/clients/python && pytest tests/test_favorites.py -v
```

- [ ] **Step 5: Commit**

```bash
git add qobuz-api/clients/python/qobuz/favorites.py qobuz-api/clients/python/tests/test_favorites.py
git commit -m "feat(qobuz-sdk): add favorites API (add/remove/list/get_ids)"
```

---

### Task 6: Playlists API

**Files:**
- Create: `qobuz-api/clients/python/qobuz/playlists.py`
- Create: `qobuz-api/clients/python/tests/test_playlists.py`

- [ ] **Step 1: Write failing tests**

```python
# qobuz-api/clients/python/tests/test_playlists.py
import pytest
from unittest.mock import AsyncMock

from conftest import SAMPLE_PLAYLIST
from qobuz.playlists import PlaylistsAPI
from qobuz.types import Playlist


class TestPlaylistCreate:
    async def test_create_posts_form(self, mock_transport):
        mock_transport.post_form = AsyncMock(return_value=(200, SAMPLE_PLAYLIST))
        api = PlaylistsAPI(mock_transport)
        result = await api.create("Test Playlist", description="desc", public=False, collaborative=False)
        assert isinstance(result, Playlist)
        assert result.name == "New Private Playlist"
        mock_transport.post_form.assert_called_once_with(
            "playlist/create",
            {"name": "Test Playlist", "description": "desc", "is_public": "false", "is_collaborative": "false"},
        )


class TestPlaylistUpdate:
    async def test_update_posts_form(self, mock_transport):
        updated = {**SAMPLE_PLAYLIST, "name": "Renamed", "is_public": True}
        mock_transport.post_form = AsyncMock(return_value=(200, updated))
        api = PlaylistsAPI(mock_transport)
        result = await api.update(61997651, name="Renamed", public=True)
        assert isinstance(result, Playlist)
        call_data = mock_transport.post_form.call_args[0][1]
        assert call_data["playlist_id"] == "61997651"
        assert call_data["name"] == "Renamed"
        assert call_data["is_public"] == "true"


class TestPlaylistDelete:
    async def test_delete_posts_form(self, mock_transport):
        mock_transport.post_form = AsyncMock(return_value=(200, {"status": "success"}))
        api = PlaylistsAPI(mock_transport)
        await api.delete(61997651)
        mock_transport.post_form.assert_called_once_with("playlist/delete", {"playlist_id": "61997651"})


class TestPlaylistAddTracks:
    async def test_add_tracks_single_batch(self, mock_transport):
        mock_transport.post_form = AsyncMock(return_value=(200, SAMPLE_PLAYLIST))
        api = PlaylistsAPI(mock_transport)
        await api.add_tracks(123, ["1", "2", "3"], no_duplicate=True)
        mock_transport.post_form.assert_called_once_with(
            "playlist/addTracks",
            {"playlist_id": "123", "track_ids": "1,2,3", "no_duplicate": "true"},
        )

    async def test_add_tracks_batches_over_50(self, mock_transport):
        mock_transport.post_form = AsyncMock(return_value=(200, SAMPLE_PLAYLIST))
        api = PlaylistsAPI(mock_transport)
        track_ids = [str(i) for i in range(75)]
        await api.add_tracks(123, track_ids)
        assert mock_transport.post_form.call_count == 2  # 50 + 25


class TestPlaylistGet:
    async def test_get_returns_playlist(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, SAMPLE_PLAYLIST))
        api = PlaylistsAPI(mock_transport)
        result = await api.get(61997651)
        assert isinstance(result, Playlist)
        assert result.id == 61997651


class TestPlaylistList:
    async def test_list_returns_playlists(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"playlists": {"items": [SAMPLE_PLAYLIST], "total": 1, "limit": 500, "offset": 0}}))
        api = PlaylistsAPI(mock_transport)
        result = await api.list()
        assert len(result.items) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd qobuz-api/clients/python && pytest tests/test_playlists.py -v
```

- [ ] **Step 3: Implement playlists.py**

```python
# qobuz-api/clients/python/qobuz/playlists.py
"""Playlists API — create, update, delete, manage tracks, list."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import Playlist, PaginatedResult

if TYPE_CHECKING:
    from ._http import HttpTransport

_BATCH_SIZE = 50


class PlaylistsAPI:
    """Operations on Qobuz playlists."""

    def __init__(self, transport: HttpTransport):
        self._t = transport

    async def create(
        self,
        name: str,
        description: str = "",
        public: bool = False,
        collaborative: bool = False,
    ) -> Playlist:
        _, body = await self._t.post_form("playlist/create", {
            "name": name,
            "description": description,
            "is_public": str(public).lower(),
            "is_collaborative": str(collaborative).lower(),
        })
        return Playlist.from_dict(body)

    async def update(
        self,
        playlist_id: int,
        name: str | None = None,
        description: str | None = None,
        public: bool | None = None,
        collaborative: bool | None = None,
    ) -> Playlist:
        data: dict[str, str] = {"playlist_id": str(playlist_id)}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if public is not None:
            data["is_public"] = str(public).lower()
        if collaborative is not None:
            data["is_collaborative"] = str(collaborative).lower()
        _, body = await self._t.post_form("playlist/update", data)
        return Playlist.from_dict(body)

    async def delete(self, playlist_id: int) -> None:
        await self._t.post_form("playlist/delete", {"playlist_id": str(playlist_id)})

    async def add_tracks(
        self,
        playlist_id: int,
        track_ids: list[str],
        no_duplicate: bool = False,
    ) -> None:
        for i in range(0, len(track_ids), _BATCH_SIZE):
            batch = track_ids[i : i + _BATCH_SIZE]
            data: dict[str, str] = {
                "playlist_id": str(playlist_id),
                "track_ids": ",".join(batch),
            }
            if no_duplicate:
                data["no_duplicate"] = "true"
            await self._t.post_form("playlist/addTracks", data)

    async def get(
        self, playlist_id: int, extra: str = "tracks", offset: int = 0, limit: int = 50
    ) -> Playlist:
        _, body = await self._t.get("playlist/get", {
            "playlist_id": str(playlist_id), "extra": extra, "offset": offset, "limit": limit,
        })
        return Playlist.from_dict(body)

    async def list(self, limit: int = 500, filter: str = "owner") -> PaginatedResult:
        _, body = await self._t.get("playlist/getUserPlaylists", {"limit": limit, "filter": filter})
        return PaginatedResult.from_dict(body, key="playlists")

    async def search(self, query: str, limit: int = 50, offset: int = 0) -> PaginatedResult:
        _, body = await self._t.get("playlist/search", {"query": query, "limit": limit, "offset": offset})
        return PaginatedResult.from_dict(body, key="playlists")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd qobuz-api/clients/python && pytest tests/test_playlists.py -v
```

- [ ] **Step 5: Commit**

```bash
git add qobuz-api/clients/python/qobuz/playlists.py qobuz-api/clients/python/tests/test_playlists.py
git commit -m "feat(qobuz-sdk): add playlists API (CRUD, add_tracks with batching)"
```

---

### Task 7: Catalog API

**Files:**
- Create: `qobuz-api/clients/python/qobuz/catalog.py`
- Create: `qobuz-api/clients/python/tests/test_catalog.py`

- [ ] **Step 1: Write failing tests**

```python
# qobuz-api/clients/python/tests/test_catalog.py
import pytest
from unittest.mock import AsyncMock

from conftest import SAMPLE_ALBUM, SAMPLE_TRACK
from qobuz.catalog import CatalogAPI
from qobuz.types import Album, Track


class TestCatalogAlbum:
    async def test_get_album(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, SAMPLE_ALBUM))
        api = CatalogAPI(mock_transport)
        album = await api.get_album("p0d55tt7gv3lc")
        assert isinstance(album, Album)
        assert album.title == "Virgin Lake"

    async def test_search_albums(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"albums": {"items": [SAMPLE_ALBUM], "total": 1, "limit": 50, "offset": 0}}))
        api = CatalogAPI(mock_transport)
        result = await api.search_albums("radiohead")
        assert len(result.items) == 1

    async def test_suggest_album(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"algorithm": "suggest-album", "albums": {"limit": 30, "items": [SAMPLE_ALBUM]}}))
        api = CatalogAPI(mock_transport)
        result = await api.suggest_album("abc")
        assert len(result) == 1
        assert result[0].title == "Virgin Lake"


class TestCatalogTrack:
    async def test_get_track(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, SAMPLE_TRACK))
        api = CatalogAPI(mock_transport)
        track = await api.get_track(33967376)
        assert isinstance(track, Track)
        assert track.title == "Blitzkrieg Bop"

    async def test_get_tracks_batch(self, mock_transport):
        mock_transport.post_json = AsyncMock(return_value=(200, {"tracks": {"total": 1, "items": [SAMPLE_TRACK]}}))
        api = CatalogAPI(mock_transport)
        tracks = await api.get_tracks([33967376])
        assert len(tracks) == 1
        mock_transport.post_json.assert_called_once_with("track/getList", {"tracks_id": [33967376]})


class TestCatalogArtist:
    async def test_search_artists(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"artists": {"items": [{"id": 1, "name": "Test"}], "total": 1, "limit": 50, "offset": 0}}))
        api = CatalogAPI(mock_transport)
        result = await api.search_artists("test")
        assert len(result.items) == 1

    async def test_get_artist_releases(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"has_more": False, "items": [SAMPLE_ALBUM]}))
        api = CatalogAPI(mock_transport)
        result = await api.get_artist_releases(12345)
        assert len(result.items) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd qobuz-api/clients/python && pytest tests/test_catalog.py -v
```

- [ ] **Step 3: Implement catalog.py**

```python
# qobuz-api/clients/python/qobuz/catalog.py
"""Catalog API — albums, artists, tracks: get, search, batch lookup, suggestions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import Album, Track, PaginatedResult

if TYPE_CHECKING:
    from ._http import HttpTransport


class CatalogAPI:
    """Read-only operations on the Qobuz catalog."""

    def __init__(self, transport: HttpTransport):
        self._t = transport

    # --- Albums ---

    async def get_album(self, album_id: str, extra: str = "track_ids,albumsFromSameArtist") -> Album:
        _, body = await self._t.get("album/get", {"album_id": album_id, "extra": extra, "offset": 0, "limit": 50})
        return Album.from_dict(body)

    async def search_albums(self, query: str, limit: int = 50, offset: int = 0) -> PaginatedResult:
        _, body = await self._t.get("album/search", {"query": query, "limit": limit, "offset": offset})
        return PaginatedResult.from_dict(body, key="albums")

    async def suggest_album(self, album_id: str) -> list[Album]:
        _, body = await self._t.get("album/suggest", {"album_id": album_id})
        items = body.get("albums", {}).get("items", [])
        return [Album.from_dict(item) for item in items]

    async def get_album_story(self, album_id: str) -> list[dict]:
        _, body = await self._t.get("album/story", {"album_id": album_id, "offset": 0, "limit": 10})
        return body.get("items", [])

    # --- Artists ---

    async def get_artist_page(self, artist_id: int, sort: str = "release_date") -> dict:
        """Returns raw dict — artist/page has a complex nested structure."""
        _, body = await self._t.get("artist/page", {"artist_id": str(artist_id), "sort": sort})
        return body

    async def get_artist_releases(
        self,
        artist_id: int,
        release_type: str = "all",
        offset: int = 0,
        limit: int = 20,
        sort: str = "release_date_by_priority",
    ) -> PaginatedResult:
        _, body = await self._t.get("artist/getReleasesList", {
            "artist_id": str(artist_id), "release_type": release_type,
            "offset": offset, "limit": limit, "sort": sort, "track_size": "15",
        })
        return PaginatedResult.from_dict(body)

    async def search_artists(self, query: str, limit: int = 50, offset: int = 0) -> PaginatedResult:
        _, body = await self._t.get("artist/search", {"query": query, "limit": limit, "offset": offset})
        return PaginatedResult.from_dict(body, key="artists")

    # --- Tracks ---

    async def get_track(self, track_id: int) -> Track:
        _, body = await self._t.get("track/get", {"track_id": str(track_id)})
        return Track.from_dict(body)

    async def get_tracks(self, track_ids: list[int]) -> list[Track]:
        _, body = await self._t.post_json("track/getList", {"tracks_id": track_ids})
        return [Track.from_dict(item) for item in body.get("tracks", {}).get("items", [])]

    async def search_tracks(self, query: str, limit: int = 50, offset: int = 0) -> PaginatedResult:
        _, body = await self._t.get("track/search", {"query": query, "limit": limit, "offset": offset})
        return PaginatedResult.from_dict(body, key="tracks")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd qobuz-api/clients/python && pytest tests/test_catalog.py -v
```

- [ ] **Step 5: Commit**

```bash
git add qobuz-api/clients/python/qobuz/catalog.py qobuz-api/clients/python/tests/test_catalog.py
git commit -m "feat(qobuz-sdk): add catalog API (albums, artists, tracks, search, batch)"
```

---

### Task 8: Discovery API

**Files:**
- Create: `qobuz-api/clients/python/qobuz/discovery.py`
- Create: `qobuz-api/clients/python/tests/test_discovery.py`

- [ ] **Step 1: Write failing tests**

```python
# qobuz-api/clients/python/tests/test_discovery.py
from unittest.mock import AsyncMock

from conftest import SAMPLE_GENRE, SAMPLE_ALBUM
from qobuz.discovery import DiscoveryAPI
from qobuz.types import Genre


class TestDiscoveryGenres:
    async def test_list_genres(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"genres": {"items": [SAMPLE_GENRE], "total": 1, "limit": 25, "offset": 0}}))
        api = DiscoveryAPI(mock_transport)
        genres = await api.list_genres()
        assert len(genres) == 1
        assert isinstance(genres[0], Genre)
        assert genres[0].name == "Pop/Rock"


class TestDiscoveryIndex:
    async def test_get_index(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {
            "containers": {
                "new_releases": {"id": "newReleases", "data": {"has_more": True, "items": [SAMPLE_ALBUM]}},
            }
        }))
        api = DiscoveryAPI(mock_transport)
        result = await api.get_index()
        assert "new_releases" in result


class TestDiscoveryNewReleases:
    async def test_new_releases(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"has_more": True, "items": [SAMPLE_ALBUM]}))
        api = DiscoveryAPI(mock_transport)
        result = await api.new_releases(limit=50)
        assert len(result.items) == 1
        assert result.has_more is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd qobuz-api/clients/python && pytest tests/test_discovery.py -v
```

- [ ] **Step 3: Implement discovery.py**

```python
# qobuz-api/clients/python/qobuz/discovery.py
"""Discovery API — browse new releases, curated playlists, genres."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import Genre, PaginatedResult

if TYPE_CHECKING:
    from ._http import HttpTransport


class DiscoveryAPI:
    """Browse and discover content on Qobuz."""

    def __init__(self, transport: HttpTransport):
        self._t = transport

    async def list_genres(self) -> list[Genre]:
        _, body = await self._t.get("genre/list", {})
        items = body.get("genres", {}).get("items", [])
        return [Genre.from_dict(g) for g in items]

    async def get_index(self, genre_ids: list[int] | None = None) -> dict[str, Any]:
        """Get the discovery index page. Returns raw containers dict."""
        params: dict[str, str] = {}
        if genre_ids:
            params["genre_ids"] = ",".join(str(g) for g in genre_ids)
        _, body = await self._t.get("discover/index", params)
        return body.get("containers", {})

    async def new_releases(
        self, genre_ids: list[int] | None = None, offset: int = 0, limit: int = 50
    ) -> PaginatedResult:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if genre_ids:
            params["genre_ids"] = ",".join(str(g) for g in genre_ids)
        _, body = await self._t.get("discover/newReleases", params)
        return PaginatedResult.from_dict(body)

    async def curated_playlists(
        self, genre_ids: list[int] | None = None, offset: int = 0, limit: int = 20
    ) -> PaginatedResult:
        params: dict[str, Any] = {"offset": offset, "limit": limit, "tags": ""}
        if genre_ids:
            params["genre_ids"] = ",".join(str(g) for g in genre_ids)
        _, body = await self._t.get("discover/playlists", params)
        return PaginatedResult.from_dict(body)

    async def ideal_discography(
        self, genre_ids: list[int] | None = None, offset: int = 0, limit: int = 48
    ) -> PaginatedResult:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if genre_ids:
            params["genre_ids"] = ",".join(str(g) for g in genre_ids)
        _, body = await self._t.get("discover/idealDiscography", params)
        return PaginatedResult.from_dict(body)

    async def album_of_the_week(
        self, genre_ids: list[int] | None = None, offset: int = 0, limit: int = 48
    ) -> PaginatedResult:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if genre_ids:
            params["genre_ids"] = ",".join(str(g) for g in genre_ids)
        _, body = await self._t.get("discover/albumOfTheWeek", params)
        return PaginatedResult.from_dict(body)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd qobuz-api/clients/python && pytest tests/test_discovery.py -v
```

- [ ] **Step 5: Commit**

```bash
git add qobuz-api/clients/python/qobuz/discovery.py qobuz-api/clients/python/tests/test_discovery.py
git commit -m "feat(qobuz-sdk): add discovery API (genres, new releases, curated playlists)"
```

---

### Task 9: Streaming API (with Request Signing)

**Files:**
- Create: `qobuz-api/clients/python/qobuz/streaming.py`
- Create: `qobuz-api/clients/python/tests/test_streaming.py`

- [ ] **Step 1: Write failing tests**

```python
# qobuz-api/clients/python/tests/test_streaming.py
import hashlib
import time
from unittest.mock import AsyncMock, patch

from qobuz.streaming import StreamingAPI, _compute_signature
from qobuz.types import FileUrl, Session


def test_compute_signature():
    sig = _compute_signature(
        endpoint="fileUrl",
        track_id="12345",
        format_id=27,
        intent="stream",
        timestamp=1000000,
        app_secret="mysecret",
    )
    expected_input = "fileUrlformat_id27intentstreamtrack_id123451000000mysecret"
    expected = hashlib.md5(expected_input.encode()).hexdigest()
    assert sig == expected


class TestStreamingGetFileUrl:
    async def test_get_file_url(self, mock_transport):
        mock_transport.app_secret = "secret"
        mock_transport.get = AsyncMock(return_value=(200, {
            "track_id": 12345, "format_id": 7, "mime_type": "audio/mp4",
            "sampling_rate": 96000, "bits_depth": 24, "duration": 133.0,
            "url_template": "https://example.com/$SEGMENT$", "n_segments": 14,
        }))
        api = StreamingAPI(mock_transport, app_secret="secret")
        result = await api.get_file_url("12345", quality=4)
        assert isinstance(result, FileUrl)
        assert result.track_id == 12345


class TestStreamingSession:
    async def test_start_session(self, mock_transport):
        mock_transport.post_form = AsyncMock(return_value=(200, {
            "session_id": "abc123", "profile": "qbz-1", "expires_at": 9999999999,
        }))
        api = StreamingAPI(mock_transport, app_secret="secret")
        session = await api.start_session()
        assert isinstance(session, Session)
        assert session.session_id == "abc123"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd qobuz-api/clients/python && pytest tests/test_streaming.py -v
```

- [ ] **Step 3: Implement streaming.py**

```python
# qobuz-api/clients/python/qobuz/streaming.py
"""Streaming API — file URLs (signed), sessions, playback event reporting."""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import TYPE_CHECKING, Any

from .types import FileUrl, Session

if TYPE_CHECKING:
    from ._http import HttpTransport

QUALITY_MAP = {1: 5, 2: 6, 3: 7, 4: 27}


def _compute_signature(
    endpoint: str, track_id: str, format_id: int, intent: str, timestamp: int, app_secret: str
) -> str:
    raw = f"{endpoint}format_id{format_id}intent{intent}track_id{track_id}{timestamp}{app_secret}"
    return hashlib.md5(raw.encode()).hexdigest()


class StreamingAPI:
    """Streaming URL acquisition, session management, and playback event reporting."""

    def __init__(self, transport: HttpTransport, app_secret: str | None = None):
        self._t = transport
        self._app_secret = app_secret

    async def get_file_url(self, track_id: str, quality: int = 3, intent: str = "stream") -> FileUrl:
        """Get a streaming/download URL for a track.

        Args:
            track_id: The track ID.
            quality: 1=MP3 320, 2=FLAC 16/44, 3=FLAC 24/96, 4=FLAC 24/192.
            intent: "stream" or "download".
        """
        if not self._app_secret:
            raise ValueError("app_secret is required for streaming — set it on QobuzClient")
        format_id = QUALITY_MAP.get(quality, QUALITY_MAP[3])
        ts = int(time.time())
        sig = _compute_signature("fileUrl", track_id, format_id, intent, ts, self._app_secret)
        _, body = await self._t.get("file/url", {
            "track_id": track_id, "format_id": format_id, "intent": intent,
            "request_ts": ts, "request_sig": sig,
        })
        return FileUrl.from_dict(body)

    async def start_session(self) -> Session:
        """Start a playback session (required before streaming)."""
        if not self._app_secret:
            raise ValueError("app_secret is required for sessions")
        ts = int(time.time())
        sig = _compute_signature("session/start", "", 0, "", ts, self._app_secret)
        # session/start uses a simpler signature — just profile + ts + secret
        raw = f"qbz-1{ts}{self._app_secret}"
        sig = hashlib.md5(raw.encode()).hexdigest()
        _, body = await self._t.post_form("session/start", {
            "profile": "qbz-1", "request_ts": str(ts), "request_sig": sig,
        })
        return Session.from_dict(body)

    async def report_start(self, track_id: int, format_id: int, user_id: int) -> dict:
        """Report that a track stream has started."""
        import json
        events = json.dumps([{"track_id": track_id, "date": int(time.time()), "user_id": user_id, "format_id": format_id}])
        _, body = await self._t.post_form("track/reportStreamingStart", {"events": events})
        return body

    async def report_end(self, events: list[dict]) -> dict:
        """Report that track streams have ended."""
        _, body = await self._t.post_json("track/reportStreamingEndJson", {
            "events": events,
            "renderer_context": {"software_version": "qobuz-sdk-0.1.0"},
        })
        return body

    async def report_context(self, track_context_uuid: str, data: dict) -> dict:
        """Report track playback context."""
        _, body = await self._t.post_json("event/reportTrackContext", {
            "version": "01.00",
            "events": [{"track_context_uuid": track_context_uuid, "data": data}],
        })
        return body

    async def dynamic_suggest(self, listened_track_ids: list[int], limit: int = 50) -> dict:
        """Get dynamic suggestions based on listening history."""
        _, body = await self._t.post_json("dynamic/suggest", {
            "limit": limit, "listened_tracks_ids": listened_track_ids,
        })
        return body
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd qobuz-api/clients/python && pytest tests/test_streaming.py -v
```

- [ ] **Step 5: Commit**

```bash
git add qobuz-api/clients/python/qobuz/streaming.py qobuz-api/clients/python/tests/test_streaming.py
git commit -m "feat(qobuz-sdk): add streaming API with request signing"
```

---

### Task 10: QobuzClient Facade

**Files:**
- Create: `qobuz-api/clients/python/qobuz/client.py`
- Create: `qobuz-api/clients/python/tests/test_client.py`
- Modify: `qobuz-api/clients/python/qobuz/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
# qobuz-api/clients/python/tests/test_client.py
import pytest
from unittest.mock import AsyncMock, patch

from qobuz.client import QobuzClient
from qobuz.favorites import FavoritesAPI
from qobuz.playlists import PlaylistsAPI
from qobuz.catalog import CatalogAPI
from qobuz.discovery import DiscoveryAPI
from qobuz.streaming import StreamingAPI


class TestQobuzClient:
    def test_has_namespace_properties(self):
        client = QobuzClient(app_id="123", user_auth_token="tok")
        assert isinstance(client.favorites, FavoritesAPI)
        assert isinstance(client.playlists, PlaylistsAPI)
        assert isinstance(client.catalog, CatalogAPI)
        assert isinstance(client.discovery, DiscoveryAPI)
        assert isinstance(client.streaming, StreamingAPI)

    async def test_context_manager(self):
        async with QobuzClient(app_id="123", user_auth_token="tok") as client:
            assert client._transport._session is not None
        assert client._transport._session is None

    async def test_last_update(self):
        client = QobuzClient(app_id="123", user_auth_token="tok")
        with patch.object(client._transport, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = (200, {"last_update": {"favorite": 123, "playlist": 456}})
            async with client:
                lu = await client.last_update()
                assert lu.favorite == 123
                assert lu.playlist == 456
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd qobuz-api/clients/python && pytest tests/test_client.py -v
```

- [ ] **Step 3: Implement client.py**

```python
# qobuz-api/clients/python/qobuz/client.py
"""QobuzClient — main entry point tying all API namespaces together."""

from __future__ import annotations

from ._http import HttpTransport
from .catalog import CatalogAPI
from .discovery import DiscoveryAPI
from .favorites import FavoritesAPI
from .playlists import PlaylistsAPI
from .streaming import StreamingAPI
from .types import LastUpdate


class QobuzClient:
    """Async Qobuz API client.

    Usage::

        async with QobuzClient(app_id="...", user_auth_token="...") as client:
            albums = await client.favorites.get_albums()
            await client.playlists.create("My Playlist")
    """

    def __init__(
        self,
        app_id: str,
        user_auth_token: str | None = None,
        app_secret: str | None = None,
        requests_per_minute: int = 30,
    ):
        self._transport = HttpTransport(
            app_id=app_id,
            user_auth_token=user_auth_token,
            requests_per_minute=requests_per_minute,
        )
        self.favorites = FavoritesAPI(self._transport)
        self.playlists = PlaylistsAPI(self._transport)
        self.catalog = CatalogAPI(self._transport)
        self.discovery = DiscoveryAPI(self._transport)
        self.streaming = StreamingAPI(self._transport, app_secret=app_secret)

    async def last_update(self) -> LastUpdate:
        """Poll for library changes — returns timestamps for each section."""
        _, body = await self._transport.get("user/lastUpdate", {})
        return LastUpdate.from_dict(body)

    async def login(self) -> dict:
        """Validate the current token and get user profile."""
        _, body = await self._transport.post_form("user/login", {"extra": "partner"})
        return body

    async def __aenter__(self) -> QobuzClient:
        await self._transport.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._transport.__aexit__(*args)
```

- [ ] **Step 4: Update __init__.py with public exports**

```python
# qobuz-api/clients/python/qobuz/__init__.py
"""Async Python client for the Qobuz API."""

from .client import QobuzClient
from .errors import (
    AuthenticationError,
    ForbiddenError,
    InvalidAppError,
    NonStreamableError,
    NotFoundError,
    QobuzError,
    RateLimitError,
)
from .types import (
    Album,
    AlbumSummary,
    ArtistRole,
    ArtistSummary,
    AudioInfo,
    Award,
    FavoriteIds,
    FileUrl,
    Genre,
    ImageSet,
    Label,
    LastUpdate,
    Playlist,
    Rights,
    Session,
    Track,
    UserSummary,
)

__all__ = [
    "QobuzClient",
    "QobuzError", "AuthenticationError", "ForbiddenError", "InvalidAppError",
    "NonStreamableError", "NotFoundError", "RateLimitError",
    "Album", "AlbumSummary", "ArtistRole", "ArtistSummary", "AudioInfo", "Award",
    "FavoriteIds", "FileUrl", "Genre", "ImageSet", "Label", "LastUpdate",
    "Playlist", "Rights", "Session", "Track", "UserSummary",
]
```

- [ ] **Step 5: Run all tests**

```bash
cd qobuz-api/clients/python && pytest -v
```
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add qobuz-api/clients/python/qobuz/client.py qobuz-api/clients/python/qobuz/__init__.py qobuz-api/clients/python/tests/test_client.py
git commit -m "feat(qobuz-sdk): add QobuzClient facade with all namespace APIs"
```

---

### Task 11: README

**Files:**
- Create: `qobuz-api/README.md`

- [ ] **Step 1: Write README**

```markdown
# qobuz-api

Async Python client for the Qobuz API — library management, catalog browsing, and streaming.

## Install

```bash
pip install -e clients/python
```

## Quick Start

```python
import asyncio
from qobuz import QobuzClient

async def main():
    async with QobuzClient(app_id="304027809", user_auth_token="YOUR_TOKEN") as client:
        # List favorite albums
        favorites = await client.favorites.get_albums(limit=50)
        for album in favorites.items:
            print(f"{album.artist.name} — {album.title}")

        # Create a playlist
        playlist = await client.playlists.create("New Playlist", public=False)
        print(f"Created playlist: {playlist.id}")

        # Search the catalog
        results = await client.catalog.search_albums("radiohead")
        for item in results.items:
            print(item)

asyncio.run(main())
```

## Getting Your Auth Token

1. Open https://play.qobuz.com in Chrome
2. Open DevTools → Network tab
3. Look for any request to `api.json`
4. Copy the `X-User-Auth-Token` header value

## API Coverage

| Namespace | Operations |
|-----------|-----------|
| `client.favorites` | add/remove albums, tracks, artists; list favorites; get IDs |
| `client.playlists` | create, update, delete; add/remove tracks; list, search |
| `client.catalog` | get/search albums, artists, tracks; batch lookup; suggestions |
| `client.discovery` | genres, new releases, curated playlists, ideal discography |
| `client.streaming` | file URLs (signed), sessions, playback reporting |
| `client.last_update()` | poll for library changes |
| `client.login()` | validate token, get user profile |

## Spec

See `docs/superpowers/specs/2026-04-08-qobuz-library-sdk-design.md` for the full API specification validated from Proxyman captures.
```

- [ ] **Step 2: Commit**

```bash
git add qobuz-api/README.md
git commit -m "docs(qobuz-sdk): add README with usage examples"
```

---

### Task 12: Final Integration Test

**Files:**
- Modify: `qobuz-api/clients/python/tests/test_client.py`

- [ ] **Step 1: Add integration-style test using aioresponses**

Add this test class to `test_client.py`:

```python
from aioresponses import aioresponses
from conftest import SAMPLE_ALBUM, SAMPLE_PLAYLIST, SAMPLE_FAVORITE_IDS


class TestQobuzClientIntegration:
    """Tests that exercise the full client through the HTTP layer."""

    async def test_full_workflow(self):
        async with QobuzClient(app_id="123", user_auth_token="tok") as client:
            with aioresponses() as m:
                base = "https://www.qobuz.com/api.json/0.2"

                # Add album to favorites
                m.post(f"{base}/favorite/create", payload={"status": "success"})
                await client.favorites.add_album("abc123")

                # Get favorite IDs
                m.get(f"{base}/favorite/getUserFavoriteIds", payload=SAMPLE_FAVORITE_IDS)
                ids = await client.favorites.get_ids()
                assert len(ids.albums) == 2

                # Create playlist
                m.post(f"{base}/playlist/create", payload=SAMPLE_PLAYLIST)
                pl = await client.playlists.create("Test")
                assert pl.id == 61997651

                # Add tracks to playlist
                m.post(f"{base}/playlist/addTracks", payload=SAMPLE_PLAYLIST)
                await client.playlists.add_tracks(pl.id, ["1", "2"])

                # Search albums
                m.get(f"{base}/album/search", payload={"albums": {"items": [SAMPLE_ALBUM], "total": 1, "limit": 50, "offset": 0}})
                results = await client.catalog.search_albums("test")
                assert len(results.items) == 1

                # Delete playlist
                m.post(f"{base}/playlist/delete", payload={"status": "success"})
                await client.playlists.delete(pl.id)
```

- [ ] **Step 2: Run full test suite**

```bash
cd qobuz-api/clients/python && pytest -v --tb=short
```
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add qobuz-api/clients/python/tests/test_client.py
git commit -m "test(qobuz-sdk): add integration test for full client workflow"
```

---

## Summary

| Task | Module | Endpoints Covered |
|------|--------|-------------------|
| 1 | Scaffolding | — |
| 2 | Errors | — |
| 3 | Types | All response models |
| 4 | HTTP Transport | All (foundational) |
| 5 | Favorites | favorite/create, delete, getUserFavorites, getUserFavoriteIds |
| 6 | Playlists | playlist/create, update, delete, addTracks, get, getUserPlaylists, search |
| 7 | Catalog | album/get, search, suggest, story; artist/page, getReleasesList, search; track/get, search, getList |
| 8 | Discovery | discover/index, newReleases, playlists, idealDiscography, albumOfTheWeek; genre/list |
| 9 | Streaming | file/url, session/start, reportStreamingStart, reportStreamingEndJson, reportTrackContext, dynamic/suggest |
| 10 | Client | QobuzClient facade, user/lastUpdate, user/login |
| 11 | README | — |
| 12 | Integration | Full workflow test |

**Total: 12 tasks, ~35 endpoint operations covered, ~12 source files, ~10 test files.**
