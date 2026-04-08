"""Tests for PlaylistsAPI."""

import pytest
from unittest.mock import AsyncMock, call

from conftest import SAMPLE_PLAYLIST
from qobuz.playlists import PlaylistsAPI, _BATCH_SIZE
from qobuz.types import Playlist, PaginatedResult


class TestCreate:
    async def test_create_posts_form_data_returns_playlist(self, mock_transport):
        mock_transport.post_form.return_value = (200, SAMPLE_PLAYLIST)
        api = PlaylistsAPI(mock_transport)

        result = await api.create("New Private Playlist", description="This is the name")

        assert isinstance(result, Playlist)
        assert result.id == 61997651
        assert result.name == "New Private Playlist"
        mock_transport.post_form.assert_awaited_once_with(
            "playlist/create",
            {
                "name": "New Private Playlist",
                "description": "This is the name",
                "is_public": "false",
                "is_collaborative": "false",
            },
        )

    async def test_create_with_public_true(self, mock_transport):
        mock_transport.post_form.return_value = (200, SAMPLE_PLAYLIST)
        api = PlaylistsAPI(mock_transport)

        await api.create("Public Playlist", public=True, collaborative=True)

        call_args = mock_transport.post_form.call_args
        assert call_args[0][1]["is_public"] == "true"
        assert call_args[0][1]["is_collaborative"] == "true"


class TestUpdate:
    async def test_update_posts_only_non_none_fields(self, mock_transport):
        mock_transport.post_form.return_value = (200, SAMPLE_PLAYLIST)
        api = PlaylistsAPI(mock_transport)

        result = await api.update(61997651, name="Renamed")

        assert isinstance(result, Playlist)
        mock_transport.post_form.assert_awaited_once_with(
            "playlist/update",
            {
                "playlist_id": "61997651",
                "name": "Renamed",
            },
        )

    async def test_update_includes_all_provided_fields(self, mock_transport):
        mock_transport.post_form.return_value = (200, SAMPLE_PLAYLIST)
        api = PlaylistsAPI(mock_transport)

        await api.update(
            61997651,
            name="New Name",
            description="New desc",
            public=True,
            collaborative=False,
        )

        call_args = mock_transport.post_form.call_args
        data = call_args[0][1]
        assert data["playlist_id"] == "61997651"
        assert data["name"] == "New Name"
        assert data["description"] == "New desc"
        assert data["is_public"] == "true"
        assert data["is_collaborative"] == "false"

    async def test_update_omits_none_fields(self, mock_transport):
        mock_transport.post_form.return_value = (200, SAMPLE_PLAYLIST)
        api = PlaylistsAPI(mock_transport)

        await api.update(61997651, description="Only desc")

        data = mock_transport.post_form.call_args[0][1]
        assert "name" not in data
        assert "is_public" not in data
        assert "is_collaborative" not in data
        assert data["description"] == "Only desc"


class TestDelete:
    async def test_delete_posts_playlist_id(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = PlaylistsAPI(mock_transport)

        result = await api.delete(61997651)

        assert result is None
        mock_transport.post_form.assert_awaited_once_with(
            "playlist/delete",
            {"playlist_id": "61997651"},
        )


class TestAddTracks:
    async def test_add_tracks_single_batch(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = PlaylistsAPI(mock_transport)
        track_ids = list(range(1, 31))  # 30 tracks, under batch size

        await api.add_tracks(61997651, track_ids)

        mock_transport.post_form.assert_awaited_once()
        call_args = mock_transport.post_form.call_args
        assert call_args[0][0] == "playlist/addTracks"
        data = call_args[0][1]
        assert data["playlist_id"] == "61997651"
        assert data["track_ids"] == ",".join(str(i) for i in range(1, 31))

    async def test_add_tracks_batches_over_50(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = PlaylistsAPI(mock_transport)
        track_ids = list(range(1, 76))  # 75 tracks -> 2 batches (50 + 25)

        await api.add_tracks(61997651, track_ids)

        assert mock_transport.post_form.await_count == 2

        # First batch: tracks 1-50
        first_call = mock_transport.post_form.call_args_list[0]
        first_ids = first_call[0][1]["track_ids"]
        assert first_ids == ",".join(str(i) for i in range(1, 51))

        # Second batch: tracks 51-75
        second_call = mock_transport.post_form.call_args_list[1]
        second_ids = second_call[0][1]["track_ids"]
        assert second_ids == ",".join(str(i) for i in range(51, 76))

    async def test_add_tracks_with_no_duplicate(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = PlaylistsAPI(mock_transport)

        await api.add_tracks(61997651, [100, 200], no_duplicate=True)

        data = mock_transport.post_form.call_args[0][1]
        assert data["no_duplicate"] == "true"

    async def test_add_tracks_without_no_duplicate(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = PlaylistsAPI(mock_transport)

        await api.add_tracks(61997651, [100, 200])

        data = mock_transport.post_form.call_args[0][1]
        assert "no_duplicate" not in data

    async def test_batch_size_constant(self):
        assert _BATCH_SIZE == 50


class TestGet:
    async def test_get_returns_playlist(self, mock_transport):
        mock_transport.get.return_value = (200, SAMPLE_PLAYLIST)
        api = PlaylistsAPI(mock_transport)

        result = await api.get(61997651)

        assert isinstance(result, Playlist)
        assert result.id == 61997651
        mock_transport.get.assert_awaited_once_with(
            "playlist/get",
            {
                "playlist_id": "61997651",
                "extra": "tracks",
                "offset": 0,
                "limit": 50,
            },
        )

    async def test_get_custom_params(self, mock_transport):
        mock_transport.get.return_value = (200, SAMPLE_PLAYLIST)
        api = PlaylistsAPI(mock_transport)

        await api.get(61997651, extra="trackIds", offset=10, limit=100)

        mock_transport.get.assert_awaited_once_with(
            "playlist/get",
            {
                "playlist_id": "61997651",
                "extra": "trackIds",
                "offset": 10,
                "limit": 100,
            },
        )


class TestList:
    async def test_list_returns_paginated_result(self, mock_transport):
        paginated_response = {
            "playlists": {
                "items": [SAMPLE_PLAYLIST],
                "total": 1,
                "limit": 500,
                "offset": 0,
            }
        }
        mock_transport.get.return_value = (200, paginated_response)
        api = PlaylistsAPI(mock_transport)

        result = await api.list()

        assert isinstance(result, PaginatedResult)
        assert len(result.items) == 1
        assert result.total == 1
        mock_transport.get.assert_awaited_once_with(
            "playlist/getUserPlaylists",
            {"limit": 500, "filter": "owner"},
        )

    async def test_list_custom_params(self, mock_transport):
        paginated_response = {
            "playlists": {
                "items": [],
                "total": 0,
                "limit": 100,
                "offset": 0,
            }
        }
        mock_transport.get.return_value = (200, paginated_response)
        api = PlaylistsAPI(mock_transport)

        await api.list(limit=100, filter="public")

        mock_transport.get.assert_awaited_once_with(
            "playlist/getUserPlaylists",
            {"limit": 100, "filter": "public"},
        )


class TestSearch:
    async def test_search_returns_paginated_result(self, mock_transport):
        paginated_response = {
            "playlists": {
                "items": [SAMPLE_PLAYLIST],
                "total": 1,
                "limit": 50,
                "offset": 0,
            }
        }
        mock_transport.get.return_value = (200, paginated_response)
        api = PlaylistsAPI(mock_transport)

        result = await api.search("chill vibes")

        assert isinstance(result, PaginatedResult)
        assert len(result.items) == 1
        mock_transport.get.assert_awaited_once_with(
            "playlist/search",
            {"query": "chill vibes", "limit": 50, "offset": 0},
        )
