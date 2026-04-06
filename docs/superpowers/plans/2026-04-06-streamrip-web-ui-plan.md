# Streamrip Web UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor streamrip from CLI/TUI to a client-server web application with FastAPI backend and SvelteKit frontend.

**Architecture:** Monorepo with `backend/` (FastAPI + existing clients) and `frontend/` (SvelteKit). Static frontend served by backend. Single Docker image. SQLite with WAL mode. WebSocket for real-time updates. Existing CLI preserved.

**Tech Stack:** Python 3.12, FastAPI, aiohttp, SQLite, SvelteKit, TypeScript, adapter-static, Docker

**Spec:** `docs/superpowers/specs/2026-04-06-streamrip-web-ui-design.md`
**Mockup:** `mockup.html` (open in browser for visual reference)
**Bug list:** `.ai-project/todos/bug-fixes-review-2026-04-06.md`

---

## Phase 1: Bug Fixes

Fix P0 runtime crashes in existing client code before wrapping in services.

### Task 1: Fix Tidal search returning empty for single results

**Files:**
- Modify: `streamrip/client/tidal.py:150`
- Test: `tests/test_tidal_fixes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tidal_fixes.py`:

```python
"""Tests for Tidal client bug fixes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTidalSearch:
    """Fix: search returns empty when exactly one result exists."""

    async def test_search_returns_single_result(self):
        """search() should return results when exactly 1 item matches."""
        from streamrip.client.tidal import TidalClient

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.access_token = "fake"

        mock_resp = {"items": [{"id": 123, "title": "Test Album"}], "totalNumberOfItems": 1}
        client._api_request = AsyncMock(return_value=mock_resp)

        result = await client.search("album", "exact match", limit=10)
        assert len(result) == 1
        assert result[0]["items"][0]["id"] == 123

    async def test_search_returns_empty_for_no_results(self):
        """search() should return empty list when no items match."""
        from streamrip.client.tidal import TidalClient

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.access_token = "fake"

        mock_resp = {"items": [], "totalNumberOfItems": 0}
        client._api_request = AsyncMock(return_value=mock_resp)

        result = await client.search("album", "nonexistent", limit=10)
        assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tidal_fixes.py::TestTidalSearch::test_search_returns_single_result -v`
Expected: FAIL — `assert len([]) == 1` because `> 1` excludes single results.

- [ ] **Step 3: Fix the comparison operator**

In `streamrip/client/tidal.py`, change line 150:

```python
# Before:
        if len(resp["items"]) > 1:
# After:
        if len(resp["items"]) >= 1:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tidal_fixes.py::TestTidalSearch -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
git add streamrip/client/tidal.py tests/test_tidal_fixes.py
git commit -m "fix(tidal): return search results when exactly one item matches"
```

---

### Task 2: Fix Tidal get_user_favorites crash on limit=None

**Files:**
- Modify: `streamrip/client/tidal.py:154-162`
- Test: `tests/test_tidal_fixes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tidal_fixes.py`:

```python
class TestTidalGetUserFavorites:
    """Fix: get_user_favorites crashes when limit=None."""

    async def test_favorites_with_limit_none(self):
        """get_user_favorites should handle limit=None (fetch all)."""
        from streamrip.client.tidal import TidalClient

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.user_id = "12345"

        mock_resp = {"items": [{"id": i} for i in range(3)]}
        client._api_request = AsyncMock(return_value=mock_resp)

        # This should not raise TypeError
        result = await client.get_user_favorites("album", limit=None)
        assert len(result) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tidal_fixes.py::TestTidalGetUserFavorites -v`
Expected: FAIL — `TypeError: '<' not supported between instances of 'NoneType' and 'int'`

- [ ] **Step 3: Fix the method signature and limit handling**

In `streamrip/client/tidal.py`, replace lines 154-164:

```python
    async def get_user_favorites(self, media_type: str, limit: int | None = None) -> list[dict]:
        """Get user's favorite albums, tracks, or artists.
        
        :param media_type: album, track, or artist
        :param limit: Maximum number of items to fetch. None for all.
        :return: List of favorite items
        """
        assert media_type in ("track", "artist", "album")
        
        endpoint = f"users/{self.config.user_id}/favorites/{media_type}s"
```

Also replace lines 170-172 (the while loop and params):

```python
        all_items = []
        offset = 0
        
        while limit is None or len(all_items) < limit:
            page_size = 100 if limit is None else min(100, limit - len(all_items))
            params = {"limit": page_size, "offset": offset}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tidal_fixes.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add streamrip/client/tidal.py tests/test_tidal_fixes.py
git commit -m "fix(tidal): handle limit=None in get_user_favorites, use config.user_id"
```

---

### Task 3: Fix Tidal get_downloadable infinite recursion

**Files:**
- Modify: `streamrip/client/tidal.py:208-212`
- Test: `tests/test_tidal_fixes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tidal_fixes.py`:

```python
from json import JSONDecodeError


class TestTidalGetDownloadable:
    """Fix: get_downloadable recurses infinitely when quality hits 0."""

    async def test_raises_at_quality_zero(self):
        """Should raise NonStreamableError instead of recursing below quality 0."""
        from streamrip.client.tidal import TidalClient
        from streamrip.exceptions import NonStreamableError

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.access_token = "fake"

        # Simulate JSONDecodeError on manifest decode at quality 0
        client._api_request = AsyncMock(return_value={
            "manifest": "bm90LWpzb24=",  # base64 of "not-json"
        })

        with pytest.raises(NonStreamableError):
            await client.get_downloadable("track_123", quality=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tidal_fixes.py::TestTidalGetDownloadable -v`
Expected: FAIL — `KeyError: -1` (or RecursionError) because quality decrements below 0.

- [ ] **Step 3: Add floor check before recursion**

In `streamrip/client/tidal.py`, replace lines 208-212:

```python
        except JSONDecodeError:
            if quality <= 0:
                raise NonStreamableError(
                    f"Track {track_id} is not available at any quality."
                )
            logger.warning(
                f"Failed to get manifest for {track_id}. Retrying with lower quality."
            )
            return await self.get_downloadable(track_id, quality - 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tidal_fixes.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add streamrip/client/tidal.py tests/test_tidal_fixes.py
git commit -m "fix(tidal): prevent infinite recursion in get_downloadable at quality 0"
```

---

### Task 4: Fix Tidal get_video_file_url treating response incorrectly

**Files:**
- Modify: `streamrip/client/tidal.py:244-249`
- Test: `tests/test_tidal_fixes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tidal_fixes.py`:

```python
import re


class TestTidalVideoUrl:
    """Fix: get_video_file_url treats aiohttp JSON response as requests.Response."""

    async def test_video_url_parses_hls_manifest(self):
        """Should fetch manifest as text and extract highest resolution URL."""
        from streamrip.client.tidal import TidalClient
        import base64, json

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.access_token = "fake"

        manifest_data = json.dumps({"urls": ["https://example.com/manifest.m3u8"]})
        manifest_b64 = base64.b64encode(manifest_data.encode()).decode()

        client._api_request = AsyncMock(return_value={
            "manifest": manifest_b64,
        })

        # Mock the HLS manifest fetch — returns text, not JSON
        hls_content = (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=500000\n"
            "https://cdn.example.com/low.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=2000000\n"
            "https://cdn.example.com/high.m3u8\n"
        )
        mock_hls_resp = AsyncMock()
        mock_hls_resp.text = AsyncMock(return_value=hls_content)
        mock_hls_resp.__aenter__ = AsyncMock(return_value=mock_hls_resp)
        mock_hls_resp.__aexit__ = AsyncMock(return_value=False)
        client.session.get = MagicMock(return_value=mock_hls_resp)

        url = await client.get_video_file_url("video_123")
        assert "high.m3u8" in url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tidal_fixes.py::TestTidalVideoUrl -v`
Expected: FAIL — `AttributeError: 'dict' object has no attribute 'encoding'`

- [ ] **Step 3: Fix to use resp.text() instead of resp.json()**

In `streamrip/client/tidal.py`, replace lines 244-249:

```python
        async with self.session.get(manifest["urls"][0]) as resp:
            available_urls = await resp.text()

        # Highest resolution is last
        *_, last_match = STREAM_URL_REGEX.finditer(available_urls)

        return last_match.group(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tidal_fixes.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add streamrip/client/tidal.py tests/test_tidal_fixes.py
git commit -m "fix(tidal): use resp.text() for HLS manifest in get_video_file_url"
```

---

### Task 5: Fix AlbumMetadata.from_tidal crash on missing releaseDate

**Files:**
- Modify: `streamrip/metadata/album.py:302-303`
- Test: `tests/test_tidal_fixes.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tidal_fixes.py`:

```python
class TestTidalAlbumMetadata:
    """Fix: from_tidal crashes when releaseDate is absent."""

    def test_from_tidal_missing_release_date(self):
        """Should handle missing releaseDate without crashing."""
        from streamrip.metadata.album import AlbumMetadata

        resp = {
            "id": 12345,
            "title": "Test Album",
            "numberOfTracks": 10,
            "copyright": "(C) 2024",
            "artists": [{"name": "Test Artist", "id": 1}],
            "artist": {"name": "Test Artist"},
            "duration": 3600,
            "streamReady": True,
            "allowStreaming": True,
            "numberOfVolumes": 1,
            "cover": "abc123",
            "explicit": False,
            # releaseDate intentionally omitted
        }

        result = AlbumMetadata.from_tidal(resp)
        assert result is not None
        assert result.year == "Unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tidal_fixes.py::TestTidalAlbumMetadata -v`
Expected: FAIL — `AssertionError` from `typed(None, str)`

- [ ] **Step 3: Handle None releaseDate**

In `streamrip/metadata/album.py`, replace lines 302-303:

```python
        date = typed(resp.get("releaseDate"), str | None)
        year = date[:4] if date is not None else "Unknown"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tidal_fixes.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add streamrip/metadata/album.py tests/test_tidal_fixes.py
git commit -m "fix(metadata): handle missing releaseDate in Tidal album metadata"
```

---

### Task 6: Fix MP3 save_audio passing string as positional arg

**Files:**
- Modify: `streamrip/metadata/tagger.py:238`
- Test: `tests/test_tagger.py` (extend existing)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tagger.py` (or create a focused test):

```python
from unittest.mock import MagicMock
from streamrip.metadata.tagger import Container


class TestContainerSaveAudio:
    """Fix: MP3 save_audio passes string 'v2_version=3' as positional v1 arg."""

    def test_mp3_save_uses_keyword_v2_version(self):
        """save_audio for MP3 should call audio.save(path, v2_version=3)."""
        audio = MagicMock()
        Container.MP3.save_audio(audio, "/tmp/test.mp3")
        audio.save.assert_called_once_with("/tmp/test.mp3", v2_version=3)

    def test_flac_save_no_args(self):
        """save_audio for FLAC should call audio.save() with no args."""
        audio = MagicMock()
        Container.FLAC.save_audio(audio, "/tmp/test.flac")
        audio.save.assert_called_once_with()

    def test_aac_save_no_args(self):
        """save_audio for AAC should call audio.save() with no args."""
        audio = MagicMock()
        Container.AAC.save_audio(audio, "/tmp/test.m4a")
        audio.save.assert_called_once_with()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tagger.py::TestContainerSaveAudio::test_mp3_save_uses_keyword_v2_version -v`
Expected: FAIL — `audio.save` called with `("/tmp/test.mp3", "v2_version=3")` not `("/tmp/test.mp3", v2_version=3)`

- [ ] **Step 3: Fix the save call**

In `streamrip/metadata/tagger.py`, replace line 238:

```python
            audio.save(path, v2_version=3)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tagger.py::TestContainerSaveAudio -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add streamrip/metadata/tagger.py tests/test_tagger.py
git commit -m "fix(tagger): use keyword arg v2_version=3 for MP3 save"
```

---

### Task 7: Fix SoundCloud segment ordering

**Files:**
- Modify: `streamrip/client/downloadable.py:344-346`
- Test: `tests/test_tidal_fixes.py` (rename to `test_client_fixes.py` at this point)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tidal_fixes.py`:

```python
import asyncio


class TestSoundcloudSegmentOrdering:
    """Fix: as_completed returns segments in completion order, not creation order."""

    async def test_segments_concatenated_in_order(self):
        """Segments should be concatenated in playlist order, not completion order."""
        from streamrip.client.downloadable import SoundcloudDownloadable

        dl = SoundcloudDownloadable.__new__(SoundcloudDownloadable)
        dl.session = MagicMock()

        # Simulate 3 segments that complete in reverse order
        async def mock_download_segment(uri):
            # Segment 3 completes first, then 2, then 1
            delay = {"seg1.mp3": 0.03, "seg2.mp3": 0.02, "seg3.mp3": 0.01}
            await asyncio.sleep(delay[uri])
            return f"/tmp/{uri}"

        dl._download_segment = mock_download_segment

        # Build a mock m3u8 response
        m3u8_content = "#EXTM3U\n#EXTINF:10,\nseg1.mp3\n#EXTINF:10,\nseg2.mp3\n#EXTINF:10,\nseg3.mp3\n"

        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value=m3u8_content)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        dl.session.get = MagicMock(return_value=mock_resp)

        dl.url = "https://example.com/playlist.m3u8"

        # Mock concat to capture the order
        captured_paths = []
        
        async def mock_concat(paths, output, fmt):
            captured_paths.extend(paths)

        with patch("streamrip.client.downloadable.concat_audio_files", mock_concat):
            await dl._download_mp3("/tmp/output.mp3", lambda x: None)

        assert captured_paths == ["/tmp/seg1.mp3", "/tmp/seg2.mp3", "/tmp/seg3.mp3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tidal_fixes.py::TestSoundcloudSegmentOrdering -v`
Expected: FAIL — segments are in reverse order `[seg3, seg2, seg1]`

- [ ] **Step 3: Replace as_completed with gather**

In `streamrip/client/downloadable.py`, replace lines 344-347:

```python
        segment_paths = await asyncio.gather(*tasks)
        for _ in segment_paths:
            callback(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tidal_fixes.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add streamrip/client/downloadable.py tests/test_tidal_fixes.py
git commit -m "fix(soundcloud): preserve segment order using gather instead of as_completed"
```

---

## Phase 2: Project Structure & Database

Set up the new project structure and extended database schema.

### Task 8: Create backend directory structure

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/main.py`
- Create: `backend/api/__init__.py`
- Create: `backend/services/__init__.py`
- Create: `backend/models/__init__.py`
- Create: `backend/models/database.py`
- Create: `backend/models/schemas.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/api backend/services backend/models
touch backend/__init__.py backend/api/__init__.py backend/services/__init__.py backend/models/__init__.py
```

- [ ] **Step 2: Create database module with WAL mode and extended schema**

Create `backend/models/database.py`:

```python
"""Extended SQLite database with WAL mode for the web application."""

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger("streamrip")

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_album_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    release_date TEXT,
    label TEXT,
    genre TEXT,
    track_count INTEGER,
    duration_seconds INTEGER,
    cover_url TEXT,
    cover_path TEXT,
    quality TEXT,
    file_size_bytes INTEGER,
    download_status TEXT NOT NULL DEFAULT 'not_downloaded',
    downloaded_at TEXT,
    added_to_library_at TEXT,
    user_id INTEGER NOT NULL DEFAULT 1,
    UNIQUE(source, source_album_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_albums_source_user ON albums(source, user_id);
CREATE INDEX IF NOT EXISTS idx_albums_download_status ON albums(download_status);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    source_track_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    track_number INTEGER,
    disc_number INTEGER DEFAULT 1,
    duration_seconds INTEGER,
    explicit BOOLEAN DEFAULT FALSE,
    isrc TEXT,
    format TEXT,
    bit_depth INTEGER,
    sample_rate INTEGER,
    file_path TEXT,
    download_status TEXT NOT NULL DEFAULT 'not_downloaded',
    UNIQUE(album_id, source_track_id)
);

CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    albums_found INTEGER DEFAULT 0,
    albums_new INTEGER DEFAULT 0,
    albums_removed INTEGER DEFAULT 0,
    albums_downloaded INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""


class AppDatabase:
    """Extended database for the web application."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            # Check if schema_version has a row
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Albums ──

    def upsert_album(
        self,
        source: str,
        source_album_id: str,
        title: str,
        artist: str,
        release_date: str | None = None,
        label: str | None = None,
        genre: str | None = None,
        track_count: int | None = None,
        duration_seconds: int | None = None,
        cover_url: str | None = None,
        quality: str | None = None,
        added_to_library_at: str | None = None,
        user_id: int = 1,
    ) -> int:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO albums
                   (source, source_album_id, title, artist, release_date, label,
                    genre, track_count, duration_seconds, cover_url, quality,
                    added_to_library_at, user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, source_album_id, user_id)
                   DO UPDATE SET
                     title=excluded.title, artist=excluded.artist,
                     release_date=excluded.release_date, label=excluded.label,
                     genre=excluded.genre, track_count=excluded.track_count,
                     duration_seconds=excluded.duration_seconds,
                     cover_url=excluded.cover_url, quality=excluded.quality,
                     added_to_library_at=excluded.added_to_library_at
                """,
                (
                    source, source_album_id, title, artist, release_date,
                    label, genre, track_count, duration_seconds, cover_url,
                    quality, added_to_library_at, user_id,
                ),
            )
            row = conn.execute(
                "SELECT id FROM albums WHERE source=? AND source_album_id=? AND user_id=?",
                (source, source_album_id, user_id),
            ).fetchone()
            return row["id"]

    def get_albums(
        self,
        source: str,
        user_id: int = 1,
        status: str | None = None,
        search: str | None = None,
        sort_by: str = "added_to_library_at",
        sort_dir: str = "DESC",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["source = ?", "user_id = ?"]
        params: list = [source, user_id]

        if status and status != "all":
            conditions.append("download_status = ?")
            params.append(status)

        if search:
            conditions.append("(title LIKE ? OR artist LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        allowed_sorts = {
            "added_to_library_at", "title", "artist", "release_date", "downloaded_at"
        }
        if sort_by not in allowed_sorts:
            sort_by = "added_to_library_at"
        if sort_dir not in ("ASC", "DESC"):
            sort_dir = "DESC"

        where = " AND ".join(conditions)
        query = f"""
            SELECT * FROM albums
            WHERE {where}
            ORDER BY {sort_by} {sort_dir}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_album(self, album_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM albums WHERE id = ?", (album_id,)).fetchone()
            return dict(row) if row else None

    def get_album_by_source_id(self, source: str, source_album_id: str, user_id: int = 1) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM albums WHERE source=? AND source_album_id=? AND user_id=?",
                (source, source_album_id, user_id),
            ).fetchone()
            return dict(row) if row else None

    def update_album_status(self, album_id: int, status: str, downloaded_at: str | None = None):
        with self._connect() as conn:
            if downloaded_at:
                conn.execute(
                    "UPDATE albums SET download_status=?, downloaded_at=? WHERE id=?",
                    (status, downloaded_at, album_id),
                )
            else:
                conn.execute(
                    "UPDATE albums SET download_status=? WHERE id=?",
                    (status, album_id),
                )

    def count_albums(self, source: str, user_id: int = 1, status: str | None = None) -> int:
        conditions = ["source = ?", "user_id = ?"]
        params: list = [source, user_id]
        if status:
            conditions.append("download_status = ?")
            params.append(status)
        where = " AND ".join(conditions)
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM albums WHERE {where}", params).fetchone()
            return row["cnt"]

    # ── Tracks ──

    def upsert_track(
        self,
        album_id: int,
        source_track_id: str,
        title: str,
        artist: str,
        track_number: int | None = None,
        disc_number: int = 1,
        duration_seconds: int | None = None,
        explicit: bool = False,
        isrc: str | None = None,
    ) -> int:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO tracks
                   (album_id, source_track_id, title, artist, track_number,
                    disc_number, duration_seconds, explicit, isrc)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(album_id, source_track_id)
                   DO UPDATE SET
                     title=excluded.title, artist=excluded.artist,
                     track_number=excluded.track_number,
                     disc_number=excluded.disc_number,
                     duration_seconds=excluded.duration_seconds,
                     explicit=excluded.explicit, isrc=excluded.isrc
                """,
                (album_id, source_track_id, title, artist, track_number,
                 disc_number, duration_seconds, explicit, isrc),
            )
            row = conn.execute(
                "SELECT id FROM tracks WHERE album_id=? AND source_track_id=?",
                (album_id, source_track_id),
            ).fetchone()
            return row["id"]

    def get_tracks(self, album_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tracks WHERE album_id=? ORDER BY disc_number, track_number",
                (album_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_track_status(self, track_id: int, status: str, file_path: str | None = None,
                            format: str | None = None, bit_depth: int | None = None,
                            sample_rate: int | None = None):
        with self._connect() as conn:
            conn.execute(
                """UPDATE tracks SET download_status=?, file_path=?,
                   format=?, bit_depth=?, sample_rate=?
                   WHERE id=?""",
                (status, file_path, format, bit_depth, sample_rate, track_id),
            )

    # ── Sync Runs ──

    def create_sync_run(self, source: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO sync_runs (source, started_at) VALUES (?, ?)",
                (source, datetime.now().isoformat()),
            )
            return cursor.lastrowid

    def complete_sync_run(self, run_id: int, albums_found: int, albums_new: int,
                          albums_removed: int, albums_downloaded: int):
        with self._connect() as conn:
            conn.execute(
                """UPDATE sync_runs SET completed_at=?, albums_found=?,
                   albums_new=?, albums_removed=?, albums_downloaded=?,
                   status='complete'
                   WHERE id=?""",
                (datetime.now().isoformat(), albums_found, albums_new,
                 albums_removed, albums_downloaded, run_id),
            )

    def get_sync_history(self, source: str, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sync_runs WHERE source=? ORDER BY started_at DESC LIMIT ?",
                (source, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Config ──

    def get_config(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
            return row["value"] if row else None

    def set_config(self, key: str, value: str):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, value, datetime.now().isoformat()),
            )

    def get_all_config(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
            return {r["key"]: r["value"] for r in rows}
```

- [ ] **Step 3: Write database tests**

Create `tests/test_app_database.py`:

```python
"""Tests for the extended web application database."""

import os
import tempfile
import pytest

from backend.models.database import AppDatabase


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = AppDatabase(path)
    yield database
    os.unlink(path)


class TestAlbums:
    def test_upsert_and_get_album(self, db):
        album_id = db.upsert_album(
            source="qobuz",
            source_album_id="abc123",
            title="In Rainbows",
            artist="Radiohead",
            release_date="2007-10-10",
            quality="FLAC 24/44",
        )
        assert album_id > 0

        album = db.get_album(album_id)
        assert album["title"] == "In Rainbows"
        assert album["download_status"] == "not_downloaded"

    def test_upsert_updates_existing(self, db):
        id1 = db.upsert_album("qobuz", "abc123", "Old Title", "Artist")
        id2 = db.upsert_album("qobuz", "abc123", "New Title", "Artist")
        assert id1 == id2
        album = db.get_album(id1)
        assert album["title"] == "New Title"

    def test_get_albums_with_filter(self, db):
        db.upsert_album("qobuz", "a1", "Album A", "Artist A")
        db.upsert_album("qobuz", "a2", "Album B", "Artist B")
        db.update_album_status(
            db.get_album_by_source_id("qobuz", "a1")["id"],
            "complete",
        )

        complete = db.get_albums("qobuz", status="complete")
        assert len(complete) == 1
        assert complete[0]["title"] == "Album A"

    def test_get_albums_with_search(self, db):
        db.upsert_album("qobuz", "a1", "In Rainbows", "Radiohead")
        db.upsert_album("qobuz", "a2", "Kid A", "Radiohead")
        db.upsert_album("qobuz", "a3", "Blue Train", "John Coltrane")

        results = db.get_albums("qobuz", search="Radiohead")
        assert len(results) == 2

    def test_count_albums(self, db):
        db.upsert_album("qobuz", "a1", "A", "B")
        db.upsert_album("qobuz", "a2", "C", "D")
        db.upsert_album("tidal", "a3", "E", "F")

        assert db.count_albums("qobuz") == 2
        assert db.count_albums("tidal") == 1


class TestTracks:
    def test_upsert_and_get_tracks(self, db):
        album_id = db.upsert_album("qobuz", "a1", "Album", "Artist")
        db.upsert_track(album_id, "t1", "Track 1", "Artist", track_number=1)
        db.upsert_track(album_id, "t2", "Track 2", "Artist", track_number=2)

        tracks = db.get_tracks(album_id)
        assert len(tracks) == 2
        assert tracks[0]["title"] == "Track 1"
        assert tracks[1]["title"] == "Track 2"

    def test_update_track_status(self, db):
        album_id = db.upsert_album("qobuz", "a1", "Album", "Artist")
        track_id = db.upsert_track(album_id, "t1", "Track", "Artist")
        db.update_track_status(track_id, "complete", "/music/track.flac", "FLAC", 24, 96000)

        tracks = db.get_tracks(album_id)
        assert tracks[0]["download_status"] == "complete"
        assert tracks[0]["file_path"] == "/music/track.flac"


class TestSyncRuns:
    def test_create_and_complete_sync_run(self, db):
        run_id = db.create_sync_run("qobuz")
        db.complete_sync_run(run_id, albums_found=100, albums_new=5,
                             albums_removed=1, albums_downloaded=4)

        history = db.get_sync_history("qobuz")
        assert len(history) == 1
        assert history[0]["albums_new"] == 5
        assert history[0]["status"] == "complete"


class TestConfig:
    def test_set_and_get_config(self, db):
        db.set_config("qobuz.quality", "3")
        assert db.get_config("qobuz.quality") == "3"

    def test_get_all_config(self, db):
        db.set_config("qobuz.quality", "3")
        db.set_config("downloads.path", "/music")
        cfg = db.get_all_config()
        assert cfg["qobuz.quality"] == "3"
        assert cfg["downloads.path"] == "/music"

    def test_upsert_config(self, db):
        db.set_config("key", "old")
        db.set_config("key", "new")
        assert db.get_config("key") == "new"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_app_database.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/ tests/test_app_database.py
git commit -m "feat: add backend structure with extended SQLite database and WAL mode"
```

---

### Task 9: Create Pydantic schemas for API

**Files:**
- Create: `backend/models/schemas.py`

- [ ] **Step 1: Create Pydantic models**

Create `backend/models/schemas.py`:

```python
"""Pydantic models for API request/response."""

from pydantic import BaseModel


class AlbumSummary(BaseModel):
    id: int
    source: str
    source_album_id: str
    title: str
    artist: str
    release_date: str | None = None
    label: str | None = None
    genre: str | None = None
    track_count: int | None = None
    duration_seconds: int | None = None
    cover_url: str | None = None
    quality: str | None = None
    download_status: str = "not_downloaded"
    downloaded_at: str | None = None
    added_to_library_at: str | None = None


class TrackDetail(BaseModel):
    id: int
    source_track_id: str
    title: str
    artist: str
    track_number: int | None = None
    disc_number: int = 1
    duration_seconds: int | None = None
    explicit: bool = False
    isrc: str | None = None
    format: str | None = None
    bit_depth: int | None = None
    sample_rate: int | None = None
    file_path: str | None = None
    download_status: str = "not_downloaded"


class AlbumDetail(AlbumSummary):
    tracks: list[TrackDetail] = []


class PaginatedAlbums(BaseModel):
    albums: list[AlbumSummary]
    total: int
    page: int
    page_size: int


class SearchResult(AlbumSummary):
    in_library: bool = False


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str
    source: str


class DownloadRequest(BaseModel):
    source: str
    album_ids: list[str]


class QueueItem(BaseModel):
    id: str
    source: str
    source_album_id: str
    title: str
    artist: str
    cover_url: str | None = None
    track_count: int = 0
    tracks_done: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    speed: float = 0.0
    status: str = "pending"  # pending, downloading, complete, failed, cancelled


class QueueStatus(BaseModel):
    items: list[QueueItem]
    active_count: int
    total_speed: float


class SyncDiff(BaseModel):
    new_albums: list[AlbumSummary]
    removed_albums: list[AlbumSummary]
    source: str
    last_sync: str | None = None


class SyncRunSummary(BaseModel):
    id: int
    source: str
    started_at: str
    completed_at: str | None = None
    albums_found: int = 0
    albums_new: int = 0
    albums_removed: int = 0
    albums_downloaded: int = 0
    status: str


class AuthStatus(BaseModel):
    source: str
    authenticated: bool
    user_id: str | None = None
    token_expires: str | None = None


class AppConfig(BaseModel):
    qobuz_quality: int = 3
    qobuz_user_id: str = ""
    qobuz_token: str = ""
    tidal_quality: int = 3
    tidal_access_token: str = ""
    downloads_path: str = ""
    max_connections: int = 6
    folder_format: str = "{albumartist} - {title} ({year}) [{container}]"
    track_format: str = "{tracknumber:02}. {artist} - {title}{explicit}"
    conversion_enabled: bool = False
    conversion_codec: str = "ALAC"
    auto_sync_enabled: bool = False
    auto_sync_interval: str = "6h"


class ConfigUpdate(BaseModel):
    """Partial config update — only set fields are applied."""
    qobuz_quality: int | None = None
    qobuz_user_id: str | None = None
    qobuz_token: str | None = None
    tidal_quality: int | None = None
    downloads_path: str | None = None
    max_connections: int | None = None
    folder_format: str | None = None
    track_format: str | None = None
    conversion_enabled: bool | None = None
    conversion_codec: str | None = None
    auto_sync_enabled: bool | None = None
    auto_sync_interval: str | None = None


class EventMessage(BaseModel):
    type: str
    data: dict
```

- [ ] **Step 2: Commit**

```bash
git add backend/models/schemas.py
git commit -m "feat: add Pydantic schemas for API request/response models"
```

---

### Task 10: Create event bus

**Files:**
- Create: `backend/services/event_bus.py`
- Test: `tests/test_event_bus.py`

- [ ] **Step 1: Write the test**

Create `tests/test_event_bus.py`:

```python
"""Tests for the in-process event bus."""

import asyncio
import pytest

from backend.services.event_bus import EventBus


class TestEventBus:
    async def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("download_progress", handler)
        await bus.publish("download_progress", {"item_id": "1", "progress": 50})

        # Give handler time to process
        await asyncio.sleep(0.01)
        assert len(received) == 1
        assert received[0]["item_id"] == "1"

    async def test_multiple_subscribers(self):
        bus = EventBus()
        received_a = []
        received_b = []

        async def handler_a(event):
            received_a.append(event)

        async def handler_b(event):
            received_b.append(event)

        bus.subscribe("test_event", handler_a)
        bus.subscribe("test_event", handler_b)
        await bus.publish("test_event", {"data": "hello"})

        await asyncio.sleep(0.01)
        assert len(received_a) == 1
        assert len(received_b) == 1

    async def test_unsubscribe(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe("test", handler)
        bus.unsubscribe("test", handler)
        await bus.publish("test", {"data": "ignored"})

        await asyncio.sleep(0.01)
        assert len(received) == 0

    async def test_no_subscribers_no_error(self):
        bus = EventBus()
        # Should not raise
        await bus.publish("nonexistent_event", {"data": "test"})
```

- [ ] **Step 2: Write the event bus**

Create `backend/services/event_bus.py`:

```python
"""In-process pub/sub event bus using asyncio."""

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger("streamrip")

EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventBus:
    """Simple async event bus for real-time updates."""

    def __init__(self):
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler):
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler):
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h is not handler
            ]

    async def publish(self, event_type: str, data: dict[str, Any]):
        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(data)
            except Exception:
                logger.exception("Event handler error for %s", event_type)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_event_bus.py -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/services/event_bus.py tests/test_event_bus.py
git commit -m "feat: add async event bus for real-time WebSocket updates"
```

---

### Task 11: Create FastAPI app skeleton

**Files:**
- Create: `backend/main.py`
- Test: `tests/test_app_startup.py`

- [ ] **Step 1: Write the test**

Create `tests/test_app_startup.py`:

```python
"""Test that the FastAPI app starts and serves basic routes."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app


class TestAppStartup:
    async def test_health_check(self):
        app = create_app(db_path=":memory:")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_auth_status(self):
        app = create_app(db_path=":memory:")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/auth/status")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Write the FastAPI app**

Create `backend/main.py`:

```python
"""FastAPI application for streamrip web UI."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .models.database import AppDatabase
from .services.event_bus import EventBus

logger = logging.getLogger("streamrip")


def create_app(db_path: str = "data/streamrip.db") -> FastAPI:
    db = AppDatabase(db_path)
    event_bus = EventBus()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db = db
        app.state.event_bus = event_bus
        logger.info("streamrip web UI started")
        yield
        logger.info("streamrip web UI shutting down")

    app = FastAPI(title="streamrip", version="3.0.0", lifespan=lifespan)

    # Store references for use outside lifespan
    app.state.db = db
    app.state.event_bus = event_bus

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/auth/status")
    async def auth_status():
        # Placeholder — will be implemented in auth API module
        return []

    return app
```

- [ ] **Step 3: Add dependencies to pyproject.toml**

Add to pyproject.toml `[tool.poetry.dependencies]`:

```toml
fastapi = ">=0.110"
uvicorn = {version = ">=0.29", extras = ["standard"]}
httpx = ">=0.27"
```

Run: `poetry add fastapi 'uvicorn[standard]' httpx`

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_app_startup.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_app_startup.py pyproject.toml poetry.lock
git commit -m "feat: add FastAPI app skeleton with health check and auth status"
```

---

## Phase 3: Backend Services & API

### Task 12: LibraryService

**Files:**
- Create: `backend/services/library.py`
- Test: `tests/test_library_service.py`

This service wraps the existing Qobuz/Tidal clients to fetch library data and store it in the extended database. It also handles search with `in_library` enrichment.

- [ ] **Step 1: Write the tests**

Create `tests/test_library_service.py`:

```python
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


@pytest.fixture
def mock_qobuz_client():
    client = AsyncMock()
    client.source = "qobuz"
    client.logged_in = True
    return client


class TestLibraryServiceGetAlbums:
    async def test_get_albums_returns_paginated(self, db, event_bus):
        # Pre-populate DB
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
    async def test_search_enriches_with_library_status(self, db, event_bus, mock_qobuz_client):
        # Album already in library
        db.upsert_album("qobuz", "existing_id", "Known Album", "Artist")

        mock_qobuz_client.search = AsyncMock(return_value=[{
            "albums": {"items": [
                {"id": "existing_id", "title": "Known Album", "artist": {"name": "Artist"},
                 "release_date_original": "2024-01-01", "duration": 3600,
                 "tracks_count": 10, "label": {"name": "Label"}, "genre": {"name": "Rock"},
                 "maximum_bit_depth": 24, "maximum_sampling_rate": 96.0,
                 "image": {"large": "https://img.com/cover.jpg"}},
                {"id": "new_id", "title": "Unknown Album", "artist": {"name": "Other"},
                 "release_date_original": "2024-06-01", "duration": 2400,
                 "tracks_count": 8, "label": {"name": "Label2"}, "genre": {"name": "Jazz"},
                 "maximum_bit_depth": 16, "maximum_sampling_rate": 44.1,
                 "image": {"large": "https://img.com/cover2.jpg"}},
            ]}
        }])

        service = LibraryService(db, event_bus, clients={"qobuz": mock_qobuz_client})
        results = await service.search("qobuz", "test query")

        assert len(results) == 2
        known = next(r for r in results if r["source_album_id"] == "existing_id")
        unknown = next(r for r in results if r["source_album_id"] == "new_id")
        assert known["in_library"] is True
        assert unknown["in_library"] is False
```

- [ ] **Step 2: Implement LibraryService**

Create `backend/services/library.py`:

```python
"""Library service — fetches and caches streaming library state."""

import logging
from typing import Any

from ..models.database import AppDatabase
from .event_bus import EventBus

logger = logging.getLogger("streamrip")


class LibraryService:
    def __init__(self, db: AppDatabase, event_bus: EventBus, clients: dict):
        self.db = db
        self.event_bus = event_bus
        self.clients = clients

    async def get_albums(
        self,
        source: str,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "added_to_library_at",
        sort_dir: str = "DESC",
        status: str | None = None,
        search: str | None = None,
    ) -> dict:
        offset = (page - 1) * page_size
        albums = self.db.get_albums(
            source=source,
            status=status,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=page_size,
            offset=offset,
        )
        total = self.db.count_albums(source, status=status)
        return {
            "albums": albums,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_album_detail(self, album_id: int) -> dict | None:
        album = self.db.get_album(album_id)
        if album is None:
            return None
        tracks = self.db.get_tracks(album_id)
        return {**album, "tracks": tracks}

    async def refresh_library(self, source: str) -> dict:
        """Re-fetch entire library from streaming API and update DB."""
        client = self.clients.get(source)
        if client is None:
            raise ValueError(f"No client configured for {source}")

        if not client.logged_in:
            raise ValueError(f"Client {source} is not authenticated")

        albums_data = await client.get_user_favorites("album", limit=None)
        new_count = 0

        for item in albums_data:
            album_resp = self._extract_album_data(source, item)
            if album_resp is None:
                continue

            existing = self.db.get_album_by_source_id(source, album_resp["source_album_id"])
            if existing is None:
                new_count += 1

            self.db.upsert_album(**album_resp)

        await self.event_bus.publish("library_updated", {
            "source": source,
            "new_count": new_count,
            "total": len(albums_data),
        })

        return {"total": len(albums_data), "new": new_count}

    async def search(self, source: str, query: str, limit: int = 20) -> list[dict]:
        """Search streaming service and enrich with library status."""
        client = self.clients.get(source)
        if client is None:
            raise ValueError(f"No client configured for {source}")

        raw_results = await client.search("album", query, limit=limit)
        if not raw_results:
            return []

        # Extract album items from the response structure
        albums = []
        for page in raw_results:
            if isinstance(page, dict) and "albums" in page:
                albums.extend(page["albums"].get("items", []))
            elif isinstance(page, dict) and "items" in page:
                albums.extend(page["items"])

        enriched = []
        for album in albums:
            parsed = self._extract_album_data(source, album)
            if parsed is None:
                continue

            existing = self.db.get_album_by_source_id(source, parsed["source_album_id"])
            enriched.append({
                **parsed,
                "in_library": existing is not None,
                "download_status": existing["download_status"] if existing else "not_downloaded",
                "id": existing["id"] if existing else 0,
            })

        return enriched

    def _extract_album_data(self, source: str, item: dict) -> dict | None:
        """Extract normalized album data from a source-specific API response."""
        try:
            if source == "qobuz":
                return self._extract_qobuz_album(item)
            elif source == "tidal":
                return self._extract_tidal_album(item)
            else:
                logger.warning("Unknown source: %s", source)
                return None
        except Exception:
            logger.exception("Failed to extract album data")
            return None

    def _extract_qobuz_album(self, item: dict) -> dict:
        # Handle both favorites response (nested under "album") and direct album response
        album = item.get("album", item) if "album" in item else item
        artist = album.get("artist", {})
        image = album.get("image", {})
        bit_depth = album.get("maximum_bit_depth", 16)
        sample_rate = album.get("maximum_sampling_rate", 44.1)
        quality = f"FLAC {bit_depth}/{sample_rate}kHz" if bit_depth else None

        return {
            "source": "qobuz",
            "source_album_id": str(album["id"]),
            "title": album.get("title", "Unknown"),
            "artist": artist.get("name", "Unknown") if isinstance(artist, dict) else str(artist),
            "release_date": album.get("release_date_original"),
            "label": album.get("label", {}).get("name") if isinstance(album.get("label"), dict) else None,
            "genre": album.get("genre", {}).get("name") if isinstance(album.get("genre"), dict) else None,
            "track_count": album.get("tracks_count"),
            "duration_seconds": album.get("duration"),
            "cover_url": image.get("large") or image.get("small"),
            "quality": quality,
        }

    def _extract_tidal_album(self, item: dict) -> dict:
        album = item.get("item", item) if "item" in item else item
        artists = album.get("artists", [])
        artist_name = ", ".join(a["name"] for a in artists) if artists else album.get("artist", {}).get("name", "Unknown")
        cover = album.get("cover", "")
        cover_url = f"https://resources.tidal.com/images/{cover.replace('-', '/')}/640x640.jpg" if cover else None

        return {
            "source": "tidal",
            "source_album_id": str(album["id"]),
            "title": album.get("title", "Unknown"),
            "artist": artist_name,
            "release_date": album.get("releaseDate"),
            "track_count": album.get("numberOfTracks"),
            "duration_seconds": album.get("duration"),
            "cover_url": cover_url,
            "quality": album.get("audioQuality"),
        }
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_library_service.py -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/services/library.py tests/test_library_service.py
git commit -m "feat: add LibraryService with search enrichment and library refresh"
```

---

### Task 13: DownloadService

**Files:**
- Create: `backend/services/download.py`
- Test: `tests/test_download_service.py`

The download service manages the in-memory queue and delegates to existing client/media code. Full implementation — queue management, progress events, cancellation.

- [ ] **Step 1: Write the tests**

Create `tests/test_download_service.py`:

```python
"""Tests for DownloadService."""

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
```

- [ ] **Step 2: Implement DownloadService**

Create `backend/services/download.py`:

```python
"""Download service — queue management and download execution."""

import asyncio
import logging
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
        """Add albums to the download queue."""
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

        # Start worker if not running
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue())

        return items

    def get_queue(self) -> list[dict]:
        return list(self._queue)

    async def cancel(self, item_ids: list[str]):
        """Cancel queued or active downloads."""
        for item_id in item_ids:
            self._cancel_requested.add(item_id)
            for item in self._queue:
                if item["id"] == item_id and item["status"] in ("pending", "downloading"):
                    item["status"] = "cancelled"
                    self.db.update_album_status(item["album_db_id"], "not_downloaded")

    async def cancel_all(self):
        """Cancel all active and pending downloads."""
        ids = [item["id"] for item in self._queue if item["status"] in ("pending", "downloading")]
        await self.cancel(ids)

    async def _process_queue(self):
        """Background worker that processes the download queue."""
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
                "item_id": item["id"],
                "status": "downloading",
                "tracks_done": 0,
                "track_count": item["track_count"],
            })

            try:
                await self._download_album(item)
                item["status"] = "complete"
                self.db.update_album_status(
                    item["album_db_id"], "complete",
                    downloaded_at=datetime.now().isoformat(),
                )
                await self.event_bus.publish("download_complete", {
                    "item_id": item["id"],
                    "title": item["title"],
                    "artist": item["artist"],
                })
            except Exception as e:
                logger.exception("Download failed for %s", item["title"])
                item["status"] = "failed"
                self.db.update_album_status(item["album_db_id"], "not_downloaded")
                await self.event_bus.publish("download_failed", {
                    "item_id": item["id"],
                    "error": str(e),
                })

    async def _download_album(self, item: dict):
        """Download an album using the existing client/media pipeline.

        This method will be fleshed out when integrating with the existing
        streamrip client code. For now it delegates to the client's existing
        download flow.
        """
        # Integration point: wire to existing streamrip.rip.main.Main pipeline.
        # Call Main.add_all_by_id([(source, "album", source_album_id)]),
        # then Main.resolve(), then Main.rip(). The existing pipeline handles
        # metadata resolution, track downloading, tagging, and conversion.
        # This wiring is done during integration testing after all services exist.
        client = self.clients.get(item["source"])
        if client is None:
            raise ValueError(f"No client for source {item['source']}")

        logger.info("Downloading album: %s - %s", item["artist"], item["title"])
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_download_service.py -v`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/services/download.py tests/test_download_service.py
git commit -m "feat: add DownloadService with queue management and cancellation"
```

---

### Task 14: API routes — library, search, downloads, config, auth

**Files:**
- Create: `backend/api/library.py`
- Create: `backend/api/downloads.py`
- Create: `backend/api/config.py`
- Create: `backend/api/auth.py`
- Create: `backend/api/websocket.py`
- Modify: `backend/main.py`
- Test: `tests/test_api_routes.py`

- [ ] **Step 1: Write API route tests**

Create `tests/test_api_routes.py`:

```python
"""Tests for API routes."""

import os
import tempfile
import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app
from backend.models.database import AppDatabase


@pytest.fixture
def app():
    return create_app(db_path=":memory:")


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestLibraryRoutes:
    async def test_get_albums_empty(self, client, app):
        resp = await client.get("/api/library/qobuz/albums")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["albums"] == []

    async def test_get_albums_with_data(self, client, app):
        app.state.db.upsert_album("qobuz", "a1", "Test Album", "Test Artist")
        resp = await client.get("/api/library/qobuz/albums")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_get_album_detail(self, client, app):
        album_id = app.state.db.upsert_album("qobuz", "a1", "Test", "Artist")
        app.state.db.upsert_track(album_id, "t1", "Track 1", "Artist", track_number=1)

        resp = await client.get(f"/api/library/qobuz/albums/{album_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test"
        assert len(data["tracks"]) == 1


class TestDownloadRoutes:
    async def test_get_empty_queue(self, client):
        resp = await client.get("/api/downloads/queue")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_enqueue_download(self, client, app):
        app.state.db.upsert_album("qobuz", "a1", "Test", "Artist")
        resp = await client.post("/api/downloads/queue", json={
            "source": "qobuz",
            "album_ids": ["a1"],
        })
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestConfigRoutes:
    async def test_get_config(self, client):
        resp = await client.get("/api/config")
        assert resp.status_code == 200

    async def test_update_config(self, client):
        resp = await client.patch("/api/config", json={
            "downloads_path": "/new/path",
        })
        assert resp.status_code == 200
```

- [ ] **Step 2: Create API route modules**

Create `backend/api/library.py`:

```python
"""Library API routes."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("/{source}/albums")
async def get_albums(
    request: Request,
    source: str,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "added_to_library_at",
    sort_dir: str = "DESC",
    status: str | None = None,
    search: str | None = None,
):
    service = request.app.state.library_service
    return await service.get_albums(
        source, page=page, page_size=page_size,
        sort_by=sort_by, sort_dir=sort_dir,
        status=status, search=search,
    )


@router.get("/{source}/albums/{album_id}")
async def get_album_detail(request: Request, source: str, album_id: int):
    service = request.app.state.library_service
    result = await service.get_album_detail(album_id)
    if result is None:
        return {"error": "Album not found"}, 404
    return result


@router.post("/refresh/{source}")
async def refresh_library(request: Request, source: str):
    service = request.app.state.library_service
    return await service.refresh_library(source)


@router.get("/search/{source}")
async def search(request: Request, source: str, q: str, limit: int = 20):
    service = request.app.state.library_service
    return await service.search(source, q, limit=limit)
```

Create `backend/api/downloads.py`:

```python
"""Downloads API routes."""

from fastapi import APIRouter, Request
from ..models.schemas import DownloadRequest

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.get("/queue")
async def get_queue(request: Request):
    service = request.app.state.download_service
    queue = service.get_queue()
    active = [q for q in queue if q["status"] == "downloading"]
    total_speed = sum(q.get("speed", 0) for q in active)
    return {
        "items": queue,
        "active_count": len(active),
        "total_speed": total_speed,
    }


@router.post("/queue")
async def enqueue(request: Request, body: DownloadRequest):
    service = request.app.state.download_service
    return await service.enqueue(body.source, body.album_ids)


@router.delete("/queue/{item_id}")
async def remove_from_queue(request: Request, item_id: str):
    service = request.app.state.download_service
    await service.cancel([item_id])
    return {"status": "cancelled"}


@router.post("/cancel")
async def cancel_all(request: Request):
    service = request.app.state.download_service
    await service.cancel_all()
    return {"status": "cancelled"}
```

Create `backend/api/config.py`:

```python
"""Config API routes."""

import json
from fastapi import APIRouter, Request
from ..models.schemas import AppConfig, ConfigUpdate

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config(request: Request) -> AppConfig:
    db = request.app.state.db
    raw = db.get_all_config()
    # Build AppConfig from stored key-value pairs
    config_dict = {}
    for key, value in raw.items():
        # Convert types
        if key in ("qobuz_quality", "tidal_quality", "max_connections"):
            config_dict[key] = int(value)
        elif key in ("conversion_enabled", "auto_sync_enabled"):
            config_dict[key] = value.lower() in ("true", "1", "yes")
        else:
            config_dict[key] = value
    return AppConfig(**config_dict)


@router.patch("")
async def update_config(request: Request, body: ConfigUpdate):
    db = request.app.state.db
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        db.set_config(key, str(value))
    return await get_config(request)
```

Create `backend/api/auth.py`:

```python
"""Auth API routes."""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
async def auth_status(request: Request):
    db = request.app.state.db
    sources = []
    for source in ("qobuz", "tidal"):
        token_key = f"{source}_token" if source == "qobuz" else f"{source}_access_token"
        token = db.get_config(token_key)
        sources.append({
            "source": source,
            "authenticated": bool(token),
            "user_id": db.get_config(f"{source}_user_id"),
        })
    return sources
```

Create `backend/api/websocket.py`:

```python
"""WebSocket handler for real-time events."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger("streamrip")


class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.connections = [c for c in self.connections if c is not websocket]

    async def broadcast(self, event_type: str, data: dict):
        message = json.dumps({"type": event_type, "data": data})
        disconnected = []
        for conn in self.connections:
            try:
                await conn.send_text(message)
            except Exception:
                disconnected.append(conn)
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

- [ ] **Step 3: Update main.py to wire routes and services**

Replace `backend/main.py`:

```python
"""FastAPI application for streamrip web UI."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import auth, config, downloads, library, websocket
from .api.websocket import manager
from .models.database import AppDatabase
from .services.download import DownloadService
from .services.event_bus import EventBus
from .services.library import LibraryService

logger = logging.getLogger("streamrip")


def create_app(db_path: str = "data/streamrip.db") -> FastAPI:
    db = AppDatabase(db_path)
    event_bus = EventBus()

    # Wire event bus to WebSocket broadcasts
    for event_type in (
        "download_progress", "download_complete", "download_failed",
        "sync_started", "sync_complete", "library_updated", "token_expired",
    ):
        async def make_handler(et):
            async def handler(data):
                await manager.broadcast(et, data)
            return handler

        # Use default arg to capture event_type in closure
        async def _handler(data, et=event_type):
            await manager.broadcast(et, data)

        event_bus.subscribe(event_type, _handler)

    library_service = LibraryService(db, event_bus, clients={})
    download_service = DownloadService(db, event_bus, clients={}, download_path="/tmp")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("streamrip web UI started")
        yield
        logger.info("streamrip web UI shutting down")

    app = FastAPI(title="streamrip", version="3.0.0", lifespan=lifespan)

    app.state.db = db
    app.state.event_bus = event_bus
    app.state.library_service = library_service
    app.state.download_service = download_service

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    app.include_router(library.router)
    app.include_router(downloads.router)
    app.include_router(config.router)
    app.include_router(auth.router)
    app.include_router(websocket.router)

    return app
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/test_api_routes.py tests/test_app_startup.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/ backend/main.py tests/test_api_routes.py
git commit -m "feat: add REST API routes for library, downloads, config, auth, and WebSocket"
```

---

## Phase 4: Frontend

### Task 15: Initialize SvelteKit project with design system

**Files:**
- Create: `frontend/` (SvelteKit scaffold)
- Create: `frontend/src/lib/design-system/tokens.css`
- Create: `frontend/src/app.html`

- [ ] **Step 1: Scaffold SvelteKit**

```bash
cd frontend
npm create svelte@latest . -- --template skeleton --types typescript
npm install
npm install -D @sveltejs/adapter-static
```

- [ ] **Step 2: Configure adapter-static**

Replace `frontend/svelte.config.js`:

```javascript
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: 'index.html',
    }),
  },
  preprocess: vitePreprocess(),
};
```

- [ ] **Step 3: Create design system tokens**

Create `frontend/src/lib/design-system/tokens.css` — copy the full CSS custom properties from the mockup.html `<style>` block (both dark and light mode tokens, typography, spacing, shadows, buttons, tags, etc.).

- [ ] **Step 4: Create app.html with font loading**

Replace `frontend/src/app.html`:

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  %sveltekit.head%
</head>
<body>
  %sveltekit.body%
</body>
</html>
```

- [ ] **Step 5: Verify build**

```bash
cd frontend && npm run build
```
Expected: Build succeeds, output in `frontend/build/`.

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: initialize SvelteKit frontend with design system tokens"
```

---

### Task 16: Frontend layout, stores, and API client

**Files:**
- Create: `frontend/src/lib/stores/websocket.ts`
- Create: `frontend/src/lib/stores/library.ts`
- Create: `frontend/src/lib/stores/downloads.ts`
- Create: `frontend/src/lib/api/client.ts`
- Create: `frontend/src/routes/+layout.svelte`

- [ ] **Step 1: Create API client**

Create `frontend/src/lib/api/client.ts`:

```typescript
const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

export const api = {
  library: {
    getAlbums: (source: string, params?: Record<string, string>) =>
      request(`/library/${source}/albums?${new URLSearchParams(params)}`),
    getAlbum: (source: string, id: number) =>
      request(`/library/${source}/albums/${id}`),
    refresh: (source: string) =>
      request(`/library/refresh/${source}`, { method: 'POST' }),
    search: (source: string, query: string) =>
      request(`/library/search/${source}?q=${encodeURIComponent(query)}`),
  },
  downloads: {
    getQueue: () => request('/downloads/queue'),
    enqueue: (source: string, albumIds: string[]) =>
      request('/downloads/queue', {
        method: 'POST',
        body: JSON.stringify({ source, album_ids: albumIds }),
      }),
    cancel: (itemId: string) =>
      request(`/downloads/queue/${itemId}`, { method: 'DELETE' }),
    cancelAll: () =>
      request('/downloads/cancel', { method: 'POST' }),
  },
  config: {
    get: () => request('/config'),
    update: (data: Record<string, unknown>) =>
      request('/config', { method: 'PATCH', body: JSON.stringify(data) }),
  },
  auth: {
    status: () => request('/auth/status'),
  },
};
```

- [ ] **Step 2: Create WebSocket store**

Create `frontend/src/lib/stores/websocket.ts`:

```typescript
import { writable } from 'svelte/store';

type EventHandler = (data: Record<string, unknown>) => void;
const handlers = new Map<string, EventHandler[]>();

let socket: WebSocket | null = null;

export function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  socket = new WebSocket(`${protocol}//${window.location.host}/api/ws`);

  socket.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    const eventHandlers = handlers.get(msg.type) || [];
    for (const handler of eventHandlers) {
      handler(msg.data);
    }
  };

  socket.onclose = () => {
    setTimeout(connectWebSocket, 3000);
  };
}

export function onEvent(type: string, handler: EventHandler) {
  if (!handlers.has(type)) handlers.set(type, []);
  handlers.get(type)!.push(handler);
}

export const connected = writable(false);
```

- [ ] **Step 3: Create library and downloads stores**

Create `frontend/src/lib/stores/library.ts`:

```typescript
import { writable } from 'svelte/store';
import { api } from '$lib/api/client';

export const albums = writable<any[]>([]);
export const totalAlbums = writable(0);
export const currentSource = writable('qobuz');
export const searchQuery = writable('');
export const sortBy = writable('added_to_library_at');
export const filterStatus = writable('all');

export async function loadAlbums(source: string, params?: Record<string, string>) {
  const data: any = await api.library.getAlbums(source, params);
  albums.set(data.albums);
  totalAlbums.set(data.total);
}
```

Create `frontend/src/lib/stores/downloads.ts`:

```typescript
import { writable } from 'svelte/store';
import { api } from '$lib/api/client';
import { onEvent } from './websocket';

export const queue = writable<any[]>([]);
export const activeCount = writable(0);
export const totalSpeed = writable(0);

export async function loadQueue() {
  const data: any = await api.downloads.getQueue();
  queue.set(data.items);
  activeCount.set(data.active_count);
  totalSpeed.set(data.total_speed);
}

// Wire up WebSocket events
onEvent('download_progress', (data) => {
  queue.update(items =>
    items.map(item =>
      item.id === data.item_id ? { ...item, ...data } : item
    )
  );
});

onEvent('download_complete', (data) => {
  queue.update(items =>
    items.map(item =>
      item.id === data.item_id ? { ...item, status: 'complete' } : item
    )
  );
});
```

- [ ] **Step 4: Create layout with sidebar**

Create `frontend/src/routes/+layout.svelte` — implement the sidebar from `mockup.html` as a Svelte component. This includes the source selector, nav items, connection status, and theme toggle. Import `tokens.css` globally.

The layout should match the mockup's `.app-shell` grid layout (220px sidebar + main content area).

- [ ] **Step 5: Verify dev server runs**

```bash
cd frontend && npm run dev
```
Expected: Dev server starts, loads the layout shell.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat: add frontend layout, stores, API client, and WebSocket connection"
```

---

### Task 17: Library page with album grid and detail panel

**Files:**
- Create: `frontend/src/lib/components/AlbumCard.svelte`
- Create: `frontend/src/lib/components/AlbumGrid.svelte`
- Create: `frontend/src/lib/components/AlbumDetail.svelte`
- Create: `frontend/src/routes/library/+page.svelte`

- [ ] **Step 1: Create AlbumCard component**

Implement from mockup: cover art (framed, 1:1, scanline overlay), status tag, title, artist, year (mono), format (mono accent).

- [ ] **Step 2: Create AlbumGrid component**

Responsive grid: `repeat(auto-fill, minmax(200px, 1fr))`. Receives albums array as prop.

- [ ] **Step 3: Create AlbumDetail slide-in panel**

520px panel from right with metadata grid, track list, download actions. Matches mockup's `.detail-panel`.

- [ ] **Step 4: Create library page**

Wire together: toolbar (search input, sort/filter selects), AlbumGrid, AlbumDetail panel. Search queries the streaming API via `api.library.search()`.

- [ ] **Step 5: Verify in browser**

Start backend (`uvicorn backend.main:app`) and frontend dev server. Navigate to library page. Verify grid renders, search works, detail panel opens.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat: add library page with album grid, search, and detail panel"
```

---

### Task 18: Downloads page

**Files:**
- Create: `frontend/src/lib/components/DownloadQueue.svelte`
- Create: `frontend/src/routes/downloads/+page.svelte`

- [ ] **Step 1: Create DownloadQueue component**

Queue items with cover thumbnail, title/artist, progress bar, cancel button. Stats cards at top. Matches mockup.

- [ ] **Step 2: Create downloads page**

Wire queue store, load on mount, WebSocket updates for real-time progress.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat: add downloads page with queue and real-time progress"
```

---

### Task 19: Sync page

**Files:**
- Create: `frontend/src/lib/components/SyncDiff.svelte`
- Create: `frontend/src/routes/sync/+page.svelte`

- [ ] **Step 1: Create SyncDiff component**

Checkbox list of new albums, removed albums section. "Download All" and "Download Selected" buttons.

- [ ] **Step 2: Create sync page**

Stats cards, diff sections, sync now button.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat: add sync page with diff view and selective download"
```

---

### Task 20: Settings page

**Files:**
- Create: `frontend/src/routes/settings/+page.svelte`

- [ ] **Step 1: Create settings page**

Per-source credential sections, download config, conversion, auto-sync. Toggle components, save button. All reads/writes via config API.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/
git commit -m "feat: add settings page with config management"
```

---

## Phase 5: Integration & Deployment

### Task 21: SyncService

**Files:**
- Create: `backend/services/sync.py`
- Create: `backend/api/sync.py`
- Modify: `backend/main.py`
- Test: `tests/test_sync_service.py`

- [ ] **Step 1: Write sync service tests**

Test: diff calculation (new albums, removed albums), sync run recording.

- [ ] **Step 2: Implement SyncService**

```python
class SyncService:
    async def get_diff(source) -> SyncDiff
    async def run_sync(source, download_new=False) -> SyncRunSummary
    async def schedule(source, interval) -> sets up asyncio background task
```

Diff logic: fetch streaming library, compare against DB albums, identify new and removed.

- [ ] **Step 3: Add sync API routes and wire into main.py**

- [ ] **Step 4: Add Tidal auto-refresh background task**

In `backend/main.py` lifespan, start a background task that checks `token_expiry` config value and calls `_refresh_access_token()` when approaching expiry.

- [ ] **Step 5: Run tests and commit**

```bash
git add backend/services/sync.py backend/api/sync.py tests/test_sync_service.py backend/main.py
git commit -m "feat: add SyncService with diff, auto-sync, and Tidal token refresh"
```

---

### Task 22: Docker packaging

**Files:**
- Create: `docker/Dockerfile`
- Create: `docker/docker-compose.yml`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Stage 1: Build frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir poetry && poetry install --no-dev --no-interaction
COPY backend/ ./backend/
COPY streamrip/ ./streamrip/
COPY --from=frontend /app/frontend/build ./backend/static/
EXPOSE 8080
CMD ["poetry", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
version: '3.8'
services:
  streamrip:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "8080:8080"
    volumes:
      - /mnt/music:/music
      - streamrip-data:/data
    environment:
      - STREAMRIP_DB_PATH=/data/streamrip.db

volumes:
  streamrip-data:
```

- [ ] **Step 3: Build and test locally**

```bash
docker build -f docker/Dockerfile -t streamrip .
docker run -p 8080:8080 streamrip
```
Expected: App starts, UI accessible at `http://localhost:8080`.

- [ ] **Step 4: Commit**

```bash
git add docker/
git commit -m "feat: add Docker packaging with multi-stage build"
```

---

### Task 23: Serve static frontend from FastAPI

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add static file serving**

In `backend/main.py`, after all API routes are registered, add:

```python
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        file_path = os.path.join(static_dir, path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(static_dir, "index.html"))
```

This serves the SvelteKit static build and falls back to `index.html` for client-side routing.

- [ ] **Step 2: Verify end-to-end**

Build frontend, copy to `backend/static/`, start server, access `http://localhost:8080`.

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: serve SvelteKit static build from FastAPI"
```

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 1-7 | Fix P0 bugs in Tidal client, metadata, tagger, SoundCloud |
| 2 | 8-11 | Project structure, database, schemas, event bus, FastAPI skeleton |
| 3 | 12-14 | LibraryService, DownloadService, all API routes |
| 4 | 15-20 | SvelteKit frontend — all pages |
| 5 | 21-23 | SyncService, Docker, static serving |
