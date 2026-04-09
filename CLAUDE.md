# AI Assistant Instructions

## Project Overview

Streamrip is a web UI for managing Qobuz and Tidal libraries — downloading, syncing, and organizing music from both services. The repo now contains only the web UI; the old streamrip CLI (`rip`, TUI, media pipeline) was removed. It consists of:

- **Backend**: FastAPI app in `backend/` serving REST API + WebSocket
- **Frontend**: SvelteKit app in `frontend/` using Arthur Soares Design System
- **SDKs**: Qobuz and Tidal Python SDKs consumed from the `sdks/qobuz_api_client` git submodule (→ `arthursoares/qobuz_api_client`). Both are installed via `make deps`. Neither depends on anything else in this repo.
- **Config**: SQLite DB (`backend/models/database.py`) stores credentials, library, and settings directly — there is no streamrip TOML bridge anymore.

## Key Commands

```bash
make deps          # Init submodule + install both SDKs (run after clone or SDK pin change)
make test          # Unit tests (~1.5s, no credentials)
make dev           # Build frontend + start backend at :8080
make dev-backend   # Start backend only (skip frontend build)
make docker        # Build + run Docker image
```

## Architecture Decisions

- **Both sources go through standalone SDKs.** `backend/services/download.py:_download_album` dispatches on `item["source"]` between `qobuz.AlbumDownloader` and `tidal.AlbumDownloader`. Both SDKs expose the same facade shape (`client.catalog`, `client.favorites`, `client.streaming`) so library/sync/search code paths are mostly source-agnostic via `hasattr(client, 'catalog')`.
- **SDKs are git submodules, not vendored copies.** The `sdks/qobuz_api_client` submodule pins an exact commit of the upstream SDK repo; Docker builds and dev installs both reference that path. Update with `git -C sdks/qobuz_api_client pull` + commit the submodule bump.
- **Progress callbacks come from the SDKs.** Both SDKs' `AlbumDownloader` takes `on_track_start` / `on_track_progress` / `on_track_complete` callbacks; `DownloadService._download_album` wires them to emit WebSocket events.
- **Per-source dedup DBs.** Qobuz uses `data/downloads.db` (legacy name preserved for existing state); Tidal uses `data/downloads-tidal.db` so track IDs from the two services can't collide.
- **Quality tiers are per-source.** The backend reads `qobuz_quality` or `tidal_quality` from the config DB — each maps onto the respective SDK's 0–3 scale.
- **Auto token refresh.** The Tidal SDK refreshes on `__aenter__` and on 401 automatically. Qobuz has no equivalent refresh endpoint — credentials are re-captured via the OAuth flow in Settings.
- **Both sources OAuth, both sources can download.** Tidal uses a device-code OAuth flow wired into Settings ("Connect Tidal" button). Qobuz uses a redirect-based OAuth flow. Tokens issued by Qobuz OAuth are bound to app `304027809`; downloads need a matching signing secret which is hardcoded in `qobuz.auth.APP_SECRET` (decoded from the official Qobuz desktop Helper bundle). Users with a manually-pasted web-player token (`798273057`) take a separate code path where the spoofer scrapes the secret from `play.qobuz.com`.

## Known Issues

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
- Cleanup plan: `~/.claude/plans/linear-tickling-aho.md`
- Web UI docs: `docs/WEB_UI.md`
