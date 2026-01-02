"""Tests for the TUI components."""

import pytest
from unittest.mock import MagicMock, patch

from streamrip.tui.app import (
    AlbumTable,
    DownloadItem,
    DownloadStatus,
    BrowserState,
    SortColumn,
)


class TestDownloadStatus:
    """Tests for DownloadStatus enum."""

    def test_all_statuses_exist(self):
        """Verify all expected statuses exist."""
        assert DownloadStatus.PENDING.value == "pending"
        assert DownloadStatus.RESOLVING.value == "resolving"
        assert DownloadStatus.DOWNLOADING.value == "downloading"
        assert DownloadStatus.COMPLETE.value == "complete"
        assert DownloadStatus.SKIPPED.value == "skipped"
        assert DownloadStatus.FAILED.value == "failed"


class TestDownloadItem:
    """Tests for DownloadItem dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        item = DownloadItem(
            album_id="123",
            title="Test Album",
            artist="Test Artist",
            source="qobuz",
        )
        assert item.album_id == "123"
        assert item.title == "Test Album"
        assert item.artist == "Test Artist"
        assert item.source == "qobuz"
        assert item.status == DownloadStatus.PENDING
        assert item.progress == 0.0
        assert item.current_track == ""
        assert item.total_tracks == 0
        assert item.completed_tracks == 0
        assert item.error is None
        assert item.skip_reason is None

    def test_with_error(self):
        """Test item with error set."""
        item = DownloadItem(
            album_id="123",
            title="Test Album",
            artist="Test Artist",
            source="qobuz",
            status=DownloadStatus.FAILED,
            error="Connection timeout",
        )
        assert item.status == DownloadStatus.FAILED
        assert item.error == "Connection timeout"

    def test_with_skip_reason(self):
        """Test item with skip reason set."""
        item = DownloadItem(
            album_id="123",
            title="Test Album",
            artist="Test Artist",
            source="qobuz",
            status=DownloadStatus.SKIPPED,
            skip_reason="Already downloaded",
        )
        assert item.status == DownloadStatus.SKIPPED
        assert item.skip_reason == "Already downloaded"


class TestBrowserState:
    """Tests for BrowserState dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        state = BrowserState()
        assert state.source == "qobuz"
        assert state.albums == []
        assert state.search_results is None
        assert state.selected_indices == set()
        assert state.download_queue == []
        assert state.is_downloading is False
        assert state.sort_column == SortColumn.ARTIST
        assert state.sort_ascending is True

    def test_custom_source(self):
        """Test with custom source."""
        state = BrowserState(source="tidal")
        assert state.source == "tidal"


class TestAlbumTableRowKeys:
    """Tests for AlbumTable row key tracking."""

    def test_row_keys_initialized_empty(self):
        """Test that row_keys starts empty."""
        table = AlbumTable()
        assert table.row_keys == []
        assert table.selected_rows == set()

    def test_selected_rows_initialized_empty(self):
        """Test that selected_rows starts empty."""
        table = AlbumTable()
        assert isinstance(table.selected_rows, set)
        assert len(table.selected_rows) == 0


class TestSelectionLogic:
    """Tests for selection toggle logic (unit tests without full widget)."""

    def test_toggle_adds_to_empty_set(self):
        """Test toggling selection on empty set adds the index."""
        selected = set()
        row_idx = 5

        # Simulate toggle logic
        if row_idx in selected:
            selected.discard(row_idx)
        else:
            selected.add(row_idx)

        assert row_idx in selected
        assert len(selected) == 1

    def test_toggle_removes_from_set(self):
        """Test toggling selection on existing item removes it."""
        selected = {5}
        row_idx = 5

        # Simulate toggle logic
        if row_idx in selected:
            selected.discard(row_idx)
        else:
            selected.add(row_idx)

        assert row_idx not in selected
        assert len(selected) == 0

    def test_select_all_creates_range(self):
        """Test select all creates correct range."""
        row_count = 10
        selected = set(range(row_count))

        assert len(selected) == 10
        assert 0 in selected
        assert 9 in selected
        assert 10 not in selected

    def test_select_none_clears(self):
        """Test select none clears all."""
        selected = {1, 2, 3, 4, 5}
        selected.clear()

        assert len(selected) == 0

    def test_row_index_bounds_check(self):
        """Test bounds checking logic."""
        row_keys_len = 10

        # Valid indices
        assert 0 >= 0 and 0 < row_keys_len
        assert 9 >= 0 and 9 < row_keys_len

        # Invalid indices
        assert not (-1 >= 0 and -1 < row_keys_len)
        assert not (10 >= 0 and 10 < row_keys_len)


class TestDownloadQueueLogic:
    """Tests for download queue logic."""

    def test_filter_pending_items(self):
        """Test filtering pending items from queue."""
        queue = [
            DownloadItem("1", "Album 1", "Artist", "qobuz", status=DownloadStatus.PENDING),
            DownloadItem("2", "Album 2", "Artist", "qobuz", status=DownloadStatus.COMPLETE),
            DownloadItem("3", "Album 3", "Artist", "qobuz", status=DownloadStatus.PENDING),
            DownloadItem("4", "Album 4", "Artist", "qobuz", status=DownloadStatus.FAILED),
        ]

        pending = [item for item in queue if item.status == DownloadStatus.PENDING]

        assert len(pending) == 2
        assert pending[0].album_id == "1"
        assert pending[1].album_id == "3"

    def test_filter_completed_for_clear(self):
        """Test filtering for clear completed action."""
        queue = [
            DownloadItem("1", "Album 1", "Artist", "qobuz", status=DownloadStatus.PENDING),
            DownloadItem("2", "Album 2", "Artist", "qobuz", status=DownloadStatus.COMPLETE),
            DownloadItem("3", "Album 3", "Artist", "qobuz", status=DownloadStatus.SKIPPED),
            DownloadItem("4", "Album 4", "Artist", "qobuz", status=DownloadStatus.FAILED),
            DownloadItem("5", "Album 5", "Artist", "qobuz", status=DownloadStatus.DOWNLOADING),
        ]

        remaining = [
            item for item in queue
            if item.status not in (DownloadStatus.COMPLETE, DownloadStatus.SKIPPED, DownloadStatus.FAILED)
        ]

        assert len(remaining) == 2
        assert remaining[0].album_id == "1"  # PENDING
        assert remaining[1].album_id == "5"  # DOWNLOADING

    def test_duplicate_check_in_queue(self):
        """Test checking for duplicates in queue."""
        queue = [
            DownloadItem("1", "Album 1", "Artist", "qobuz"),
            DownloadItem("2", "Album 2", "Artist", "qobuz"),
        ]

        # Check if album_id "1" is already in queue
        assert any(item.album_id == "1" for item in queue)

        # Check if album_id "3" is not in queue
        assert not any(item.album_id == "3" for item in queue)

    def test_count_by_status(self):
        """Test counting items by status."""
        queue = [
            DownloadItem("1", "Album 1", "Artist", "qobuz", status=DownloadStatus.COMPLETE),
            DownloadItem("2", "Album 2", "Artist", "qobuz", status=DownloadStatus.COMPLETE),
            DownloadItem("3", "Album 3", "Artist", "qobuz", status=DownloadStatus.SKIPPED),
            DownloadItem("4", "Album 4", "Artist", "qobuz", status=DownloadStatus.FAILED),
        ]

        completed = sum(1 for i in queue if i.status == DownloadStatus.COMPLETE)
        skipped = sum(1 for i in queue if i.status == DownloadStatus.SKIPPED)
        failed = sum(1 for i in queue if i.status == DownloadStatus.FAILED)

        assert completed == 2
        assert skipped == 1
        assert failed == 1


class TestStatusMessages:
    """Tests for status message building."""

    def test_build_summary_all_types(self):
        """Test building summary with all status types."""
        completed = 5
        skipped = 2
        failed = 1

        parts = []
        if completed:
            parts.append(f"{completed} downloaded")
        if skipped:
            parts.append(f"{skipped} skipped")
        if failed:
            parts.append(f"{failed} failed")

        message = f"Complete: {', '.join(parts)}"

        assert message == "Complete: 5 downloaded, 2 skipped, 1 failed"

    def test_build_summary_only_completed(self):
        """Test building summary with only completed."""
        completed = 3
        skipped = 0
        failed = 0

        parts = []
        if completed:
            parts.append(f"{completed} downloaded")
        if skipped:
            parts.append(f"{skipped} skipped")
        if failed:
            parts.append(f"{failed} failed")

        message = f"Complete: {', '.join(parts)}"

        assert message == "Complete: 3 downloaded"

    def test_severity_with_failures(self):
        """Test severity is error when there are failures."""
        failed = 1
        severity = "error" if failed else "information"
        assert severity == "error"

    def test_severity_without_failures(self):
        """Test severity is information when no failures."""
        failed = 0
        severity = "error" if failed else "information"
        assert severity == "information"


class TestSortColumn:
    """Tests for SortColumn enum."""

    def test_all_columns_exist(self):
        """Verify all expected sort columns exist."""
        assert SortColumn.ALBUM.value == "album"
        assert SortColumn.ARTIST.value == "artist"
        assert SortColumn.YEAR.value == "year"
        assert SortColumn.FORMAT.value == "format"

    def test_column_count(self):
        """Test there are exactly 4 sort columns."""
        assert len(list(SortColumn)) == 4


class TestSortLogic:
    """Tests for sorting logic."""

    def test_sort_by_album_ascending(self):
        """Test sorting albums by title ascending."""
        albums = [
            {"title": "Zebra", "artist": {"name": "Artist A"}},
            {"title": "Alpha", "artist": {"name": "Artist B"}},
            {"title": "Middle", "artist": {"name": "Artist C"}},
        ]

        sorted_albums = sorted(albums, key=lambda a: a.get("title", "").lower())

        assert sorted_albums[0]["title"] == "Alpha"
        assert sorted_albums[1]["title"] == "Middle"
        assert sorted_albums[2]["title"] == "Zebra"

    def test_sort_by_artist_ascending(self):
        """Test sorting albums by artist ascending."""
        albums = [
            {"title": "Album 1", "artist": {"name": "Zed"}},
            {"title": "Album 2", "artist": {"name": "Alpha"}},
            {"title": "Album 3", "artist": {"name": "Beta"}},
        ]

        sorted_albums = sorted(
            albums,
            key=lambda a: a.get("artist", {}).get("name", "").lower()
        )

        assert sorted_albums[0]["artist"]["name"] == "Alpha"
        assert sorted_albums[1]["artist"]["name"] == "Beta"
        assert sorted_albums[2]["artist"]["name"] == "Zed"

    def test_sort_by_year_descending(self):
        """Test sorting albums by year descending."""
        albums = [
            {"title": "Album 1", "release_date_original": "2020-01-01"},
            {"title": "Album 2", "release_date_original": "2024-01-01"},
            {"title": "Album 3", "release_date_original": "2018-01-01"},
        ]

        sorted_albums = sorted(
            albums,
            key=lambda a: a.get("release_date_original", "")[:4],
            reverse=True
        )

        assert sorted_albums[0]["release_date_original"][:4] == "2024"
        assert sorted_albums[1]["release_date_original"][:4] == "2020"
        assert sorted_albums[2]["release_date_original"][:4] == "2018"

    def test_sort_by_format(self):
        """Test sorting albums by format (Hi-Res first)."""
        albums = [
            {"title": "Album 1", "hires_streamable": False},
            {"title": "Album 2", "hires_streamable": True},
            {"title": "Album 3", "hires_streamable": False},
        ]

        # Sort with Hi-Res first (0 = Hi-Res, 1 = CD)
        sorted_albums = sorted(
            albums,
            key=lambda a: "0" if a.get("hires_streamable", False) else "1"
        )

        assert sorted_albums[0]["hires_streamable"] is True
        assert sorted_albums[1]["hires_streamable"] is False

    def test_cycle_sort_columns(self):
        """Test cycling through sort columns."""
        columns = list(SortColumn)
        current_idx = 0  # Start at ALBUM

        # Cycle through all columns
        visited = []
        for _ in range(len(columns)):
            visited.append(columns[current_idx])
            current_idx = (current_idx + 1) % len(columns)

        assert len(visited) == 4
        assert SortColumn.ALBUM in visited
        assert SortColumn.ARTIST in visited
        assert SortColumn.YEAR in visited
        assert SortColumn.FORMAT in visited
