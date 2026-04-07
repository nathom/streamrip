"""Integration tests for the download pipeline.

Tests the full chain: config_bridge -> Main -> resolve -> rip
to catch configuration issues before they reach production.
"""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.database import AppDatabase
from backend.services.config_bridge import build_streamrip_config
from backend.services.download import DownloadService
from backend.services.event_bus import EventBus


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = AppDatabase(path)
    yield database
    os.unlink(path)


@pytest.fixture
def event_bus():
    return EventBus()


class TestConfigBridge:
    """Test that config_bridge produces a valid Config for the download pipeline."""

    def test_defaults_have_valid_db_paths(self, db):
        """Config should always have non-empty database paths."""
        config = build_streamrip_config(db)
        assert config.session.database.downloads_path, "downloads_path must not be empty"
        assert config.session.database.failed_downloads_path, "failed_downloads_path must not be empty"

    def test_defaults_have_valid_download_folder(self, db):
        """Config should always have a download folder set."""
        config = build_streamrip_config(db)
        assert config.session.downloads.folder, "downloads folder must not be empty"

    def test_db_values_override_defaults(self, db):
        """DB config values should take precedence over defaults."""
        db.set_config("downloads_path", "/custom/music")
        db.set_config("max_connections", "10")
        db.set_config("folder_format", "{artist} - {title}")
        db.set_config("qobuz_quality", "4")

        config = build_streamrip_config(db)
        assert config.session.downloads.folder == "/custom/music"
        assert config.session.downloads.max_connections == 10
        assert config.session.filepaths.folder_format == "{artist} - {title}"
        assert config.session.qobuz.quality == 4

    def test_qobuz_credentials_applied(self, db):
        """Qobuz token and user_id should be set on the config."""
        db.set_config("qobuz_token", "test-token-123")
        db.set_config("qobuz_user_id", "99999")

        config = build_streamrip_config(db)
        assert config.session.qobuz.use_auth_token is True
        assert config.session.qobuz.email_or_userid == "99999"
        assert config.session.qobuz.password_or_token == "test-token-123"

    def test_conversion_settings_applied(self, db):
        """Conversion settings should be applied from DB."""
        db.set_config("conversion_enabled", "true")
        db.set_config("conversion_codec", "MP3")

        config = build_streamrip_config(db)
        assert config.session.conversion.enabled is True
        assert config.session.conversion.codec == "MP3"

    def test_empty_db_produces_valid_config(self, db):
        """An empty DB should still produce a usable config."""
        config = build_streamrip_config(db)
        # Should not raise, and critical paths should have values
        assert config.session.database.downloads_path
        assert config.session.downloads.folder


class TestMainConstruction:
    """Test that Main can be constructed from config_bridge output."""

    def test_main_creates_with_bridge_config(self, db):
        """Main(config) should not crash when given a config_bridge config."""
        from streamrip.rip.main import Main

        config = build_streamrip_config(db)
        # This was crashing with AssertionError on empty db path
        main = Main(config)
        assert main.database is not None

    def test_main_creates_with_custom_download_path(self, db):
        """Main should use the download path from config."""
        from streamrip.rip.main import Main

        with tempfile.TemporaryDirectory() as tmpdir:
            db.set_config("downloads_path", tmpdir)
            config = build_streamrip_config(db)
            main = Main(config)
            assert config.session.downloads.folder == tmpdir


class TestDownloadServicePipeline:
    """Test the download service's integration with the streamrip pipeline."""

    async def test_download_album_auto_logins_when_not_logged_in(self, db, event_bus):
        """Should attempt login when client is not logged in."""
        mock_client = AsyncMock()
        mock_client.source = "qobuz"
        mock_client.logged_in = False
        mock_client.login = AsyncMock(side_effect=ValueError("Login failed in test"))

        service = DownloadService(
            db, event_bus,
            clients={"qobuz": mock_client},
            download_path="/tmp",
        )

        item = {
            "id": "test-id",
            "album_db_id": 1,
            "source": "qobuz",
            "source_album_id": "123",
            "title": "Test",
            "artist": "Artist",
            "track_count": 10,
            "status": "downloading",
        }
        with pytest.raises(ValueError, match="failed to login"):
            await service._download_album(item)
        mock_client.login.assert_called_once()

    async def test_download_album_auto_logins_when_no_secret(self, db, event_bus):
        """Should attempt login when Qobuz client has no secret."""
        mock_client = AsyncMock()
        mock_client.source = "qobuz"
        mock_client.logged_in = True
        mock_client.secret = None
        mock_client.login = AsyncMock(side_effect=ValueError("Login failed in test"))

        service = DownloadService(
            db, event_bus,
            clients={"qobuz": mock_client},
            download_path="/tmp",
        )

        item = {
            "id": "test-id",
            "album_db_id": 1,
            "source": "qobuz",
            "source_album_id": "123",
            "title": "Test",
            "artist": "Artist",
            "track_count": 10,
            "status": "downloading",
        }
        with pytest.raises(ValueError, match="failed to login"):
            await service._download_album(item)
        mock_client.login.assert_called_once()

    async def test_download_album_resolve_failure(self, db, event_bus):
        """Should raise when PendingAlbum.resolve() returns None."""
        mock_client = AsyncMock()
        mock_client.source = "qobuz"
        mock_client.logged_in = True
        mock_client.secret = "test-secret"

        service = DownloadService(
            db, event_bus,
            clients={"qobuz": mock_client},
            download_path="/tmp",
        )

        item = {
            "id": "test-id",
            "album_db_id": 1,
            "source": "qobuz",
            "source_album_id": "nonexistent",
            "title": "Test",
            "artist": "Artist",
            "track_count": 10,
            "status": "downloading",
        }

        with patch("streamrip.media.PendingAlbum") as MockPending:
            mock_pending = MockPending.return_value
            mock_pending.resolve = AsyncMock(return_value=None)
            with pytest.raises(ValueError, match="Failed to resolve"):
                await service._download_album(item)

    async def test_client_state_preserved_through_pipeline(self, db, event_bus):
        """The logged-in client should retain secret and logged_in through the pipeline."""
        from streamrip.client.qobuz import QobuzClient
        from streamrip.config import Config

        config = build_streamrip_config(db)
        real_client = QobuzClient(config)
        # Simulate logged-in state
        real_client.logged_in = True
        real_client.secret = "test-secret-abc"

        service = DownloadService(
            db, event_bus,
            clients={"qobuz": real_client},
            download_path="/tmp",
        )

        # Verify the client we pass is the same one that has the secret
        assert service.clients["qobuz"].secret == "test-secret-abc"
        assert service.clients["qobuz"].logged_in is True

        # Now check that Main construction doesn't destroy our client's state
        from streamrip.rip.main import Main
        main = Main(config)
        main.clients["qobuz"] = real_client
        main._add_by_id_client(real_client, "album", "test-id-123")

        # The pending item should reference our client
        pending = main.pending[0]
        assert pending.client is real_client
        assert pending.client.secret == "test-secret-abc"
        assert pending.client.logged_in is True

    async def test_queue_marks_failed_on_error(self, db, event_bus):
        """Queue processor should mark album as failed when download raises."""
        db.upsert_album("qobuz", "fail-album", "Fail Album", "Artist")

        mock_client = AsyncMock()
        mock_client.source = "qobuz"
        mock_client.logged_in = True

        service = DownloadService(
            db, event_bus,
            clients={"qobuz": mock_client},
            download_path="/tmp",
        )

        # Make _download_album raise
        service._download_album = AsyncMock(side_effect=RuntimeError("test error"))

        items = await service.enqueue("qobuz", ["fail-album"])
        assert len(items) == 1

        # Wait for the worker to process
        import asyncio
        await asyncio.sleep(0.1)

        queue = service.get_queue()
        failed = [q for q in queue if q["source_album_id"] == "fail-album"]
        assert failed[0]["status"] == "failed"

        # DB should show not_downloaded (not complete!)
        album = db.get_album_by_source_id("qobuz", "fail-album")
        assert album["download_status"] == "not_downloaded"
