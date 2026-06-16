import os
import pytest
import deezer
from unittest.mock import Mock, patch
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
    """Unit test: WrongLicense raises NonStreamableError when fallback is disabled."""
    mock_deezer_client.config.lower_quality_if_not_available = False

    mock_track_info = {
        "FILESIZE_FLAC": 25000000,
        "FILESIZE_MP3_320": 5000000,
        "FILESIZE_MP3_128": 2000000,
        "TRACK_TOKEN": "test_token",
    }
    mock_deezer_client.client.gw.get_track.return_value = mock_track_info
    # Simulate the account not having FLAC rights
    mock_deezer_client.client.get_track_url.side_effect = deezer.WrongLicense("FLAC")

    with patch.object(mock_deezer_client, 'get_session'):
        with pytest.raises(NonStreamableError, match="fallback is disabled"):
            arun(mock_deezer_client.get_downloadable("123", quality=2))

def test_deezer_album_cache(mock_deezer_client):
    """Unit test: verify get_album results are cached and retrieved on subsequent calls"""
    mock_deezer_client.client.api.get_album.return_value = {"id": "album_123", "title": "Test Album", "genres": {"data": []}}
    mock_deezer_client.client.api.get_album_tracks.return_value = {"data": []}
    
    # Call get_album twice
    res1 = arun(mock_deezer_client.get_album("album_123"))
    res2 = arun(mock_deezer_client.get_album("album_123"))
    
    # Assert return values are identical
    assert res1 == res2
    assert res1["title"] == "Test Album"
    
    # Assert api call was made exactly once
    assert mock_deezer_client.client.api.get_album.call_count == 1
    assert mock_deezer_client.client.api.get_album_tracks.call_count == 1

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
