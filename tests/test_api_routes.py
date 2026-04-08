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


class TestSyncRoutes:
    async def test_sync_status(self, client, app):
        resp = await client.get("/api/sync/status/qobuz")
        assert resp.status_code == 200
        data = resp.json()
        assert "new_albums" in data
        assert "removed_albums" in data
        assert data["source"] == "qobuz"

    async def test_sync_history(self, client):
        resp = await client.get("/api/sync/history?source=qobuz")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestAuthOAuthRoutes:
    async def test_oauth_url(self, client):
        resp = await client.get("/api/auth/qobuz/oauth-url")
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert "qobuz.com" in data["url"]


class TestConfigReload:
    async def test_update_config_saves_values(self, client, app):
        resp = await client.patch("/api/config", json={"downloads_path": "/test/path"})
        assert resp.status_code == 200
        # Verify persisted
        get_resp = await client.get("/api/config")
        assert get_resp.json()["downloads_path"] == "/test/path"

    async def test_config_type_conversion(self, client, app):
        app.state.db.set_config("qobuz_quality", "3")
        app.state.db.set_config("conversion_enabled", "true")
        resp = await client.get("/api/config")
        data = resp.json()
        assert isinstance(data["qobuz_quality"], int)
        assert isinstance(data["conversion_enabled"], bool)
