"""Main Textual application for library browsing."""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Optional

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from ..metadata import SearchResults


class DownloadStatus(Enum):
    """Status of a download item."""

    PENDING = "pending"
    RESOLVING = "resolving"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    SKIPPED = "skipped"  # Already downloaded / duplicate
    FAILED = "failed"


class TrackStatus(Enum):
    """Status of a track download."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class TrackItem:
    """Represents a track in the download queue."""

    track_id: str
    name: str
    track_num: int
    status: TrackStatus = TrackStatus.QUEUED
    error: Optional[str] = None
    bytes_downloaded: int = 0
    bytes_total: int = 0
    download_speed: float = 0.0  # bytes per second


@dataclass
class DownloadItem:
    """Represents an item in the download queue."""

    album_id: str
    title: str
    artist: str
    source: str
    year: str = ""
    format_str: str = ""
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    current_track: str = ""
    total_tracks: int = 0
    completed_tracks: int = 0
    error: Optional[str] = None
    skip_reason: Optional[str] = None
    tracks: list[TrackItem] = field(default_factory=list)  # Individual track info


class SortColumn(Enum):
    """Column to sort by."""

    ALBUM = "album"
    ARTIST = "artist"
    YEAR = "year"
    FORMAT = "format"


@dataclass
class BrowserState:
    """State for the library browser."""

    source: str = "qobuz"
    albums: list = field(default_factory=list)
    filtered_albums: list = field(default_factory=list)  # Albums after search filter
    search_results: Optional[SearchResults] = None
    selected_indices: set = field(default_factory=set)
    download_queue: list[DownloadItem] = field(default_factory=list)
    is_downloading: bool = False
    current_download_task: Optional[asyncio.Task] = None  # For cancellation
    sort_column: SortColumn = SortColumn.ARTIST
    sort_ascending: bool = True
    search_query: str = ""  # Current search/filter text
    album_cache: Optional[list] = None  # Cache for album data


class AlbumTable(DataTable):
    """DataTable for displaying albums."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("space", "toggle_select", "Select", show=True),
        Binding("enter", "request_add_to_queue", "Add to Queue", show=True),
        Binding("a", "select_all", "Select All", show=True),
        Binding("n", "select_none", "Clear Selection", show=True),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_rows: set[int] = set()
        self.row_keys: list = []  # Store row keys for reliable access
        # Enable row cursor for navigation
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.can_focus = True

    def on_mount(self) -> None:
        """Set up table columns."""
        self.add_column("", key="selected", width=3)
        self.add_column("Album", key="album", width=70)
        self.add_column("Artist", key="artist", width=30)
        self.add_column("Year", key="year", width=6)
        self.add_column("Tracks", key="tracks", width=6)
        self.add_column("Format", key="format", width=10)
        # Focus the table for keyboard navigation
        self.focus()

    def action_toggle_select(self) -> None:
        """Toggle selection of current row."""
        if self.cursor_row is not None:
            row_idx = self.cursor_row
            if row_idx < 0 or row_idx >= len(self.row_keys):
                return  # Invalid row index
            if row_idx in self.selected_rows:
                self.selected_rows.discard(row_idx)
            else:
                self.selected_rows.add(row_idx)
            self._update_row_selection(row_idx)
            self.post_message(self.SelectionChanged(self.selected_rows.copy()))

    def action_select_all(self) -> None:
        """Select all rows."""
        self.selected_rows = set(range(self.row_count))
        self._update_selection_display()
        self.post_message(self.SelectionChanged(self.selected_rows.copy()))

    def action_select_none(self) -> None:
        """Clear all selections."""
        self.selected_rows.clear()
        self._update_selection_display()
        self.post_message(self.SelectionChanged(self.selected_rows.copy()))

    def _update_row_selection(self, row_idx: int) -> None:
        """Update the selection checkmark for a single row."""
        if row_idx < 0 or row_idx >= len(self.row_keys):
            return
        row_key = self.row_keys[row_idx]
        marker = "✓" if row_idx in self.selected_rows else " "
        self.update_cell(row_key, "selected", marker)

    def _update_selection_display(self) -> None:
        """Update the selection checkmarks in the table."""
        for row_idx in range(len(self.row_keys)):
            self._update_row_selection(row_idx)

    def add_album_row(self, selected: str, title: str, artist: str, year: str, tracks: str, format_str: str):
        """Add a row and track its key."""
        row_key = self.add_row(selected, title, artist, year, tracks, format_str)
        self.row_keys.append(row_key)
        return row_key

    def clear_albums(self) -> None:
        """Clear all rows and reset tracking."""
        self.clear()
        self.row_keys.clear()
        self.selected_rows.clear()

    class SelectionChanged(Message):
        """Message sent when selection changes."""

        def __init__(self, selected: set[int]):
            super().__init__()
            self.selected = selected

    class AddToQueueRequested(Message):
        """Message sent when user requests to add selections to queue."""

        def __init__(self):
            super().__init__()

    def action_request_add_to_queue(self) -> None:
        """Request adding selected items to download queue."""
        if self.selected_rows:
            self.post_message(self.AddToQueueRequested())


class DownloadQueueWidget(Static):
    """Widget showing download queue and progress."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue: list[DownloadItem] = []

    def compose(self) -> ComposeResult:
        yield Label("Download Queue", id="queue-title")
        yield Static("", id="queue-summary")  # Total progress summary
        yield ListView(id="queue-list")
        yield Static("", id="current-progress")

    def update_queue(self, queue: list[DownloadItem]) -> None:
        """Update the queue display."""
        self.queue = queue
        list_view = self.query_one("#queue-list", ListView)
        list_view.clear()

        # Update queue summary
        summary_widget = self.query_one("#queue-summary", Static)
        if queue:
            total = len(queue)
            completed = sum(1 for i in queue if i.status == DownloadStatus.COMPLETE)
            skipped = sum(1 for i in queue if i.status == DownloadStatus.SKIPPED)
            failed = sum(1 for i in queue if i.status == DownloadStatus.FAILED)
            pending = sum(1 for i in queue if i.status == DownloadStatus.PENDING)
            active = sum(1 for i in queue if i.status in (DownloadStatus.DOWNLOADING, DownloadStatus.RESOLVING))

            summary = Text()
            summary.append(f"{completed + skipped}/{total}", style="bold green" if completed + skipped == total else "bold")
            summary.append(" albums", style="dim")
            if active:
                summary.append(f" | {active} active", style="cyan")
            if pending:
                summary.append(f" | {pending} pending", style="dim")
            if failed:
                summary.append(f" | {failed} failed", style="red")
            summary_widget.update(summary)
        else:
            summary_widget.update(Text("No items in queue", style="dim"))

        for item in queue:
            # Album header: Artist - Album (Year) - Format
            album_status_icon = {
                DownloadStatus.PENDING: "○",
                DownloadStatus.RESOLVING: "◐",
                DownloadStatus.DOWNLOADING: "↓",
                DownloadStatus.COMPLETE: "✓",
                DownloadStatus.SKIPPED: "⊘",
                DownloadStatus.FAILED: "✗",
            }.get(item.status, "?")

            album_status_color = {
                DownloadStatus.PENDING: "dim",
                DownloadStatus.RESOLVING: "yellow",
                DownloadStatus.DOWNLOADING: "cyan",
                DownloadStatus.COMPLETE: "green",
                DownloadStatus.SKIPPED: "yellow",
                DownloadStatus.FAILED: "red",
            }.get(item.status, "white")

            # Build album header
            header = Text()
            header.append(f"{album_status_icon} ", style=album_status_color)
            header.append(f"{item.artist}", style="bold")
            header.append(" - ", style="dim")
            header.append(f"{item.title}", style="bold")
            if item.year:
                header.append(f" ({item.year})", style="dim")
            if item.format_str:
                header.append(f" - {item.format_str}", style="cyan")

            # Add album status info with better error messages
            if item.status == DownloadStatus.SKIPPED and item.skip_reason:
                header.append(f" [{item.skip_reason}]", style="yellow")
            elif item.status == DownloadStatus.FAILED and item.error:
                # Format error message for better readability
                error_msg = item.error
                if "timeout" in error_msg.lower():
                    error_msg = "Connection timeout"
                elif "401" in error_msg or "unauthorized" in error_msg.lower():
                    error_msg = "Auth expired - re-login"
                elif "403" in error_msg or "forbidden" in error_msg.lower():
                    error_msg = "Access denied"
                elif "404" in error_msg or "not found" in error_msg.lower():
                    error_msg = "Not found"
                elif "429" in error_msg or "rate" in error_msg.lower():
                    error_msg = "Rate limited - wait"
                elif "connection" in error_msg.lower():
                    error_msg = "Connection error"
                else:
                    error_msg = error_msg[:30]
                header.append(f" [{error_msg}]", style="red")

            list_view.append(ListItem(Static(header)))

            # Add individual tracks if available
            if item.tracks and item.status in (DownloadStatus.DOWNLOADING, DownloadStatus.COMPLETE, DownloadStatus.FAILED):
                for track in item.tracks:
                    track_text = Text()
                    track_text.append("   ")  # Indent

                    # Track status icon
                    track_icon = {
                        TrackStatus.QUEUED: "○",
                        TrackStatus.DOWNLOADING: "↓",
                        TrackStatus.COMPLETE: "✓",
                        TrackStatus.SKIPPED: "⊘",
                        TrackStatus.FAILED: "✗",
                    }.get(track.status, "?")

                    track_color = {
                        TrackStatus.QUEUED: "dim",
                        TrackStatus.DOWNLOADING: "cyan",
                        TrackStatus.COMPLETE: "green",
                        TrackStatus.SKIPPED: "yellow",
                        TrackStatus.FAILED: "red",
                    }.get(track.status, "white")

                    track_text.append(f"{track_icon} ", style=track_color)
                    track_text.append(f"{track.track_num}. ", style="dim")
                    track_text.append(track.name[:30], style=track_color)

                    # Show progress bar and speed for downloading tracks
                    if track.status == TrackStatus.DOWNLOADING and track.bytes_total > 0:
                        # Calculate progress percentage
                        pct = (track.bytes_downloaded / track.bytes_total) * 100
                        # Build mini progress bar (10 chars)
                        filled = int(pct / 10)
                        bar = "█" * filled + "░" * (10 - filled)
                        track_text.append(f" [{bar}]", style="cyan")
                        track_text.append(f" {pct:.0f}%", style="cyan")
                        # Show speed
                        if track.download_speed > 0:
                            speed_str = self._format_speed(track.download_speed)
                            track_text.append(f" {speed_str}", style="green")
                    elif track.status == TrackStatus.DOWNLOADING:
                        track_text.append(" - Downloading...", style="cyan")
                    elif track.status == TrackStatus.QUEUED:
                        track_text.append(" - Queued", style="dim")
                    elif track.status == TrackStatus.SKIPPED:
                        track_text.append(" - Skipped", style="yellow")
                    elif track.status == TrackStatus.FAILED:
                        track_text.append(" - Failed", style="red")

                    list_view.append(ListItem(Static(track_text)))

        # Update current progress
        active = next(
            (i for i in queue if i.status == DownloadStatus.DOWNLOADING), None
        )
        progress_widget = self.query_one("#current-progress", Static)
        if active:
            # Show overall album progress
            progress_text = Text()
            progress_text.append(f"Album: {active.completed_tracks}/{active.total_tracks} tracks\n", style="bold")
            # Find active track
            active_track = next((t for t in active.tracks if t.status == TrackStatus.DOWNLOADING), None)
            if active_track and active_track.bytes_total > 0:
                pct = (active_track.bytes_downloaded / active_track.bytes_total) * 100
                speed_str = self._format_speed(active_track.download_speed) if active_track.download_speed > 0 else ""
                progress_text.append(f"Track: {active_track.name[:25]} - {pct:.0f}% {speed_str}", style="cyan")
            progress_widget.update(progress_text)
        else:
            progress_widget.update("")

    def _format_speed(self, bytes_per_sec: float) -> str:
        """Format download speed in human readable format."""
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"


class LibraryBrowser(App):
    """Textual app for browsing and downloading music library."""

    CSS = """
    #main-container {
        layout: horizontal;
        height: 1fr;
    }

    #left-panel {
        width: 2fr;
        height: 100%;
        border: solid $primary;
        padding: 0;
    }

    #right-panel {
        width: 1fr;
        height: 100%;
        border: solid $primary;
        padding: 0;
    }

    #panel-title {
        text-style: bold;
        padding: 0 1;
        height: 1;
        background: $surface;
        color: $text;
    }

    #search-container {
        height: 3;
        padding: 0 1;
    }

    #search-input {
        width: 100%;
    }

    #album-table {
        height: 1fr;
    }

    #album-table:focus {
        border: none;
    }

    #album-table > .datatable--cursor {
        background: $accent;
        color: $text;
    }

    #download-queue {
        height: 100%;
    }

    #queue-title {
        text-style: bold;
        padding: 0 1;
        height: 1;
        background: $surface;
        color: $text;
    }

    #queue-summary {
        height: 1;
        padding: 0 1;
        background: $surface-darken-1;
    }

    #queue-list {
        height: 1fr;
        padding: 0;
        margin: 0;
    }

    #queue-list > ListItem {
        padding: 0;
        height: auto;
    }

    #current-progress {
        height: auto;
        min-height: 2;
        padding: 0 1;
        background: $surface;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("d", "start_downloads", "Download", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("c", "clear_completed", "Clear Done", show=True),
        Binding("s", "cycle_sort", "Sort", show=True),
        Binding("/", "focus_search", "Search", show=True),
        Binding("R", "retry_failed", "Retry", show=True),
        Binding("x", "cancel_downloads", "Cancel", show=True),
        Binding("m", "mark_downloaded", "Mark Done", show=True),
        Binding("S", "toggle_sort_direction", "Sort ↑↓", show=False),
        Binding("1", "sort_by_album", "By Album", show=False),
        Binding("2", "sort_by_artist", "By Artist", show=False),
        Binding("3", "sort_by_year", "By Year", show=False),
        Binding("4", "sort_by_format", "By Format", show=False),
        Binding("escape", "clear_search", "Clear Search", show=False),
    ]

    selected_count = reactive(0)

    def __init__(
        self,
        main_instance,
        source: str,
        include_downloaded: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.main = main_instance
        self.state = BrowserState(source=source)
        self.include_downloaded = include_downloaded
        self._download_task: Optional[asyncio.Task] = None

    @staticmethod
    def _format_quality(album: dict) -> str:
        """Format album quality as bit depth/sample rate (e.g., '24/96')."""
        bit_depth = album.get("maximum_bit_depth")
        sample_rate = album.get("maximum_sampling_rate")

        if bit_depth and sample_rate:
            # Format sample rate: show as integer if whole number, else one decimal
            if sample_rate == int(sample_rate):
                rate_str = str(int(sample_rate))
            else:
                rate_str = f"{sample_rate:.1f}".rstrip('0').rstrip('.')
            return f"{bit_depth}/{rate_str}"
        elif album.get("hires_streamable"):
            return "Hi-Res"
        else:
            return "16/44.1"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield Label("Library", id="panel-title")
                with Horizontal(id="search-container"):
                    yield Input(placeholder="Filter albums... (press / to focus)", id="search-input")
                yield AlbumTable(id="album-table")
                yield Static("", id="status-bar")
            with Vertical(id="right-panel"):
                yield DownloadQueueWidget(id="download-queue")
        yield Footer()

    async def on_mount(self) -> None:
        """Load albums when app starts."""
        self.title = f"Library Browser - {self.state.source.capitalize()}"
        await self.load_albums()
        # Ensure table has focus for keyboard navigation
        table = self.query_one("#album-table", AlbumTable)
        table.focus()

    async def load_albums(self, force_refresh: bool = False) -> None:
        """Load albums from the library with caching support."""
        table = self.query_one("#album-table", AlbumTable)
        table.loading = True

        try:
            # Use cache if available and not forcing refresh
            if self.state.album_cache is not None and not force_refresh:
                all_albums = self.state.album_cache
            else:
                client = await self.main.get_logged_in_client(self.state.source)

                # Fetch albums
                pages = await client.get_user_favorites("album", limit=None)
                all_albums = []
                for page in pages:
                    albums_data = page.get("albums", {})
                    albums_items = albums_data.get("items", [])
                    all_albums.extend(albums_items)

                # Cache the raw album data
                self.state.album_cache = all_albums

            # Filter downloaded albums using optimized batch lookup
            if not self.include_downloaded:
                # Get all downloaded album IDs at once (single DB query)
                downloaded_ids = self.main.database.get_downloaded_album_ids(self.state.source)
                # Filter using set membership (O(1) per album)
                all_albums = [
                    album for album in all_albums
                    if str(album.get("id")) not in downloaded_ids
                ]

            self.state.albums = all_albums
            self.state.filtered_albums = all_albums

            # Sort and populate table
            self._apply_filter_and_refresh()

            # Re-focus table after loading
            table.focus()

        except Exception as e:
            self.notify(f"Error loading albums: {e}", severity="error")
        finally:
            table.loading = False
            table.focus()

    def _update_status(self) -> None:
        """Update the status bar."""
        table = self.query_one("#album-table", AlbumTable)
        status = self.query_one("#status-bar", Static)

        total = len(self.state.albums)
        filtered = len(self.state.filtered_albums) if self.state.filtered_albums else total
        selected = len(table.selected_rows)

        status_text = Text()

        # Show album count (filtered/total if filtering)
        if self.state.search_query:
            status_text.append(f"{filtered}/{total} albums", style="yellow")
            status_text.append(f" matching '{self.state.search_query}'", style="dim")
        else:
            status_text.append(f"{total} albums")

        # Show sort info
        direction = "↑" if self.state.sort_ascending else "↓"
        status_text.append(" | ", style="dim")
        status_text.append(f"{self.state.sort_column.value.capitalize()} {direction}", style="cyan")

        if selected > 0:
            status_text.append(" | ", style="dim")
            status_text.append(f"{selected} selected", style="green bold")

        if self.state.is_downloading:
            status_text.append(" | ", style="dim")
            status_text.append("Downloading...", style="yellow")

        status.update(status_text)

    def on_album_table_selection_changed(
        self, message: AlbumTable.SelectionChanged
    ) -> None:
        """Handle selection changes."""
        self.selected_count = len(message.selected)
        self._update_status()

    def on_album_table_add_to_queue_requested(
        self, message: AlbumTable.AddToQueueRequested
    ) -> None:
        """Handle request to add selections to queue."""
        self.action_add_to_queue()

    def action_add_to_queue(self) -> None:
        """Add selected albums to download queue."""
        table = self.query_one("#album-table", AlbumTable)

        if not table.selected_rows:
            self.notify("No albums selected", severity="warning")
            return

        # Use filtered_albums since that's what's displayed in the table
        albums_list = self.state.filtered_albums if self.state.filtered_albums else self.state.albums

        added = 0
        for row_idx in table.selected_rows:
            if row_idx < len(albums_list):
                album = albums_list[row_idx]
                album_id = str(album.get("id"))

                # Check if already in queue
                if any(item.album_id == album_id for item in self.state.download_queue):
                    continue

                artist_info = album.get("artist", {})
                artist = (
                    artist_info.get("name", "Unknown")
                    if isinstance(artist_info, dict)
                    else "Unknown"
                )
                year = str(album.get("release_date_original", ""))[:4]
                format_str = self._format_quality(album)

                item = DownloadItem(
                    album_id=album_id,
                    title=album.get("title", "Unknown"),
                    artist=artist,
                    source=self.state.source,
                    year=year,
                    format_str=format_str,
                )
                self.state.download_queue.append(item)
                added += 1

        # Clear selections
        table.selected_rows.clear()
        table._update_selection_display()

        # Update queue display
        queue_widget = self.query_one("#download-queue", DownloadQueueWidget)
        queue_widget.update_queue(self.state.download_queue)

        self._update_status()
        self.notify(f"Added {added} albums to queue")

    def action_start_downloads(self) -> None:
        """Start downloading queued items."""
        # If nothing in queue but items are selected, add them first
        table = self.query_one("#album-table", AlbumTable)
        if not self.state.download_queue and table.selected_rows:
            self.action_add_to_queue()

        pending = [
            item
            for item in self.state.download_queue
            if item.status == DownloadStatus.PENDING
        ]

        if not pending:
            self.notify("No pending downloads - select albums first (Space)", severity="warning")
            return

        self.state.is_downloading = True
        self._update_status()
        self._run_downloads()

    async def _download_with_progress(self, album, item: DownloadItem) -> None:
        """Download album tracks with progress updates (concurrent)."""
        import time

        from ..media.album import Album

        if isinstance(album, Album):
            # Preprocess (create directories, download cover art)
            await album.preprocess()

            # Get concurrency settings from config
            max_connections = getattr(self.main.config.session.downloads, 'max_connections', 6)
            concurrency_enabled = getattr(self.main.config.session.downloads, 'concurrency', True)

            # Use semaphore to limit concurrent downloads
            semaphore = asyncio.Semaphore(max_connections if concurrency_enabled else 1)

            # Build track list with names from metadata
            item.tracks = []
            for i, pending_track in enumerate(album.tracks):
                track_name = f"Track {i + 1}"
                if hasattr(album, 'meta') and album.meta:
                    if hasattr(album.meta, 'info') and album.meta.info:
                        tracklist = getattr(album.meta.info, 'tracklist', None)
                        if tracklist and i < len(tracklist):
                            track_name = tracklist[i].get('title', track_name)

                item.tracks.append(TrackItem(
                    track_id=str(pending_track.id),
                    name=track_name,
                    track_num=i + 1,
                    status=TrackStatus.QUEUED,
                ))

            # Track download function with progress callback (respects semaphore)
            async def download_track(idx: int, pending_track, track_item: TrackItem):
                async with semaphore:
                    start_time = time.time()
                    last_update = start_time
                    bytes_since_update = 0

                    def progress_callback(chunk_size: int):
                        nonlocal last_update, bytes_since_update
                        track_item.bytes_downloaded += chunk_size
                        bytes_since_update += chunk_size

                        now = time.time()
                        elapsed = now - last_update
                        if elapsed >= 0.3:  # Update speed every 300ms
                            track_item.download_speed = bytes_since_update / elapsed
                            bytes_since_update = 0
                            last_update = now

                    try:
                        # Check if already downloaded
                        if pending_track.db.downloaded(pending_track.id):
                            track_item.status = TrackStatus.SKIPPED
                            return True

                        # Mark as downloading
                        track_item.status = TrackStatus.DOWNLOADING

                        # Resolve track
                        track = await pending_track.resolve()
                        if track is None:
                            track_item.status = TrackStatus.SKIPPED
                            return True

                        # Get track name from resolved metadata
                        if hasattr(track, 'meta') and track.meta:
                            track_item.name = getattr(track.meta, 'title', track_item.name)

                        # Get file size
                        if hasattr(track, 'downloadable'):
                            try:
                                track_item.bytes_total = await track.downloadable.size()
                            except Exception:
                                track_item.bytes_total = 0

                        # Download with custom progress callback
                        await track.preprocess()

                        # Override the download to use our callback
                        if hasattr(track, 'downloadable') and track_item.bytes_total > 0:
                            await track.downloadable.download(track.download_path, progress_callback)
                        else:
                            await track.download()

                        await track.postprocess()

                        track_item.status = TrackStatus.COMPLETE
                        track_item.download_speed = 0
                        return True

                    except Exception as e:
                        track_item.status = TrackStatus.FAILED
                        track_item.error = str(e)[:30]
                        return False

            # Download all tracks concurrently (UI updates handled by global task in _run_downloads)
            await asyncio.gather(
                *[download_track(i, pt, item.tracks[i]) for i, pt in enumerate(album.tracks)],
                return_exceptions=True
            )

            # Count successes
            successful = sum(1 for t in item.tracks if t.status == TrackStatus.COMPLETE)
            skipped = sum(1 for t in item.tracks if t.status == TrackStatus.SKIPPED)

            # Update final count
            item.completed_tracks = successful + skipped

            # Postprocess (progress bar cleanup)
            album.successful_tracks = successful + skipped
            album.total_tracks = item.total_tracks
            await album.postprocess()

            # Explicitly mark album as downloaded using the original album ID from favorites
            # This ensures consistency since album.meta.info.id may differ from the favorites API ID
            all_tracks_succeeded = (successful + skipped) == item.total_tracks
            if all_tracks_succeeded:
                if not self.main.database.album_downloaded(item.source, item.album_id):
                    self.main.database.set_album_downloaded(
                        item.source, item.album_id, item.title, item.artist
                    )
        else:
            # Fallback for non-album media
            await album.rip()

    @work(exclusive=True, thread=False)
    async def _run_downloads(self) -> None:
        """Background worker for downloads."""
        queue_widget = self.query_one("#download-queue", DownloadQueueWidget)

        # Start a global UI update task that runs throughout all downloads
        ui_update_running = True

        async def global_ui_update():
            while ui_update_running:
                queue_widget.update_queue(self.state.download_queue)
                await asyncio.sleep(0.3)

        ui_task = asyncio.create_task(global_ui_update())

        try:
            for item in self.state.download_queue:
                if item.status != DownloadStatus.PENDING:
                    continue

                try:
                    # Check if already downloaded
                    if self.main.database.album_downloaded(item.source, item.album_id):
                        item.status = DownloadStatus.SKIPPED
                        item.skip_reason = "Already downloaded"
                        continue

                    # Update status to resolving
                    item.status = DownloadStatus.RESOLVING

                    # Add to main's pending list
                    await self.main.add_by_id(item.source, "album", item.album_id)

                    # Check if anything was added (might be filtered)
                    if not self.main.pending:
                        item.status = DownloadStatus.SKIPPED
                        item.skip_reason = "Not available"
                        continue

                    # Resolve
                    await self.main.resolve()

                    # Check if anything was resolved
                    if not self.main.media:
                        item.status = DownloadStatus.SKIPPED
                        item.skip_reason = "Could not resolve"
                        self.main.pending.clear()
                        continue

                    # Get track count from resolved album
                    album = self.main.media[0]
                    if hasattr(album, "tracks"):
                        item.total_tracks = len(album.tracks)
                    else:
                        item.total_tracks = 1

                    # Update status to downloading
                    item.status = DownloadStatus.DOWNLOADING
                    item.completed_tracks = 0

                    # Download with progress tracking
                    await self._download_with_progress(album, item)

                    # Mark complete
                    item.status = DownloadStatus.COMPLETE
                    item.completed_tracks = item.total_tracks

                    # Clear main's media list for next album
                    self.main.media.clear()

                except Exception as e:
                    item.status = DownloadStatus.FAILED
                    item.error = str(e)
                    self.notify(f"Failed: {item.title}: {e}", severity="error")
                    # Clear any pending state
                    self.main.pending.clear()
                    self.main.media.clear()

        finally:
            # Stop the UI update task
            ui_update_running = False
            await ui_task
            # Final UI update
            queue_widget.update_queue(self.state.download_queue)

        self.state.is_downloading = False
        self._update_status()

        # Count results
        completed = sum(
            1 for i in self.state.download_queue if i.status == DownloadStatus.COMPLETE
        )
        skipped = sum(
            1 for i in self.state.download_queue if i.status == DownloadStatus.SKIPPED
        )
        failed = sum(
            1 for i in self.state.download_queue if i.status == DownloadStatus.FAILED
        )

        # Build summary message
        parts = []
        if completed:
            parts.append(f"{completed} downloaded")
        if skipped:
            parts.append(f"{skipped} skipped")
        if failed:
            parts.append(f"{failed} failed")

        if parts:
            severity = "error" if failed else "information"
            self.notify(f"Complete: {', '.join(parts)}", severity=severity)

    def action_refresh(self) -> None:
        """Refresh the album list (force refresh from API)."""
        self.state.album_cache = None  # Clear cache to force refresh
        self.run_worker(self.load_albums(force_refresh=True))

    def action_clear_completed(self) -> None:
        """Clear completed/skipped/failed downloads from queue."""
        self.state.download_queue = [
            item
            for item in self.state.download_queue
            if item.status not in (DownloadStatus.COMPLETE, DownloadStatus.SKIPPED, DownloadStatus.FAILED)
        ]
        queue_widget = self.query_one("#download-queue", DownloadQueueWidget)
        queue_widget.update_queue(self.state.download_queue)
        self.notify("Cleared completed downloads")

    def action_focus_search(self) -> None:
        """Focus the search input."""
        search_input = self.query_one("#search-input", Input)
        search_input.focus()

    def action_clear_search(self) -> None:
        """Clear search and refocus table."""
        search_input = self.query_one("#search-input", Input)
        search_input.value = ""
        self.state.search_query = ""
        self._apply_filter_and_refresh()
        table = self.query_one("#album-table", AlbumTable)
        table.focus()

    def action_retry_failed(self) -> None:
        """Retry all failed downloads."""
        failed_count = 0
        for item in self.state.download_queue:
            if item.status == DownloadStatus.FAILED:
                item.status = DownloadStatus.PENDING
                item.error = None
                item.tracks = []
                item.completed_tracks = 0
                failed_count += 1

        if failed_count > 0:
            queue_widget = self.query_one("#download-queue", DownloadQueueWidget)
            queue_widget.update_queue(self.state.download_queue)
            self.notify(f"Retrying {failed_count} failed downloads")
            # Start downloads if not already running
            if not self.state.is_downloading:
                self.action_start_downloads()
        else:
            self.notify("No failed downloads to retry", severity="warning")

    def action_cancel_downloads(self) -> None:
        """Cancel current downloads."""
        if not self.state.is_downloading:
            self.notify("No downloads in progress", severity="warning")
            return

        # Mark downloading items as failed
        for item in self.state.download_queue:
            if item.status in (DownloadStatus.DOWNLOADING, DownloadStatus.RESOLVING):
                item.status = DownloadStatus.FAILED
                item.error = "Cancelled by user"

        self.state.is_downloading = False
        queue_widget = self.query_one("#download-queue", DownloadQueueWidget)
        queue_widget.update_queue(self.state.download_queue)
        self._update_status()
        self.notify("Downloads cancelled")

    def action_mark_downloaded(self) -> None:
        """Mark selected albums as downloaded without downloading them."""
        table = self.query_one("#album-table", AlbumTable)

        if not table.selected_rows:
            self.notify("No albums selected", severity="warning")
            return

        albums_list = self.state.filtered_albums if self.state.filtered_albums else self.state.albums

        marked = 0
        for row_idx in table.selected_rows:
            if row_idx < len(albums_list):
                album = albums_list[row_idx]
                album_id = str(album.get("id"))
                title = album.get("title", "Unknown")
                artist_info = album.get("artist", {})
                artist = (
                    artist_info.get("name", "Unknown")
                    if isinstance(artist_info, dict)
                    else "Unknown"
                )

                # Mark as downloaded in the database
                self.main.database.set_album_downloaded(
                    self.state.source, album_id, title, artist
                )
                marked += 1

        # Clear selections
        table.selected_rows.clear()
        table._update_selection_display()

        if marked > 0:
            self.notify(f"Marked {marked} album(s) as downloaded")
            # Invalidate cache and refresh to remove marked albums from view
            self.state.album_cache = None
            self.run_worker(self.load_albums(force_refresh=True))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            self.state.search_query = event.value
            self._apply_filter_and_refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submit (Enter key)."""
        if event.input.id == "search-input":
            # Focus back to table after search
            table = self.query_one("#album-table", AlbumTable)
            table.focus()

    def action_quit(self) -> None:
        """Quit the application."""
        if self.state.is_downloading:
            self.notify(
                "Downloads in progress. Press Q again to force quit.",
                severity="warning",
            )
            # Actually quit on second press
            self.exit()
        else:
            self.exit()

    def action_cycle_sort(self) -> None:
        """Cycle through sort columns."""
        columns = list(SortColumn)
        current_idx = columns.index(self.state.sort_column)
        next_idx = (current_idx + 1) % len(columns)
        self.state.sort_column = columns[next_idx]
        self._apply_filter_and_refresh()
        direction = "↑" if self.state.sort_ascending else "↓"
        self.notify(f"Sort: {self.state.sort_column.value.capitalize()} {direction}")

    def action_toggle_sort_direction(self) -> None:
        """Toggle sort direction."""
        self.state.sort_ascending = not self.state.sort_ascending
        self._apply_filter_and_refresh()
        direction = "↑ Ascending" if self.state.sort_ascending else "↓ Descending"
        self.notify(f"Sort: {direction}")

    def action_sort_by_album(self) -> None:
        """Sort by album name."""
        self._set_sort(SortColumn.ALBUM)

    def action_sort_by_artist(self) -> None:
        """Sort by artist name."""
        self._set_sort(SortColumn.ARTIST)

    def action_sort_by_year(self) -> None:
        """Sort by year."""
        self._set_sort(SortColumn.YEAR)

    def action_sort_by_format(self) -> None:
        """Sort by format."""
        self._set_sort(SortColumn.FORMAT)

    def _set_sort(self, column: SortColumn) -> None:
        """Set sort column, toggling direction if same column."""
        if self.state.sort_column == column:
            self.state.sort_ascending = not self.state.sort_ascending
        else:
            self.state.sort_column = column
            self.state.sort_ascending = True
        self._apply_filter_and_refresh()
        direction = "↑" if self.state.sort_ascending else "↓"
        self.notify(f"Sort: {column.value.capitalize()} {direction}")

    def _apply_filter_and_refresh(self) -> None:
        """Apply search filter, sort albums and refresh the table display."""
        if not self.state.albums:
            self._update_status()
            return

        # Apply search filter
        query = self.state.search_query.lower().strip()
        if query:
            filtered = []
            for album in self.state.albums:
                title = album.get("title", "").lower()
                artist_info = album.get("artist", {})
                artist = artist_info.get("name", "").lower() if isinstance(artist_info, dict) else ""
                if query in title or query in artist:
                    filtered.append(album)
            self.state.filtered_albums = filtered
        else:
            self.state.filtered_albums = self.state.albums

        # Define sort key functions
        def get_sort_key(album):
            if self.state.sort_column == SortColumn.ALBUM:
                return album.get("title", "").lower()
            elif self.state.sort_column == SortColumn.ARTIST:
                artist_info = album.get("artist", {})
                if isinstance(artist_info, dict):
                    return artist_info.get("name", "").lower()
                return ""
            elif self.state.sort_column == SortColumn.YEAR:
                return album.get("release_date_original", "")[:4]
            elif self.state.sort_column == SortColumn.FORMAT:
                # Sort by bit depth * sample rate (higher quality first)
                bit_depth = album.get("maximum_bit_depth", 16)
                sample_rate = album.get("maximum_sampling_rate", 44.1)
                return bit_depth * sample_rate
            return ""

        # Sort the filtered albums
        self.state.filtered_albums.sort(key=get_sort_key, reverse=not self.state.sort_ascending)

        # Refresh the table
        table = self.query_one("#album-table", AlbumTable)
        table.clear_albums()

        for album in self.state.filtered_albums:
            title = album.get("title", "Unknown")[:33]
            artist_info = album.get("artist", {})
            artist = (
                artist_info.get("name", "Unknown")[:23]
                if isinstance(artist_info, dict)
                else "Unknown"
            )
            year = str(album.get("release_date_original", "")[:4])
            tracks = str(album.get("tracks_count", album.get("tracks", {}).get("total", "?")))
            format_str = self._format_quality(album)

            table.add_album_row(" ", title, artist, year, tracks, format_str)

        self._update_status()
