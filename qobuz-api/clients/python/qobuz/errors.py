"""Qobuz API error hierarchy."""

from __future__ import annotations


class QobuzError(Exception):
    """Base exception for all Qobuz API errors."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"[{status}] {message}")


class AuthenticationError(QobuzError):
    """401 — Invalid or expired token."""


class ForbiddenError(QobuzError):
    """403 — Insufficient permissions (e.g., free account)."""


class NotFoundError(QobuzError):
    """404 — Resource not found."""


class RateLimitError(QobuzError):
    """429 — Too many requests."""


class InvalidAppError(QobuzError):
    """400 — Invalid app_id or bad request."""


class NonStreamableError(QobuzError):
    """Track has streaming restrictions."""


_STATUS_MAP: dict[int, type[QobuzError]] = {
    400: InvalidAppError,
    401: AuthenticationError,
    403: ForbiddenError,
    404: NotFoundError,
    429: RateLimitError,
}


def raise_for_status(status: int, body: dict) -> None:
    """Raise the appropriate QobuzError if status indicates failure."""
    if status < 400:
        return
    exc_cls = _STATUS_MAP.get(status, QobuzError)
    message = body.get("message", f"HTTP {status}")
    raise exc_cls(status=status, message=message)
