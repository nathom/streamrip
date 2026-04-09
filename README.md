# streamrip

A self-hosted web UI for managing and downloading your Qobuz and Tidal music libraries.

Runs as a small FastAPI + SvelteKit server in Docker (or locally) and is accessed through any browser. It syncs your streaming-service favorites into a local database, lets you search and trigger downloads with live progress, and organizes the files on disk with your preferred folder/track templates. Both Qobuz and Tidal go through standalone async Python SDKs (consumed as a git submodule) — no CLI, no TOML config, no hidden state.

> This repo started as a fork of [nathom/streamrip](https://github.com/nathom/streamrip) and has since been rebuilt around a web UI. The original `rip` CLI, the TUI, and the Deezer/SoundCloud source clients are no longer part of this project. See [Acknowledgements](#acknowledgements) for credit to the upstream.

## Features

- **Library browsing** — every album you've favorited in Qobuz or Tidal, with cover art, sortable table, and search
- **Album detail** — full track list, bit-depth / sample-rate / codec info, per-track download status
- **Search** — queries the streaming services directly; results show whether each album is already in your library
- **Downloads** — queue albums from the library or search, with real-time per-track progress pushed over WebSocket
- **Sync** — manual refresh or scheduled auto-sync to keep local library in step with the streaming service
- **Custom paths** — folder/track format templates with live preview in Settings (`{albumartist}`, `{title}`, `{container}`, `{bit_depth}`, `{sampling_rate}`, etc.)
- **Filesystem dedup** — a `.tidal.json` / `.streamrip.json` sentinel file per album folder so re-scans and reset-database operations don't re-download work you already have
- **Artwork embedding** — cover art baked into tags at configurable resolution
- **OAuth login** for Qobuz (browser flow + headless URL-paste flow for remote hosts)
- **Per-source dedup database** so Qobuz and Tidal track IDs never collide

## Requirements

- **Docker** (recommended) — everything runs inside the image, you just need a folder to mount for music and a volume for the SQLite data
- **or** Python 3.10+, Node 20+, `poetry`, `ffmpeg`, and SSH access to [`arthursoares/qobuz_api_client`](https://github.com/arthursoares/qobuz_api_client) for the SDK submodule

A **premium Qobuz or Tidal subscription** is required for downloads. This project doesn't bypass DRM or account restrictions — it uses your own credentials against the streaming services' own APIs.

## Quick start — Docker

```bash
# clone with submodules so the Qobuz + Tidal SDKs come along
git clone --recursive git@github.com:arthursoares/streamrip.git
cd streamrip

# build
docker build -f docker/Dockerfile -t streamrip .

# run — mount your music folder and a data volume for the SQLite DB
docker run -p 8080:8080 \
  -v ~/Music:/music \
  -v streamrip-data:/data \
  -e STREAMRIP_DB_PATH=/data/streamrip.db \
  streamrip
```

Open http://localhost:8080 and follow the first-time setup below.

If you forgot `--recursive`, you can initialize the submodule after the fact:

```bash
git submodule update --init --recursive
```

## Quick start — local dev

```bash
git clone --recursive git@github.com:arthursoares/streamrip.git
cd streamrip

# install backend deps + both SDKs from the submodule
make deps
poetry install

# install frontend deps
cd frontend && npm install && cd ..

# build frontend + run backend with hot-reload on :8080
make dev
```

Separate targets if you want more control:

- `make dev-backend` — backend only, assumes `backend/static/` already has a built frontend
- `make dev-frontend` — frontend only with Vite hot-reload, proxied to a running backend
- `make test` — unit tests (no credentials needed; ~1s)
- `make lint` — ruff check on `backend/`
- `make docker` — build and run the Docker image

## First-time setup

1. Open http://localhost:8080 → **Settings**.
2. **Qobuz** — click **Log in with Qobuz** to run the OAuth flow. On a remote/headless host, use **Log in via URL** instead: run the flow on your local machine, copy the redirect URL, paste it into the box.
3. **Tidal** — currently requires manually setting your access token, refresh token, user ID, and country code. The Tidal SDK supports the device-code OAuth flow, but it isn't wired into the Settings UI yet (PRs welcome).
4. Set **Download Path** to `/music` (Docker) or your preferred local path.
5. Choose **Quality** — 0 = LOW, 1 = HIGH, 2 = LOSSLESS (CD), 3 = HI_RES (Qobuz HiRes, Tidal MQA).
6. Tweak **Folder Format** and **Track Format** if you don't like the defaults. The Settings page has a live preview.
7. Click **Save**.
8. Go to **Library** → **Refresh Library** to pull in your favorites.

## Architecture (one-paragraph version)

`backend/` is a FastAPI app serving both a REST API and a WebSocket channel. `frontend/` is a SvelteKit app compiled to static HTML/CSS/JS and served by the backend. State lives in a single SQLite database (`backend/models/database.py`) — albums, tracks, config, sync history. Streaming-service access goes through [`arthursoares/qobuz_api_client`](https://github.com/arthursoares/qobuz_api_client), consumed as a git submodule at `sdks/qobuz_api_client/`, which provides two separate Python packages: `qobuz` and `tidal`. Each exposes an `AlbumDownloader` with progress callbacks that the backend wires to WebSocket events. There is no CLI, no TOML config file, no hidden process — everything the app does is controlled from the Settings page and persisted in the SQLite DB.

For more detail see [`docs/WEB_UI.md`](docs/WEB_UI.md) and [`CLAUDE.md`](CLAUDE.md).

## Repo layout

```
streamrip/
├── backend/           FastAPI app (REST + WebSocket)
│   ├── api/           Route modules (library, downloads, sync, auth, config, websocket)
│   ├── services/      Library, download, sync services wiring the SDKs to the DB
│   ├── models/        SQLite schema + Pydantic request/response models
│   └── main.py        create_app factory + lifespan
├── frontend/          SvelteKit app
│   └── src/lib/       Components, stores, API client, design system
├── sdks/
│   └── qobuz_api_client/     Git submodule: qobuz + tidal Python SDKs
├── tests/             Pytest suite covering backend services, API routes, database
├── docker/Dockerfile  Multi-stage build (Node → Python)
├── docs/WEB_UI.md     Full architecture + API reference
├── CLAUDE.md          Architecture notes for AI assistants working in the repo
├── Makefile           Dev/test/build/run targets
└── pyproject.toml     Poetry, 3.0.0, backend-only
```

## Contributing

Bug reports and PRs are welcome. Please run `make test` and `make lint` before opening a PR. For non-trivial changes, open an issue first so we can agree on the approach.

## Acknowledgements

The original [`nathom/streamrip`](https://github.com/nathom/streamrip) — this fork started from there and inherited the Qobuz/Tidal client logic, the tagging helpers, and the MQA decryption primitives. Most of that code now lives in the standalone `qobuz_api_client` SDK, but the design and much of the hard-won protocol knowledge came from upstream. Thanks to nathom, Vitiko98, Sorrow446, DashLt, and the projects that inspired streamrip in the first place:

- [qobuz-dl](https://github.com/vitiko98/qobuz-dl)
- [Qo-DL Reborn](https://github.com/badumbass/Qo-DL-Reborn)
- [Tidal-Media-Downloader](https://github.com/yaronzz/Tidal-Media-Downloader)

## Disclaimer

This software is for personal use with your own legitimately-purchased streaming subscriptions. You are responsible for complying with the terms of service of Qobuz and Tidal. The authors take no responsibility for how you use it.

## License

GPL-3.0-only, same as the upstream [`nathom/streamrip`](https://github.com/nathom/streamrip) project.
