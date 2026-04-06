# Streamrip Web UI — Design Specification

**Date:** 2026-04-06
**Status:** Draft
**Author:** Arthur Soares + Claude

---

## Overview

Refactor streamrip from a CLI/TUI tool into a client-server application with a web UI for managing Qobuz and Tidal music libraries. The app runs headless on a server (e.g., roonserver) and is accessed via any browser on the network.

**Core capabilities:**
- Browse and search streaming library with rich album metadata and cover art
- Download albums/tracks with real-time progress tracking
- Sync streaming library to local disk (on-demand or scheduled)
- Configure all settings via the UI
- Search streaming services directly for albums not yet in library

**Non-goals for v1:**
- Multi-user auth (data model supports it, UI does not)
- Deezer and SoundCloud support (interfaces designed for extension)
- Playlist management (albums only)
- Mobile-responsive layout (desktop/tablet browser)
- Qobuz automatic token refresh (manual with good expiry UX)

---

## Architecture

### High-Level

```
+-------------------------------------------+
|  SvelteKit Frontend (static build)        |
|  REST + WebSocket                         |
+-------------------------------------------+
|  FastAPI Backend                          |
|  +-------+----------+-----------+-------+ |
|  |Library|Download  |  Sync     |Config | |
|  |Service|Service   | Service   |Service| |
|  +-------+----------+-----------+-------+ |
|  |     Service Layer (new)              | |
|  +--------------------------------------+ |
|  |  Existing Clients (bug-fixed)        | |
|  |  Qobuz | Tidal                       | |
|  +--------------------------------------+ |
|  |  SQLite (extended schema, WAL mode)  | |
|  +--------------------------------------+ |
+-------------------------------------------+
|  Docker container                         |
+-------------------------------------------+
```

### Monorepo Structure

```
streamrip/
+-- backend/
|   +-- main.py               # FastAPI app, startup/shutdown, static file serving
|   +-- api/
|   |   +-- auth.py            # POST /api/auth/login/{source}, GET /api/auth/status
|   |   +-- library.py         # GET /api/library/{source}/albums, search
|   |   +-- downloads.py       # POST/GET/DELETE /api/downloads/queue
|   |   +-- sync.py            # GET/POST /api/sync/*
|   |   +-- config.py          # GET/PATCH /api/config
|   |   +-- websocket.py       # WS /api/ws
|   +-- services/
|   |   +-- library.py         # LibraryService
|   |   +-- download.py        # DownloadService
|   |   +-- sync.py            # SyncService
|   |   +-- config.py          # ConfigService
|   |   +-- event_bus.py       # In-process pub/sub for real-time events
|   +-- models/
|   |   +-- database.py        # SQLite connection, migrations, WAL setup
|   |   +-- schemas.py         # Pydantic models for API request/response
|   |   +-- tables.py          # Album, Track, SyncRun table definitions
|   +-- clients/               # Existing client code, moved and bug-fixed
|   |   +-- client.py
|   |   +-- qobuz.py
|   |   +-- tidal.py
|   |   +-- downloadable.py
|   |   +-- ...
|   +-- media/                 # Existing media pipeline (Album, Track, etc.)
|   +-- metadata/              # Existing metadata/tagger code
|   +-- utils/
+-- frontend/
|   +-- src/
|   |   +-- lib/
|   |   |   +-- design-system/  # CSS tokens + base components
|   |   |   +-- components/     # App-specific components
|   |   |   +-- stores/         # Svelte stores (library, downloads, sync, ws)
|   |   |   +-- api/            # Typed API client
|   |   +-- routes/
|   |       +-- +layout.svelte  # App shell: sidebar + content area
|   |       +-- library/        # Album grid, search, detail panel
|   |       +-- downloads/      # Queue, progress, history
|   |       +-- sync/           # Diff view, auto-sync config
|   |       +-- settings/       # All configuration
|   +-- static/                 # Fonts (Atkinson Hyperlegible), favicon
|   +-- svelte.config.js        # adapter-static
+-- docker/
|   +-- Dockerfile              # Multi-stage: build frontend, serve from backend
+-- config/                     # Default config, migration scripts
+-- tests/
```

---

## Backend

### API Endpoints

```
Authentication:
  POST   /api/auth/login/{source}        Login to Qobuz/Tidal
  GET    /api/auth/status                Which sources are authenticated

Library:
  GET    /api/library/{source}/albums    Paginated album list with metadata
  GET    /api/library/{source}/albums/{id}  Album detail with tracks
  POST   /api/library/refresh/{source}   Re-fetch library from streaming API

Search:
  GET    /api/search/{source}            Search streaming service
         ?q=query&type=album&limit=20
         Returns albums with in_library + download_status merged

Downloads:
  POST   /api/downloads/queue            Add albums/tracks to queue
  GET    /api/downloads/queue            Current queue state
  DELETE /api/downloads/queue/{id}       Remove from queue
  POST   /api/downloads/cancel           Cancel active downloads

Sync:
  GET    /api/sync/status/{source}       Diff: streaming vs local
  POST   /api/sync/run/{source}          Run sync now
  GET    /api/sync/history               Past sync runs

Config:
  GET    /api/config                     Current config
  PATCH  /api/config                     Update config sections

WebSocket:
  WS     /api/ws                         Real-time events
```

### Services

**LibraryService** — Fetches and caches streaming library state.
```
get_albums(source, page, sort, filter) -> PaginatedAlbums
get_album_detail(source, album_id) -> AlbumDetail (tracks, metadata, art)
refresh_library(source) -> SyncResult (re-fetch from API, update cache)
search(source, query, media_type, limit) -> SearchResults
```

Search results include `in_library: bool` and `download_status: str` by joining against the local albums table. Users see immediately whether a search result is already downloaded.

**DownloadService** — Manages download queue and execution.
```
enqueue(items: list[DownloadRequest]) -> list[QueueItem]
cancel(item_ids: list[str])
get_queue() -> list[QueueItem]
```
Emits events via EventBus: DownloadProgress, DownloadComplete, DownloadFailed.

Uses existing Client.get_downloadable() and Track.download() with the global semaphore and retry logic.

**SyncService** — Diffs streaming library against local downloads.
```
get_diff(source) -> SyncDiff (new, removed, updated)
run_sync(source, strategy: AutoDownload | ReviewFirst)
schedule(source, interval) -> sets up background task
```

Sync runs are recorded in `sync_runs` table. Auto-sync is an asyncio background task that runs on a configurable interval.

**ConfigService** — CRUD for all configuration.
```
get() -> AppConfig
update(partial: dict) -> AppConfig
```

All config is stored in the database. On first run, if `~/.config/streamrip/config.toml` exists, it is auto-imported.

### Event Bus

In-process pub/sub using `asyncio.Queue`. No external message queue needed — this is a single-process app.

```
Events:
  DownloadProgress(item_id, track_id, bytes_done, bytes_total, speed)
  DownloadComplete(item_id, album_metadata)
  DownloadFailed(item_id, error)
  SyncStarted(source)
  SyncComplete(source, diff)
  LibraryUpdated(source, new_count)
  TokenExpired(source)
```

The WebSocket handler subscribes to the event bus and broadcasts to all connected clients.

### Token Management

**Tidal:** Automatic refresh. A background task checks `token_expiry` and calls `_refresh_access_token()` proactively before expiry. The existing refresh token flow in `tidal.py` handles this.

**Qobuz:** Manual refresh with good UX. The `user_auth_token` is a session token with no refresh endpoint. When API calls return 401:
1. Backend emits `TokenExpired(source="qobuz")` event
2. Frontend shows a notification banner: "Qobuz token expired"
3. Settings page highlights the token field with instructions
4. User pastes new token, backend calls `resolve_user_id()` to validate, saves

---

## Database

SQLite with WAL mode and 30s write timeout for async concurrency safety.

### Schema

```sql
-- Existing tables (kept for backwards compatibility)
CREATE TABLE downloads (
    id TEXT UNIQUE NOT NULL
);

CREATE TABLE failed_downloads (
    source TEXT NOT NULL,
    media_type TEXT NOT NULL,
    id TEXT UNIQUE NOT NULL
);

-- New tables

CREATE TABLE albums (
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

CREATE INDEX idx_albums_source_user ON albums(source, user_id);
CREATE INDEX idx_albums_download_status ON albums(download_status);

CREATE TABLE tracks (
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

CREATE INDEX idx_tracks_album ON tracks(album_id);

CREATE TABLE sync_runs (
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

CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### Migration

On first startup, if `~/.config/streamrip/config.toml` exists:
1. Import all config values into the `config` table
2. Import `downloads.db` track IDs into the `downloads` table
3. Import `downloaded_albums` data into the new `albums` table with `download_status = 'complete'`

The `user_id DEFAULT 1` column on `albums` and future tables allows multi-user extension without schema changes. All queries include `WHERE user_id = ?`.

---

## Frontend

### Design System

Uses the Arthur Soares design system throughout:
- **Hard edges:** `border-radius: 0` everywhere
- **Solid shadows:** 0px blur, always down-right
- **Typography:** Atkinson Hyperlegible only, monospace for metadata values
- **No transitions** except 80ms on list/nav hovers
- **Dark mode default** (warm near-black #1a1918, not cool gray)
- **Light mode** available via toggle
- **TUI decorations:** diamond, block chars, arrows in section titles
- **Album art always framed:** 2px border + shadow, scanline overlay

### App Shell

Fixed 220px sidebar with:
- Logo + version
- Source selector (Qobuz / Tidal tabs)
- Navigation: Library, Downloads, Sync, Settings
- Active nav: 3px left accent border, accent-subtle bg, weight 700
- Download count badge when queue is active
- Connection status indicator
- Theme toggle

Main content area scrolls independently.

### Pages

**Library** (default view)
- Page header: title, album count, refresh button
- Toolbar: search input, sort dropdown (added/artist/title/year), filter dropdown (all/downloaded/not downloaded/partial)
- Search queries the streaming API directly — results appear as a "Search Results" section above the library grid, each result tagged with `in_library` and `download_status`
- Album grid: responsive `auto-fill, minmax(200px, 1fr)`. Each card shows:
  - Cover art (framed, 1:1 aspect ratio, scanline overlay)
  - Status tag (top-right): Complete, Not DL, Partial, Queued
  - Title, artist, year (mono), format (mono, accent color)
- Click album -> slide-in detail panel (520px, right side)

**Album Detail** (slide-in panel)
- Large cover art (framed)
- Title (H2, 800 weight), artist, metadata grid:
  - Year, label, format, size, tracks, duration, genre, status
- Actions: Download / Re-download, Open Folder
- Track list: number, title, duration, per-track status tag
- Tracks from search results that aren't in library show a download button per-track

**Downloads**
- Stats cards: Active count, speed, total downloaded, disk usage
- Active queue: cover thumbnail, title/artist/track count, progress bar with speed, cancel button per item
- Completed history: collapsible, same layout with "Done" tags

**Sync**
- Stats cards: In Library, Downloaded, New, Missing
- "New in Library" section: checkbox list of albums added since last sync, "Download All" button, selective pick
- "Removed from Library" section: albums no longer in streaming library, shown as struck-through, files kept on disk
- Last sync timestamp, Sync Now button, Schedule button

**Settings**
- Sections with header bars:
  - Per-source credentials (Qobuz: user ID + token input; Tidal: OAuth connect button)
  - Connection status tag per source
  - Token expiry notification for Qobuz (highlighted when expired)
  - Quality preference per source
  - Download path, max connections, folder format, track format
  - Conversion toggle + codec selector
  - Auto-sync toggle + interval selector

### Real-Time Updates

Single WebSocket connection managed by `websocket.ts` store. On message, dispatches to relevant store:

```
download_progress -> downloadStore.updateProgress()
download_complete -> downloadStore.markComplete(), libraryStore.updateStatus()
download_failed   -> downloadStore.markFailed()
sync_complete     -> syncStore.updateDiff()
library_updated   -> libraryStore.invalidate()
token_expired     -> configStore.flagExpired()
```

No polling. Progress bars, queue state, and sync status update in real-time.

### SvelteKit Build

Uses `adapter-static` to compile to plain HTML/CSS/JS. FastAPI serves these via `StaticFiles`. No Node runtime needed in production.

---

## Deployment

### Docker (primary)

Multi-stage Dockerfile:
1. Stage 1: Node 20 Alpine — build SvelteKit frontend to static files
2. Stage 2: Python 3.12 slim + ffmpeg — install backend, copy static frontend

```
docker run -d \
  -p 8080:8080 \
  -v /mnt/music:/music \
  -v streamrip-data:/data \
  streamrip
```

- `/music` — mount point for download directory
- `/data` — persistent volume for SQLite databases and config
- Port 8080 — web UI accessible from any browser on the network

### CLI Preserved

The existing `rip url`, `rip search`, `rip file` commands remain functional. They use the same service layer the web UI uses. The CLI is an alternative interface for scripting and power users, not a separate system.

### Config Migration

On first run, if `~/.config/streamrip/config.toml` exists, auto-import credentials, quality preferences, and paths into the database. Existing users get a seamless transition.

---

## What We Keep vs. Build New

| Layer | Action | Effort |
|-------|--------|--------|
| Qobuz client | Fix 2 P0 bugs, wrap in service | Small |
| Tidal client | Fix 5 P0 bugs, wrap in service | Small |
| Metadata/tagger | Fix MP3 save bug (tagger.py:238), keep | Tiny |
| Downloadable | Fix SoundCloud segment ordering, keep | Small |
| Existing DB tables | Keep, add WAL mode + new tables | Small |
| CLI commands | Keep, point at service layer | Small |
| FastAPI backend | New | Medium |
| Service layer | New | Medium |
| WebSocket + event bus | New | Small |
| SvelteKit frontend | New | Large |
| Sync engine | New | Medium |
| Docker packaging | New | Small |
| Textual TUI | Retire (replaced by web UI) | -- |

### Bug Fixes Required Before Build

These P0 bugs from the code review must be fixed in the client layer before wrapping in services:

1. `tidal.py:164` — `self.user_id` never set, use `self.config.user_id`
2. `tidal.py:245-249` — `get_video_file_url` treats aiohttp response as requests.Response
3. `tidal.py:154` — `get_user_favorites` crashes on `limit=None`
4. `tidal.py:150-152` — `search` returns empty for single results (`> 1` should be `>= 1`)
5. `tidal.py:212` — Infinite recursion in `get_downloadable`, no floor on quality
6. `metadata/album.py:302` — `from_tidal` crashes when `releaseDate` absent
7. `tagger.py:238` — `audio.save(path, "v2_version=3")` should be `audio.save(path, v2_version=3)`
8. `downloadable.py:344-349` — SoundCloud segment ordering uses `as_completed` (non-deterministic)

Full bug list documented in `.ai-project/todos/bug-fixes-review-2026-04-06.md`.

---

## UI Mockup

Interactive HTML mockup at `mockup.html` in the project root. Open in browser to see all four views with the design system applied.
