"""QobuzClient — main entry point tying all API namespaces together."""

from __future__ import annotations

from ._http import HttpTransport
from .catalog import CatalogAPI
from .discovery import DiscoveryAPI
from .favorites import FavoritesAPI
from .playlists import PlaylistsAPI
from .streaming import StreamingAPI
from .types import LastUpdate


class QobuzClient:
    """Async Qobuz API client.

    Usage::

        async with QobuzClient(app_id="...", user_auth_token="...") as client:
            albums = await client.favorites.get_albums()
            await client.playlists.create("My Playlist")
    """

    def __init__(
        self,
        app_id: str,
        user_auth_token: str | None = None,
        app_secret: str | None = None,
        requests_per_minute: int = 30,
    ):
        self._transport = HttpTransport(
            app_id=app_id,
            user_auth_token=user_auth_token,
            requests_per_minute=requests_per_minute,
        )
        self.favorites = FavoritesAPI(self._transport)
        self.playlists = PlaylistsAPI(self._transport)
        self.catalog = CatalogAPI(self._transport)
        self.discovery = DiscoveryAPI(self._transport)
        self.streaming = StreamingAPI(self._transport, app_secret=app_secret)

    async def last_update(self) -> LastUpdate:
        """Poll for library changes — returns timestamps for each section."""
        _, body = await self._transport.get("user/lastUpdate", {})
        return LastUpdate.from_dict(body)

    async def login(self) -> dict:
        """Validate the current token and get user profile."""
        _, body = await self._transport.post_form("user/login", {"extra": "partner"})
        return body

    async def __aenter__(self) -> QobuzClient:
        await self._transport.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._transport.__aexit__(*args)
