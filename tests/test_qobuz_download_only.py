"""Unit tests for the conditional download-store (free/purchased account) path.

A free Qobuz account (no streaming subscription) returns an empty
``credential.parameters`` on login. It cannot stream, but it can still download
albums it has *purchased*. These tests verify that:

* a subscriber (non-empty parameters) is NOT flagged download-only and keeps
  using ``intent=stream`` (no streaming regression),
* a free account (empty parameters) is flagged ``download_only`` without
  raising, and
* ``_request_file_url`` selects the matching ``intent`` in BOTH the signed
  request-signature preimage and the params dict.

All network calls are mocked; these run without Qobuz credentials.
"""

import hashlib
from unittest.mock import AsyncMock

from util import arun

from streamrip.client.qobuz import QobuzClient
from streamrip.config import Config


class _FakeSession:
    """Minimal stand-in for the aiohttp session used during login()."""

    def __init__(self):
        self.headers = {}

    async def close(self):
        pass


def _make_client() -> QobuzClient:
    config = Config.defaults()
    c = config.session.qobuz
    c.email_or_userid = "13103092"
    c.password_or_token = "fake-token"
    c.use_auth_token = True
    # Pre-seed app_id/secrets so login() skips the spoofer/network fetch.
    c.app_id = "123456789"
    c.secrets = ["fakesecret"]
    return QobuzClient(config)


def _login_resp(parameters):
    return {
        "user": {"credential": {"parameters": parameters}},
        "user_auth_token": "fake-uat",
    }


def _run_login(monkeypatch, parameters) -> QobuzClient:
    client = _make_client()
    monkeypatch.setattr(client, "get_session", AsyncMock(return_value=_FakeSession()))
    monkeypatch.setattr(
        client,
        "_api_request",
        AsyncMock(return_value=(200, _login_resp(parameters))),
    )
    monkeypatch.setattr(
        client, "_get_valid_secret", AsyncMock(return_value="fakesecret")
    )
    arun(client.login())
    return client


def test_subscriber_login_not_download_only(monkeypatch):
    """Non-empty credential.parameters -> NOT download_only, does not raise."""
    client = _run_login(monkeypatch, {"lossy_streaming": True, "hires_streaming": True})
    assert client.download_only is False
    assert client.logged_in is True


def test_free_account_login_sets_download_only(monkeypatch):
    """Empty credential.parameters -> download_only=True, does NOT raise."""
    client = _run_login(monkeypatch, [])
    assert client.download_only is True
    # Login still succeeds (no IneligibleError); the account can download
    # purchased content.
    assert client.logged_in is True


def _capture_file_url_params(monkeypatch, download_only: bool) -> dict:
    client = _make_client()
    client.download_only = download_only
    captured: dict = {}

    async def fake_api(epoint, params):
        captured["epoint"] = epoint
        captured["params"] = params
        return (200, {})

    monkeypatch.setattr(client, "_api_request", fake_api)
    arun(client._request_file_url("19512574", 3, "abc123secret"))
    return captured


def test_request_file_url_download_intent_when_download_only(monkeypatch):
    """download_only=True -> intent=download in BOTH params and signed preimage."""
    secret = "abc123secret"
    track_id = "19512574"
    quality = 3
    client = _make_client()
    client.download_only = True
    captured: dict = {}

    async def fake_api(epoint, params):
        captured["params"] = params
        return (200, {})

    monkeypatch.setattr(client, "_api_request", fake_api)
    arun(client._request_file_url(track_id, quality, secret))

    params = captured["params"]
    # 1. params dict uses intent=download
    assert params["intent"] == "download"
    # 2. the signed preimage used intent=download too (reconstruct + md5 match)
    format_id = QobuzClient.get_quality(quality)
    expected_preimage = (
        f"trackgetFileUrlformat_id{format_id}intentdownload"
        f"track_id{track_id}{params['request_ts']}{secret}"
    )
    assert (
        hashlib.md5(expected_preimage.encode("utf-8")).hexdigest()
        == params["request_sig"]
    )


def test_request_file_url_stream_intent_when_subscriber(monkeypatch):
    """download_only=False -> intent=stream in BOTH params and signed preimage."""
    secret = "abc123secret"
    track_id = "19512574"
    quality = 3
    client = _make_client()
    client.download_only = False
    captured: dict = {}

    async def fake_api(epoint, params):
        captured["params"] = params
        return (200, {})

    monkeypatch.setattr(client, "_api_request", fake_api)
    arun(client._request_file_url(track_id, quality, secret))

    params = captured["params"]
    assert params["intent"] == "stream"
    format_id = QobuzClient.get_quality(quality)
    expected_preimage = (
        f"trackgetFileUrlformat_id{format_id}intentstream"
        f"track_id{track_id}{params['request_ts']}{secret}"
    )
    assert (
        hashlib.md5(expected_preimage.encode("utf-8")).hexdigest()
        == params["request_sig"]
    )
