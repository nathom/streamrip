# AI Assistant Instructions

## Project Overview

Streamrip is a music download manager with a web UI for managing Qobuz and Tidal libraries. It consists of:

- **Backend**: FastAPI app in `backend/` serving REST API + WebSocket
- **Frontend**: SvelteKit app in `frontend/` using Arthur Soares Design System
- **Clients**: Existing streamrip clients in `streamrip/client/` (Qobuz, Tidal, Deezer, SoundCloud)
- **Media pipeline**: `streamrip/media/` — PendingAlbum → resolve → Album → rip → tagged audio files
- **Config**: SQLite DB (`backend/models/database.py`) + bridge to streamrip TOML config (`backend/services/config_bridge.py`)

## Key Commands

```bash
make test          # Unit tests (~1.5s, no credentials)
make test-e2e      # E2E tests (needs QOBUZ_TOKEN, QOBUZ_USER_ID env vars)
make dev           # Build frontend + start backend at :8080
make dev-backend   # Start backend only (skip frontend build)
make docker        # Build + run Docker image
```

## Architecture Decisions

- **No Main class for downloads**: `DownloadService._download_album()` uses `PendingAlbum` directly instead of `Main` to preserve logged-in client state (Main.__init__ creates new un-logged-in clients)
- **Config bridge**: `backend/services/config_bridge.py` is the single source of truth for building streamrip Config from the web DB
- **Progress hooks**: `WebProgressManager` replaces streamrip's Rich `ProgressManager` during downloads to emit WebSocket events
- **Quality values**: Streamrip uses 1-4 internally, mapped to Qobuz format IDs (5, 6, 7, 27) via `QobuzClient.get_quality()`
- **Auto-login fallback**: `_download_album` attempts `client.login()` if client isn't ready, handles the Docker cold-start scenario

## Known Issues

- Track download status in album detail only updates after full album download completes (no per-track real-time update in album view)
- `test_album_handles_failed_track` is xfail due to Album dataclass `slots=True` vs dynamic attributes
- Qobuz token refresh is manual (no OAuth refresh endpoint)

## Design System

All frontend follows `frontend/src/lib/design-system/tokens.css`:
- `border-radius: 0` everywhere
- Solid shadows, 0px blur
- Atkinson Hyperlegible font only
- Dark mode default (warm near-black #1a1918)
- No CSS transitions except 80ms on hover

## Specs and Plans

- Design spec: `docs/superpowers/specs/2026-04-06-streamrip-web-ui-design.md`
- Implementation plan: `docs/superpowers/plans/2026-04-06-streamrip-web-ui-plan.md`
- Bug fix list: `.ai-project/todos/bug-fixes-review-2026-04-06.md`
- Web UI docs: `docs/WEB_UI.md`
