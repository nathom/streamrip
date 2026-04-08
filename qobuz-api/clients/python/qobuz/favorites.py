"""Favorites API — add, remove, list, and get IDs for Qobuz favorites."""

from __future__ import annotations

from dataclasses import dataclass

from qobuz._http import HttpTransport
from qobuz.types import Album, FavoriteIds, PaginatedResult


@dataclass
class FavoriteAlbums:
    """Paginated list of favorite albums with parsed Album objects."""

    items: list[Album]
    total: int
    limit: int
    offset: int


class FavoritesAPI:
    """High-level wrapper around the Qobuz favorite/* endpoints."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    # -- Add ------------------------------------------------------------------

    async def add_album(self, album_id: str) -> None:
        """Add a single album to favorites."""
        await self._transport.post_form(
            "favorite/create",
            {"album_ids": album_id, "artist_ids": "", "track_ids": ""},
        )

    async def add_albums(self, album_ids: list[str]) -> None:
        """Add multiple albums to favorites (comma-joined IDs)."""
        await self._transport.post_form(
            "favorite/create",
            {"album_ids": ",".join(album_ids), "artist_ids": "", "track_ids": ""},
        )

    async def add_track(self, track_id: str) -> None:
        """Add a single track to favorites."""
        await self._transport.post_form(
            "favorite/create",
            {"album_ids": "", "artist_ids": "", "track_ids": track_id},
        )

    async def add_tracks(self, track_ids: list[str]) -> None:
        """Add multiple tracks to favorites (comma-joined IDs)."""
        await self._transport.post_form(
            "favorite/create",
            {"album_ids": "", "artist_ids": "", "track_ids": ",".join(track_ids)},
        )

    async def add_artist(self, artist_id: str) -> None:
        """Add a single artist to favorites."""
        await self._transport.post_form(
            "favorite/create",
            {"album_ids": "", "artist_ids": artist_id, "track_ids": ""},
        )

    # -- Remove ---------------------------------------------------------------

    async def remove_album(self, album_id: str) -> None:
        """Remove an album from favorites."""
        await self._transport.post_form(
            "favorite/delete",
            {"album_ids": album_id, "artist_ids": "", "track_ids": ""},
        )

    async def remove_track(self, track_id: str) -> None:
        """Remove a track from favorites."""
        await self._transport.post_form(
            "favorite/delete",
            {"album_ids": "", "artist_ids": "", "track_ids": track_id},
        )

    async def remove_artist(self, artist_id: str) -> None:
        """Remove an artist from favorites."""
        await self._transport.post_form(
            "favorite/delete",
            {"album_ids": "", "artist_ids": artist_id, "track_ids": ""},
        )

    # -- List -----------------------------------------------------------------

    async def get_albums(self, limit: int = 500, offset: int = 0) -> FavoriteAlbums:
        """Get favorite albums with fully parsed Album objects."""
        _, body = await self._transport.get(
            "favorite/getUserFavorites",
            {"type": "albums", "limit": limit, "offset": offset},
        )
        container = body.get("albums", {})
        return FavoriteAlbums(
            items=[Album.from_dict(item) for item in container.get("items", [])],
            total=container.get("total", 0),
            limit=container.get("limit", limit),
            offset=container.get("offset", offset),
        )

    async def get_tracks(self, limit: int = 500, offset: int = 0) -> PaginatedResult:
        """Get favorite tracks as a paginated result."""
        _, body = await self._transport.get(
            "favorite/getUserFavorites",
            {"type": "tracks", "limit": limit, "offset": offset},
        )
        return PaginatedResult.from_dict(body, key="tracks")

    async def get_artists(self, limit: int = 100, offset: int = 0) -> PaginatedResult:
        """Get favorite artists as a paginated result."""
        _, body = await self._transport.get(
            "favorite/getUserFavorites",
            {"type": "artists", "limit": limit, "offset": offset},
        )
        return PaginatedResult.from_dict(body, key="artists")

    # -- IDs ------------------------------------------------------------------

    async def get_ids(self, limit: int = 5000) -> FavoriteIds:
        """Get all favorite IDs (albums, tracks, artists, labels, awards)."""
        _, body = await self._transport.get(
            "favorite/getUserFavoriteIds",
            {"limit": limit},
        )
        return FavoriteIds.from_dict(body)
