# Qobuz Library SDK — Design Spec

> **Status:** VALIDATED (from Proxyman captures 2026-04-08)
> **Date:** 2026-04-08
> **Author:** Arthur Soares + Claude

## Purpose

Create a language-agnostic specification of the Qobuz API, plus a reference Python implementation, for library management and discovery operations. This enables building Qobuz-integrated clients in any language from a single source of truth (OpenAPI 3.1 spec).

## Deliverables

1. **OpenAPI 3.1 spec** (`spec/qobuz-api.yaml`) — machine-readable, auto-generates clients
2. **Reference Python client** (`clients/python/`) — async, typed, validates the spec against the live API
3. **Documentation** — auth flows, rate limiting, usage examples

---

## Project Structure

```
qobuz-api/
├── spec/
│   ├── qobuz-api.yaml          # OpenAPI 3.1 specification
│   └── schemas/                 # Shared JSON Schema components
│       ├── album.yaml
│       ├── artist.yaml
│       ├── track.yaml
│       ├── playlist.yaml
│       └── auth.yaml
├── clients/
│   └── python/                  # Reference implementation
│       ├── qobuz/
│       │   ├── __init__.py
│       │   ├── client.py        # Main async client
│       │   ├── auth.py          # Auth strategies (token, OAuth, spoofer)
│       │   ├── favorites.py     # Favorites operations
│       │   ├── playlists.py     # Playlist CRUD + track management
│       │   ├── catalog.py       # Albums, artists, tracks, search, discovery
│       │   ├── streaming.py     # File URLs, sessions, event reporting
│       │   ├── pagination.py    # Paginator helper
│       │   └── types.py         # Typed response models (dataclasses)
│       ├── tests/
│       │   ├── test_favorites.py
│       │   ├── test_playlists.py
│       │   ├── test_catalog.py
│       │   └── conftest.py
│       └── pyproject.toml
├── docs/
│   ├── authentication.md
│   ├── rate-limiting.md
│   └── examples/
└── README.md
```

---

## API Base

```
https://www.qobuz.com/api.json/0.2/
```

All requests include `X-App-Id: <app_id>` header. Authenticated endpoints also require `X-User-Auth-Token: <token>`.

---

## Authentication (Validated)

### Auth Headers

All requests:
```
X-App-Id: 304027809
```

Authenticated requests additionally:
```
X-User-Auth-Token: <user_auth_token>
```

### Strategy 1: Direct Token (Simplest)

User provides `app_id` and `user_auth_token` directly. Token can be extracted from:
- Browser DevTools (Network tab → any `api.json` request → `X-User-Auth-Token` header)
- Qobuz desktop app traffic capture

### Strategy 2: OAuth (App-Initiated Flow)

Validated from capture. This is a **custom Qobuz OAuth flow**, not standard OAuth2:

```
Step 1: Open browser to:
  GET https://www.qobuz.com/signin/oauth?ext_app_id={app_id}&redirect_url={callback_url}

Step 2: User logs in via web form:
  POST https://www.qobuz.com/signin/login/check
  Body: _username={email}&_password={password}&g-recaptcha-response={token}&_token={csrf}
  Response: {"success": true, "targetPath": "https://www.qobuz.com/signin/oauth?..."}

Step 3: After login, browser redirects to callback with code:
  GET {redirect_url}?code={code}&private_key={private_key}

Step 4: Exchange code for token:
  GET /api.json/0.2/oauth/callback?code={code}&private_key={private_key}
  Headers: X-App-Id: {app_id}
  Response: {"token": "<user_auth_token>", "user_id": "<user_id>"}

Step 5: Validate token via user/login:
  POST /api.json/0.2/user/login
  Headers: X-App-Id, X-User-Auth-Token
  Body: extra=partner
  Response: Full user profile with subscription, credential, last_update timestamps
```

**Key details:**
- `ext_app_id=304027809` is the Qobuz desktop app's application ID
- `redirect_url` for native apps: `qobuzapp://discover` (custom protocol)
- The OAuth consent page (Step 3) uses JavaScript `window.location` to redirect to `qobuzapp://discover?code_autorisation=<AUTH_CODE>` — the API call then uses `code` param (not `code_autorisation`)
- `private_key` in `oauth/callback` is an **app-level secret** (12 chars), NOT per-user. It's tied to `ext_app_id`.
- The login form (Step 2) requires **reCAPTCHA** — programmatic OAuth requires browser automation or user-assisted login
- For SDK: use `http://localhost:{port}/callback` as `redirect_url` and spin up a local server, or open the browser and let the user complete login manually
- The returned `token` is the `user_auth_token` for all subsequent requests
- After `oauth/callback`, the app validates via `POST user/login` which returns the full user profile including subscription tier and streaming capabilities

### Strategy 3: Spoofer (Optional Fallback)

Extracts `app_id` and `app_secret` by scraping Qobuz web player JS bundle:
1. Fetch `https://play.qobuz.com/login`
2. Extract bundle.js URL from HTML
3. Regex-extract `app_id` and seed/timezone pairs
4. Derive secrets via base64 decoding

**Status:** Fragile — breaks when Qobuz updates their web player. Include as optional utility, not core dependency.

---

## Endpoint Catalog (Validated from Captures)

### Auth & User (5 endpoints)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `oauth/callback` | App-Id | Exchange OAuth code for token. Params: `code`, `private_key`. Returns: `{token, user_id}` |
| POST | `user/login` | Both | Validate token, get full user profile. Body: `extra=partner`. Returns: user object with subscription, credential, last_update |
| GET | `user/lastUpdate` | Both | Poll for library changes. Returns: `{last_update: {favorite: unix_ts, favorite_album: unix_ts, ...}}` |
| GET | `user/tracking` | Both | Analytics. **Signed** (`request_ts` + `request_sig`). Returns: GTM tracking data |
| POST | `qws/createToken` | Both | Create WebSocket token. Body: `jwt=jwt_qws`. Returns: `{jwt_qws: {exp, jwt, endpoint: "wss://..."}}` |

### Favorites — Library Management (4 endpoints)

| Method | Endpoint | Auth | Params | Description |
|--------|----------|------|--------|-------------|
| **POST** | `favorite/create` | Both | Body: `artist_ids`, `album_ids`, `track_ids` (form-encoded) | Add to favorites. Returns: `{status: "success"}` |
| **POST** | `favorite/delete` | Both | Body: `artist_ids`, `album_ids`, `track_ids` (form-encoded) | Remove from favorites. Returns: `{status: "success"}` |
| GET | `favorite/getUserFavorites` | Both | `type` (albums/tracks/artists), `limit`, `offset` | List favorites (paginated). Returns: `{albums: {offset, limit, total, items: [...]}}` |
| GET | `favorite/getUserFavoriteIds` | Both | `limit` (up to 5000) | IDs only (fast). Returns: `{albums: ["id",...], tracks: [id,...], artists: [id,...], labels: [id,...], awards: [id,...]}` |

**Notes:**
- `favorite/create` and `favorite/delete` use **POST** with `application/x-www-form-urlencoded` body
- Send all three `*_ids` params; set unused ones to empty string
- Comma-separated IDs for batch operations

### Playlists — Library Management (7 endpoints)

| Method | Endpoint | Auth | Params | Description |
|--------|----------|------|--------|-------------|
| **POST** | `playlist/create` | Both | Body: `name`, `description`, `is_public`, `is_collaborative` (form-encoded, URL-encoded values) | Create playlist. Returns: playlist object |
| **POST** | `playlist/update` | Both | Body: `playlist_id`, `name`, `description`, `is_public`, `is_collaborative` | Update playlist metadata. Returns: updated playlist object |
| **POST** | `playlist/delete` | Both | Body: `playlist_id` | Delete playlist. Returns: `{status: "success"}` |
| **POST** | `playlist/addTracks` | Both | Body: `playlist_id`, `track_ids` (comma-sep), `no_duplicate` (bool) | Add tracks. Returns: updated playlist object |
| GET | `playlist/get` | Optional | `playlist_id`, `extra` (tracks/track_ids/getSimilarPlaylists), `offset`, `limit` | Get playlist + tracks |
| GET | `playlist/getUserPlaylists` | Both | `limit`, `filter` (default: "owner") | List user playlists |
| GET | `playlist/search` | No | `query`, `limit`, `offset` | Search public playlists |

**Playlist object shape (from capture):**
```json
{
  "id": 61997651,
  "name": "New Private Playlist",
  "description": "This is the name",
  "tracks_count": 0,
  "users_count": 0,
  "duration": 0,
  "public_at": false,
  "created_at": 1775635602,
  "updated_at": 1775635602,
  "is_public": false,
  "is_collaborative": false,
  "owner": {"id": 2113276, "name": "arthursoares"}
}
```

**Notes:**
- All write operations use **POST** with `application/x-www-form-urlencoded`
- `playlist/create`: values are URL-encoded in the form body (e.g., `name=New%20Private%20Playlist`)
- `playlist/addTracks`: supports `no_duplicate=true` to skip already-present tracks
- `playlist/deleteTracks`: uses `playlist_track_ids` (positional IDs within playlist, not global track IDs). **Not captured** — documented from python-qobuz; verify before implementing.
- `favorite/status`: documented in python-qobuz (`GET favorite/status?item=X&type=album`) but **not captured**. May still exist — verify before implementing. The `favorite/getUserFavoriteIds` endpoint is a faster alternative for checking favorites.
- `playlist/get` supports `extra=track_ids,getSimilarPlaylists` for album-detail-style enrichment

### Catalog — Albums, Artists, Tracks (10 endpoints)

| Method | Endpoint | Auth | Params | Description |
|--------|----------|------|--------|-------------|
| GET | `album/get` | Optional | `album_id`, `offset`, `limit`, `extra` (track_ids, albumsFromSameArtist) | Album detail + tracks |
| GET | `album/search` | No | `query`, `limit`, `offset` | Search albums |
| GET | `album/story` | Optional | `album_id`, `offset`, `limit` | Album editorial content |
| GET | `album/suggest` | Optional | `album_id` | Album recommendations. Returns: `{algorithm, albums: {limit, items: [...]}}` |
| GET | `artist/page` | Optional | `artist_id`, `sort` (release_date) | Full artist page (bio, similar, top tracks, releases) |
| GET | `artist/getReleasesList` | Optional | `artist_id`, `release_type` (all/album/single/etc), `track_size`, `offset`, `limit`, `sort` (release_date_by_priority) | Paginated releases |
| GET | `artist/search` | No | `query`, `limit`, `offset` | Search artists |
| GET | `track/get` | No | `track_id` | Track metadata |
| GET | `track/search` | No | `query`, `limit`, `offset` | Search tracks |
| POST | `track/getList` | Both | JSON body: `{"tracks_id": [id1, id2, ...]}` | Batch track lookup. Returns: `{tracks: {total, items: [...]}}` |

**Album object shape (from capture):**
```json
{
  "id": "p0d55tt7gv3lc",
  "title": "Virgin Lake",
  "version": null,
  "maximum_bit_depth": 24,
  "maximum_sampling_rate": 44.1,
  "maximum_channel_count": 2,
  "duration": 3487,
  "tracks_count": 14,
  "parental_warning": true,
  "release_date_original": "2026-04-03",
  "upc": "0067003183055",
  "streamable": true,
  "downloadable": true,
  "hires": true,
  "hires_streamable": true,
  "image": {
    "small": "https://static.qobuz.com/.../230.jpg",
    "thumbnail": "https://static.qobuz.com/.../50.jpg",
    "large": "https://static.qobuz.com/.../600.jpg"
  },
  "artist": {"id": 11162390, "name": "Philine Sonny", "albums_count": 25},
  "artists": [{"id": 11162390, "name": "Philine Sonny", "roles": ["main-artist"]}],
  "label": {"id": 2367808, "name": "Nettwerk Music Group"},
  "genre": {"id": 113, "name": "Alternativ und Indie", "path": [112, ...]},
  "description": "...",
  "awards": []
}
```

**Artist page shape (from capture):**
```json
{
  "id": 38895,
  "name": {"display": "Talk Talk"},
  "artist_category": "performer",
  "biography": {"content": "...", "source": null, "language": "de"},
  "images": {"portrait": {"hash": "...", "format": "jpg"}},
  "similar_artists": {"has_more": true, "items": [...]},
  "top_tracks": [{"id": ..., "title": ..., "duration": ..., "album": {...}}]
}
```

**Artist releases list shape:**
```json
{
  "has_more": true,
  "items": [{
    "id": "swefowueepqfv",
    "title": "Sliced by a Fingernail",
    "release_type": "single",
    "tracks_count": 1,
    "duration": 248,
    "dates": {"download": "2026-03-31", "original": "2026-03-31", "stream": "2026-03-31"},
    "audio_info": {"maximum_bit_depth": 24, "maximum_channel_count": 2, "maximum_sampling_rate": 96},
    "rights": {"purchasable": true, "streamable": true, "downloadable": true, "hires_streamable": true},
    "artist": {"id": 4611743, "name": {"display": "Dry Cleaning"}},
    "image": {...},
    "label": {"id": 9300, "name": "4AD"},
    "genre": {...},
    "tracks": {"has_more": false, "items": [...]}
  }]
}
```

### Discovery (6 endpoints)

| Method | Endpoint | Auth | Params | Description |
|--------|----------|------|--------|-------------|
| GET | `discover/index` | Both | `genre_ids` (comma-sep, empty for all) | Full discovery page: banners, new_releases, qobuzissims, playlists, etc. |
| GET | `discover/newReleases` | Both | `genre_ids`, `offset`, `limit` | New releases (paginated) |
| GET | `discover/playlists` | Both | `genre_ids`, `tags`, `offset`, `limit` | Curated playlists by genre |
| GET | `discover/idealDiscography` | Both | `genre_ids`, `offset`, `limit` | Ideal discography recommendations |
| GET | `discover/albumOfTheWeek` | Both | `genre_ids`, `offset`, `limit` | Album of the week |
| GET | `genre/list` | Both | (none) | All genres. Returns: `{genres: {limit, offset, total, items: [{id, color, name, path, slug}]}}` |

**Genre object:**
```json
{"id": 112, "color": "#5eabc1", "name": "Pop/Rock", "path": [112], "slug": "pop-rock"}
```

**Discovery index shape (containers):**
```json
{
  "containers": {
    "banners": {"id": "banners", "data": {"has_more": false, "items": [...]}},
    "new_releases": {"id": "newReleases", "data": {"has_more": true, "items": [...]}},
    "recent_releases": {"id": "recentReleases", "data": {...}},
    "qobuzissims": {"id": "qobuzissims", "data": {...}},
    "playlists": {"id": "playlists", "data": {...}},
    "ideal_discography": {"id": "idealDiscography", "data": {...}}
  }
}
```

### Streaming (6 endpoints)

| Method | Endpoint | Auth | Signed | Params | Description |
|--------|----------|------|--------|--------|-------------|
| GET | `file/url` | Both | **Yes** | `track_id`, `format_id`, `intent` (stream), `request_ts`, `request_sig` | Get streaming URL. Returns: url_template, segments, key, blob |
| POST | `session/start` | Both | **Yes** | Body: `profile=qbz-1&request_ts=X&request_sig=Y` | Start playback session. Returns: `{session_id, profile, expires_at}` |
| POST | `track/reportStreamingStart` | Both | No | Body: `events=[{track_id, date, user_id, format_id}]` (URL-encoded JSON array) | Report stream start. Returns: `{transUId, status, code}` |
| POST | `track/reportStreamingEndJson` | Both | No | JSON body: `{events: [{blob, track_context_uuid, start_stream, online, local, duration}], renderer_context: {software_version}}` | Report stream end. Returns: `{status: "success"}` |
| POST | `event/reportTrackContext` | Both | No | JSON body: `{version, events: [{track_context_uuid, data: {contentGroupType, contentGroupId, ...}}]}` | Report track context. Returns: `{status: "success"}` |
| POST | `dynamic/suggest` | Both | No | JSON body: `{limit, listened_tracks_ids: [...]}` | Dynamic suggestions during playback. Returns: `{algorithm, tracks: {limit, items: [...]}}` |

**file/url response shape:**
```json
{
  "file_type": "full",
  "track_id": 33967376,
  "format_id": 7,
  "audio_file_id": 18764294,
  "sampling_rate": 96000,
  "bits_depth": 24,
  "n_channels": 2,
  "duration": 133.29,
  "n_samples": 12796090,
  "mime_type": "audio/mp4; codecs=\"flac\"",
  "url_template": "https://streaming-qobuz-sec.akamaized.net/file?...&s=$SEGMENT$&...",
  "n_segments": 14,
  "key_id": "bfff4e0a-b8d9-6de0-81d8-833f326f3082",
  "key": "qbz-1.<encrypted>",
  "restrictions": [{"code": "FormatRestrictedByFormatAvailability"}],
  "blob": "<opaque_tracking_blob>"
}
```

**Request signing:**
```
signature_input = f"fileUrlformat_id{format_id}intentstreamtrack_id{track_id}{request_ts}{app_secret}"
request_sig = MD5(signature_input)
```

Note: The `file/url` endpoint replaces the older `track/getFileUrl` but uses the same signing mechanism. The response now uses segmented streaming with a `url_template` containing `$SEGMENT$` placeholder.

### Purchases (1 endpoint)

| Method | Endpoint | Auth | Params | Description |
|--------|----------|------|--------|-------------|
| GET | `purchase/getUserPurchases` | Both | `type` (albums), `offset`, `limit` | User purchases. Returns: `{albums: {offset, limit, total, items: [...]}}` |

---

## Pagination Pattern

Two pagination styles observed:

**Style 1: Standard offset/limit (most endpoints)**
```json
{
  "albums": {
    "offset": 0,
    "limit": 500,
    "total": 1101,
    "items": [...]
  }
}
```

**Style 2: has_more flag (discovery, releases)**
```json
{
  "has_more": true,
  "items": [...]
}
```

---

## Error Handling

**Error response shape (from capture):**
```json
{"status": "error", "code": 401, "message": "Session authentication is required"}
```

| HTTP Status | Meaning |
|-------------|---------|
| 200 | Success |
| 201 | Created (streaming event reports) |
| 400 | Bad request / invalid params / bad app_id |
| 401 | Auth required or invalid token |
| 403 | Forbidden (free account trying premium feature) |
| 404 | Resource not found |
| 429 | Rate limited |
| 999 | Connection/proxy error (seen in capture, retry) |

---

## Reference Client Design

### Client Interface

```python
async with QobuzClient(app_id="...", user_auth_token="...") as client:
    # Favorites
    await client.favorites.add_album("album-id")
    await client.favorites.add_tracks(["track-1", "track-2"])
    await client.favorites.remove_artist("artist-id")
    fav_ids = await client.favorites.get_ids()  # Fast — all IDs at once
    albums = await client.favorites.get_albums(limit=50)

    # Playlists
    playlist = await client.playlists.create("My Playlist", description="...", public=True)
    await client.playlists.add_tracks(playlist.id, ["track-1", "track-2"], no_duplicate=True)
    await client.playlists.update(playlist.id, name="Renamed", public=False)
    await client.playlists.delete(playlist.id)
    my_playlists = await client.playlists.list()

    # Catalog
    album = await client.catalog.get_album("album-id")
    results = await client.catalog.search_albums("radiohead")
    artist = await client.catalog.get_artist_page("artist-id")
    releases = await client.catalog.get_artist_releases("artist-id", release_type="all")
    similar = await client.catalog.suggest_album("album-id")
    tracks = await client.catalog.get_tracks([id1, id2, id3])  # Batch

    # Discovery
    index = await client.discovery.get_index(genre_ids=[112])
    new_releases = await client.discovery.new_releases(limit=50)
    genres = await client.discovery.list_genres()

    # Streaming
    session = await client.streaming.start_session()
    file_info = await client.streaming.get_file_url("track-id", quality=4)
    await client.streaming.report_start(track_id="...", format_id=27)
    await client.streaming.report_end(events=[...])
```

### Auth Strategies

```python
# Direct token
client = QobuzClient(app_id="304027809", user_auth_token="abc...")

# OAuth (opens browser, local callback server)
client = await QobuzClient.from_oauth(app_id="304027809", redirect_port=8888)

# With spoofer (auto-detect app_id)
client = QobuzClient(user_auth_token="abc...")
await client.auto_configure()  # Spoofer fetches app_id
```

### Response Models

```python
@dataclass
class Album:
    id: str
    title: str
    version: str | None
    artist: Artist
    artists: list[ArtistRole]
    label: Label | None
    genre: Genre | None
    image: ImageSet
    release_date_original: str | None
    duration: int
    tracks_count: int
    maximum_bit_depth: int
    maximum_sampling_rate: float
    maximum_channel_count: int
    streamable: bool
    downloadable: bool
    hires: bool
    hires_streamable: bool
    upc: str | None
    description: str | None
    awards: list[Award]

@dataclass
class Track:
    id: int
    title: str
    version: str | None
    isrc: str | None
    duration: int
    track_number: int
    disc_number: int
    explicit: bool  # parental_warning
    performer: ArtistSummary
    album: AlbumSummary
    audio_info: AudioInfo
    rights: Rights

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
    public_at: int | bool  # Unix timestamp or false
    created_at: int
    updated_at: int
    owner: UserSummary

@dataclass
class Genre:
    id: int
    name: str
    color: str
    path: list[int]
    slug: str

@dataclass
class ArtistPage:
    id: int
    name: str  # from name.display
    category: str
    biography: Biography | None
    images: ArtistImages | None
    similar_artists: list[ArtistSummary]
    top_tracks: list[Track]
```

### Error Handling

```python
class QobuzError(Exception):
    def __init__(self, status: int, code: int, message: str): ...

class AuthenticationError(QobuzError): ...    # 401
class ForbiddenError(QobuzError): ...         # 403
class NotFoundError(QobuzError): ...          # 404
class RateLimitError(QobuzError): ...         # 429
class InvalidAppError(QobuzError): ...        # 400
class NonStreamableError(QobuzError): ...     # restriction codes
```

### Design Principles

- **Async-first** — all operations are `async` via aiohttp
- **Auto-pagination** — list operations return async iterators that handle offset/limit transparently
- **Rate limiting** — built-in via `aiolimiter`, configurable requests-per-minute
- **Batch helpers** — `playlist.add_tracks()` auto-batches in chunks of 50; `catalog.get_tracks()` does batch lookups
- **Typed responses** — dataclass models for everything, not raw dicts
- **Context manager** — manages aiohttp session lifecycle
- **No streamrip dependency** — standalone package
- **Change detection** — `user/lastUpdate` polling helper for detecting library changes

---

## Key Differences from python-qobuz (Outdated Library)

| Aspect | python-qobuz (2023) | Actual API (2026 capture) |
|--------|---------------------|---------------------------|
| Write methods | All GET | All **POST** (form-encoded) |
| Auth | Email + MD5 password | OAuth flow + token auth |
| File URL endpoint | `track/getFileUrl` | `file/url` |
| File URL response | Simple `{url}` | Segmented: `{url_template, n_segments, key, key_id, blob}` |
| Session management | None | `session/start` required before streaming |
| WebSocket | None | `qws/createToken` for real-time updates |
| Discovery | `album/getFeatured` only | Full `discover/*` namespace (index, newReleases, playlists, idealDiscography, albumOfTheWeek) |
| Artist detail | `artist/get` only | `artist/page` (full page), `artist/getReleasesList` (paginated releases with sort) |
| Album enrichment | None | `album/story`, `album/suggest` |
| Playlist enrichment | None | `playlist/story`, `getSimilarPlaylists` |
| Favorite IDs | Not available | `favorite/getUserFavoriteIds` (fast, up to 5000) |
| Batch track lookup | Not available | `track/getList` (POST with JSON body) |
| Streaming reports | GET with query params | POST with form-encoded or JSON body |

---

## Capture Source

All endpoint shapes validated from Proxyman captures:
- `captures/Qobuz Helper_04-08-2026-10-09-15.har` — Qobuz desktop app (142 API calls)
- `captures/www.qobuz.com_04-08-2026-10-09-49.har` — Chrome OAuth login flow
