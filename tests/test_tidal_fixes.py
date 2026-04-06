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
