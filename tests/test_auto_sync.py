"""Auto-sync scheduler tests for SyncService.

Covers ``start_auto_sync`` / ``stop_auto_sync`` / ``_auto_sync_loop``.

The loop sleeps ``interval_seconds``, runs a sync, and repeats forever
until cancelled.  Tests use ``asyncio.sleep`` patches to compress wall
time so a 0.01s "interval" represents a real-world hour.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.database import AppDatabase
from backend.services.event_bus import EventBus
from backend.services.library import LibraryService
from backend.services.sync import SyncService


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


def _mock_client_with_empty_favorites():
    """Build a mock SDK client whose favorites + catalog return empty pages."""
    page = MagicMock()
    page.items = []
    page.total = 0
    page.limit = 500
    page.offset = 0

    client = MagicMock()
    client.favorites = MagicMock()
    client.favorites.get_albums = AsyncMock(return_value=page)
    client.catalog = MagicMock()
    client.catalog.search_albums = AsyncMock(return_value=page)
    return client


def _make_service(db, event_bus, run_sync_impl=None) -> SyncService:
    """Build a SyncService with an empty-favorites Qobuz client.

    If *run_sync_impl* is given, it replaces ``service.run_sync`` so the
    test can count invocations and inject delays without going through
    the real refresh path.
    """
    client = _mock_client_with_empty_favorites()
    clients = {"qobuz": client}
    library_service = LibraryService(db, event_bus, clients=clients)
    service = SyncService(
        db, event_bus, clients=clients, library_service=library_service
    )
    if run_sync_impl is not None:
        service.run_sync = run_sync_impl  # type: ignore[assignment]
    return service


# ---------------------------------------------------------------------------
# start_auto_sync / loop
# ---------------------------------------------------------------------------


class TestAutoSyncLoop:
    async def test_loop_runs_sync_at_intervals(self, db, event_bus):
        """The loop should call run_sync each interval until cancelled."""
        call_count = {"n": 0}

        async def fake_run_sync(source):
            call_count["n"] += 1
            return {"status": "complete"}

        service = _make_service(db, event_bus, run_sync_impl=fake_run_sync)
        # 10ms interval — fast enough to test, slow enough that the loop
        # is event-loop-friendly.
        service.start_auto_sync("qobuz", interval_seconds=0.01)

        # Wait long enough for ~3 syncs to fire
        await asyncio.sleep(0.05)

        # Cancel before asserting so the loop doesn't keep running
        service.stop_auto_sync()
        # Give the cancellation a chance to take effect
        await asyncio.sleep(0)

        assert call_count["n"] >= 2, (
            f"expected at least 2 syncs in 50ms with a 10ms interval, got {call_count['n']}"
        )

    async def test_loop_first_sync_happens_after_one_interval(
        self, db, event_bus
    ):
        """The loop sleeps BEFORE the first sync, so call_count is 0 at t=0."""
        call_count = {"n": 0}

        async def fake_run_sync(source):
            call_count["n"] += 1
            return {"status": "complete"}

        service = _make_service(db, event_bus, run_sync_impl=fake_run_sync)
        service.start_auto_sync("qobuz", interval_seconds=0.05)

        # Immediately after start, no sync has happened yet (still sleeping)
        assert call_count["n"] == 0

        # Wait > one interval
        await asyncio.sleep(0.08)
        service.stop_auto_sync()
        await asyncio.sleep(0)

        # At least one sync should have run
        assert call_count["n"] >= 1


# ---------------------------------------------------------------------------
# stop_auto_sync / cancellation
# ---------------------------------------------------------------------------


class TestStopAutoSync:
    async def test_stop_cancels_the_loop(self, db, event_bus):
        call_count = {"n": 0}

        async def fake_run_sync(source):
            call_count["n"] += 1
            return {"status": "complete"}

        service = _make_service(db, event_bus, run_sync_impl=fake_run_sync)
        service.start_auto_sync("qobuz", interval_seconds=0.01)

        await asyncio.sleep(0.03)
        snapshot = call_count["n"]
        service.stop_auto_sync()

        # Wait again — call count must NOT keep growing
        await asyncio.sleep(0.05)
        assert call_count["n"] == snapshot, (
            f"loop kept running after stop_auto_sync: {snapshot} → {call_count['n']}"
        )
        # Task object cleared
        assert service._auto_sync_task is None

    async def test_stop_when_not_running_is_noop(self, db, event_bus):
        service = _make_service(db, event_bus)
        # No start was ever called
        service.stop_auto_sync()  # Must not raise
        assert service._auto_sync_task is None

    async def test_starting_again_cancels_previous_task(self, db, event_bus):
        """A second call to start_auto_sync should cancel the first loop."""
        first_calls = {"n": 0}
        second_calls = {"n": 0}

        async def first_run_sync(source):
            first_calls["n"] += 1
            return {"status": "complete"}

        service = _make_service(db, event_bus, run_sync_impl=first_run_sync)
        service.start_auto_sync("qobuz", interval_seconds=0.01)
        first_task = service._auto_sync_task

        # Replace run_sync and restart
        async def second_run_sync(source):
            second_calls["n"] += 1
            return {"status": "complete"}

        service.run_sync = second_run_sync  # type: ignore[assignment]
        service.start_auto_sync("qobuz", interval_seconds=0.01)
        second_task = service._auto_sync_task

        await asyncio.sleep(0.05)
        service.stop_auto_sync()
        await asyncio.sleep(0)

        assert first_task is not second_task
        assert first_task.cancelled() or first_task.done()
        # The second loop should have run at least once
        assert second_calls["n"] >= 1


# ---------------------------------------------------------------------------
# Resilience: exceptions in run_sync don't kill the loop
# ---------------------------------------------------------------------------


class TestLoopResilience:
    async def test_exception_in_run_sync_does_not_kill_loop(
        self, db, event_bus
    ):
        """A failing sync should be logged but the loop should keep running."""
        attempts = {"n": 0}

        async def flaky_run_sync(source):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient failure on first attempt")
            return {"status": "complete"}

        service = _make_service(db, event_bus, run_sync_impl=flaky_run_sync)
        service.start_auto_sync("qobuz", interval_seconds=0.01)

        await asyncio.sleep(0.05)
        service.stop_auto_sync()
        await asyncio.sleep(0)

        # The loop survived the first exception and ran a second time
        assert attempts["n"] >= 2, (
            f"loop died after first exception; only {attempts['n']} attempts"
        )
