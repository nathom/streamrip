# Streamrip Web UI

A web-based interface for managing Qobuz and Tidal music libraries. Runs as a server (Docker or local) and is accessed via any browser.

## Quick Start

### Docker (recommended)

```bash
docker build -f docker/Dockerfile -t streamrip .
docker run -p 8080:8080 \
  -v ~/Music:/music \
  -v streamrip-data:/data \
  -e STREAMRIP_DB_PATH=/data/streamrip.db \
  streamrip
```

Open http://localhost:8080

### Local Development

```bash
# Install dependencies
poetry install
cd frontend && npm install && cd ..

# Run (builds frontend + starts backend)
make dev

# Or run backend only (skip frontend rebuild)
make dev-backend
```

## First-Time Setup

1. Open http://localhost:8080
2. Go to **Settings**
3. Enter your Qobuz credentials:
   - **User ID**: Your numeric Qobuz user ID
   - **Auth Token**: Get from browser DevTools (Network tab → any `api.json` request → `X-User-Auth-Token` header)
4. Set **Download Path** to `/music` (Docker) or your preferred local path
5. Click **Save**
6. Go to **Library** → click **Refresh Library** to sync your Qobuz favorites

## Features

### Library
- Browse all synced albums with cover art
- Filter by title/artist, sort by added date/artist/title/year
- Filter by download status (all/downloaded/not downloaded)
- Click album for detail panel with track list and metadata

### Search
- Search the streaming service directly for any album
- Results show whether albums are already in your library
- Download directly from search results

### Downloads
- Queue albums for download from Library or Search
- Real-time progress: per-track status, speed, completion
- Click queue items to expand per-track breakdown
- Force re-download option (bypasses download history)
- Failed downloads shown with error status

### Settings
- Qobuz/Tidal credentials with connection status
- Download quality (320kbps to 24-bit/192kHz)
- Download path, folder/track format templates
- Source subdirectories, disc subdirectories
- Artwork embedding and size
- Conversion (codec, sampling rate, bit depth)
- Booklet PDF downloads
- Auto-sync schedule

## Architecture

```
Frontend (SvelteKit)  →  REST + WebSocket  →  Backend (FastAPI)
                                                  ↓
                                            Service Layer
                                          (Library, Download, Sync)
                                                  ↓
                                         Existing streamrip clients
                                          (Qobuz, Tidal)
                                                  ↓
                                            SQLite (WAL mode)
```

- **Frontend**: SvelteKit with adapter-static, compiled to plain HTML/CSS/JS
- **Backend**: FastAPI serving the static frontend + REST API + WebSocket
- **Database**: SQLite with WAL mode for async safety
- **Downloads**: Uses existing streamrip pipeline (PendingAlbum → resolve → rip)
- **Real-time**: WebSocket pushes download progress, sync events to frontend

## Testing

```bash
# Unit tests (no credentials needed, ~1.5s)
make test

# E2E tests (requires Qobuz credentials)
QOBUZ_TOKEN=your-token QOBUZ_USER_ID=your-id make test-e2e

# All tests
make test-all
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STREAMRIP_DB_PATH` | `data/streamrip.db` | Path to SQLite database |
| `STREAMRIP_DOWNLOADS_PATH` | `/music` | Fallback download directory |
| `STREAMRIP_CONFIG_PATH` | `~/.config/streamrip/config.toml` | Path to streamrip TOML config (optional) |

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/auth/status` | GET | Authentication status per source |
| `/api/library/{source}/albums` | GET | Paginated album list |
| `/api/library/{source}/albums/{id}` | GET | Album detail with tracks |
| `/api/library/refresh/{source}` | POST | Sync library from streaming service |
| `/api/library/search/{source}` | GET | Search streaming service |
| `/api/downloads/queue` | GET/POST | Download queue management |
| `/api/downloads/queue/{id}` | DELETE | Cancel download |
| `/api/downloads/cancel` | POST | Cancel all downloads |
| `/api/sync/status/{source}` | GET | Sync diff |
| `/api/sync/run/{source}` | POST | Run sync |
| `/api/sync/history` | GET | Sync history |
| `/api/config` | GET/PATCH | Configuration |
| `/api/ws` | WebSocket | Real-time events |

## Design System

Uses the [Arthur Soares Design System](../frontend/src/lib/design-system/tokens.css):
- Hard edges (border-radius: 0)
- Solid shadows (0px blur)
- Atkinson Hyperlegible font
- Warm dark mode default
- TUI decorations (diamond, block chars)
