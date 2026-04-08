"""Playlists API — CRUD operations and track management."""

from __future__ import annotations

from typing import Any

from qobuz._http import HttpTransport
from qobuz.types import Playlist, PaginatedResult

_BATCH_SIZE = 50


def _bool_str(v: bool) -> str:
    """Convert a Python bool to the ``"true"``/``"false"`` strings Qobuz expects."""
    return "true" if v else "false"


class PlaylistsAPI:
    """High-level wrapper around the ``playlist/*`` endpoints."""

    def __init__(self, transport: HttpTransport) -> None:
        self._t = transport

    # -- Write operations (POST form-encoded) ---------------------------------

    async def create(
        self,
        name: str,
        description: str = "",
        public: bool = False,
        collaborative: bool = False,
    ) -> Playlist:
        """Create a new playlist.

        Returns the newly created :class:`Playlist`.
        """
        data: dict[str, Any] = {
            "name": name,
            "description": description,
            "is_public": _bool_str(public),
            "is_collaborative": _bool_str(collaborative),
        }
        _status, body = await self._t.post_form("playlist/create", data)
        return Playlist.from_dict(body)

    async def update(
        self,
        playlist_id: int | str,
        *,
        name: str | None = None,
        description: str | None = None,
        public: bool | None = None,
        collaborative: bool | None = None,
    ) -> Playlist:
        """Update an existing playlist. Only non-``None`` params are sent."""
        data: dict[str, Any] = {"playlist_id": str(playlist_id)}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if public is not None:
            data["is_public"] = _bool_str(public)
        if collaborative is not None:
            data["is_collaborative"] = _bool_str(collaborative)
        _status, body = await self._t.post_form("playlist/update", data)
        return Playlist.from_dict(body)

    async def delete(self, playlist_id: int | str) -> None:
        """Delete a playlist."""
        await self._t.post_form("playlist/delete", {"playlist_id": str(playlist_id)})

    async def add_tracks(
        self,
        playlist_id: int | str,
        track_ids: list[int],
        no_duplicate: bool = False,
    ) -> None:
        """Add tracks to a playlist, auto-batching in chunks of 50."""
        for i in range(0, len(track_ids), _BATCH_SIZE):
            batch = track_ids[i : i + _BATCH_SIZE]
            data: dict[str, Any] = {
                "playlist_id": str(playlist_id),
                "track_ids": ",".join(str(tid) for tid in batch),
            }
            if no_duplicate:
                data["no_duplicate"] = "true"
            await self._t.post_form("playlist/addTracks", data)

    # -- Read operations (GET) ------------------------------------------------

    async def get(
        self,
        playlist_id: int | str,
        extra: str = "tracks",
        offset: int = 0,
        limit: int = 50,
    ) -> Playlist:
        """Fetch a single playlist by ID."""
        _status, body = await self._t.get(
            "playlist/get",
            {
                "playlist_id": str(playlist_id),
                "extra": extra,
                "offset": offset,
                "limit": limit,
            },
        )
        return Playlist.from_dict(body)

    async def list(
        self,
        limit: int = 500,
        filter: str = "owner",
    ) -> PaginatedResult:
        """List the current user's playlists."""
        _status, body = await self._t.get(
            "playlist/getUserPlaylists",
            {"limit": limit, "filter": filter},
        )
        return PaginatedResult.from_dict(body, key="playlists")

    async def search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedResult:
        """Search for playlists."""
        _status, body = await self._t.get(
            "playlist/search",
            {"query": query, "limit": limit, "offset": offset},
        )
        return PaginatedResult.from_dict(body, key="playlists")
