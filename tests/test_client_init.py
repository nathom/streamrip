"""Tests for client initialization and hot-reload."""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.models.database import AppDatabase
from backend.main import _init_clients


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = AppDatabase(path)
    yield database
    os.unlink(path)


class TestInitClients:
    def test_returns_empty_when_no_credentials(self, db):
        """Should return empty dict when no tokens are stored."""
        clients = _init_clients(db)
        assert clients == {}

    def test_returns_empty_when_only_user_id(self, db):
        """Should not create client with user_id but no token."""
        db.set_config("qobuz_user_id", "12345")
        clients = _init_clients(db)
        assert "qobuz" not in clients

    def test_creates_qobuz_client_with_credentials(self, db):
        """Should create QobuzClient when both token and user_id exist."""
        db.set_config("qobuz_token", "fake-token")
        db.set_config("qobuz_user_id", "12345")

        mock_cfg = MagicMock()
        mock_cfg.session.qobuz.use_auth_token = True
        mock_cfg.session.qobuz.email_or_userid = ""
        mock_cfg.session.qobuz.password_or_token = ""

        mock_config_cls = MagicMock()
        mock_config_cls.defaults.return_value = mock_cfg

        mock_qobuz_client = MagicMock()

        # Config and QobuzClient are imported locally inside _init_clients,
        # so we patch them in their source modules.
        with patch("streamrip.config.Config", mock_config_cls), \
             patch("streamrip.client.qobuz.QobuzClient", mock_qobuz_client):
            clients = _init_clients(db)

        assert "qobuz" in clients
        assert mock_cfg.session.qobuz.use_auth_token is True
        assert mock_cfg.session.qobuz.email_or_userid == "12345"
        assert mock_cfg.session.qobuz.password_or_token == "fake-token"

    def test_handles_import_error_gracefully(self, db):
        """Should not crash if streamrip config import raises."""
        db.set_config("qobuz_token", "fake-token")
        db.set_config("qobuz_user_id", "12345")

        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def fail_streamrip_config(name, *args, **kwargs):
            if name == "streamrip.config":
                raise ImportError("no module")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fail_streamrip_config):
            # Should log error but not crash
            clients = _init_clients(db)
            assert clients == {}
