"""Tests for HTTP transport layer."""

import pytest
from aioresponses import aioresponses

from qobuz._http import HttpTransport
from qobuz.errors import AuthenticationError

BASE = "https://www.qobuz.com/api.json/0.2"


class TestHttpTransport:
    async def test_get_sends_app_id_header(self):
        transport = HttpTransport(app_id="123", user_auth_token="tok")
        with aioresponses() as m:
            m.get(f"{BASE}/test/endpoint", payload={"ok": True})
            async with transport:
                status, body = await transport.get("test/endpoint", {})
            assert status == 200
            assert body == {"ok": True}

    async def test_get_sends_auth_token_header(self):
        transport = HttpTransport(app_id="123", user_auth_token="my-token")
        with aioresponses() as m:
            m.get(f"{BASE}/user/get", payload={"user": {}}, repeat=True)
            async with transport:
                status, body = await transport.get("user/get", {})
            assert status == 200

    async def test_get_without_auth_token(self):
        transport = HttpTransport(app_id="123")
        with aioresponses() as m:
            m.get(f"{BASE}/album/get?album_id=abc", payload={"id": "abc"})
            async with transport:
                status, body = await transport.get("album/get", {"album_id": "abc"})
            assert status == 200
            assert body["id"] == "abc"

    async def test_get_passes_query_params(self):
        transport = HttpTransport(app_id="123", user_auth_token="tok")
        with aioresponses() as m:
            m.get(f"{BASE}/album/get?album_id=xyz", payload={"id": "xyz"})
            async with transport:
                status, body = await transport.get("album/get", {"album_id": "xyz"})
            assert status == 200

    async def test_post_form_sends_data(self):
        transport = HttpTransport(app_id="123", user_auth_token="tok")
        with aioresponses() as m:
            m.post(f"{BASE}/favorite/create", payload={"status": "success"})
            async with transport:
                status, body = await transport.post_form(
                    "favorite/create", {"album_ids": "abc"}
                )
            assert status == 200
            assert body["status"] == "success"

    async def test_post_json_sends_json_body(self):
        transport = HttpTransport(app_id="123", user_auth_token="tok")
        with aioresponses() as m:
            m.post(
                f"{BASE}/track/getList",
                payload={"tracks": {"items": []}},
            )
            async with transport:
                status, body = await transport.post_json(
                    "track/getList", {"tracks_id": [1, 2]}
                )
            assert status == 200

    async def test_get_raises_on_401(self):
        transport = HttpTransport(app_id="123", user_auth_token="bad")
        with aioresponses() as m:
            m.get(
                f"{BASE}/user/login",
                status=401,
                payload={
                    "status": "error",
                    "code": 401,
                    "message": "Auth required",
                },
            )
            async with transport:
                with pytest.raises(AuthenticationError):
                    await transport.get("user/login", {}, raise_errors=True)

    async def test_get_no_raise_when_disabled(self):
        transport = HttpTransport(app_id="123", user_auth_token="bad")
        with aioresponses() as m:
            m.get(
                f"{BASE}/user/login",
                status=401,
                payload={"message": "Auth required"},
            )
            async with transport:
                status, body = await transport.get(
                    "user/login", {}, raise_errors=False
                )
            assert status == 401
            assert body["message"] == "Auth required"

    async def test_headers_include_user_agent(self):
        transport = HttpTransport(app_id="app1", user_auth_token="tok1")
        headers = transport._headers()
        assert "User-Agent" in headers
        assert headers["X-App-Id"] == "app1"
        assert headers["X-User-Auth-Token"] == "tok1"

    async def test_headers_omit_token_when_none(self):
        transport = HttpTransport(app_id="app1")
        headers = transport._headers()
        assert "X-User-Auth-Token" not in headers
        assert headers["X-App-Id"] == "app1"
