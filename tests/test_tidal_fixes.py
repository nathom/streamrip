"""Tests for Tidal client bug fixes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTidalSearch:
    """Fix: search returns empty when exactly one result exists."""

    async def test_search_returns_single_result(self):
        """search() should return results when exactly 1 item matches."""
        from streamrip.client.tidal import TidalClient

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.access_token = "fake"

        mock_resp = {"items": [{"id": 123, "title": "Test Album"}], "totalNumberOfItems": 1}
        client._api_request = AsyncMock(return_value=mock_resp)

        result = await client.search("album", "exact match", limit=10)
        assert len(result) == 1
        assert result[0]["items"][0]["id"] == 123

    async def test_search_returns_empty_for_no_results(self):
        """search() should return empty list when no items match."""
        from streamrip.client.tidal import TidalClient

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.access_token = "fake"

        mock_resp = {"items": [], "totalNumberOfItems": 0}
        client._api_request = AsyncMock(return_value=mock_resp)

        result = await client.search("album", "nonexistent", limit=10)
        assert result == []


class TestTidalGetUserFavorites:
    """Fix: get_user_favorites crashes when limit=None."""

    async def test_favorites_with_limit_none(self):
        """get_user_favorites should handle limit=None (fetch all)."""
        from streamrip.client.tidal import TidalClient

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.user_id = "12345"

        mock_resp = {"items": [{"id": i} for i in range(3)]}
        client._api_request = AsyncMock(return_value=mock_resp)

        # This should not raise TypeError
        result = await client.get_user_favorites("album", limit=None)
        assert len(result) == 3


class TestTidalAlbumMetadata:
    """Fix: from_tidal crashes when releaseDate is absent."""

    def test_from_tidal_missing_release_date(self):
        """Should handle missing releaseDate without crashing."""
        from streamrip.metadata.album import AlbumMetadata

        resp = {
            "id": 12345,
            "title": "Test Album",
            "numberOfTracks": 10,
            "copyright": "(C) 2024",
            "artists": [{"name": "Test Artist", "id": 1}],
            "artist": {"name": "Test Artist"},
            "duration": 3600,
            "streamReady": True,
            "allowStreaming": True,
            "numberOfVolumes": 1,
            "cover": "abc123",
            "explicit": False,
        }

        result = AlbumMetadata.from_tidal(resp)
        assert result is not None
        assert result.year == "Unknown"


from json import JSONDecodeError


class TestTidalGetDownloadable:
    """Fix: get_downloadable recurses infinitely when quality hits 0."""

    async def test_raises_at_quality_zero(self):
        """Should raise NonStreamableError instead of recursing below quality 0."""
        from streamrip.client.tidal import TidalClient
        from streamrip.exceptions import NonStreamableError

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.access_token = "fake"

        client._api_request = AsyncMock(return_value={
            "manifest": "bm90LWpzb24=",  # base64 of "not-json"
        })

        with pytest.raises(NonStreamableError):
            await client.get_downloadable("track_123", quality=0)


class TestTidalVideoUrl:
    """Fix: get_video_file_url treats aiohttp JSON response as requests.Response."""

    async def test_video_url_parses_hls_manifest(self):
        """Should fetch manifest as text and extract highest resolution URL."""
        from streamrip.client.tidal import TidalClient
        import base64, json

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.access_token = "fake"

        manifest_data = json.dumps({"urls": ["https://example.com/manifest.m3u8"]})
        manifest_b64 = base64.b64encode(manifest_data.encode()).decode()

        client._api_request = AsyncMock(return_value={
            "manifest": manifest_b64,
        })

        # Mock the HLS manifest fetch — returns text, not JSON
        hls_content = (
            "#EXTM3U\n"
            '#EXT-X-STREAM-INF:BANDWIDTH=500000,AVERAGE-BANDWIDTH=450000,CODECS="avc1.640028,mp4a.40.2",RESOLUTION=640x360\n'
            "https://cdn.example.com/low.m3u8\n"
            '#EXT-X-STREAM-INF:BANDWIDTH=2000000,AVERAGE-BANDWIDTH=1900000,CODECS="avc1.640028,mp4a.40.2",RESOLUTION=1280x720\n'
            "https://cdn.example.com/high.m3u8\n"
        )
        mock_hls_resp = AsyncMock()
        mock_hls_resp.text = AsyncMock(return_value=hls_content)
        mock_hls_resp.__aenter__ = AsyncMock(return_value=mock_hls_resp)
        mock_hls_resp.__aexit__ = AsyncMock(return_value=False)
        client.session.get = MagicMock(return_value=mock_hls_resp)

        url = await client.get_video_file_url("video_123")
        assert "high.m3u8" in url


class TestTidalAutoRefresh:
    """Test that _api_request auto-refreshes on 401."""

    async def test_retries_on_401_with_refresh_token(self):
        """Should refresh token and retry when getting 401."""
        from streamrip.client.tidal import TidalClient

        client = TidalClient.__new__(TidalClient)
        client.session = MagicMock()
        client.rate_limiter = AsyncMock()
        client.config = MagicMock()
        client.config.access_token = "old-token"
        client.config.country_code = "US"
        client.refresh_token = "refresh-token"
        client.logged_in = True
        client._retried_401 = False

        # First call returns 401, second returns 200
        mock_resp_401 = AsyncMock()
        mock_resp_401.status = 401
        mock_resp_401.json = AsyncMock(return_value={"status": 401})
        mock_resp_401.__aenter__ = AsyncMock(return_value=mock_resp_401)
        mock_resp_401.__aexit__ = AsyncMock(return_value=False)

        mock_resp_200 = AsyncMock()
        mock_resp_200.status = 200
        mock_resp_200.json = AsyncMock(return_value={"items": [{"id": 1}]})
        mock_resp_200.raise_for_status = MagicMock()  # sync, not async
        mock_resp_200.__aenter__ = AsyncMock(return_value=mock_resp_200)
        mock_resp_200.__aexit__ = AsyncMock(return_value=False)

        client.session.get = MagicMock(side_effect=[mock_resp_401, mock_resp_200])
        client._refresh_access_token = AsyncMock()
        client._update_authorization_from_config = MagicMock()

        result = await client._api_request("test/endpoint", {"key": "value"})

        # Should have called refresh
        client._refresh_access_token.assert_called_once()
        assert result["items"][0]["id"] == 1
