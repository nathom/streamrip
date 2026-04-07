"""End-to-end test for the download pipeline.

Tests the full flow: config save → client login → album resolve → download
using real Qobuz credentials from the environment or DB.

Run with: poetry run pytest tests/test_e2e_download.py -v -s
"""

import asyncio
import os
import tempfile
import pytest

from backend.models.database import AppDatabase
from backend.services.config_bridge import build_streamrip_config
from backend.services.download import DownloadService
from backend.services.event_bus import EventBus


# Use env vars or skip
QOBUZ_TOKEN = os.environ.get("QOBUZ_TOKEN", "")
QOBUZ_USER_ID = os.environ.get("QOBUZ_USER_ID", "")
# A known small Qobuz album for testing (Harold Budd - Ambient 2, 10 tracks)
TEST_ALBUM_ID = os.environ.get("TEST_ALBUM_ID", "0724386649751")

skip_no_creds = pytest.mark.skipif(
    not QOBUZ_TOKEN or not QOBUZ_USER_ID,
    reason="Set QOBUZ_TOKEN and QOBUZ_USER_ID env vars to run e2e tests"
)


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = AppDatabase(path)
    yield database
    os.unlink(path)


@pytest.fixture
def event_bus():
    return EventBus()


class TestQobuzClientLogin:
    """Test that the Qobuz client can login and has all required state."""

    @skip_no_creds
    async def test_login_sets_secret_and_session(self, db):
        """After login, client should have secret, session, and logged_in=True."""
        db.set_config("qobuz_token", QOBUZ_TOKEN)
        db.set_config("qobuz_user_id", QOBUZ_USER_ID)

        config = build_streamrip_config(db)

        from streamrip.client.qobuz import QobuzClient
        client = QobuzClient(config)

        assert not client.logged_in
        assert client.secret is None

        await client.login()

        assert client.logged_in, "Client should be logged in after login()"
        assert client.secret is not None, "Client secret should be set after login()"
        assert client.session is not None, "Client session should be open after login()"

        # Cleanup
        if client.session:
            await client.session.close()

    @skip_no_creds
    async def test_login_with_auto_resolve_user_id(self, db):
        """Login should work with only a token (no user_id) by auto-resolving."""
        db.set_config("qobuz_token", QOBUZ_TOKEN)
        # Deliberately NOT setting qobuz_user_id

        config = build_streamrip_config(db)
        # Clear user_id to test auto-resolve
        config.session.qobuz.email_or_userid = ""

        from streamrip.client.qobuz import QobuzClient
        client = QobuzClient(config)
        await client.login()

        assert client.logged_in
        assert client.secret is not None
        # user_id should have been auto-resolved
        assert config.session.qobuz.email_or_userid != ""

        if client.session:
            await client.session.close()


class TestQobuzGetDownloadable:
    """Test that a logged-in client can get downloadable URLs."""

    @skip_no_creds
    async def test_get_downloadable_returns_url(self, db):
        """A logged-in client should be able to get a stream URL for a track."""
        db.set_config("qobuz_token", QOBUZ_TOKEN)
        db.set_config("qobuz_user_id", QOBUZ_USER_ID)

        config = build_streamrip_config(db)
        from streamrip.client.qobuz import QobuzClient
        client = QobuzClient(config)
        await client.login()

        # Get album tracks to find a real track ID
        album = await client.get_album(TEST_ALBUM_ID)
        tracks = album.get("tracks", {}).get("items", [])
        assert len(tracks) > 0, f"Album {TEST_ALBUM_ID} should have tracks"

        track_id = str(tracks[0]["id"])
        downloadable = await client.get_downloadable(track_id, quality=3)
        assert downloadable is not None

        if client.session:
            await client.session.close()


class TestDownloadPipelineE2E:
    """Test the full download pipeline end-to-end."""

    @skip_no_creds
    async def test_main_pipeline_with_logged_in_client(self, db):
        """Main should be able to resolve and prepare an album for download."""
        db.set_config("qobuz_token", QOBUZ_TOKEN)
        db.set_config("qobuz_user_id", QOBUZ_USER_ID)

        with tempfile.TemporaryDirectory() as tmpdir:
            db.set_config("downloads_path", tmpdir)
            config = build_streamrip_config(db)

            from streamrip.client.qobuz import QobuzClient
            client = QobuzClient(config)
            await client.login()

            assert client.logged_in
            assert client.secret is not None

            from streamrip.rip.main import Main
            main = Main(config)
            # Inject our logged-in client
            main.clients["qobuz"] = client
            main._add_by_id_client(client, "album", TEST_ALBUM_ID)

            assert len(main.pending) == 1

            # Verify the pending item has our client with secret
            pending = main.pending[0]
            assert pending.client is client
            assert pending.client.secret is not None
            assert pending.client.logged_in

            # Resolve (fetch metadata) — this is the step before rip()
            await main.resolve()

            assert len(main.media) > 0, "resolve() should produce at least one media item"

            media = main.media[0]
            assert hasattr(media, 'meta'), "Resolved media should have metadata"

            if client.session:
                await client.session.close()

    @skip_no_creds
    async def test_download_service_pipeline(self, db, event_bus):
        """DownloadService should successfully download an album."""
        db.set_config("qobuz_token", QOBUZ_TOKEN)
        db.set_config("qobuz_user_id", QOBUZ_USER_ID)

        config = build_streamrip_config(db)

        from streamrip.client.qobuz import QobuzClient
        client = QobuzClient(config)
        await client.login()

        with tempfile.TemporaryDirectory() as tmpdir:
            db.set_config("downloads_path", tmpdir)

            service = DownloadService(
                db, event_bus,
                clients={"qobuz": client},
                download_path=tmpdir,
            )

            # Add album to DB first (required for enqueue)
            db.upsert_album("qobuz", TEST_ALBUM_ID, "Test Album", "Test Artist")

            items = await service.enqueue("qobuz", [TEST_ALBUM_ID])
            assert len(items) == 1
            assert items[0]["status"] == "pending"

            # Wait for the background worker
            for _ in range(120):  # 2 minute timeout
                await asyncio.sleep(1)
                queue = service.get_queue()
                item = next((q for q in queue if q["source_album_id"] == TEST_ALBUM_ID), None)
                if item and item["status"] in ("complete", "failed"):
                    break

            queue = service.get_queue()
            item = next(q for q in queue if q["source_album_id"] == TEST_ALBUM_ID)

            assert item["status"] == "complete", (
                f"Download should have completed but status is '{item['status']}'. "
                f"Check logs for errors."
            )

            # Verify files were created
            files = []
            for root, dirs, filenames in os.walk(tmpdir):
                files.extend(filenames)
            assert len(files) > 0, f"Expected downloaded files in {tmpdir}, found none"

        if client.session:
            await client.session.close()
