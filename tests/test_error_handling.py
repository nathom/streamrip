import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from streamrip.media.album import Album
from streamrip.media.playlist import Playlist
from streamrip.media.track import Track


class TestErrorHandling:
    """Test error handling in playlist and album downloads."""

    @pytest.mark.asyncio
    async def test_playlist_handles_failed_track(self):
        """Test that a playlist download continues even if one track fails."""
        mock_config = MagicMock()
        mock_client = MagicMock()

        mock_track_success = MagicMock()
        mock_track_success.resolve = AsyncMock(return_value=MagicMock())
        mock_track_success.resolve.return_value.rip = AsyncMock()

        mock_track_failure = MagicMock()
        mock_track_failure.resolve = AsyncMock(
            side_effect=json.JSONDecodeError("Expecting value", "", 0)
        )

        playlist = Playlist(
            name="Test Playlist",
            config=mock_config,
            client=mock_client,
            tracks=[mock_track_success, mock_track_failure],
        )

        await playlist.download()

        mock_track_success.resolve.assert_called_once()
        mock_track_success.resolve.return_value.rip.assert_called_once()
        mock_track_failure.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_album_handles_failed_track(self):
        """Test that an album download continues even if one track fails."""
        mock_config = MagicMock()
        mock_db = MagicMock()
        mock_meta = MagicMock()

        # Create a list of mock tracks - one will succeed, one will fail
        mock_track_success = MagicMock()
        mock_track_success.resolve = AsyncMock(return_value=MagicMock())
        mock_track_success.resolve.return_value.rip = AsyncMock()

        # This track will raise a JSONDecodeError when resolved
        mock_track_failure = MagicMock()
        mock_track_failure.resolve = AsyncMock(
            side_effect=json.JSONDecodeError("Expecting value", "", 0)
        )

        album = Album(
            meta=mock_meta,
            config=mock_config,
            tracks=[mock_track_success, mock_track_failure],
            folder="/test/folder",
            db=mock_db,
        )

        await album.download()

        mock_track_success.resolve.assert_called_once()
        mock_track_success.resolve.return_value.rip.assert_called_once()
        mock_track_failure.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_album_starts_parallel_downloads_in_track_order(self):
        events = []
        mock_config = MagicMock()
        mock_config.session.downloads.concurrency = True
        mock_config.session.downloads.max_connections = 2
        mock_db = MagicMock()
        mock_meta = MagicMock()

        class ResolvedTrack:
            def __init__(self, name):
                self.name = name

            async def rip(self):
                events.append(f"rip {self.name}")
                await asyncio.sleep(0)

        class PendingTrack:
            def __init__(self, name, delay):
                self.name = name
                self.delay = delay

            async def resolve(self):
                events.append(f"resolve {self.name}")
                await asyncio.sleep(self.delay)
                return ResolvedTrack(self.name)

        album = Album(
            meta=mock_meta,
            config=mock_config,
            tracks=[
                PendingTrack("01", 0.01),
                PendingTrack("02", 0),
            ],
            folder="/test/folder",
            db=mock_db,
        )

        await album.download()

        assert events.index("rip 01") < events.index("resolve 02")
        assert events.index("rip 01") < events.index("rip 02")

    @pytest.mark.asyncio
    async def test_main_rip_handles_failed_media(self):
        """Test that the Main.rip method handles failed media items."""
        from streamrip.rip.main import Main

        mock_config = MagicMock()

        mock_config.session.downloads.requests_per_minute = 0
        mock_config.session.database.downloads_enabled = False
        mock_config.session.database.failed_downloads_enabled = False

        with (
            patch("streamrip.rip.main.QobuzClient"),
            patch("streamrip.rip.main.TidalClient"),
            patch("streamrip.rip.main.DeezerClient"),
            patch("streamrip.rip.main.SoundcloudClient"),
        ):
            main = Main(mock_config)

            mock_media_success = MagicMock()
            mock_media_success.rip = AsyncMock()

            mock_media_failure = MagicMock()
            mock_media_failure.rip = AsyncMock(
                side_effect=Exception("Media download failed")
            )

            main.media = [mock_media_success, mock_media_failure]

            await main.rip()

            mock_media_success.rip.assert_called_once()
            mock_media_failure.rip.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_download_failure_is_not_marked_downloaded(self):
        """Persistent download failures should not be recorded as successful."""
        config = MagicMock()
        config.session.cli.progress_bars = False
        config.session.downloads.concurrency = False

        meta = MagicMock()
        meta.title = "Failed Track"
        meta.tracknumber = 1
        meta.info = SimpleNamespace(id="track-id")

        downloadable = MagicMock()
        downloadable.url = "https://example.test/file.flac?token=secret&expires=1"
        downloadable.source = "qobuz"
        downloadable.size = AsyncMock(return_value=100)
        downloadable.download = AsyncMock(side_effect=Exception("network error"))

        database = MagicMock()

        track = Track(
            meta=meta,
            downloadable=downloadable,
            config=config,
            folder="/tmp",
            cover_path=None,
            db=database,
            download_path="/tmp/failed.flac",
        )

        with pytest.raises(Exception, match="network error"):
            await track.download()

        database.set_failed.assert_called_once_with("qobuz", "track", "track-id")
        database.set_downloaded.assert_not_called()

    @pytest.mark.asyncio
    async def test_rip_urls_starts_ready_url_before_slow_url_resolves(self):
        """A ready URL should begin ripping before every URL has resolved."""
        from streamrip.rip.main import Main

        events = []
        config = MagicMock()
        config.session.downloads.requests_per_minute = 0
        config.session.database.downloads_enabled = False
        config.session.database.failed_downloads_enabled = False

        class Parsed:
            source = "qobuz"

            def __init__(self, name):
                self.name = name

            async def into_pending(self, *_):
                return Pending(self.name)

        class Pending:
            def __init__(self, name):
                self.name = name

            async def resolve(self):
                if self.name == "slow":
                    await asyncio.sleep(0.05)
                events.append((self.name, "resolved"))
                return Media(self.name)

        class Media:
            def __init__(self, name):
                self.name = name

            async def rip(self):
                events.append((self.name, "ripped"))

        with (
            patch("streamrip.rip.main.QobuzClient") as qobuz_client,
            patch("streamrip.rip.main.TidalClient"),
            patch("streamrip.rip.main.DeezerClient"),
            patch("streamrip.rip.main.SoundcloudClient"),
            patch(
                "streamrip.rip.main.parse_url",
                side_effect=[Parsed("slow"), Parsed("fast")],
            ),
        ):
            qobuz_client.return_value.logged_in = True
            main = Main(config)

            await main.rip_urls(["slow-url", "fast-url"])

        assert events.index(("fast", "ripped")) < events.index(("slow", "resolved"))
