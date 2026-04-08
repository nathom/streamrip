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
2. Open DevTools (F12) → Network tab
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

## Running Tests

```bash
cd clients/python
pip install -e ".[dev]"
pytest -v
```

## Spec

See `docs/superpowers/specs/2026-04-08-qobuz-library-sdk-design.md` for the full API specification validated from Proxyman captures.
