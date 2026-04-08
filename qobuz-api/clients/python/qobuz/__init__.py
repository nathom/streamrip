"""Async Python client for the Qobuz API."""

from .client import QobuzClient
from .errors import (
    AuthenticationError,
    ForbiddenError,
    InvalidAppError,
    NonStreamableError,
    NotFoundError,
    QobuzError,
    RateLimitError,
)
from .types import (
    Album,
    AlbumSummary,
    ArtistRole,
    ArtistSummary,
    AudioInfo,
    Award,
    FavoriteIds,
    FileUrl,
    Genre,
    ImageSet,
    Label,
    LastUpdate,
    Playlist,
    Rights,
    Session,
    Track,
    UserSummary,
)

__all__ = [
    "QobuzClient",
    "QobuzError", "AuthenticationError", "ForbiddenError", "InvalidAppError",
    "NonStreamableError", "NotFoundError", "RateLimitError",
    "Album", "AlbumSummary", "ArtistRole", "ArtistSummary", "AudioInfo", "Award",
    "FavoriteIds", "FileUrl", "Genre", "ImageSet", "Label", "LastUpdate",
    "Playlist", "Rights", "Session", "Track", "UserSummary",
]
