"""Async HTTP transport for the Qobuz API."""

from __future__ import annotations

from typing import Any

import aiohttp
from aiolimiter import AsyncLimiter

from qobuz.errors import raise_for_status

BASE_URL = "https://www.qobuz.com/api.json/0.2"

_USER_AGENT = "qobuz-python-sdk/0.1.0"


class HttpTransport:
    """Low-level async HTTP client for the Qobuz REST API.

    Manages session lifecycle, auth headers, rate limiting, and error mapping.
    Must be used as an async context manager::

        async with HttpTransport(app_id="...", user_auth_token="...") as t:
            status, body = await t.get("album/get", {"album_id": "abc"})
    """

    def __init__(
        self,
        app_id: str,
        user_auth_token: str | None = None,
        requests_per_minute: int = 30,
    ) -> None:
        self.app_id = app_id
        self.user_auth_token = user_auth_token
        self._limiter = AsyncLimiter(requests_per_minute, 60)
        self._session: aiohttp.ClientSession | None = None

    # -- Header helpers -------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        """Build request headers with app ID and optional auth token."""
        h: dict[str, str] = {
            "User-Agent": _USER_AGENT,
            "X-App-Id": self.app_id,
        }
        if self.user_auth_token is not None:
            h["X-User-Auth-Token"] = self.user_auth_token
        return h

    # -- Context manager ------------------------------------------------------

    async def __aenter__(self) -> HttpTransport:
        self._session = aiohttp.ClientSession(headers=self._headers())
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    # -- Request methods ------------------------------------------------------

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        raise_errors: bool = True,
    ) -> tuple[int, dict]:
        """Send a GET request.

        Returns:
            ``(status_code, json_body)`` tuple.

        Raises:
            QobuzError subclass when *raise_errors* is True and the API
            returns an error status code.
        """
        url = f"{BASE_URL}/{endpoint}"
        async with self._limiter:
            assert self._session is not None, "Use HttpTransport as an async context manager"
            async with self._session.get(url, params=params) as resp:
                status = resp.status
                body = await resp.json()
        if raise_errors:
            raise_for_status(status, body)
        return status, body

    async def post_form(
        self,
        endpoint: str,
        data: dict[str, Any],
        *,
        raise_errors: bool = True,
    ) -> tuple[int, dict]:
        """Send a POST request with form-encoded body.

        Returns:
            ``(status_code, json_body)`` tuple.
        """
        url = f"{BASE_URL}/{endpoint}"
        async with self._limiter:
            assert self._session is not None, "Use HttpTransport as an async context manager"
            async with self._session.post(url, data=data) as resp:
                status = resp.status
                body = await resp.json()
        if raise_errors:
            raise_for_status(status, body)
        return status, body

    async def post_json(
        self,
        endpoint: str,
        json_body: dict[str, Any],
        *,
        raise_errors: bool = True,
    ) -> tuple[int, dict]:
        """Send a POST request with a JSON body.

        Returns:
            ``(status_code, json_body)`` tuple.
        """
        url = f"{BASE_URL}/{endpoint}"
        async with self._limiter:
            assert self._session is not None, "Use HttpTransport as an async context manager"
            async with self._session.post(url, json=json_body) as resp:
                status = resp.status
                body = await resp.json()
        if raise_errors:
            raise_for_status(status, body)
        return status, body
