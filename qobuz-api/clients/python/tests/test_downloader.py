"""E2E test for the album downloader."""

import asyncio
import os
import tempfile

import pytest

from qobuz import QobuzClient, AlbumDownloader, DownloadConfig

QOBUZ_TOKEN = os.environ.get("QOBUZ_TOKEN", "")
QOBUZ_USER_ID = os.environ.get("QOBUZ_USER_ID", "")
APP_ID = "798273057"
# Harold Budd — Ambient 2 (10 tracks, small album)
TEST_ALBUM_ID = "0724386649751"

skip_no_creds = pytest.mark.skipif(
    not QOBUZ_TOKEN, reason="Set QOBUZ_TOKEN env var to run"
)


@skip_no_creds
async def test_download_album_e2e():
    """Full download: resolve → download → tag → verify files."""
    # First we need the app_secret — get it by logging in and testing secrets
    # For simplicity, we'll skip the secret-fetching and use the streaming module
    # which requires an app_secret

    from qobuz.spoofer import fetch_app_credentials, find_working_secret

    app_id, secrets = await fetch_app_credentials()
    app_secret = await find_working_secret(app_id, secrets, QOBUZ_TOKEN)

    # Now download
    progress_events = []

    def on_start(num, title):
        progress_events.append(("start", num, title))

    def on_progress(num, done, total):
        progress_events.append(("progress", num, done, total))

    def on_complete(num, title, success):
        progress_events.append(("complete", num, title, success))

    with tempfile.TemporaryDirectory() as tmpdir:
        async with QobuzClient(
            app_id=app_id,
            user_auth_token=QOBUZ_TOKEN,
            app_secret=app_secret,
        ) as client:
            dl = AlbumDownloader(
                client,
                DownloadConfig(output_dir=tmpdir, quality=2),
                on_track_start=on_start,
                on_track_progress=on_progress,
                on_track_complete=on_complete,
            )
            result = await dl.download(TEST_ALBUM_ID)

        assert result.total > 0, "Should have tracks"
        assert result.successful > 0, "Should have successful downloads"
        assert result.success_rate >= 0.8, f"Success rate {result.success_rate:.0%} below 80%"
        assert result.cover_path is not None, "Should have cover art"
        assert os.path.exists(result.cover_path)

        # Verify FLAC files exist
        flac_files = [t for t in result.tracks if t.success and t.path and t.path.endswith(".flac")]
        assert len(flac_files) > 0, "Should have FLAC files"
        for t in flac_files:
            assert os.path.exists(t.path), f"File should exist: {t.path}"
            assert os.path.getsize(t.path) > 1000, f"File too small: {t.path}"

        # Verify progress callbacks fired
        starts = [e for e in progress_events if e[0] == "start"]
        completes = [e for e in progress_events if e[0] == "complete"]
        assert len(starts) > 0, "Should have track start events"
        assert len(completes) > 0, "Should have track complete events"

        # Verify tags (FLAC)
        from mutagen.flac import FLAC
        tagged = FLAC(flac_files[0].path)
        assert tagged.get("title"), "Should have title tag"
        assert tagged.get("artist"), "Should have artist tag"
        assert tagged.get("album"), "Should have album tag"

        print(f"\n✓ Downloaded {result.successful}/{result.total} tracks")
        print(f"  Album: {result.artist} — {result.title}")
        print(f"  Path: {tmpdir}")
        for t in result.tracks:
            status = "✓" if t.success else "✗"
            print(f"  {status} {t.title}")
