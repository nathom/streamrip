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
        """Should create SDK QobuzClient when token exists."""
        db.set_config("qobuz_token", "fake-token")
        db.set_config("qobuz_user_id", "12345")

        with patch("qobuz.QobuzClient") as MockClient:
            MockClient.return_value = MagicMock()
            clients = _init_clients(db)

        assert "qobuz" in clients
        MockClient.assert_called_once()
        call_kwargs = MockClient.call_args[1]
        assert call_kwargs["user_auth_token"] == "fake-token"

    def test_handles_import_error_gracefully(self, db):
        """Should not crash if qobuz SDK import fails."""
        db.set_config("qobuz_token", "fake-token")

        with patch("qobuz.QobuzClient", side_effect=ImportError("no module")):
            clients = _init_clients(db)
            assert "qobuz" not in clients
