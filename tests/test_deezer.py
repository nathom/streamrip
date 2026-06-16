import os
import pytest
import deezer
from unittest.mock import Mock, AsyncMock, patch
from util import arun

from streamrip.client.downloadable import DeezerDownloadable
from streamrip.client.deezer import DeezerClient
from streamrip.config import Config
from streamrip.exceptions import NonStreamableError

@pytest.fixture(scope="session")
def deezer_client():
    """Integration test fixture - requires DEEZER_ARL environment variable"""
    config = Config.defaults()
    config.session.deezer.arl = os.environ.get("DEEZER_ARL", "")
    config.session.deezer.quality = 2  # FLAC
    config.session.deezer.lower_quality_if_not_available = True
    client = DeezerClient(config)
    arun(client.login())
    
    yield client
    
    arun(client.session.close())

@pytest.fixture
def mock_deezer_client():
    """Unit test fixture - mocked client for fast testing"""
    config = Config.defaults()
    config.session.deezer.arl = "test_arl"
    config.session.deezer.quality = 2
    config.session.deezer.lower_quality_if_not_available = True
    
    client = DeezerClient(config)
    client.client = Mock()
    client.client.gw = Mock()
    client.session = Mock()
    
    return client

# ===== UNIT TESTS =====

def test_deezer_fallback_logic_with_mock_data(mock_deezer_client):
    """Unit test: fallback logic works with mocked track data"""
    # Mock track info where FLAC is unavailable but MP3_320 is available
    # quality_map: [(9, "MP3_128"), (3, "MP3_320"), (1, "FLAC")]
    # So FILESIZE_MP3_128 = quality 0, FILESIZE_MP3_320 = quality 1, FILESIZE_FLAC = quality 2
    mock_track_info = {
        "FILESIZE_FLAC": 0,      # FLAC unavailable (quality 2)
        "FILESIZE_MP3_320": 5000000, # MP3_320 available (quality 1)
        "FILESIZE_MP3_128": 2000000, # MP3_128 available (quality 0)
        "TRACK_TOKEN": "test_token"
    }
    
    # Mock the client methods
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info
    mock_deezer_client.client.get_track_url.return_value = "https://test.mp3"
    
    # Test fallback behavior
    with patch.object(mock_deezer_client, 'get_session'):
        downloadable = arun(mock_deezer_client.get_downloadable("123", quality=2))
        
        # Should have fallen back to quality 1 (MP3_320) since FLAC is unavailable
        assert downloadable.quality == 1

def test_deezer_no_fallback_when_quality_available(mock_deezer_client):
    """Unit test: no fallback when requested quality is available"""
    # Mock track info where FLAC is available
    # quality_map: [(9, "MP3_128"), (3, "MP3_320"), (1, "FLAC")]
    mock_track_info = {
        "FILESIZE_FLAC": 25000000, # FLAC available (quality 2)
        "FILESIZE_MP3_320": 5000000,  # MP3_320 available (quality 1)
        "FILESIZE_MP3_128": 2000000,  # MP3_128 available (quality 0)
        "TRACK_TOKEN": "test_token"
    }
    
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info
    mock_deezer_client.client.get_track_url.return_value = "https://test.flac"
    
    with patch.object(mock_deezer_client, 'get_session'):
        downloadable = arun(mock_deezer_client.get_downloadable("123", quality=2))
        
        # Should use requested quality 2 (FLAC)
        assert downloadable.quality == 2

def test_deezer_fallback_to_lowest_available_quality(mock_deezer_client):
    """Unit test: fallback walks down quality list until finding available quality"""
    # Mock track info where only MP3_128 is available
    # quality_map: [(9, "MP3_128"), (3, "MP3_320"), (1, "FLAC")]
    mock_track_info = {
        "FILESIZE_FLAC": 0,      # FLAC unavailable (quality 2)
        "FILESIZE_MP3_320": 0,      # MP3_320 unavailable (quality 1)
        "FILESIZE_MP3_128": 2000000, # MP3_128 available (quality 0)
        "TRACK_TOKEN": "test_token"
    }
    
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info
    mock_deezer_client.client.get_track_url.return_value = "https://test.mp3"
    
    with patch.object(mock_deezer_client, 'get_session'):
        downloadable = arun(mock_deezer_client.get_downloadable("123", quality=2))
        
        # Should have fallen back to quality 0 (MP3_128) since higher qualities unavailable
        assert downloadable.quality == 0

def test_deezer_no_fallback_when_disabled(mock_deezer_client):
    """Unit test: no fallback when lower_quality_if_not_available is False"""
    # Disable fallback
    mock_deezer_client.config.lower_quality_if_not_available = False
    
    # Mock track info where FLAC is unavailable
    # quality_map: [(9, "MP3_128"), (3, "MP3_320"), (1, "FLAC")]
    mock_track_info = {
        "FILESIZE_FLAC": 0,      # FLAC unavailable (quality 2)
        "FILESIZE_MP3_320": 5000000, # MP3_320 available (quality 1)
        "FILESIZE_MP3_128": 2000000, # MP3_128 available (quality 0)
        "TRACK_TOKEN": "test_url"
    }
    
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info
    mock_deezer_client.client.get_track_url.return_value = "https://test.mp3"
    
    # Should raise an error when requested quality is unavailable and fallback is disabled
    with patch.object(mock_deezer_client, 'get_session'):
        with pytest.raises(NonStreamableError, match="The requested quality 2 is not available and fallback is disabled"):
            arun(mock_deezer_client.get_downloadable("123", quality=2))

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

    with pytest.raises(NonStreamableError, match="country"):
        arun(mock_deezer_client.get_downloadable("123", quality=2))


# ===== get_downloadable — encrypted URL fallback =====

def test_deezer_encrypted_url_fallback(mock_deezer_client):
    """When get_track_url returns None, falls back to the AES-encrypted CDN URL."""
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

    track = arun(mock_deezer_client.get_track("100"))

    assert track["title"] == "Test Track"
    assert track["album"]["title"] == "Test Album"
    assert track["album"]["track_total"] == 1


# ===== get_playlist =====

def test_deezer_get_playlist(mock_deezer_client):
    """get_playlist returns playlist metadata enriched with tracks and track_total."""
    mock_deezer_client.client.api.get_playlist.return_value = {
        "title": "My Playlist",
    }
    mock_deezer_client.client.api.get_playlist_tracks.return_value = {
        "data": [{"id": "1"}, {"id": "2"}],
    }

    result = arun(mock_deezer_client.get_playlist("playlist_123"))

    assert result["title"] == "My Playlist"
    assert result["track_total"] == 2
    assert len(result["tracks"]) == 2


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


# ===== INTEGRATION TEST =====

@pytest.mark.skipif(
    "DEEZER_ARL" not in os.environ, reason="Deezer ARL not found in env."
)
def test_deezer_fallback_actually_occurred(deezer_client):
    """Integration test: verify fallback works with real track 77874822"""
    # We know track 77874822 doesn't have FLAC available, so test fallback scenario
    downloadable = arun(deezer_client.get_downloadable("77874822", quality=2))
    
    # Since we requested FLAC (quality=2) but it's not available,
    # we should have fallen back to the next available quality (1 = MP3_320)
    assert downloadable.quality == 1, "Should have fallen back to MP3_320 when FLAC unavailable"
    print("Fallback occurred: FLAC unavailable, fell back to MP3_320")
    
    # Verify the URL is actually accessible and working
    assert downloadable.url.startswith("https://")
    assert downloadable._size > 0, "Downloadable should have a valid file size"
    assert downloadable.extension == "mp3", "MP3_320 should have .mp3 extension"
