"""Test that the FastAPI app starts and serves basic routes."""

import pytest
from httpx import ASGITransport, AsyncClient
from backend.main import create_app


class TestAppStartup:
    async def test_health_check(self):
        app = create_app(db_path=":memory:")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_auth_status(self):
        app = create_app(db_path=":memory:")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/auth/status")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
