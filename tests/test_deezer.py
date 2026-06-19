import asyncio
import os
from unittest.mock import AsyncMock, Mock, patch

import deezer
import pytest
from deezer.errors import DataException
from util import arun

from streamrip.client.deezer import DeezerClient
from streamrip.config import Config
from streamrip.exceptions import NonStreamableError


@pytest.fixture(scope="session")
def deezer_client():
    """Integration test fixture — requires DEEZER_ARL environment variable."""
    config = Config.defaults()
    config.session.deezer.arl = os.environ.get("DEEZER_ARL", "")
    config.session.deezer.quality = 2
    config.session.deezer.lower_quality_if_not_available = True
    client = DeezerClient(config)
    arun(client.login())

    yield client

    arun(client.session.close())


@pytest.fixture
def mock_deezer_client():
    """Unit test fixture — mocked deezer.Deezer client for fast, offline testing."""
    config = Config.defaults()
    config.session.deezer.arl = "test_arl"
    config.session.deezer.quality = 2
    config.session.deezer.lower_quality_if_not_available = True

    client = DeezerClient(config)
    client.client = Mock()
    client.client.gw = Mock()
    client.session = Mock()

    return client


# ===== get_downloadable — guard =====

def test_deezer_item_id_none(mock_deezer_client):
    """get_downloadable raises NonStreamableError immediately when item_id is None."""
    with pytest.raises(NonStreamableError):
        arun(mock_deezer_client.get_downloadable(None, quality=2))


# ===== get_downloadable — quality fallback =====

def test_deezer_fallback_logic_with_mock_data(mock_deezer_client):
    """WrongLicense on FLAC triggers fallback to MP3_320."""
    mock_track_info = {
        "FILESIZE_FLAC": 0,
        "FILESIZE_MP3_320": 5_000_000,
        "FILESIZE_MP3_128": 2_000_000,
        "TRACK_TOKEN": "test_token",
    }
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info

    def url_side_effect(token, fmt):
        if fmt == "FLAC":
            raise deezer.WrongLicense("FLAC")
        return "https://test.mp3"

    mock_deezer_client.client.get_track_url.side_effect = url_side_effect

    downloadable = arun(mock_deezer_client.get_downloadable("123", quality=2))
    assert downloadable.quality == 1


def test_deezer_no_fallback_when_quality_available(mock_deezer_client):
    """Requested quality is returned unchanged when the API accepts it."""
    mock_track_info = {
        "FILESIZE_FLAC": 25_000_000,
        "FILESIZE_MP3_320": 5_000_000,
        "FILESIZE_MP3_128": 2_000_000,
        "TRACK_TOKEN": "test_token",
    }
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info
    mock_deezer_client.client.get_track_url.return_value = "https://test.flac"

    downloadable = arun(mock_deezer_client.get_downloadable("123", quality=2))
    assert downloadable.quality == 2


def test_deezer_fallback_to_lowest_available_quality(mock_deezer_client):
    """WrongLicense on FLAC and MP3_320 falls back all the way to MP3_128."""
    mock_track_info = {
        "FILESIZE_FLAC": 0,
        "FILESIZE_MP3_320": 0,
        "FILESIZE_MP3_128": 2_000_000,
        "TRACK_TOKEN": "test_token",
    }
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info

    def url_side_effect(token, fmt):
        if fmt in ("FLAC", "MP3_320"):
            raise deezer.WrongLicense(fmt)
        return "https://test.mp3"

    mock_deezer_client.client.get_track_url.side_effect = url_side_effect

    downloadable = arun(mock_deezer_client.get_downloadable("123", quality=2))
    assert downloadable.quality == 0


def test_deezer_no_fallback_when_disabled(mock_deezer_client):
    """WrongLicense raises NonStreamableError immediately when fallback is disabled."""
    mock_deezer_client.config.lower_quality_if_not_available = False

    mock_track_info = {
        "FILESIZE_FLAC": 25_000_000,
        "FILESIZE_MP3_320": 5_000_000,
        "FILESIZE_MP3_128": 2_000_000,
        "TRACK_TOKEN": "test_token",
    }
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info
    mock_deezer_client.client.get_track_url.side_effect = deezer.WrongLicense("FLAC")

    with pytest.raises(NonStreamableError, match="fallback is disabled"):
        arun(mock_deezer_client.get_downloadable("123", quality=2))


def test_deezer_wrong_license_all_qualities(mock_deezer_client):
    """WrongLicense on every quality level falls through to the encrypted CDN URL."""
    mock_track_info = {
        "FILESIZE_FLAC": 25_000_000,
        "FILESIZE_MP3_320": 5_000_000,
        "FILESIZE_MP3_128": 2_000_000,
        "TRACK_TOKEN": "test_token",
        "MD5_ORIGIN": "abc123def456abc123def456abc12345",
        "MEDIA_VERSION": "1",
    }
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info
    mock_deezer_client.client.get_track_url.side_effect = deezer.WrongLicense("any")

    with patch.object(
        mock_deezer_client,
        "_get_encrypted_file_url",
        return_value="https://e-cdns-proxy-a.dzcdn.net/mobile/1/deadbeef",
    ) as mock_encrypted:
        downloadable = arun(mock_deezer_client.get_downloadable("123", quality=2))

    mock_encrypted.assert_called_once_with(
        "123", "abc123def456abc123def456abc12345", "1"
    )
    assert downloadable.url == "https://e-cdns-proxy-a.dzcdn.net/mobile/1/deadbeef"


# ===== get_downloadable — geoblocking =====

def test_deezer_geoblocked_with_fallback(mock_deezer_client):
    """WrongGeolocation retries the download using the FALLBACK track ID."""
    def gw_get_track_side_effect(track_id):
        if track_id == "123":
            return {
                "FILESIZE_FLAC": 25_000_000,
                "FILESIZE_MP3_320": 5_000_000,
                "FILESIZE_MP3_128": 2_000_000,
                "TRACK_TOKEN": "token_123",
                "FALLBACK": {"SNG_ID": "456"},
            }
        return {
            "FILESIZE_FLAC": 25_000_000,
            "FILESIZE_MP3_320": 5_000_000,
            "FILESIZE_MP3_128": 2_000_000,
            "TRACK_TOKEN": "token_456",
        }

    mock_deezer_client.client.gw.get_track.side_effect = gw_get_track_side_effect

    def url_side_effect(token, fmt):
        if token == "token_123":
            raise deezer.WrongGeolocation("FR")
        return "https://test.flac"

    mock_deezer_client.client.get_track_url.side_effect = url_side_effect

    downloadable = arun(mock_deezer_client.get_downloadable("123", quality=2))
    assert downloadable.quality == 2
    assert mock_deezer_client.client.gw.get_track.call_count == 2


def test_deezer_geoblocked_no_fallback(mock_deezer_client):
    """WrongGeolocation raises NonStreamableError when no FALLBACK ID is available."""
    mock_track_info = {
        "FILESIZE_FLAC": 25_000_000,
        "FILESIZE_MP3_320": 5_000_000,
        "FILESIZE_MP3_128": 2_000_000,
        "TRACK_TOKEN": "test_token",
        # no FALLBACK key
    }
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info
    mock_deezer_client.client.get_track_url.side_effect = deezer.WrongGeolocation("FR")

    with pytest.raises(NonStreamableError, match="geoblocked"):
        arun(mock_deezer_client.get_downloadable("123", quality=2))


# ===== get_downloadable — encrypted URL fallback =====

def test_deezer_encrypted_url_fallback(mock_deezer_client):
    """When get_track_url returns None for all qualities, falls back to the AES-encrypted CDN URL."""
    mock_track_info = {
        "FILESIZE_FLAC": 25_000_000,
        "FILESIZE_MP3_320": 5_000_000,
        "FILESIZE_MP3_128": 2_000_000,
        "TRACK_TOKEN": "test_token",
        "MD5_ORIGIN": "abc123def456abc123def456abc12345",
        "MEDIA_VERSION": "1",
    }
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info
    mock_deezer_client.client.get_track_url.return_value = None

    with patch.object(
        mock_deezer_client,
        "_get_encrypted_file_url",
        return_value="https://e-cdns-proxy-a.dzcdn.net/mobile/1/deadbeef",
    ) as mock_encrypted:
        downloadable = arun(mock_deezer_client.get_downloadable("123", quality=2))

    mock_encrypted.assert_called_once_with(
        "123", "abc123def456abc123def456abc12345", "1"
    )
    assert downloadable.url == "https://e-cdns-proxy-a.dzcdn.net/mobile/1/deadbeef"


# ===== get_album =====

def test_deezer_album_cache(mock_deezer_client):
    """Repeated get_album calls for the same ID hit the API exactly once."""
    mock_deezer_client.client.api.get_album.return_value = {
        "id": "album_123",
        "title": "Test Album",
        "genres": {"data": []},
    }
    mock_deezer_client.client.api.get_album_tracks.return_value = {"data": []}

    res1 = arun(mock_deezer_client.get_album("album_123"))
    res2 = arun(mock_deezer_client.get_album("album_123"))

    assert res1 == res2
    assert res1["title"] == "Test Album"
    assert mock_deezer_client.client.api.get_album.call_count == 1
    assert mock_deezer_client.client.api.get_album_tracks.call_count == 1


def test_deezer_album_cache_concurrent(mock_deezer_client):
    """Concurrent get_album calls for the same ID make only one pair of API calls."""
    mock_deezer_client.client.api.get_album.return_value = {
        "id": "album_123",
        "title": "Test Album",
        "genres": {"data": []},
    }
    mock_deezer_client.client.api.get_album_tracks.return_value = {"data": []}

    async def run():
        return await asyncio.gather(
            mock_deezer_client.get_album("album_123"),
            mock_deezer_client.get_album("album_123"),
            mock_deezer_client.get_album("album_123"),
        )

    results = arun(run())
    assert all(r["title"] == "Test Album" for r in results)
    assert mock_deezer_client.client.api.get_album.call_count == 1
    assert mock_deezer_client.client.api.get_album_tracks.call_count == 1


def test_deezer_get_album_redirect(mock_deezer_client):
    """DataException on get_album triggers redirect resolution; original ID is cached."""
    def api_get_album_side_effect(item_id):
        if item_id == "old_id":
            raise DataException
        return {"id": item_id, "title": "Redirected Album"}

    def api_get_album_tracks_side_effect(item_id):
        if item_id == "old_id":
            raise DataException
        return {"data": []}

    mock_deezer_client.client.api.get_album.side_effect = api_get_album_side_effect
    mock_deezer_client.client.api.get_album_tracks.side_effect = api_get_album_tracks_side_effect

    with patch.object(
        mock_deezer_client,
        "_resolve_redirect",
        new=AsyncMock(return_value="new_id"),
    ):
        result = arun(mock_deezer_client.get_album("old_id"))

    assert result["title"] == "Redirected Album"
    # Both the original and canonical IDs should be in the cache.
    assert mock_deezer_client._album_cache.get("old_id") is not None
    assert mock_deezer_client._album_cache.get("new_id") is not None


# ===== get_track =====

def test_deezer_get_track(mock_deezer_client):
    """get_track returns a track dict with full album metadata embedded."""
    mock_deezer_client.client.api.get_track.return_value = {
        "id": "100",
        "title": "Test Track",
        "album": {"id": 200},
    }
    mock_deezer_client.client.api.get_album.return_value = {
        "id": "200",
        "title": "Test Album",
    }
    mock_deezer_client.client.api.get_album_tracks.return_value = {
        "data": [{"id": "100"}]
    }
    mock_deezer_client.client.gw.get_track.return_value = {
        "SNG_CONTRIBUTORS": {"composer": ["Bach", "Handel"]},
    }

    track = arun(mock_deezer_client.get_track("100"))

    assert track["title"] == "Test Track"
    assert track["album"]["title"] == "Test Album"
    assert track["album"]["track_total"] == 1
    assert track["composer"] == ["Bach", "Handel"]


def test_deezer_get_track_for_playlist(mock_deezer_client):
    """get_track_for_playlist skips get_album and keeps the REST stub album object."""
    mock_deezer_client.client.api.get_track.return_value = {
        "id": "100",
        "title": "Test Track",
        "album": {"id": 200, "title": "Stub Album"},
    }
    mock_deezer_client.client.gw.get_track.return_value = {
        "SNG_CONTRIBUTORS": {"author": ["Lennon"]},
        "GAIN": "-6.0",
    }

    track = arun(mock_deezer_client.get_track_for_playlist("100"))

    assert track["title"] == "Test Track"
    # album sub-object is the minimal REST stub, not the full album fetch
    assert track["album"] == {"id": 200, "title": "Stub Album"}
    assert track["author"] == ["Lennon"]
    assert track["gain"] == "-6.0"
    # get_album must NOT have been called
    mock_deezer_client.client.api.get_album.assert_not_called()
    mock_deezer_client.client.api.get_album_tracks.assert_not_called()


# ===== get_playlist =====

def test_deezer_get_playlist(mock_deezer_client):
    """get_playlist returns a normalized structure from the GW API response."""
    mock_deezer_client.client.gw.get_playlist.return_value = {
        "DATA": {"TITLE": "My Playlist"}
    }
    mock_deezer_client.client.gw.get_playlist_tracks.return_value = [
        {"SNG_ID": "1"},
        {"SNG_ID": "2"},
    ]

    result = arun(mock_deezer_client.get_playlist("playlist_123"))

    assert result["title"] == "My Playlist"
    assert result["track_total"] == 2
    assert result["tracks"] == [{"id": "1"}, {"id": "2"}]


def test_deezer_get_playlist_favorites_routing(mock_deezer_client):
    """get_playlist routes 'favorites:<user_id>' to get_user_favorites."""
    mock_deezer_client.logged_in_user_id = 42
    mock_deezer_client.client.gw.get_my_favorite_tracks.return_value = [
        {"id": "1"},
        {"id": "2"},
        {"id": "3"},
    ]

    result = arun(mock_deezer_client.get_playlist("favorites:42"))

    assert result["title"] == "Loved Tracks"
    assert result["track_total"] == 3
    assert result["tracks"] == [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    mock_deezer_client.client.gw.get_my_favorite_tracks.assert_called_once()
    mock_deezer_client.client.gw.get_playlist.assert_not_called()


# ===== get_user_favorites =====

def test_deezer_get_user_favorites_own_profile(mock_deezer_client):
    """Fetching own favorites calls get_my_favorite_tracks, never get_user_tracks."""
    mock_deezer_client.logged_in_user_id = 42
    # get_my_favorite_tracks returns map_user_track() results, which have "id" not "SNG_ID"
    mock_deezer_client.client.gw.get_my_favorite_tracks.return_value = [{"id": "1"}]

    result = arun(mock_deezer_client.get_user_favorites("42"))

    assert result["track_total"] == 1
    assert result["tracks"] == [{"id": "1"}]
    mock_deezer_client.client.gw.get_my_favorite_tracks.assert_called_once_with(
        DeezerClient.max_favorites
    )
    mock_deezer_client.client.gw.get_user_tracks.assert_not_called()


def test_deezer_get_user_favorites_other_profile(mock_deezer_client):
    """Fetching another user's favorites calls get_user_tracks with the numeric UID."""
    mock_deezer_client.logged_in_user_id = 42
    # get_user_tracks returns map_user_track() results, which have "id" not "SNG_ID"
    mock_deezer_client.client.gw.get_user_tracks.return_value = [
        {"id": "1"},
        {"id": "2"},
    ]

    result = arun(mock_deezer_client.get_user_favorites("99"))

    assert result["track_total"] == 2
    assert result["tracks"] == [{"id": "1"}, {"id": "2"}]
    mock_deezer_client.client.gw.get_user_tracks.assert_called_once_with(
        99, DeezerClient.max_favorites
    )
    mock_deezer_client.client.gw.get_my_favorite_tracks.assert_not_called()


# ===== get_metadata =====

def test_deezer_get_metadata_dispatch(mock_deezer_client):
    """get_metadata dispatches to the correct handler for each media type."""
    with patch.object(
        mock_deezer_client, "get_album", return_value={"id": "1"}
    ) as mock_get_album:
        result = arun(mock_deezer_client.get_metadata("1", "album"))
        mock_get_album.assert_called_once_with("1")
        assert result == {"id": "1"}


def test_deezer_get_metadata_invalid_type(mock_deezer_client):
    """get_metadata raises for unsupported media types."""
    with pytest.raises(Exception, match="not available on deezer"):
        arun(mock_deezer_client.get_metadata("1", "label"))


# ===== search =====

def test_deezer_search_track(mock_deezer_client):
    """search returns a list containing the API response when results are found."""
    mock_deezer_client.client.api.search_track.return_value = {
        "total": 2,
        "data": [{"id": "1"}, {"id": "2"}],
    }

    results = arun(mock_deezer_client.search("track", "test query"))

    assert len(results) == 1
    assert results[0]["total"] == 2
    mock_deezer_client.client.api.search_track.assert_called_once_with(
        "test query", limit=200
    )


def test_deezer_search_no_results(mock_deezer_client):
    """search returns an empty list when the API reports zero results."""
    mock_deezer_client.client.api.search_track.return_value = {"total": 0, "data": []}

    results = arun(mock_deezer_client.search("track", "nonexistent"))

    assert results == []


# ===== Integration test =====

@pytest.mark.skipif(
    "DEEZER_ARL" not in os.environ, reason="Deezer ARL not found in env."
)
def test_deezer_fallback_actually_occurred(deezer_client):
    """Integration: track 77874822 has no FLAC — verify fallback to MP3_320."""
    downloadable = arun(deezer_client.get_downloadable("77874822", quality=2))

    assert downloadable.quality == 1, "Should have fallen back to MP3_320 when FLAC unavailable"
    assert downloadable.url.startswith("https://")
    assert downloadable._size > 0, "Downloadable should have a valid file size"
    assert downloadable.extension == "mp3", "MP3_320 should have .mp3 extension"
