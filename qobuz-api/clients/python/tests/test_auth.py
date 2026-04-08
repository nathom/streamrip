"""Tests for qobuz.auth — URL building, code extraction, credential storage."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
from aioresponses import aioresponses

from qobuz.auth import (
    APP_ID,
    BASE_URL,
    PRIVATE_KEY,
    extract_code_from_url,
    exchange_code,
    get_oauth_url,
    load_credentials,
    save_credentials,
    wait_for_callback,
)


# --- get_oauth_url ---


class TestGetOAuthUrl:
    def test_default_port(self):
        url = get_oauth_url()
        assert "ext_app_id=304027809" in url
        assert "redirect_url=http://localhost:11111/callback" in url
        assert url.startswith("https://www.qobuz.com/signin/oauth")

    def test_custom_port(self):
        url = get_oauth_url(port=9999)
        assert "redirect_url=http://localhost:9999/callback" in url


# --- extract_code_from_url ---


class TestExtractCodeFromUrl:
    def test_valid_callback_url(self):
        url = "http://localhost:11111/callback?code_autorisation=abc123"
        assert extract_code_from_url(url) == "abc123"

    def test_url_with_extra_params(self):
        url = "http://localhost:11111/callback?code_autorisation=xyz&other=1"
        assert extract_code_from_url(url) == "xyz"

    def test_missing_code_raises(self):
        with pytest.raises(ValueError, match="No code_autorisation"):
            extract_code_from_url("http://localhost:11111/callback?foo=bar")

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="No code_autorisation"):
            extract_code_from_url("http://localhost:11111/callback")


# --- wait_for_callback ---


class TestWaitForCallback:
    def test_receives_code(self):
        """Simulate a browser redirect hitting the local callback server."""
        import urllib.request

        port = 18765  # Use a non-default port to avoid conflicts

        def send_callback():
            """Send a fake callback request after the server starts."""
            import time

            time.sleep(0.2)
            try:
                urllib.request.urlopen(
                    f"http://localhost:{port}/callback?code_autorisation=test_code_123"
                )
            except Exception:
                pass  # We don't care about the response in this thread

        t = threading.Thread(target=send_callback, daemon=True)
        t.start()

        code = wait_for_callback(port=port)
        assert code == "test_code_123"
        t.join(timeout=2)

    def test_missing_code_raises(self):
        """Server should raise when callback has no code."""
        import urllib.request

        port = 18766

        def send_bad_callback():
            import time

            time.sleep(0.2)
            try:
                urllib.request.urlopen(f"http://localhost:{port}/callback?bad=param")
            except Exception:
                pass

        t = threading.Thread(target=send_bad_callback, daemon=True)
        t.start()

        with pytest.raises(RuntimeError, match="Did not receive auth code"):
            wait_for_callback(port=port)
        t.join(timeout=2)


# --- exchange_code ---


class TestExchangeCode:
    @pytest.mark.asyncio
    async def test_successful_exchange(self):
        oauth_pattern = re.compile(r"^https://www\.qobuz\.com/api\.json/0\.2/oauth/callback\?")
        login_url = f"{BASE_URL}/user/login"

        with aioresponses() as m:
            # Mock token exchange (URL includes query params from aiohttp params=)
            m.get(
                oauth_pattern,
                payload={"token": "my-token", "user_id": "12345"},
            )
            # Mock login validation
            m.post(
                login_url,
                payload={
                    "user": {"display_name": "testuser", "id": 12345},
                },
            )

            creds = await exchange_code("test-code")

            assert creds["app_id"] == APP_ID
            assert creds["user_auth_token"] == "my-token"
            assert creds["user_id"] == "12345"
            assert creds["display_name"] == "testuser"

    @pytest.mark.asyncio
    async def test_exchange_fails_on_bad_status(self):
        oauth_pattern = re.compile(r"^https://www\.qobuz\.com/api\.json/0\.2/oauth/callback\?")

        with aioresponses() as m:
            m.get(oauth_pattern, status=401)

            with pytest.raises(RuntimeError, match="Token exchange failed"):
                await exchange_code("bad-code")

    @pytest.mark.asyncio
    async def test_login_validation_fails(self):
        oauth_pattern = re.compile(r"^https://www\.qobuz\.com/api\.json/0\.2/oauth/callback\?")
        login_url = f"{BASE_URL}/user/login"

        with aioresponses() as m:
            m.get(
                oauth_pattern,
                payload={"token": "my-token", "user_id": "12345"},
            )
            m.post(login_url, status=403)

            with pytest.raises(RuntimeError, match="Login validation failed"):
                await exchange_code("test-code")


# --- save / load credentials ---


class TestCredentialStorage:
    def test_save_and_load(self, tmp_path):
        creds = {
            "app_id": "304027809",
            "user_auth_token": "tok",
            "user_id": "123",
            "display_name": "testuser",
        }
        cred_file = tmp_path / "credentials.json"

        with patch("qobuz.auth.CONFIG_DIR", tmp_path), patch(
            "qobuz.auth.CREDENTIALS_FILE", cred_file
        ):
            path = save_credentials(creds)
            assert path == cred_file
            assert cred_file.exists()

            loaded = load_credentials()
            assert loaded == creds

    def test_load_returns_none_when_missing(self, tmp_path):
        cred_file = tmp_path / "credentials.json"
        with patch("qobuz.auth.CREDENTIALS_FILE", cred_file):
            assert load_credentials() is None
