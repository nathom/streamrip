"""Tests for SoundCloud client bug fixes."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSoundcloudSegmentOrdering:
    """Fix: as_completed returns segments in completion order, not creation order."""

    async def test_segments_concatenated_in_order(self):
        """Segments should be concatenated in playlist order, not completion order."""
        from streamrip.client.downloadable import SoundcloudDownloadable

        dl = SoundcloudDownloadable.__new__(SoundcloudDownloadable)
        dl.session = MagicMock()

        # Simulate 3 segments that complete in reverse order
        async def mock_download_segment(uri):
            delay = {"seg1.mp3": 0.03, "seg2.mp3": 0.02, "seg3.mp3": 0.01}
            await asyncio.sleep(delay[uri])
            return f"/tmp/{uri}"

        dl._download_segment = mock_download_segment

        m3u8_content = "#EXTM3U\n#EXTINF:10,\nseg1.mp3\n#EXTINF:10,\nseg2.mp3\n#EXTINF:10,\nseg3.mp3\n"

        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value=m3u8_content)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        dl.session.get = MagicMock(return_value=mock_resp)

        dl.url = "https://example.com/playlist.m3u8"

        captured_paths = []

        async def mock_concat(paths, output, fmt):
            captured_paths.extend(paths)

        with patch("streamrip.client.downloadable.concat_audio_files", mock_concat):
            await dl._download_mp3("/tmp/output.mp3", lambda x: None)

        assert captured_paths == ["/tmp/seg1.mp3", "/tmp/seg2.mp3", "/tmp/seg3.mp3"]
