"""Tests for the 80% success-rate threshold in DownloadService._download_album.

When ``result.success_rate < 0.8``, the service raises ``RuntimeError``
which propagates out of ``_download_album`` and is caught by
``_process_queue``, marking the queue item as ``failed`` and reverting
the album DB row to ``not_downloaded``.

These tests inject a fake ``qobuz.AlbumDownloader`` so we never touch
the network or run the real download pipeline — we just verify the
threshold logic and the queue/DB state changes.
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
# Fake AlbumResult / TrackResult — minimal shape the service reads
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
    """Mimics the shape of qobuz.AlbumResult that DownloadService reads.

    The service touches: total, successful, success_rate, tracks, title,
    artist.  AlbumDownloader returns a real dataclass; we fake it.
    """
    total: int
    successful: int
    title: str = "Test Album"
    artist: str = "Test Artist"
    tracks: list[FakeTrackResult] = field(default_factory=list)
    cover_path: str | None = None
    booklet_paths: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.successful / self.total if self.total > 0 else 0.0


def _make_fake_downloader_returning(result: FakeAlbumResult):
    """Build a callable replacing the qobuz.AlbumDownloader class.

    The callable takes (client, config, **callbacks) and returns an
    object whose async ``download(album_id)`` resolves to ``result``.
    """

    def _fake_class(client, config, *, on_track_start=None,
                    on_track_progress=None, on_track_complete=None):
        instance = MagicMock()
        instance.download = AsyncMock(return_value=result)
        return instance

    return _fake_class


def _make_qobuz_client():
    """Bare client mock — _download_album never calls anything on it
    directly, the (mocked) AlbumDownloader does."""
    client = MagicMock()
    client.catalog = MagicMock()
    return client


def _seed_album(db, source: str, source_album_id: str) -> int:
    db_id = db.upsert_album(
        source=source,
        source_album_id=source_album_id,
        title="Test Album",
        artist="Test Artist",
        track_count=10,
    )
    return db_id


def _make_queue_item(db, source: str, source_album_id: str, force: bool = False) -> dict:
    db_id = _seed_album(db, source, source_album_id)
    return {
        "id": "queue-id-1",
        "album_db_id": db_id,
        "source": source,
        "source_album_id": source_album_id,
        "title": "Test Album",
        "artist": "Test Artist",
        "cover_url": None,
        "track_count": 10,
        "tracks_done": 0,
        "bytes_done": 0,
        "bytes_total": 0,
        "speed": 0.0,
        "status": "downloading",
        "force": force,
    }


# ---------------------------------------------------------------------------
# 80% threshold tests
# ---------------------------------------------------------------------------


class TestSuccessThreshold:
    async def test_below_80_percent_raises_runtime_error(self, db, event_bus):
        """0/10 should raise — the album is treated as failed."""
        result = FakeAlbumResult(
            total=10,
            successful=0,
            tracks=[
                FakeTrackResult(track_id=i, title=f"T{i}", success=False)
                for i in range(10)
            ],
        )
        client = _make_qobuz_client()
        service = DownloadService(
            db, event_bus, clients={"qobuz": client}, download_path="/tmp"
        )
        item = _make_queue_item(db, "qobuz", "fail-album")

        fake_downloader = _make_fake_downloader_returning(result)
        with patch("qobuz.AlbumDownloader", new=fake_downloader):
            with pytest.raises(RuntimeError, match="0/10.*0%.*below 80%"):
                await service._download_album(item)

    async def test_exactly_threshold_passes(self, db, event_bus):
        """8/10 = 80% should NOT raise — the threshold is strictly < 0.8."""
        result = FakeAlbumResult(
            total=10,
            successful=8,
            tracks=[
                FakeTrackResult(track_id=i, title=f"T{i}", success=(i < 8))
                for i in range(10)
            ],
        )
        client = _make_qobuz_client()
        service = DownloadService(
            db, event_bus, clients={"qobuz": client}, download_path="/tmp"
        )
        item = _make_queue_item(db, "qobuz", "exact-threshold")

        fake_downloader = _make_fake_downloader_returning(result)
        with patch("qobuz.AlbumDownloader", new=fake_downloader):
            # Must NOT raise
            await service._download_album(item)

    async def test_just_below_threshold_raises(self, db, event_bus):
        """7/10 = 70% must raise."""
        result = FakeAlbumResult(
            total=10,
            successful=7,
            tracks=[
                FakeTrackResult(track_id=i, title=f"T{i}", success=(i < 7))
                for i in range(10)
            ],
        )
        client = _make_qobuz_client()
        service = DownloadService(
            db, event_bus, clients={"qobuz": client}, download_path="/tmp"
        )
        item = _make_queue_item(db, "qobuz", "below-threshold")

        fake_downloader = _make_fake_downloader_returning(result)
        with patch("qobuz.AlbumDownloader", new=fake_downloader):
            with pytest.raises(RuntimeError, match="below 80%"):
                await service._download_album(item)

    async def test_one_failed_track_in_otherwise_full_album_passes(
        self, db, event_bus
    ):
        """9/10 = 90% should NOT raise — a single bad track is tolerable."""
        result = FakeAlbumResult(
            total=10,
            successful=9,
            tracks=[
                FakeTrackResult(track_id=i, title=f"T{i}", success=(i != 5))
                for i in range(10)
            ],
        )
        client = _make_qobuz_client()
        service = DownloadService(
            db, event_bus, clients={"qobuz": client}, download_path="/tmp"
        )
        item = _make_queue_item(db, "qobuz", "single-fail")

        fake_downloader = _make_fake_downloader_returning(result)
        with patch("qobuz.AlbumDownloader", new=fake_downloader):
            # Must NOT raise
            await service._download_album(item)

    async def test_zero_total_does_not_raise(self, db, event_bus):
        """An empty album (total=0) should not crash on the threshold check."""
        result = FakeAlbumResult(total=0, successful=0, tracks=[])
        client = _make_qobuz_client()
        service = DownloadService(
            db, event_bus, clients={"qobuz": client}, download_path="/tmp"
        )
        item = _make_queue_item(db, "qobuz", "empty-album")

        fake_downloader = _make_fake_downloader_returning(result)
        with patch("qobuz.AlbumDownloader", new=fake_downloader):
            # The guard `if result.total > 0` skips the check entirely
            await service._download_album(item)


# ---------------------------------------------------------------------------
# Queue-level: failure marks the queue item AND reverts the DB row
# ---------------------------------------------------------------------------


def _build_queue_item_in_place(service, db, source: str, source_album_id: str):
    """Build a queue item directly without going through enqueue().

    enqueue() auto-starts a worker that races with our test patches —
    this helper just appends a pending item to the queue and seeds the
    DB row, leaving the worker for the test to drive manually.
    """
    db_id = _seed_album(db, source, source_album_id)
    db.update_album_status(db_id, "queued")
    item = {
        "id": f"queue-{source_album_id}",
        "album_db_id": db_id,
        "source": source,
        "source_album_id": source_album_id,
        "title": "Test Album",
        "artist": "Test Artist",
        "cover_url": None,
        "track_count": 10,
        "tracks_done": 0,
        "bytes_done": 0,
        "bytes_total": 0,
        "speed": 0.0,
        "status": "pending",
        "force": False,
    }
    service._queue.append(item)
    return item, db_id


class TestProcessQueueHandlesFailure:
    async def test_failed_download_marks_queue_item_failed(
        self, db, event_bus
    ):
        """When _download_album raises, _process_queue must mark the item
        as failed and revert the album DB row to not_downloaded."""
        result = FakeAlbumResult(
            total=10, successful=2,
            tracks=[
                FakeTrackResult(track_id=i, title=f"T{i}", success=(i < 2))
                for i in range(10)
            ],
        )
        client = _make_qobuz_client()
        service = DownloadService(
            db, event_bus, clients={"qobuz": client}, download_path="/tmp"
        )

        item, db_id = _build_queue_item_in_place(service, db, "qobuz", "queue-fail")
        assert db.get_album(db_id)["download_status"] == "queued"

        fake_downloader = _make_fake_downloader_returning(result)
        with patch("qobuz.AlbumDownloader", new=fake_downloader):
            await service._process_queue()

        # Queue item should be marked failed
        queue = service.get_queue()
        failed_items = [q for q in queue if q["id"] == item["id"]]
        assert failed_items[0]["status"] == "failed"

        # And the album DB row should have been reverted to not_downloaded
        album_after = db.get_album(db_id)
        assert album_after["download_status"] == "not_downloaded"

    async def test_successful_download_marks_queue_item_complete(
        self, db, event_bus
    ):
        """A 100% successful download must mark the queue item complete
        and the album row complete."""
        result = FakeAlbumResult(
            total=4, successful=4,
            tracks=[
                FakeTrackResult(track_id=i, title=f"T{i}", success=True, path=f"/x/{i}.flac")
                for i in range(4)
            ],
        )
        client = _make_qobuz_client()
        service = DownloadService(
            db, event_bus, clients={"qobuz": client}, download_path="/tmp"
        )

        item, db_id = _build_queue_item_in_place(service, db, "qobuz", "queue-success")

        fake_downloader = _make_fake_downloader_returning(result)
        with patch("qobuz.AlbumDownloader", new=fake_downloader):
            await service._process_queue()

        queue = service.get_queue()
        ok_items = [q for q in queue if q["id"] == item["id"]]
        assert ok_items[0]["status"] == "complete"

        album_after = db.get_album(db_id)
        assert album_after["download_status"] == "complete"
