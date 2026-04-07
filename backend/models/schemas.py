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
    force: bool = False


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
    status: str = "pending"


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
