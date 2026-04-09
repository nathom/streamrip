"""Tests for the ``force=True`` flag in DownloadService.

When ``force`` is set on a queue item, the SDK's ``DownloadConfig`` must
be built with:

  - ``skip_downloaded=False``  (don't short-circuit on dedup match)
  - ``downloads_db_path=None`` (don't even open the dedup DB)

The existing ``test_force_flag_preserved`` only checks that the flag is
stored on the queue item — it doesn't verify the flag actually changes
the downloader's behavior.  These tests close that gap by inspecting
the DownloadConfig that ``_download_album`` constructs.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.database import AppDatabase
from backend.services.download import DownloadService
from backend.services.event_bus import EventBus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Fake AlbumResult / spying AlbumDownloader
# ---------------------------------------------------------------------------


@dataclass
class FakeTrackResult:
    track_id: int
    title: str
    success: bool
    path: str | None = None
    error: str | None = None


@dataclass
class FakeAlbumResult:
    total: int
    successful: int
    title: str = "T"
    artist: str = "A"
    tracks: list[FakeTrackResult] = field(default_factory=list)
    cover_path: str | None = None
    booklet_paths: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.successful / self.total if self.total > 0 else 0.0


def _spying_downloader_class(captured: dict):
    """Build a fake AlbumDownloader class that captures the config it
    was constructed with into ``captured``."""

    def _fake_class(client, config, *, on_track_start=None,
                    on_track_progress=None, on_track_complete=None):
        captured["config"] = config
        instance = MagicMock()
        instance.download = AsyncMock(
            return_value=FakeAlbumResult(
                total=4, successful=4,
                tracks=[
                    FakeTrackResult(i, f"T{i}", True, f"/x/{i}.flac")
                    for i in range(4)
                ],
            )
        )
        return instance

    return _fake_class


def _make_item(db, source: str, source_album_id: str, force: bool) -> dict:
    db_id = db.upsert_album(source, source_album_id, "T", "A", track_count=4)
    return {
        "id": "queue-1",
        "album_db_id": db_id,
        "source": source,
        "source_album_id": source_album_id,
        "title": "T",
        "artist": "A",
        "cover_url": None,
        "track_count": 4,
        "tracks_done": 0,
        "bytes_done": 0,
        "bytes_total": 0,
        "speed": 0.0,
        "status": "downloading",
        "force": force,
    }


# ---------------------------------------------------------------------------
# DownloadConfig: skip_downloaded + downloads_db_path
# ---------------------------------------------------------------------------


class TestForceBypassesDedup:
    async def test_force_true_disables_skip_downloaded(self, db, event_bus):
        client = MagicMock()
        client.catalog = MagicMock()
        service = DownloadService(
            db, event_bus, clients={"qobuz": client}, download_path="/tmp"
        )
        item = _make_item(db, "qobuz", "force-album", force=True)

        captured: dict = {}
        with patch("qobuz.AlbumDownloader", new=_spying_downloader_class(captured)):
            await service._download_album(item)

        config = captured["config"]
        assert config.skip_downloaded is False, (
            "force=True must disable skip_downloaded so dedup hits are re-attempted"
        )

    async def test_force_true_clears_downloads_db_path(self, db, event_bus):
        client = MagicMock()
        client.catalog = MagicMock()
        service = DownloadService(
            db, event_bus, clients={"qobuz": client}, download_path="/tmp"
        )
        item = _make_item(db, "qobuz", "force-album", force=True)

        captured: dict = {}
        with patch("qobuz.AlbumDownloader", new=_spying_downloader_class(captured)):
            await service._download_album(item)

        config = captured["config"]
        assert config.downloads_db_path is None, (
            "force=True should not even open the dedup DB; "
            f"got {config.downloads_db_path!r}"
        )

    async def test_force_false_uses_normal_dedup_path(self, db, event_bus):
        client = MagicMock()
        client.catalog = MagicMock()
        service = DownloadService(
            db, event_bus, clients={"qobuz": client}, download_path="/tmp"
        )
        item = _make_item(db, "qobuz", "normal-album", force=False)

        captured: dict = {}
        with patch("qobuz.AlbumDownloader", new=_spying_downloader_class(captured)):
            await service._download_album(item)

        config = captured["config"]
        assert config.skip_downloaded is True, (
            "non-force downloads should keep skip_downloaded=True"
        )
        # Should point at downloads.db (Qobuz)
        assert config.downloads_db_path is not None
        assert config.downloads_db_path.endswith("downloads.db")

    async def test_force_false_tidal_uses_separate_dedup_db(self, db, event_bus):
        """Per-source dedup DB filename: Tidal uses downloads-tidal.db
        instead of downloads.db so the two services' track IDs can't collide."""
        client = MagicMock()
        client.catalog = MagicMock()
        # Use a fresh download path to avoid env path interference
        service = DownloadService(
            db, event_bus, clients={"tidal": client}, download_path="/tmp"
        )
        item = _make_item(db, "tidal", "tidal-album", force=False)

        captured: dict = {}
        # Tidal _download_album imports `from tidal import AlbumDownloader`
        with patch("tidal.AlbumDownloader", new=_spying_downloader_class(captured)):
            await service._download_album(item)

        config = captured["config"]
        assert config.downloads_db_path is not None
        assert config.downloads_db_path.endswith("downloads-tidal.db")
        assert "downloads-tidal.db" in config.downloads_db_path


class TestQueueItemForceFlag:
    """Sanity-check the existing happy path: enqueue with force=True
    propagates the flag to the queue item (regression cover for the
    pre-existing test_force_flag_preserved)."""

    async def test_enqueue_propagates_force_flag(self, db, event_bus):
        db.upsert_album("qobuz", "abc", "T", "A")
        service = DownloadService(
            db, event_bus, clients={}, download_path="/tmp"
        )
        items = await service.enqueue("qobuz", ["abc"], force=True)
        assert items[0]["force"] is True

    async def test_enqueue_default_force_is_false(self, db, event_bus):
        db.upsert_album("qobuz", "abc", "T", "A")
        service = DownloadService(
            db, event_bus, clients={}, download_path="/tmp"
        )
        items = await service.enqueue("qobuz", ["abc"])  # no force kwarg
        assert items[0]["force"] is False
