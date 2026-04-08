"""Catalog API — albums, artists, tracks, and search."""

from __future__ import annotations

from typing import Any

from qobuz._http import HttpTransport
from qobuz.types import Album, PaginatedResult, Track


class CatalogAPI:
    """Wraps album/*, artist/*, and track/* Qobuz endpoints."""

    def __init__(self, transport: HttpTransport) -> None:
        self._t = transport

    # -- Albums ---------------------------------------------------------------

    async def get_album(
        self,
        album_id: str,
        *,
        extra: str = "track_ids,albumsFromSameArtist",
    ) -> Album:
        """GET album/get — fetch a single album by ID."""
        _, body = await self._t.get("album/get", {"album_id": album_id, "extra": extra})
        return Album.from_dict(body)

    async def get_album_with_tracks(
        self,
        album_id: str,
    ) -> tuple[Album, list[Track]]:
        """GET album/get — fetch album metadata and inline track list.

        Returns (Album, list[Track]) parsed from the response's
        ``tracks.items`` array.
        """
        _, body = await self._t.get(
            "album/get", {"album_id": album_id, "extra": "track_ids"}
        )
        album = Album.from_dict(body)
        track_items = body.get("tracks", {}).get("items", [])
        tracks = [Track.from_dict(t) for t in track_items]
        return album, tracks

    async def search_albums(
        self,
        query: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResult:
        """GET album/search — search albums by query string."""
        _, body = await self._t.get(
            "album/search",
            {"query": query, "limit": limit, "offset": offset},
        )
        return PaginatedResult.from_dict(body, key="albums")

    async def suggest_album(self, album_id: str) -> list[Album]:
        """GET album/suggest — return similar albums."""
        _, body = await self._t.get("album/suggest", {"album_id": album_id})
        items = body.get("albums", {}).get("items", [])
        return [Album.from_dict(item) for item in items]

    async def get_album_story(self, album_id: str) -> list[dict]:
        """GET album/story — return story items (editorial content)."""
        _, body = await self._t.get("album/story", {"album_id": album_id})
        return body.get("items", [])

    # -- Artists --------------------------------------------------------------

    async def get_artist_page(
        self,
        artist_id: int,
        *,
        sort: str = "release_date",
    ) -> dict:
        """GET artist/page — raw dict (complex nested structure)."""
        _, body = await self._t.get(
            "artist/page",
            {"artist_id": artist_id, "sort": sort},
        )
        return body

    async def get_artist_releases(
        self,
        artist_id: int,
        *,
        release_type: str = "all",
        offset: int = 0,
        limit: int = 20,
        sort: str = "release_date_by_priority",
    ) -> PaginatedResult:
        """GET artist/getReleasesList — has_more-style pagination."""
        _, body = await self._t.get(
            "artist/getReleasesList",
            {
                "artist_id": artist_id,
                "release_type": release_type,
                "offset": offset,
                "limit": limit,
                "sort": sort,
            },
        )
        return PaginatedResult.from_dict(body)

    async def search_artists(
        self,
        query: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResult:
        """GET artist/search — search artists by query string."""
        _, body = await self._t.get(
            "artist/search",
            {"query": query, "limit": limit, "offset": offset},
        )
        return PaginatedResult.from_dict(body, key="artists")

    # -- Tracks ---------------------------------------------------------------

    async def get_track(self, track_id: int) -> Track:
        """GET track/get — fetch a single track by ID."""
        _, body = await self._t.get("track/get", {"track_id": track_id})
        return Track.from_dict(body)

    async def get_tracks(self, track_ids: list[int]) -> list[Track]:
        """POST track/getList — batch fetch tracks by IDs.

        Sends a JSON body ``{"tracks_id": [...]}``.
        Returns an empty list if *track_ids* is empty.
        """
        if not track_ids:
            return []
        _, body = await self._t.post_json(
            "track/getList",
            {"tracks_id": track_ids},
        )
        items = body.get("tracks", {}).get("items", [])
        return [Track.from_dict(item) for item in items]

    async def search_tracks(
        self,
        query: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResult:
        """GET track/search — search tracks by query string."""
        _, body = await self._t.get(
            "track/search",
            {"query": query, "limit": limit, "offset": offset},
        )
        return PaginatedResult.from_dict(body, key="tracks")
