# Streamrip Web UI

Detailed documentation for the streamrip web UI — the app-level README (`../README.md`) is the "getting started" page; this file is the reference.

## Architecture

```
          ┌──────────────────────────────┐
          │  Frontend (SvelteKit 5)      │
          │  — compiled to static HTML   │
          │  — served by backend on /    │
          └───────────────┬──────────────┘
                          │  REST + WebSocket
                          ▼
          ┌──────────────────────────────┐
          │  Backend (FastAPI)           │
          │  backend/api/                │
          │  backend/services/           │
          │  backend/models/             │
          └───────┬──────────────┬───────┘
                  │              │
                  ▼              ▼
       ┌──────────────┐  ┌──────────────┐
       │  SQLite      │  │  SDKs        │
       │  (WAL mode)  │  │              │
       │              │  │  qobuz/      │
       │  albums      │  │  tidal/      │
       │  tracks      │  │              │
       │  sync_runs   │  │  (from       │
       │  config      │  │   submodule) │
       └──────────────┘  └──────────────┘
                                  │
                                  ▼
                         Qobuz / Tidal APIs
```

Key points:
- **One process** — FastAPI serves both the static frontend and the API. There is no separate web server, no background worker daemon.
- **No TOML config** — the streamrip TOML config and `streamrip.config.Config` dataclass are gone. All settings live in the SQLite `config` table and are round-tripped through the Settings page.
- **SDKs come from a submodule** — `sdks/qobuz_api_client/` is a git submodule pinned to a specific commit of [`arthursoares/qobuz_api_client`](https://github.com/arthursoares/qobuz_api_client). Both `qobuz` and `tidal` Python packages are installed from that subdirectory via `make deps`.
- **Both sources use the same facade shape** — every SDK client exposes `client.catalog`, `client.favorites`, `client.streaming`, and can be used with `async with client:`. The backend uses `hasattr(client, 'catalog')` as the "is this an SDK client" check.
- **Downloads dispatch on source** — `DownloadService._download_album` picks `qobuz.AlbumDownloader` or `tidal.AlbumDownloader` based on `item["source"]` and wires the same progress callbacks either way.
- **Per-source dedup DBs** — Qobuz uses `data/downloads.db` (legacy name preserved for existing users), Tidal uses `data/downloads-tidal.db`. Track IDs from different services can never collide.

## First-time setup

### Qobuz (OAuth)

1. Open the **Settings** page.
2. Click **Log in with Qobuz** — this opens the Qobuz OAuth page in your browser. Sign in and authorize.
3. The backend catches the callback on `localhost:11111` and stores the resulting user ID + auth token in the SQLite DB.
4. Clients are hot-reloaded immediately; the green "Connected" dot appears next to Qobuz.

**Headless / remote hosts** (the browser callback can't reach the server):

1. On your local machine, visit the OAuth URL from the **Log in via URL** button.
2. Sign in. Instead of catching the callback, copy the full URL you were redirected to (it contains `?code_autorisation=…`).
3. Paste it into the **Redirect URL** field. The backend extracts the code and exchanges it on your behalf.

### Tidal (manual for now)

The Tidal SDK supports the device-code OAuth flow (see `tidal.auth.request_device_code` / `poll_device_code` / `refresh_access_token`), but the flow isn't wired into the Settings UI yet. In the meantime:

1. Get an access token + refresh token via another Tidal client (e.g. [`tidal-dl`](https://github.com/yaronzz/Tidal-Media-Downloader)) or by running `python -c "from tidal import auth; import asyncio; ..."` against the SDK helpers directly.
2. Write them to the SQLite DB via the API:

   ```bash
   curl -X PATCH http://localhost:8080/api/config -H "Content-Type: application/json" -d '{
     "tidal_access_token": "...",
     "tidal_refresh_token": "...",
     "tidal_user_id": "...",
     "tidal_country_code": "US",
     "tidal_token_expiry": "1893456000"
   }'
   ```

3. The backend hot-reloads the Tidal client on the next request.

The Tidal SDK will auto-refresh any token that expires within 24 hours on `__aenter__`, and also has a 401 retry path on the HTTP transport, so once credentials are in the DB you shouldn't need to touch them again unless the refresh token itself expires.

## Features

### Library

- Browse every album you've favorited on the streaming service, paginated and cached locally in SQLite
- Sortable columns: title, artist, year, added-date, download status
- Filter by title/artist text or by download status (all / downloaded / not-downloaded)
- Click an album to open the side detail panel: full track list, per-track download status, cover art, metadata
- **Refresh Library** — pulls the full favorites list from the streaming service and diffs against local state
- **Scan Folder** — walks the download directory and reconciles `.tidal.json` / `.streamrip.json` sentinel files against the DB so manually-copied albums get picked up

### Search

- Queries the streaming service directly (not the local library)
- Results show an `in_library` badge for albums already synced
- **Download** button on any result — the backend auto-creates a DB entry for the album before downloading so track statuses persist

### Downloads

- Queue albums individually or in batch (multi-select checkbox in the library table)
- Real-time progress over WebSocket: per-track status, aggregated bytes, speed, current track name
- Click a queue entry to expand the per-track breakdown
- **Force re-download** toggle bypasses the dedup DB for single downloads
- Failed tracks don't cancel the album; the `AlbumDownloader` uses `asyncio.gather(..., return_exceptions=True)` under a semaphore so one bad track can't block the rest
- Success threshold: if fewer than 80% of tracks downloaded, the whole album is marked failed (configurable in code, not yet in UI)

### Sync

- **Auto-sync** — on a schedule (1h / 6h / daily) the backend re-runs a library refresh and optionally auto-downloads new albums
- **Sync history** — every manual or auto-sync run is recorded in the `sync_runs` table with counts of found / new / removed / downloaded

### Settings

- **Source credentials** — Qobuz (OAuth), Tidal (manual tokens for now)
- **Qualities** — independent per-source: 0 LOW, 1 HIGH, 2 LOSSLESS (CD), 3 HI_RES
- **Download path**
- **Folder format** / **Track format** with live preview and sample data
- **Source subdirectories** — nest under `Qobuz/` and `Tidal/` top-level folders
- **Disc subdirectories** — multi-disc albums get `Disc N/` per CD
- **Artwork embedding** + size (small / medium / large)
- **Auto-sync** toggle + interval
- **Reset Database** — nukes library and history (config preserved) with a two-step confirmation

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `STREAMRIP_DB_PATH` | `data/streamrip.db` | Path to the SQLite database |
| `STREAMRIP_DOWNLOADS_PATH` | `/music` | Fallback download directory if none set in Settings |

Runtime paths derived from `STREAMRIP_DB_PATH`:

- `{dir}/downloads.db` — Qobuz dedup (legacy name, preserved)
- `{dir}/downloads-tidal.db` — Tidal dedup

## API reference

All endpoints live under `/api` and return JSON. Content-Type is `application/json` unless otherwise stated.

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | `{"status": "ok"}` liveness check |
| `/api/auth/status` | GET | List of sources with `authenticated`, `user_id`, `has_credentials` |
| `/api/auth/qobuz/oauth-url` | GET | `{"url": "…"}` — open in a browser to start the Qobuz OAuth flow |
| `/api/auth/qobuz/oauth-callback` | POST | Exchange an OAuth code for credentials (browser flow) |
| `/api/auth/qobuz/oauth-from-url` | POST | Extract the code from a pasted redirect URL and exchange it (headless flow) |
| `/api/library/{source}/albums` | GET | Paginated album list — `?page=1&page_size=50&sort_by=added_to_library_at&sort_dir=DESC&status=…&search=…` |
| `/api/library/{source}/albums/{id}` | GET | Album detail with tracks |
| `/api/library/refresh/{source}` | POST | Full library refresh from the streaming service |
| `/api/library/search/{source}` | GET | `?query=…&limit=20` — search the streaming service directly |
| `/api/library/scan` | POST | Reconcile `.tidal.json` / `.streamrip.json` sentinels under `downloads_path` against the DB |
| `/api/downloads/queue` | GET | Current queue with progress |
| `/api/downloads/queue` | POST | `{"source": "qobuz", "album_ids": [...], "force": false}` — enqueue |
| `/api/downloads/queue/{id}` | DELETE | Cancel a single queued/running item |
| `/api/downloads/cancel` | POST | Cancel everything |
| `/api/sync/status/{source}` | GET | Diff: new / removed vs local DB + last sync timestamp |
| `/api/sync/run/{source}` | POST | Trigger a sync run (records a row in `sync_runs`) |
| `/api/sync/history` | GET | `?source=qobuz&limit=10` — sync run history |
| `/api/config` | GET | Current config as `AppConfig` |
| `/api/config` | PATCH | Partial update as `ConfigUpdate`; hot-reloads clients if credentials changed |
| `/api/config/reset` | POST | Wipe library data (albums, tracks, sync_runs). Config and credentials are preserved. Files on disk are untouched. |
| `/api/ws` | WS | WebSocket channel — emits `download_progress`, `download_complete`, `download_failed`, `sync_started`, `sync_complete`, `library_updated`, `token_expired` |

## Testing

```bash
make test          # unit tests — ~1s, no credentials
make test-unit     # same but verbose
make lint          # ruff check on backend/
```

The test suite covers:
- `backend/services/library.py` — library fetch, search, track caching
- `backend/services/download.py` — queue management and source dispatch
- `backend/services/sync.py` — diff + run_sync + history
- `backend/models/database.py` — SQLite schema + CRUD
- `backend/api/*.py` — route contracts via the FastAPI test client
- `backend/main.py:create_app` — startup smoke test

SDK-level tests live in the submodule at `sdks/qobuz_api_client/clients/python/{tests,tidal/tests}/` — see the [upstream repo](https://github.com/arthursoares/qobuz_api_client) for those.

## Design system

Uses the [Arthur Soares Design System](../frontend/src/lib/design-system/tokens.css):

- Hard edges — `border-radius: 0` everywhere
- Solid shadows — 0px blur
- [Atkinson Hyperlegible](https://brailleinstitute.org/freefont) as the only font family
- Warm near-black (`#1a1918`) dark mode default
- TUI-inspired decorations (diamond, block characters in section headers)
- No CSS transitions except 80ms on hover

## Updating the SDK submodule

When the upstream `qobuz_api_client` repo has new commits you want to pick up:

```bash
# pull the latest on the submodule's tracked branch (main)
git -C sdks/qobuz_api_client pull --ff-only origin main

# re-install editably (only needed if SDK deps changed)
poetry run pip install -e sdks/qobuz_api_client/clients/python
poetry run pip install -e sdks/qobuz_api_client/clients/python/tidal

# commit the new pin
git add sdks/qobuz_api_client
git commit -m "chore: bump qobuz_api_client submodule to <sha>"
```

The Dockerfile also COPYs from `sdks/qobuz_api_client/clients/python/`, so rebuilding the image picks up the new pin automatically.

## Known gaps

- **Tidal OAuth flow** is implemented in the SDK but not wired into Settings — Tidal credentials currently have to be set manually through `/api/config`.
- **Track download status in album detail** only updates after the full album finishes. The per-track progress events are emitted and used by the queue panel, but the album detail panel doesn't subscribe to them yet.
- **Qobuz token refresh** is manual — the Qobuz API doesn't expose a refresh endpoint, so the credentials have to be re-captured via the OAuth flow when they expire.
- **Playlists** — neither SDK's `catalog` namespace surfaces playlists in the web UI yet. The underlying API calls exist (Tidal SDK has `FavoritesAPI.get_tracks` and `CatalogAPI.search_*`; Qobuz SDK has a full `PlaylistsAPI`), but there's no frontend surface.
