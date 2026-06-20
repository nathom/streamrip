import os
import tempfile

from streamrip.media.media import DownloadStats
from streamrip.rip.main import Main


class TestDownloadStats:
    def test_initial_state(self):
        s = DownloadStats()
        assert s.tracks_downloaded == 0
        assert s.tracks_failed == 0
        assert s.bytes_downloaded == 0

    def test_record_failure(self):
        s = DownloadStats()
        s.record_failure()
        s.record_failure()
        assert s.tracks_failed == 2
        assert s.tracks_downloaded == 0

    def test_record_success_increments_count(self):
        s = DownloadStats()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"\x00" * 1024)
            path = f.name
        try:
            s.record_success(path)
            assert s.tracks_downloaded == 1
            assert s.bytes_downloaded == 1024
        finally:
            os.unlink(path)

    def test_record_success_missing_file_no_crash(self):
        s = DownloadStats()
        s.record_success("/nonexistent/path/track.flac")
        assert s.tracks_downloaded == 1
        assert s.bytes_downloaded == 0

    def test_record_success_accumulates_bytes(self):
        s = DownloadStats()
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(3):
                path = os.path.join(tmp, f"track{i}.flac")
                with open(path, "wb") as f:
                    f.write(b"\x00" * 500)
                s.record_success(path)
        assert s.tracks_downloaded == 3
        assert s.bytes_downloaded == 1500


class TestFormatSummary:
    def test_zero_errors_not_shown(self):
        s = DownloadStats(tracks_downloaded=5, tracks_failed=0, bytes_downloaded=1_000_000)
        result = Main._format_summary(s, 30.0)
        assert "error" not in result.lower()
        assert "5 tracks" in result

    def test_errors_shown_when_nonzero(self):
        s = DownloadStats(tracks_downloaded=3, tracks_failed=2, bytes_downloaded=500_000)
        result = Main._format_summary(s, 10.0)
        assert "2 errors" in result

    def test_kb_formatting(self):
        s = DownloadStats(tracks_downloaded=1, bytes_downloaded=512_000)
        result = Main._format_summary(s, 5.0)
        assert "KB" in result

    def test_mb_formatting(self):
        s = DownloadStats(tracks_downloaded=1, bytes_downloaded=50_000_000)
        result = Main._format_summary(s, 5.0)
        assert "MB" in result

    def test_gb_formatting(self):
        s = DownloadStats(tracks_downloaded=10, bytes_downloaded=2_500_000_000)
        result = Main._format_summary(s, 60.0)
        assert "GB" in result

    def test_time_under_60s(self):
        s = DownloadStats(tracks_downloaded=1, bytes_downloaded=0)
        result = Main._format_summary(s, 45.0)
        assert "45s" in result
        assert "m" not in result

    def test_time_over_60s(self):
        s = DownloadStats(tracks_downloaded=1, bytes_downloaded=0)
        result = Main._format_summary(s, 125.0)
        assert "2m" in result
        assert "05s" in result
