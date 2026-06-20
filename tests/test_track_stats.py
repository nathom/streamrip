from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from streamrip.media.media import DownloadStats
from streamrip.media.track import Track


def _make_track(download_path: str = "/tmp/track.flac") -> Track:
    track = Track(
        meta=MagicMock(),
        downloadable=MagicMock(),
        config=MagicMock(),
        folder="/tmp",
        cover_path=None,
        db=MagicMock(),
    )
    track.download_path = download_path
    return track


class TestTrackRipStats:
    @pytest.mark.asyncio
    async def test_success_records_in_stats(self):
        track = _make_track("/tmp/track.flac")
        stats = DownloadStats()

        with (
            patch.object(Track, "preprocess", new=AsyncMock()),
            patch.object(Track, "download", new=AsyncMock()),
            patch.object(Track, "postprocess", new=AsyncMock()),
            patch("streamrip.media.media.os.path.getsize", return_value=5_000_000),
        ):
            await track.rip(stats)

        assert stats.tracks_downloaded == 1
        assert stats.tracks_failed == 0
        assert stats.bytes_downloaded == 5_000_000

    @pytest.mark.asyncio
    async def test_failure_records_in_stats_and_reraises(self):
        track = _make_track()
        stats = DownloadStats()

        with (
            patch.object(Track, "preprocess", new=AsyncMock(side_effect=RuntimeError("boom"))),
            patch.object(Track, "download", new=AsyncMock()),
            patch.object(Track, "postprocess", new=AsyncMock()),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await track.rip(stats)

        assert stats.tracks_failed == 1
        assert stats.tracks_downloaded == 0

    @pytest.mark.asyncio
    async def test_no_stats_no_crash_on_success(self):
        track = _make_track()

        with (
            patch.object(Track, "preprocess", new=AsyncMock()),
            patch.object(Track, "download", new=AsyncMock()),
            patch.object(Track, "postprocess", new=AsyncMock()),
        ):
            await track.rip(None)  # must not raise

    @pytest.mark.asyncio
    async def test_no_stats_no_crash_on_failure(self):
        track = _make_track()

        with (
            patch.object(Track, "preprocess", new=AsyncMock(side_effect=ValueError("oops"))),
            patch.object(Track, "download", new=AsyncMock()),
            patch.object(Track, "postprocess", new=AsyncMock()),
        ):
            with pytest.raises(ValueError):
                await track.rip(None)  # must not raise AttributeError

    @pytest.mark.asyncio
    async def test_postprocess_failure_records(self):
        track = _make_track()
        stats = DownloadStats()

        with (
            patch.object(Track, "preprocess", new=AsyncMock()),
            patch.object(Track, "download", new=AsyncMock()),
            patch.object(Track, "postprocess", new=AsyncMock(side_effect=OSError("tag fail"))),
        ):
            with pytest.raises(OSError):
                await track.rip(stats)

        assert stats.tracks_failed == 1
        assert stats.tracks_downloaded == 0
