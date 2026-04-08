"""Discovery API — browse new releases, curated playlists, genres."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import Genre, PaginatedResult

if TYPE_CHECKING:
    from ._http import HttpTransport


class DiscoveryAPI:
    """Browse and discover content on Qobuz."""

    def __init__(self, transport: HttpTransport):
        self._t = transport

    async def list_genres(self) -> list[Genre]:
        _, body = await self._t.get("genre/list", {})
        items = body.get("genres", {}).get("items", [])
        return [Genre.from_dict(g) for g in items]

    async def get_index(self, genre_ids: list[int] | None = None) -> dict[str, Any]:
        """Get the discovery index page. Returns raw containers dict."""
        params: dict[str, Any] = {}
        if genre_ids:
            params["genre_ids"] = ",".join(str(g) for g in genre_ids)
        _, body = await self._t.get("discover/index", params)
        return body.get("containers", {})

    async def new_releases(
        self, genre_ids: list[int] | None = None, offset: int = 0, limit: int = 50
    ) -> PaginatedResult:
        params = self._build_params(genre_ids, offset, limit)
        _, body = await self._t.get("discover/newReleases", params)
        return PaginatedResult.from_dict(body)

    async def curated_playlists(
        self, genre_ids: list[int] | None = None, offset: int = 0, limit: int = 20
    ) -> PaginatedResult:
        params = self._build_params(genre_ids, offset, limit)
        params["tags"] = ""
        _, body = await self._t.get("discover/playlists", params)
        return PaginatedResult.from_dict(body)

    async def ideal_discography(
        self, genre_ids: list[int] | None = None, offset: int = 0, limit: int = 48
    ) -> PaginatedResult:
        params = self._build_params(genre_ids, offset, limit)
        _, body = await self._t.get("discover/idealDiscography", params)
        return PaginatedResult.from_dict(body)

    async def album_of_the_week(
        self, genre_ids: list[int] | None = None, offset: int = 0, limit: int = 48
    ) -> PaginatedResult:
        params = self._build_params(genre_ids, offset, limit)
        _, body = await self._t.get("discover/albumOfTheWeek", params)
        return PaginatedResult.from_dict(body)

    @staticmethod
    def _build_params(genre_ids: list[int] | None, offset: int, limit: int) -> dict[str, Any]:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if genre_ids:
            params["genre_ids"] = ",".join(str(g) for g in genre_ids)
        return params
