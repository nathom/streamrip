"""Tests for catalog API (albums, artists, tracks, search, batch)."""

import pytest
from unittest.mock import AsyncMock

from conftest import SAMPLE_ALBUM, SAMPLE_TRACK

from qobuz.catalog import CatalogAPI
from qobuz.types import Album, Track, PaginatedResult


@pytest.fixture
def catalog(mock_transport: AsyncMock) -> CatalogAPI:
    return CatalogAPI(mock_transport)


# ---------------------------------------------------------------------------
# Albums
# ---------------------------------------------------------------------------


async def test_get_album_returns_album(catalog: CatalogAPI, mock_transport: AsyncMock):
    mock_transport.get.return_value = (200, SAMPLE_ALBUM)

    result = await catalog.get_album("p0d55tt7gv3lc")

    assert isinstance(result, Album)
    assert result.id == "p0d55tt7gv3lc"
    assert result.title == "Virgin Lake"
    assert result.artist.name == "Philine Sonny"
    mock_transport.get.assert_awaited_once_with(
        "album/get",
        {"album_id": "p0d55tt7gv3lc", "extra": "track_ids,albumsFromSameArtist"},
    )


async def test_get_album_custom_extra(catalog: CatalogAPI, mock_transport: AsyncMock):
    mock_transport.get.return_value = (200, SAMPLE_ALBUM)

    await catalog.get_album("p0d55tt7gv3lc", extra="track_ids")

    mock_transport.get.assert_awaited_once_with(
        "album/get",
        {"album_id": "p0d55tt7gv3lc", "extra": "track_ids"},
    )


async def test_search_albums_returns_paginated_result(
    catalog: CatalogAPI, mock_transport: AsyncMock
):
    mock_transport.get.return_value = (
        200,
        {
            "albums": {
                "items": [SAMPLE_ALBUM, SAMPLE_ALBUM],
                "total": 150,
                "limit": 50,
                "offset": 0,
            }
        },
    )

    result = await catalog.search_albums("Philine Sonny")

    assert isinstance(result, PaginatedResult)
    assert result.total == 150
    assert len(result.items) == 2
    assert result.limit == 50
    assert result.offset == 0
    assert result.has_more is True
    mock_transport.get.assert_awaited_once_with(
        "album/search",
        {"query": "Philine Sonny", "limit": 50, "offset": 0},
    )


async def test_search_albums_custom_limit_offset(
    catalog: CatalogAPI, mock_transport: AsyncMock
):
    mock_transport.get.return_value = (
        200,
        {
            "albums": {
                "items": [SAMPLE_ALBUM],
                "total": 1,
                "limit": 10,
                "offset": 5,
            }
        },
    )

    result = await catalog.search_albums("test", limit=10, offset=5)

    assert result.total == 1
    mock_transport.get.assert_awaited_once_with(
        "album/search",
        {"query": "test", "limit": 10, "offset": 5},
    )


async def test_suggest_album_returns_list_of_albums(
    catalog: CatalogAPI, mock_transport: AsyncMock
):
    mock_transport.get.return_value = (
        200,
        {"albums": {"items": [SAMPLE_ALBUM, SAMPLE_ALBUM]}},
    )

    result = await catalog.suggest_album("p0d55tt7gv3lc")

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(a, Album) for a in result)
    assert result[0].title == "Virgin Lake"
    mock_transport.get.assert_awaited_once_with(
        "album/suggest",
        {"album_id": "p0d55tt7gv3lc"},
    )


async def test_suggest_album_empty(catalog: CatalogAPI, mock_transport: AsyncMock):
    mock_transport.get.return_value = (200, {"albums": {"items": []}})

    result = await catalog.suggest_album("nonexistent")

    assert result == []


async def test_get_album_story(catalog: CatalogAPI, mock_transport: AsyncMock):
    story_items = [
        {"type": "paragraph", "content": "Some text"},
        {"type": "image", "url": "https://example.com/img.jpg"},
    ]
    mock_transport.get.return_value = (200, {"items": story_items})

    result = await catalog.get_album_story("p0d55tt7gv3lc")

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["type"] == "paragraph"
    mock_transport.get.assert_awaited_once_with(
        "album/story",
        {"album_id": "p0d55tt7gv3lc"},
    )


# ---------------------------------------------------------------------------
# Artists
# ---------------------------------------------------------------------------


async def test_get_artist_page_returns_raw_dict(
    catalog: CatalogAPI, mock_transport: AsyncMock
):
    raw = {"id": 11162390, "name": {"display": "Philine Sonny"}, "bio": {}, "releases": {}}
    mock_transport.get.return_value = (200, raw)

    result = await catalog.get_artist_page(11162390)

    assert isinstance(result, dict)
    assert result["id"] == 11162390
    mock_transport.get.assert_awaited_once_with(
        "artist/page",
        {"artist_id": 11162390, "sort": "release_date"},
    )


async def test_get_artist_page_custom_sort(
    catalog: CatalogAPI, mock_transport: AsyncMock
):
    mock_transport.get.return_value = (200, {"id": 1})

    await catalog.get_artist_page(1, sort="popularity")

    mock_transport.get.assert_awaited_once_with(
        "artist/page",
        {"artist_id": 1, "sort": "popularity"},
    )


async def test_get_artist_releases_returns_paginated_result(
    catalog: CatalogAPI, mock_transport: AsyncMock
):
    mock_transport.get.return_value = (
        200,
        {"has_more": True, "items": [SAMPLE_ALBUM, SAMPLE_ALBUM, SAMPLE_ALBUM]},
    )

    result = await catalog.get_artist_releases(11162390)

    assert isinstance(result, PaginatedResult)
    assert result.has_more is True
    assert len(result.items) == 3
    assert result.total is None  # has_more-style pagination has no total
    mock_transport.get.assert_awaited_once_with(
        "artist/getReleasesList",
        {
            "artist_id": 11162390,
            "release_type": "all",
            "offset": 0,
            "limit": 20,
            "sort": "release_date_by_priority",
        },
    )


async def test_get_artist_releases_custom_params(
    catalog: CatalogAPI, mock_transport: AsyncMock
):
    mock_transport.get.return_value = (200, {"has_more": False, "items": []})

    result = await catalog.get_artist_releases(
        1, release_type="album", offset=20, limit=10, sort="popularity"
    )

    assert result.has_more is False
    assert len(result.items) == 0
    mock_transport.get.assert_awaited_once_with(
        "artist/getReleasesList",
        {
            "artist_id": 1,
            "release_type": "album",
            "offset": 20,
            "limit": 10,
            "sort": "popularity",
        },
    )


async def test_search_artists_returns_paginated_result(
    catalog: CatalogAPI, mock_transport: AsyncMock
):
    artist_item = {"id": 11162390, "name": "Philine Sonny", "albums_count": 25}
    mock_transport.get.return_value = (
        200,
        {
            "artists": {
                "items": [artist_item],
                "total": 1,
                "limit": 50,
                "offset": 0,
            }
        },
    )

    result = await catalog.search_artists("Philine Sonny")

    assert isinstance(result, PaginatedResult)
    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0]["name"] == "Philine Sonny"
    mock_transport.get.assert_awaited_once_with(
        "artist/search",
        {"query": "Philine Sonny", "limit": 50, "offset": 0},
    )


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------


async def test_get_track_returns_track(catalog: CatalogAPI, mock_transport: AsyncMock):
    mock_transport.get.return_value = (200, SAMPLE_TRACK)

    result = await catalog.get_track(33967376)

    assert isinstance(result, Track)
    assert result.id == 33967376
    assert result.title == "Blitzkrieg Bop"
    assert result.performer.name == "Ramones"
    mock_transport.get.assert_awaited_once_with(
        "track/get",
        {"track_id": 33967376},
    )


async def test_get_tracks_does_post_with_json_body(
    catalog: CatalogAPI, mock_transport: AsyncMock
):
    mock_transport.post_json.return_value = (
        200,
        {"tracks": {"items": [SAMPLE_TRACK, SAMPLE_TRACK]}},
    )

    result = await catalog.get_tracks([33967376, 12345678])

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(t, Track) for t in result)
    assert result[0].id == 33967376
    mock_transport.post_json.assert_awaited_once_with(
        "track/getList",
        {"tracks_id": [33967376, 12345678]},
    )


async def test_get_tracks_empty_list(catalog: CatalogAPI, mock_transport: AsyncMock):
    result = await catalog.get_tracks([])

    assert result == []
    mock_transport.post_json.assert_not_awaited()


async def test_search_tracks_returns_paginated_result(
    catalog: CatalogAPI, mock_transport: AsyncMock
):
    mock_transport.get.return_value = (
        200,
        {
            "tracks": {
                "items": [SAMPLE_TRACK],
                "total": 42,
                "limit": 50,
                "offset": 0,
            }
        },
    )

    result = await catalog.search_tracks("Blitzkrieg Bop")

    assert isinstance(result, PaginatedResult)
    assert result.total == 42
    assert len(result.items) == 1
    assert result.has_more is False
    mock_transport.get.assert_awaited_once_with(
        "track/search",
        {"query": "Blitzkrieg Bop", "limit": 50, "offset": 0},
    )
