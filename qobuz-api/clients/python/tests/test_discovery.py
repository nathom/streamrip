"""Tests for the Discovery API."""

from unittest.mock import AsyncMock

from conftest import SAMPLE_ALBUM, SAMPLE_GENRE
from qobuz.discovery import DiscoveryAPI
from qobuz.types import Genre, PaginatedResult


class TestListGenres:
    async def test_returns_list_of_genres(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"genres": {"items": [SAMPLE_GENRE], "total": 1, "limit": 25, "offset": 0}}))
        api = DiscoveryAPI(mock_transport)
        genres = await api.list_genres()
        assert len(genres) == 1
        assert isinstance(genres[0], Genre)
        assert genres[0].name == "Pop/Rock"


class TestGetIndex:
    async def test_returns_containers_dict(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {
            "containers": {
                "new_releases": {"id": "newReleases", "data": {"has_more": True, "items": [SAMPLE_ALBUM]}},
            }
        }))
        api = DiscoveryAPI(mock_transport)
        result = await api.get_index()
        assert "new_releases" in result

    async def test_passes_genre_ids(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"containers": {}}))
        api = DiscoveryAPI(mock_transport)
        await api.get_index(genre_ids=[112, 80])
        call_args = mock_transport.get.call_args[0]
        assert call_args[1]["genre_ids"] == "112,80"


class TestNewReleases:
    async def test_returns_paginated_result(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"has_more": True, "items": [SAMPLE_ALBUM]}))
        api = DiscoveryAPI(mock_transport)
        result = await api.new_releases(limit=50)
        assert isinstance(result, PaginatedResult)
        assert len(result.items) == 1
        assert result.has_more is True


class TestCuratedPlaylists:
    async def test_includes_tags_param(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"has_more": False, "items": []}))
        api = DiscoveryAPI(mock_transport)
        await api.curated_playlists()
        call_args = mock_transport.get.call_args[0]
        assert call_args[1]["tags"] == ""


class TestAlbumOfTheWeek:
    async def test_returns_paginated_result(self, mock_transport):
        mock_transport.get = AsyncMock(return_value=(200, {"has_more": True, "items": [SAMPLE_ALBUM]}))
        api = DiscoveryAPI(mock_transport)
        result = await api.album_of_the_week()
        assert isinstance(result, PaginatedResult)
        assert result.has_more is True
