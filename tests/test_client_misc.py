"""Tests for client-layer logic that doesn't require real network access."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from streamrip.config import Config
from streamrip.exceptions import AuthenticationError, MissingCredentialsError, NonStreamableError


# ── Client.get_track_for_playlist default ────────────────────────────────────

class TestClientGetTrackForPlaylist:
    @pytest.mark.asyncio
    async def test_default_delegates_to_get_metadata(self):
        """The base Client.get_track_for_playlist must call get_metadata('track')."""
        from streamrip.client.client import Client
        from streamrip.client.downloadable import Downloadable

        class ConcreteClient(Client):
            source = "test"
            max_quality = 2
            logged_in = False

            async def login(self): pass
            async def get_metadata(self, item, media_type):
                return {"item": item, "media_type": media_type}
            async def search(self, media_type, query, limit=500): return []
            async def get_downloadable(self, item, quality) -> Downloadable: pass

        concrete = ConcreteClient()
        concrete._login_lock = asyncio.Lock()
        result = await concrete.get_track_for_playlist("99")
        assert result == {"item": "99", "media_type": "track"}


# ── DeezerClient.login error paths ───────────────────────────────────────────

class TestDeezerClientLoginErrors:
    def _client(self):
        from streamrip.client.deezer import DeezerClient
        config = Config.defaults()
        config.session.deezer.arl = ""
        return DeezerClient(config)

    @pytest.mark.asyncio
    async def test_missing_arl_raises(self):
        client = self._client()
        client.session = MagicMock()
        with patch.object(client, "get_session", new=AsyncMock(return_value=MagicMock())):
            with pytest.raises(MissingCredentialsError):
                await client.login()

    @pytest.mark.asyncio
    async def test_failed_login_raises_auth_error(self):
        from streamrip.client.deezer import DeezerClient
        config = Config.defaults()
        config.session.deezer.arl = "fake-bad-arl"
        client = DeezerClient(config)
        client.client.login_via_arl = MagicMock(return_value=False)
        with patch.object(client, "get_session", new=AsyncMock(return_value=MagicMock())):
            with pytest.raises(AuthenticationError):
                await client.login()

    @pytest.mark.asyncio
    async def test_successful_login_sets_logged_in(self):
        from streamrip.client.deezer import DeezerClient
        config = Config.defaults()
        config.session.deezer.arl = "valid-arl"
        client = DeezerClient(config)
        client.client.login_via_arl = MagicMock(return_value=True)
        client.client.current_user = {"id": 42}
        with patch.object(client, "get_session", new=AsyncMock(return_value=MagicMock())):
            await client.login()
        assert client.logged_in is True
        assert client.logged_in_user_id == 42


# ── DeezerClient.get_metadata unknown type ───────────────────────────────────

class TestDeezerClientGetMetadata:
    def _logged_in_client(self):
        from streamrip.client.deezer import DeezerClient
        config = Config.defaults()
        client = DeezerClient(config)
        client.logged_in = True
        return client

    @pytest.mark.asyncio
    async def test_unknown_media_type_raises(self):
        client = self._logged_in_client()
        with pytest.raises(Exception, match="not available on deezer"):
            await client.get_metadata("123", "video")


# ── DeezerClient.get_album cache ─────────────────────────────────────────────

class TestDeezerClientAlbumCache:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_network(self):
        from streamrip.client.deezer import DeezerClient
        config = Config.defaults()
        client = DeezerClient(config)
        client._album_cache["999"] = {"id": "999", "title": "Cached Album"}

        result = await client.get_album("999")
        assert result["title"] == "Cached Album"


# ── DeezerClient._get_encrypted_file_url ─────────────────────────────────────

class TestDeezerEncryptedFileUrl:
    def test_returns_cdn_url(self):
        from streamrip.client.deezer import DeezerClient
        config = Config.defaults()
        client = DeezerClient(config)

        url = client._get_encrypted_file_url(
            "77874822",
            "d41d8cd98f00b204e9800998ecf8427e",
            "1",
        )
        assert url.startswith("https://e-cdns-proxy-")
        assert ".dzcdn.net/mobile/1/" in url

    def test_deterministic(self):
        from streamrip.client.deezer import DeezerClient
        config = Config.defaults()
        client = DeezerClient(config)

        u1 = client._get_encrypted_file_url("123", "abcdef1234567890abcdef1234567890", "2")
        u2 = client._get_encrypted_file_url("123", "abcdef1234567890abcdef1234567890", "2")
        assert u1 == u2


# ── DeezerClient.get_track_for_playlist ──────────────────────────────────────

class TestDeezerGetTrackForPlaylist:
    @pytest.mark.asyncio
    async def test_calls_get_track_without_album_fetch(self):
        from streamrip.client.deezer import DeezerClient
        config = Config.defaults()
        client = DeezerClient(config)
        client.get_track = AsyncMock(return_value={"id": "42"})

        await client.get_track_for_playlist("42")

        client.get_track.assert_called_once_with("42", fetch_album=False)


# ── Client constructors (soundcloud, qobuz, tidal) ───────────────────────────

class TestClientConstructors:
    def test_soundcloud_client_init(self):
        from streamrip.client.soundcloud import SoundcloudClient
        config = Config.defaults()
        config.session.downloads.requests_per_minute = 0
        client = SoundcloudClient(config)
        assert client.logged_in is False
        assert client.source == "soundcloud"

    def test_qobuz_client_init(self):
        from streamrip.client.qobuz import QobuzClient
        config = Config.defaults()
        config.session.downloads.requests_per_minute = 0
        client = QobuzClient(config)
        assert client.logged_in is False
        assert client.source == "qobuz"
        assert client.secret is None

    def test_tidal_client_init(self):
        from streamrip.client.tidal import TidalClient
        config = Config.defaults()
        config.session.downloads.requests_per_minute = 0
        client = TidalClient(config)
        assert client.logged_in is False
        assert client.source == "tidal"

    def test_deezer_client_init(self):
        from streamrip.client.deezer import DeezerClient
        config = Config.defaults()
        client = DeezerClient(config)
        assert client.logged_in is False
        assert client.source == "deezer"
        assert client.logged_in_user_id is None


# ── Client.get_rate_limiter ───────────────────────────────────────────────────

class TestGetRateLimiter:
    def test_zero_returns_nullcontext(self):
        import contextlib
        from streamrip.client.client import Client
        result = Client.get_rate_limiter(0)
        assert isinstance(result, contextlib.nullcontext)

    def test_nonzero_returns_limiter(self):
        import aiolimiter
        from streamrip.client.client import Client
        result = Client.get_rate_limiter(60)
        assert isinstance(result, aiolimiter.AsyncLimiter)
