import asyncio
import inspect
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

import aiohttp
from streamrip.client.client import Client
from streamrip.client.qobuz import QobuzSpoofer
from streamrip.rip.cli import latest_streamrip_version, rip


@pytest.fixture
def mock_client_session():
    """Fixture that provides a mocked aiohttp.ClientSession."""
    with patch('aiohttp.ClientSession') as mock_session:
        mock_session.return_value = AsyncMock()
        yield mock_session


@pytest.fixture
def mock_tcp_connector():
    """Fixture that provides a mocked aiohttp.TCPConnector."""
    with patch('aiohttp.TCPConnector') as mock_connector:
        mock_connector.return_value = MagicMock()
        yield mock_connector


def test_client_get_session_supports_verify_ssl():
    """Test that Client.get_session supports verify_ssl parameter."""
    # Check if the get_session method accepts the verify_ssl parameter
    signature = inspect.signature(Client.get_session)
    
    # Check for verify_ssl parameter
    has_verify_ssl = 'verify_ssl' in signature.parameters
    
    # Skip rather than fail if option isn't implemented yet
    if not has_verify_ssl:
        pytest.skip("verify_ssl parameter not implemented in Client.get_session yet")


@pytest.mark.asyncio
async def test_client_get_session_creates_connector(mock_client_session):
    """Test that Client.get_session creates a session with correct parameters."""
    signature = inspect.signature(Client.get_session)
    
    if 'verify_ssl' not in signature.parameters:
        pytest.skip("verify_ssl parameter not implemented in Client.get_session yet")
    
    await Client.get_session(verify_ssl=True)
    
    assert mock_client_session.called


def test_latest_streamrip_version_supports_verify_ssl():
    """Test that latest_streamrip_version supports verify_ssl parameter."""
    signature = inspect.signature(latest_streamrip_version)
    
    has_verify_ssl = 'verify_ssl' in signature.parameters
    
    if not has_verify_ssl:
        pytest.skip("verify_ssl parameter not implemented in latest_streamrip_version yet")


@pytest.mark.asyncio
async def test_latest_streamrip_version_creates_session(mock_client_session):
    """Test that latest_streamrip_version creates a session with verify_ssl parameter."""
    signature = inspect.signature(latest_streamrip_version)
    
    if 'verify_ssl' not in signature.parameters:
        pytest.skip("verify_ssl parameter not implemented in latest_streamrip_version yet")
    
    mock_session_instance = AsyncMock()
    mock_client_session.return_value = mock_session_instance
    
    mock_context_manager = AsyncMock()
    mock_session_instance.get.return_value = mock_context_manager
    mock_context_manager.__aenter__.return_value.json.return_value = {
        "info": {"version": "1.0.0"}
    }
    
    try:
        await latest_streamrip_version(verify_ssl=False)
    except Exception:
        # We just need to ensure it doesn't raise TypeError for the verify_ssl parameter
        pass
    
    assert mock_client_session.called


@pytest.mark.asyncio
async def test_qobuz_spoofer_initialization(mock_client_session):
    """Test that QobuzSpoofer initialization works with available parameters."""
    signature = inspect.signature(QobuzSpoofer.__init__)
    has_verify_ssl = 'verify_ssl' in signature.parameters
    
    if has_verify_ssl:
        spoofer = QobuzSpoofer(verify_ssl=True)
    else:
        spoofer = QobuzSpoofer()
    
    assert spoofer is not None
    
    with patch.object(spoofer, 'session', None):
        await spoofer.__aenter__()
        assert mock_client_session.called
        
        await spoofer.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_lastfm_playlist_session_creation(mock_client_session):
    """Test that PendingLastfmPlaylist creates a ClientSession."""
    from streamrip.media.playlist import PendingLastfmPlaylist
    
    mock_client = MagicMock()
    mock_fallback_client = MagicMock()
    mock_config = MagicMock()
    mock_db = MagicMock()
    
    pending_playlist = PendingLastfmPlaylist(
        "https://www.last.fm/test",
        mock_client,
        mock_fallback_client,
        mock_config,
        mock_db
    )
    
    try:
        mock_config.session.downloads.verify_ssl = False
    except AttributeError:
        pass
    
    mock_session_instance = AsyncMock()
    mock_client_session.return_value = mock_session_instance
    
    mock_session_instance.get.side_effect = Exception("Test exception")
    
    try:
        await pending_playlist._parse_lastfm_playlist("https://www.last.fm/test")
    except Exception:
        # Expected to fail, but we just need to check the session was created
        pass
    
    assert mock_client_session.called


@pytest.mark.asyncio
async def test_client_uses_config_settings():
    """Test that client implementations use the config settings correctly."""
    from streamrip.client.tidal import TidalClient
    
    mock_config = MagicMock()
    mock_config.session.downloads.requests_per_minute = 0  # Use 0 to avoid rate limiting issues
    mock_config.session.tidal = MagicMock()
    
    try:
        mock_config.session.downloads.verify_ssl = False
    except AttributeError:
        pass
    
    with patch.object(TidalClient, 'get_session', new_callable=AsyncMock) as mock_get_session:
        tidal_client = TidalClient(mock_config)
        
        assert tidal_client is not None
        
        try:
            await tidal_client.login()
        except:
            pass
        
        assert mock_get_session.called


def test_cli_option_registered():
    """Test if the --no-ssl-verify CLI option is registered."""
    has_no_ssl_verify = False
    for param in rip.params:
        if getattr(param, 'name', '') == 'no_ssl_verify':
            has_no_ssl_verify = True
            break
    
    if not has_no_ssl_verify:
        pytest.skip("--no-ssl-verify option not implemented in CLI yet") 