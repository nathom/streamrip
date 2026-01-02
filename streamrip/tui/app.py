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
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
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
    FAILED = "failed"


@dataclass
class DownloadItem:
    """Represents an item in the download queue."""

    album_id: str
    title: str
    artist: str
    source: str
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    current_track: str = ""
    total_tracks: int = 0
    completed_tracks: int = 0
    error: Optional[str] = None


@dataclass
class BrowserState:
    """State for the library browser."""

    source: str = "qobuz"
    albums: list = field(default_factory=list)
    search_results: Optional[SearchResults] = None
    selected_indices: set = field(default_factory=set)
    download_queue: list[DownloadItem] = field(default_factory=list)
    is_downloading: bool = False
    offset: int = 0
    limit: int = 50


class AlbumTable(DataTable):
    """DataTable for displaying albums."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("space", "toggle_select", "Select", show=True),
        Binding("a", "select_all", "Select All", show=True),
        Binding("n", "select_none", "Clear Selection", show=True),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_rows: set[int] = set()
        self.cursor_type = "row"

    def on_mount(self) -> None:
        """Set up table columns."""
        self.add_column("", key="selected", width=3)
        self.add_column("Album", key="album", width=40)
        self.add_column("Artist", key="artist", width=30)
        self.add_column("Year", key="year", width=6)
        self.add_column("Format", key="format", width=15)

    def action_toggle_select(self) -> None:
        """Toggle selection of current row."""
        if self.cursor_row is not None:
            row_key = self.cursor_row
            if row_key in self.selected_rows:
                self.selected_rows.discard(row_key)
            else:
                self.selected_rows.add(row_key)
            self._update_selection_display()
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

    def _update_selection_display(self) -> None:
        """Update the selection checkmarks in the table."""
        for row_idx in range(self.row_count):
            row_key = self.get_row_at(row_idx)
            marker = "✓" if row_idx in self.selected_rows else " "
            self.update_cell(row_key, "selected", marker)

    class SelectionChanged:
        """Message sent when selection changes."""

        def __init__(self, selected: set[int]):
            self.selected = selected


class DownloadQueueWidget(Static):
    """Widget showing download queue and progress."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue: list[DownloadItem] = []

    def compose(self) -> ComposeResult:
        yield Label("Download Queue", id="queue-title")
        yield ListView(id="queue-list")
        yield Static("", id="current-progress")

    def update_queue(self, queue: list[DownloadItem]) -> None:
        """Update the queue display."""
        self.queue = queue
        list_view = self.query_one("#queue-list", ListView)
        list_view.clear()

        for item in queue:
            status_icon = {
                DownloadStatus.PENDING: "○",
                DownloadStatus.RESOLVING: "◐",
                DownloadStatus.DOWNLOADING: "↓",
                DownloadStatus.COMPLETE: "✓",
                DownloadStatus.FAILED: "✗",
            }.get(item.status, "?")

            status_color = {
                DownloadStatus.PENDING: "dim",
                DownloadStatus.RESOLVING: "yellow",
                DownloadStatus.DOWNLOADING: "cyan",
                DownloadStatus.COMPLETE: "green",
                DownloadStatus.FAILED: "red",
            }.get(item.status, "white")

            text = Text()
            text.append(f"{status_icon} ", style=status_color)
            text.append(f"{item.title}", style="bold")
            text.append(f" - {item.artist}", style="dim")

            if item.status == DownloadStatus.DOWNLOADING:
                text.append(
                    f" ({item.completed_tracks}/{item.total_tracks})", style="cyan"
                )

            list_view.append(ListItem(Static(text)))

        # Update current progress
        active = next(
            (i for i in queue if i.status == DownloadStatus.DOWNLOADING), None
        )
        progress_widget = self.query_one("#current-progress", Static)
        if active:
            progress_text = (
                f"Downloading: {active.current_track}\n"
                f"Track {active.completed_tracks + 1}/{active.total_tracks}"
            )
            progress_widget.update(progress_text)
        else:
            progress_widget.update("")


class LibraryBrowser(App):
    """Textual app for browsing and downloading music library."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2;
        grid-columns: 2fr 1fr;
    }

    #left-panel {
        height: 100%;
        border: solid $primary;
    }

    #right-panel {
        height: 100%;
        border: solid $secondary;
    }

    #album-table {
        height: 100%;
    }

    #queue-title {
        text-style: bold;
        padding: 1;
        background: $surface;
    }

    #queue-list {
        height: 1fr;
        min-height: 10;
    }

    #current-progress {
        height: auto;
        padding: 1;
        background: $surface-darken-1;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    .selected-count {
        color: $success;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("enter", "add_to_queue", "Add to Queue", show=True),
        Binding("d", "start_downloads", "Download", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("c", "clear_completed", "Clear Done", show=True),
        Binding("/", "focus_search", "Search", show=True),
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

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-panel"):
                yield AlbumTable(id="album-table")
                yield Static("", id="status-bar")
            with Vertical(id="right-panel"):
                yield DownloadQueueWidget(id="download-queue")
        yield Footer()

    async def on_mount(self) -> None:
        """Load albums when app starts."""
        self.title = f"Library Browser - {self.state.source.capitalize()}"
        await self.load_albums()

    async def load_albums(self) -> None:
        """Load albums from the library."""
        table = self.query_one("#album-table", AlbumTable)
        table.loading = True

        try:
            client = await self.main.get_logged_in_client(self.state.source)

            # Fetch albums
            pages = await client.get_user_favorites("album", limit=500)
            all_albums = []
            for page in pages:
                albums_data = page.get("albums", {})
                albums_items = albums_data.get("items", [])
                all_albums.extend(albums_items)

            # Filter if needed
            if not self.include_downloaded:
                filtered = []
                for album in all_albums:
                    album_id = str(album.get("id"))
                    if not self.main.database.album_downloaded(
                        self.state.source, album_id
                    ):
                        filtered.append(album)
                all_albums = filtered

            self.state.albums = all_albums

            # Populate table
            table.clear()
            for album in all_albums:
                title = album.get("title", "Unknown")[:38]
                artist_info = album.get("artist", {})
                artist = (
                    artist_info.get("name", "Unknown")[:28]
                    if isinstance(artist_info, dict)
                    else "Unknown"
                )
                year = str(album.get("release_date_original", "")[:4])

                # Format info
                hires = album.get("hires_streamable", False)
                format_str = "Hi-Res" if hires else "CD"

                table.add_row(" ", title, artist, year, format_str)

            self._update_status()

        except Exception as e:
            self.notify(f"Error loading albums: {e}", severity="error")
        finally:
            table.loading = False

    def _update_status(self) -> None:
        """Update the status bar."""
        table = self.query_one("#album-table", AlbumTable)
        status = self.query_one("#status-bar", Static)

        total = len(self.state.albums)
        selected = len(table.selected_rows)

        status_text = Text()
        status_text.append(f"{total} albums")
        if selected > 0:
            status_text.append(" | ", style="dim")
            status_text.append(f"{selected} selected", style="green bold")

        if self.state.is_downloading:
            status_text.append(" | ", style="dim")
            status_text.append("Downloading...", style="cyan")

        status.update(status_text)

    def on_album_table_selection_changed(
        self, message: AlbumTable.SelectionChanged
    ) -> None:
        """Handle selection changes."""
        self.selected_count = len(message.selected)
        self._update_status()

    def action_add_to_queue(self) -> None:
        """Add selected albums to download queue."""
        table = self.query_one("#album-table", AlbumTable)

        if not table.selected_rows:
            self.notify("No albums selected", severity="warning")
            return

        added = 0
        for row_idx in table.selected_rows:
            if row_idx < len(self.state.albums):
                album = self.state.albums[row_idx]
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

                item = DownloadItem(
                    album_id=album_id,
                    title=album.get("title", "Unknown"),
                    artist=artist,
                    source=self.state.source,
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
        pending = [
            item
            for item in self.state.download_queue
            if item.status == DownloadStatus.PENDING
        ]

        if not pending:
            self.notify("No pending downloads", severity="warning")
            return

        self.state.is_downloading = True
        self._update_status()
        self._run_downloads()

    @work(exclusive=True, thread=False)
    async def _run_downloads(self) -> None:
        """Background worker for downloads."""
        queue_widget = self.query_one("#download-queue", DownloadQueueWidget)

        for item in self.state.download_queue:
            if item.status != DownloadStatus.PENDING:
                continue

            try:
                # Update status to resolving
                item.status = DownloadStatus.RESOLVING
                queue_widget.update_queue(self.state.download_queue)

                # Add to main's pending list
                await self.main.add_by_id(item.source, "album", item.album_id)

                # Resolve
                await self.main.resolve()

                # Update status to downloading
                item.status = DownloadStatus.DOWNLOADING
                queue_widget.update_queue(self.state.download_queue)

                # Download
                await self.main.rip()

                # Mark complete
                item.status = DownloadStatus.COMPLETE
                queue_widget.update_queue(self.state.download_queue)

                # Clear main's media list for next album
                self.main.media.clear()

            except Exception as e:
                item.status = DownloadStatus.FAILED
                item.error = str(e)
                queue_widget.update_queue(self.state.download_queue)
                self.notify(f"Failed: {item.title}: {e}", severity="error")

        self.state.is_downloading = False
        self._update_status()

        # Count results
        completed = sum(
            1 for i in self.state.download_queue if i.status == DownloadStatus.COMPLETE
        )
        failed = sum(
            1 for i in self.state.download_queue if i.status == DownloadStatus.FAILED
        )

        if failed > 0:
            self.notify(f"Downloads complete: {completed} ok, {failed} failed")
        else:
            self.notify(
                f"Downloads complete: {completed} albums", severity="information"
            )

    def action_refresh(self) -> None:
        """Refresh the album list."""
        self.run_worker(self.load_albums())

    def action_clear_completed(self) -> None:
        """Clear completed downloads from queue."""
        self.state.download_queue = [
            item
            for item in self.state.download_queue
            if item.status not in (DownloadStatus.COMPLETE, DownloadStatus.FAILED)
        ]
        queue_widget = self.query_one("#download-queue", DownloadQueueWidget)
        queue_widget.update_queue(self.state.download_queue)
        self.notify("Cleared completed downloads")

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
