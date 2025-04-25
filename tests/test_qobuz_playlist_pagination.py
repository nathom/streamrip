import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from streamrip.client.qobuz import QobuzClient
from streamrip.config import Config


@pytest.fixture
def mock_config():
    """Fixture that provides a mocked Config."""
    config = MagicMock()
    # Create nested mock objects
    session = MagicMock()
    qobuz = MagicMock()
    downloads = MagicMock()
    
    # Set up the structure
    config.session = session
    session.qobuz = qobuz
    session.downloads = downloads
    
    # Set the values
    qobuz.app_id = "12345"
    qobuz.email_or_userid = "test@example.com"
    qobuz.password_or_token = "test_token"
    qobuz.use_auth_token = True
    qobuz.secrets = ["secret1", "secret2"]
    downloads.verify_ssl = True
    downloads.requests_per_minute = 100
    
    return config


@pytest.fixture
def mock_qobuz_client(mock_config):
    """Fixture that provides a mocked QobuzClient."""
    with patch.object(QobuzClient, "login", AsyncMock(return_value=None)):
        with patch.object(QobuzClient, "get_session", AsyncMock()):
            client = QobuzClient(mock_config)
            client.session = MagicMock()
            client.logged_in = True
            client.secret = "test_secret"
            yield client


@pytest.mark.asyncio
async def test_get_playlist_pagination(mock_qobuz_client):
    """Test that get_playlist correctly paginates results for large playlists."""
    # Mock the _api_request method to return different responses for different offsets
    
    # First page response (offset 0)
    first_page_response = {
        "tracks_count": 1200,  # Total tracks in the playlist
        "tracks": {
            "items": [{"id": f"track_{i}"} for i in range(500)]  # 500 tracks
        }
    }
    
    # Second page response (offset 500)
    second_page_response = {
        "tracks": {
            "items": [{"id": f"track_{i}"} for i in range(500, 1000)]  # 500 more tracks
        }
    }
    
    # Third page response (offset 1000)
    third_page_response = {
        "tracks": {
            "items": [{"id": f"track_{i}"} for i in range(1000, 1200)]  # 200 more tracks
        }
    }
    
    # Mock the _api_request method to return different responses based on offset
    async def mock_api_request(endpoint, params):
        if params.get("offset") == 0:
            return 200, first_page_response
        elif params.get("offset") == 500:
            return 200, second_page_response
        elif params.get("offset") == 1000:
            return 200, third_page_response
        else:
            return 404, {"message": "Not found"}
    
    mock_qobuz_client._api_request = AsyncMock(side_effect=mock_api_request)
    
    # Call the get_playlist method
    result = await mock_qobuz_client.get_playlist("test_playlist_id")
    
    # Verify that the _api_request method was called with the correct parameters
    assert mock_qobuz_client._api_request.call_count == 3
    
    # Verify that the result contains all tracks from all pages
    assert len(result["tracks"]["items"]) == 1200
    
    # Verify that the tracks are in the correct order
    for i in range(1200):
        assert result["tracks"]["items"][i]["id"] == f"track_{i}"


@pytest.mark.asyncio
async def test_get_playlist_small(mock_qobuz_client):
    """Test that get_playlist works correctly for small playlists (no pagination needed)."""
    # Mock response for a small playlist
    small_playlist_response = {
        "tracks_count": 100,  # Total tracks in the playlist
        "tracks": {
            "items": [{"id": f"track_{i}"} for i in range(100)]  # 100 tracks
        }
    }
    
    # Mock the _api_request method to return the small playlist response
    mock_qobuz_client._api_request = AsyncMock(return_value=(200, small_playlist_response))
    
    # Call the get_playlist method
    result = await mock_qobuz_client.get_playlist("test_small_playlist_id")
    
    # Verify that the _api_request method was called only once (no pagination needed)
    assert mock_qobuz_client._api_request.call_count == 1
    
    # Verify that the result contains all tracks
    assert len(result["tracks"]["items"]) == 100
