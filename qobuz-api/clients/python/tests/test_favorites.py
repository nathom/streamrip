"""Tests for the Favorites API."""

import pytest

from conftest import SAMPLE_ALBUM, SAMPLE_FAVORITE_IDS
from qobuz.favorites import FavoritesAPI, FavoriteAlbums
from qobuz.types import Album, FavoriteIds


class TestAddAlbum:
    async def test_posts_correct_form_data(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = FavoritesAPI(mock_transport)

        await api.add_album("abc123")

        mock_transport.post_form.assert_called_once_with(
            "favorite/create",
            {"album_ids": "abc123", "artist_ids": "", "track_ids": ""},
        )


class TestAddAlbums:
    async def test_joins_ids_with_comma(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = FavoritesAPI(mock_transport)

        await api.add_albums(["id1", "id2", "id3"])

        mock_transport.post_form.assert_called_once_with(
            "favorite/create",
            {"album_ids": "id1,id2,id3", "artist_ids": "", "track_ids": ""},
        )


class TestAddTrack:
    async def test_posts_correct_form_data(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = FavoritesAPI(mock_transport)

        await api.add_track("77158728")

        mock_transport.post_form.assert_called_once_with(
            "favorite/create",
            {"album_ids": "", "artist_ids": "", "track_ids": "77158728"},
        )


class TestAddTracks:
    async def test_joins_ids_with_comma(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = FavoritesAPI(mock_transport)

        await api.add_tracks(["111", "222"])

        mock_transport.post_form.assert_called_once_with(
            "favorite/create",
            {"album_ids": "", "artist_ids": "", "track_ids": "111,222"},
        )


class TestAddArtist:
    async def test_posts_correct_form_data(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = FavoritesAPI(mock_transport)

        await api.add_artist("38895")

        mock_transport.post_form.assert_called_once_with(
            "favorite/create",
            {"album_ids": "", "artist_ids": "38895", "track_ids": ""},
        )


class TestRemoveAlbum:
    async def test_posts_correct_form_data(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = FavoritesAPI(mock_transport)

        await api.remove_album("abc123")

        mock_transport.post_form.assert_called_once_with(
            "favorite/delete",
            {"album_ids": "abc123", "artist_ids": "", "track_ids": ""},
        )


class TestRemoveTrack:
    async def test_posts_correct_form_data(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = FavoritesAPI(mock_transport)

        await api.remove_track("77158728")

        mock_transport.post_form.assert_called_once_with(
            "favorite/delete",
            {"album_ids": "", "artist_ids": "", "track_ids": "77158728"},
        )


class TestRemoveArtist:
    async def test_sends_correct_endpoint(self, mock_transport):
        mock_transport.post_form.return_value = (200, {"status": "success"})
        api = FavoritesAPI(mock_transport)

        await api.remove_artist("38895")

        mock_transport.post_form.assert_called_once_with(
            "favorite/delete",
            {"album_ids": "", "artist_ids": "38895", "track_ids": ""},
        )


class TestGetAlbums:
    async def test_returns_parsed_album_objects(self, mock_transport):
        mock_transport.get.return_value = (200, {
            "albums": {
                "items": [SAMPLE_ALBUM],
                "total": 1,
                "limit": 500,
                "offset": 0,
            }
        })
        api = FavoritesAPI(mock_transport)

        result = await api.get_albums()

        assert isinstance(result, FavoriteAlbums)
        assert len(result.items) == 1
        assert isinstance(result.items[0], Album)
        assert result.items[0].id == "p0d55tt7gv3lc"
        assert result.items[0].title == "Virgin Lake"
        assert result.total == 1
        assert result.limit == 500
        assert result.offset == 0
        mock_transport.get.assert_called_once_with(
            "favorite/getUserFavorites",
            {"type": "albums", "limit": 500, "offset": 0},
        )

    async def test_custom_limit_and_offset(self, mock_transport):
        mock_transport.get.return_value = (200, {
            "albums": {
                "items": [],
                "total": 0,
                "limit": 50,
                "offset": 100,
            }
        })
        api = FavoritesAPI(mock_transport)

        result = await api.get_albums(limit=50, offset=100)

        mock_transport.get.assert_called_once_with(
            "favorite/getUserFavorites",
            {"type": "albums", "limit": 50, "offset": 100},
        )
        assert result.limit == 50
        assert result.offset == 100


class TestGetTracks:
    async def test_returns_paginated_result(self, mock_transport):
        mock_transport.get.return_value = (200, {
            "tracks": {
                "items": [{"id": 123, "title": "Track 1"}],
                "total": 1,
                "limit": 500,
                "offset": 0,
            }
        })
        api = FavoritesAPI(mock_transport)

        result = await api.get_tracks()

        assert result.total == 1
        assert len(result.items) == 1
        mock_transport.get.assert_called_once_with(
            "favorite/getUserFavorites",
            {"type": "tracks", "limit": 500, "offset": 0},
        )


class TestGetArtists:
    async def test_returns_paginated_result(self, mock_transport):
        mock_transport.get.return_value = (200, {
            "artists": {
                "items": [{"id": 38895, "name": "Talk Talk"}],
                "total": 1,
                "limit": 100,
                "offset": 0,
            }
        })
        api = FavoritesAPI(mock_transport)

        result = await api.get_artists()

        assert result.total == 1
        assert len(result.items) == 1
        mock_transport.get.assert_called_once_with(
            "favorite/getUserFavorites",
            {"type": "artists", "limit": 100, "offset": 0},
        )


class TestGetIds:
    async def test_returns_favorite_ids(self, mock_transport):
        mock_transport.get.return_value = (200, SAMPLE_FAVORITE_IDS)
        api = FavoritesAPI(mock_transport)

        result = await api.get_ids()

        assert isinstance(result, FavoriteIds)
        assert len(result.albums) == 2
        assert "xetru34w7hkdv" in result.albums
        assert len(result.tracks) == 2
        assert 77158728 in result.tracks
        assert len(result.artists) == 2
        assert 38895 in result.artists
        mock_transport.get.assert_called_once_with(
            "favorite/getUserFavoriteIds",
            {"limit": 5000},
        )

    async def test_custom_limit(self, mock_transport):
        mock_transport.get.return_value = (200, {
            "albums": [], "tracks": [], "artists": [],
            "labels": [], "awards": [],
        })
        api = FavoritesAPI(mock_transport)

        await api.get_ids(limit=1000)

        mock_transport.get.assert_called_once_with(
            "favorite/getUserFavoriteIds",
            {"limit": 1000},
        )
