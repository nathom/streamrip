"""Streaming API — file URLs with request signing, sessions, and playback reporting."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from qobuz.types import FileUrl, Session

QUALITY_MAP = {1: 5, 2: 6, 3: 7, 4: 27}


def _compute_signature(
    track_id: str,
    format_id: str,
    intent: str,
    timestamp: str,
    app_secret: str,
) -> str:
    """Compute the MD5 request signature for track/getFileUrl.

    The raw string matches the Qobuz API's expected format:
        ``trackgetFileUrlformat_id{format_id}intent{intent}track_id{track_id}{timestamp}{app_secret}``
    """
    raw = f"trackgetFileUrlformat_id{format_id}intent{intent}track_id{track_id}{timestamp}{app_secret}"
    return hashlib.md5(raw.encode()).hexdigest()


class StreamingAPI:
    """High-level methods for streaming, sessions, and playback telemetry.

    Args:
        transport: An :class:`~qobuz._http.HttpTransport` instance (or mock).
        app_secret: Qobuz app secret used for request signing.
            Required for :meth:`get_file_url` and :meth:`start_session`.
    """

    def __init__(self, transport: Any, app_secret: str | None = None) -> None:
        self._transport = transport
        self._app_secret = app_secret

    # -- File URL (signed) ---------------------------------------------------

    async def get_file_url(
        self,
        track_id: int,
        quality: int = 3,
        intent: str = "stream",
    ) -> FileUrl:
        """Get a streamable/downloadable file URL for a track.

        Args:
            track_id: Qobuz track ID.
            quality: Quality tier 1-4 (mapped to Qobuz format IDs 5, 6, 7, 27).
            intent: ``"stream"`` or ``"download"``.

        Returns:
            :class:`~qobuz.types.FileUrl` with the resolved URL template.

        Raises:
            ValueError: If *app_secret* was not provided at construction time.
        """
        if self._app_secret is None:
            raise ValueError("app_secret is required for get_file_url")

        format_id = QUALITY_MAP.get(quality, 7)
        unix_ts = time.time()
        sig = _compute_signature(
            track_id=str(track_id),
            format_id=str(format_id),
            intent=intent,
            timestamp=str(unix_ts),
            app_secret=self._app_secret,
        )

        params: dict[str, Any] = {
            "track_id": track_id,
            "format_id": format_id,
            "intent": intent,
            "request_ts": unix_ts,
            "request_sig": sig,
        }

        _status, body = await self._transport.get("track/getFileUrl", params)
        return FileUrl.from_dict(body)

    # -- Session (signed) ----------------------------------------------------

    async def start_session(self) -> Session:
        """Start a streaming session.

        The request signature for this endpoint uses a different formula::

            MD5(f"qbz-1{timestamp}{app_secret}")

        Returns:
            :class:`~qobuz.types.Session` with session ID and expiry.

        Raises:
            ValueError: If *app_secret* was not provided.
        """
        if self._app_secret is None:
            raise ValueError("app_secret is required for start_session")

        timestamp = str(int(time.time()))
        sig = hashlib.md5(
            f"qbz-1{timestamp}{self._app_secret}".encode()
        ).hexdigest()

        data: dict[str, Any] = {
            "request_ts": timestamp,
            "request_sig": sig,
        }

        _status, body = await self._transport.post_form("session/start", data)
        return Session.from_dict(body)

    # -- Playback reporting --------------------------------------------------

    async def report_start(
        self,
        track_id: int,
        format_id: int,
        user_id: int,
    ) -> dict:
        """Report the start of track playback.

        Sends a POST to ``track/reportStreamingStart`` with form-encoded data
        containing a JSON-serialized events array.

        Args:
            track_id: Qobuz track ID.
            format_id: Audio format ID.
            user_id: Current user ID.

        Returns:
            Raw API response dict.
        """
        event = {
            "track_id": track_id,
            "format_id": format_id,
            "user_id": user_id,
        }
        data = {"events": json.dumps([event])}

        _status, body = await self._transport.post_form(
            "track/reportStreamingStart", data
        )
        return body

    async def report_end(self, events: list[dict]) -> dict:
        """Report the end of track playback.

        Sends a POST to ``track/reportStreamingEndJson`` with a JSON body.

        Args:
            events: List of playback event dicts.

        Returns:
            Raw API response dict.
        """
        _status, body = await self._transport.post_json(
            "track/reportStreamingEndJson", {"events": events}
        )
        return body

    async def report_context(
        self,
        track_context_uuid: str,
        data: dict,
    ) -> dict:
        """Report track playback context.

        Sends a POST to ``event/reportTrackContext`` with a JSON body.

        Args:
            track_context_uuid: UUID for the track context.
            data: Context data dict (e.g., source, album_id).

        Returns:
            Raw API response dict.
        """
        _status, body = await self._transport.post_json(
            "event/reportTrackContext",
            {"track_context_uuid": track_context_uuid, "data": data},
        )
        return body

    async def dynamic_suggest(
        self,
        listened_track_ids: list[int],
        limit: int = 50,
    ) -> dict:
        """Get dynamic track suggestions based on listening history.

        Sends a POST to ``dynamic/suggest`` with a JSON body.

        Args:
            listened_track_ids: List of recently listened track IDs.
            limit: Maximum number of suggestions (default 50).

        Returns:
            Raw API response dict.
        """
        _status, body = await self._transport.post_json(
            "dynamic/suggest",
            {"listened_track_ids": listened_track_ids, "limit": limit},
        )
        return body
