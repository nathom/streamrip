import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from streamrip.media.playlist import Playlist, PendingPlaylistTrack
from streamrip.media.album import Album, PendingTrack
from streamrip.exceptions import NonStreamableError


class TestErrorHandling:
    """Test error handling in playlist and album downloads."""

    @pytest.mark.asyncio
    async def test_playlist_handles_failed_track(self):
        """Test that a playlist download continues even if one track fails."""
        mock_config = MagicMock()
        mock_client = MagicMock()
        mock_db = MagicMock()
        
        mock_track_success = MagicMock()
        mock_track_success.resolve = AsyncMock(return_value=MagicMock())
        mock_track_success.resolve.return_value.rip = AsyncMock()
        
        mock_track_failure = MagicMock()
        mock_track_failure.resolve = AsyncMock(side_effect=json.JSONDecodeError("Expecting value", "", 0))
        
        playlist = Playlist(
            name="Test Playlist",
            config=mock_config,
            client=mock_client,
            tracks=[mock_track_success, mock_track_failure]
        )
        
        await playlist.download()
        
        mock_track_success.resolve.assert_called_once()
        mock_track_success.resolve.return_value.rip.assert_called_once()
        mock_track_failure.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_album_handles_failed_track(self):
        """Test that an album download continues even if one track fails."""
        mock_config = MagicMock()
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_meta = MagicMock()
        
        # Create a list of mock tracks - one will succeed, one will fail
        mock_track_success = MagicMock()
        mock_track_success.resolve = AsyncMock(return_value=MagicMock())
        mock_track_success.resolve.return_value.rip = AsyncMock()
        
        # This track will raise a JSONDecodeError when resolved
        mock_track_failure = MagicMock()
        mock_track_failure.resolve = AsyncMock(side_effect=json.JSONDecodeError("Expecting value", "", 0))
        
        album = Album(
            meta=mock_meta,
            config=mock_config,
            tracks=[mock_track_success, mock_track_failure],
            folder="/test/folder",
            db=mock_db
        )
        
        await album.download()
        
        mock_track_success.resolve.assert_called_once()
        mock_track_success.resolve.return_value.rip.assert_called_once()
        mock_track_failure.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_rip_handles_failed_media(self):
        """Test that the Main.rip method handles failed media items."""
        from streamrip.rip.main import Main
        
        mock_config = MagicMock()
        
        mock_config.session.downloads.requests_per_minute = 0
        mock_config.session.database.downloads_enabled = False
        mock_config.session.database.failed_downloads_enabled = False
        
        with patch('streamrip.rip.main.QobuzClient'), \
             patch('streamrip.rip.main.TidalClient'), \
             patch('streamrip.rip.main.DeezerClient'), \
             patch('streamrip.rip.main.SoundcloudClient'):
            
            main = Main(mock_config)
            
            mock_media_success = MagicMock()
            mock_media_success.rip = AsyncMock()
            
            mock_media_failure = MagicMock()
            mock_media_failure.rip = AsyncMock(side_effect=Exception("Media download failed"))
            
            main.media = [mock_media_success, mock_media_failure]
            
            await main.rip()
            
            mock_media_success.rip.assert_called_once()
            mock_media_failure.rip.assert_called_once() 