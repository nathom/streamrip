"""Tests for the QobuzClient facade."""

import re
from unittest.mock import AsyncMock, patch

import pytest
from aioresponses import aioresponses

from conftest import SAMPLE_ALBUM, SAMPLE_FAVORITE_IDS, SAMPLE_LAST_UPDATE, SAMPLE_PLAYLIST
from qobuz.catalog import CatalogAPI
from qobuz.client import QobuzClient
from qobuz.discovery import DiscoveryAPI
from qobuz.favorites import FavoritesAPI
from qobuz.playlists import PlaylistsAPI
from qobuz.streaming import StreamingAPI


class TestQobuzClient:
    def test_has_favorites_namespace(self):
        client = QobuzClient(app_id="123", user_auth_token="tok")
        assert isinstance(client.favorites, FavoritesAPI)

    def test_has_playlists_namespace(self):
        client = QobuzClient(app_id="123", user_auth_token="tok")
        assert isinstance(client.playlists, PlaylistsAPI)

    def test_has_catalog_namespace(self):
        client = QobuzClient(app_id="123", user_auth_token="tok")
        assert isinstance(client.catalog, CatalogAPI)

    def test_has_discovery_namespace(self):
        client = QobuzClient(app_id="123", user_auth_token="tok")
        assert isinstance(client.discovery, DiscoveryAPI)

    def test_has_streaming_namespace(self):
        client = QobuzClient(app_id="123", user_auth_token="tok")
        assert isinstance(client.streaming, StreamingAPI)

    async def test_context_manager_opens_session(self):
        async with QobuzClient(app_id="123", user_auth_token="tok") as client:
            assert client._transport._session is not None
        assert client._transport._session is None

    async def test_last_update(self):
        client = QobuzClient(app_id="123", user_auth_token="tok")
        with patch.object(client._transport, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = (200, SAMPLE_LAST_UPDATE)
            async with client:
                lu = await client.last_update()
                assert lu.favorite == 1775473221
                assert lu.playlist == 1775208266

    async def test_login(self):
        client = QobuzClient(app_id="123", user_auth_token="tok")
        with patch.object(client._transport, "post_form", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = (200, {"user": {"id": 123}})
            async with client:
                result = await client.login()
                assert result["user"]["id"] == 123
                mock_post.assert_called_once_with("user/login", {"extra": "partner"})


class TestQobuzClientIntegration:
    """Integration tests exercising the full client through HTTP mocking."""

    async def test_full_workflow(self):
        async with QobuzClient(app_id="123", user_auth_token="tok") as client:
            with aioresponses() as m:
                base = "https://www.qobuz.com/api.json/0.2"

                # Add album to favorites
                m.post(f"{base}/favorite/create", payload={"status": "success"})
                await client.favorites.add_album("abc123")

                # Get favorite IDs
                m.get(re.compile(r".*/favorite/getUserFavoriteIds.*"), payload=SAMPLE_FAVORITE_IDS)
                ids = await client.favorites.get_ids()
                assert len(ids.albums) == 2

                # Create playlist
                m.post(f"{base}/playlist/create", payload=SAMPLE_PLAYLIST)
                pl = await client.playlists.create("Test")
                assert pl.id == 61997651

                # Add tracks to playlist
                m.post(f"{base}/playlist/addTracks", payload=SAMPLE_PLAYLIST)
                await client.playlists.add_tracks(pl.id, ["1", "2"])

                # Search albums
                m.get(re.compile(r".*/album/search.*"), payload={"albums": {"items": [SAMPLE_ALBUM], "total": 1, "limit": 50, "offset": 0}})
                results = await client.catalog.search_albums("test")
                assert len(results.items) == 1

                # Delete playlist
                m.post(f"{base}/playlist/delete", payload={"status": "success"})
                await client.playlists.delete(pl.id)
