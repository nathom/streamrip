"""Tests for API routes."""
import pytest
from httpx import ASGITransport, AsyncClient
from backend.main import create_app


@pytest.fixture
def app():
    return create_app(db_path=":memory:")


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestLibraryRoutes:
    async def test_get_albums_empty(self, client, app):
        resp = await client.get("/api/library/qobuz/albums")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["albums"] == []

    async def test_get_albums_with_data(self, client, app):
        app.state.db.upsert_album("qobuz", "a1", "Test Album", "Test Artist")
        resp = await client.get("/api/library/qobuz/albums")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_get_album_detail(self, client, app):
        album_id = app.state.db.upsert_album("qobuz", "a1", "Test", "Artist")
        app.state.db.upsert_track(album_id, "t1", "Track 1", "Artist", track_number=1)
        resp = await client.get(f"/api/library/qobuz/albums/{album_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test"
        assert len(data["tracks"]) == 1


class TestDownloadRoutes:
    async def test_get_empty_queue(self, client):
        resp = await client.get("/api/downloads/queue")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_enqueue_download(self, client, app):
        app.state.db.upsert_album("qobuz", "a1", "Test", "Artist")
        resp = await client.post("/api/downloads/queue", json={"source": "qobuz", "album_ids": ["a1"]})
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestConfigRoutes:
    async def test_get_config(self, client):
        resp = await client.get("/api/config")
        assert resp.status_code == 200

    async def test_update_config(self, client):
        resp = await client.patch("/api/config", json={"downloads_path": "/new/path"})
        assert resp.status_code == 200


class TestAuthRoutes:
    async def test_auth_status(self, client):
        resp = await client.get("/api/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["source"] == "qobuz"
        assert data[1]["source"] == "tidal"
