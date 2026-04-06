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
