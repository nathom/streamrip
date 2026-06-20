import asyncio
import json
import logging
import platform
import time

import aiofiles

from .. import db
from ..client import Client, DeezerClient, QobuzClient, SoundcloudClient, TidalClient
from ..config import Config
from ..console import console
from ..media import (
    Media,
    Pending,
    PendingLastfmPlaylist,
    remove_artwork_tempdirs,
)
from ..media.media import DownloadStats
from ..metadata import SearchResults
from ..progress import clear_progress
from .parse_url import _pending_from_type, parse_url
from .prompter import get_prompter

logger = logging.getLogger("streamrip")

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]


class Main:
    """Provides all of the functionality called into by the CLI.

    * Logs in to Clients and prompts for credentials
    * Handles output logging
    * Handles downloading Media
    * Handles interactive search

    User input (urls) -> Main --> Download files & Output messages to terminal
    """

    def __init__(self, config: Config):
        # Data pipeline:
        # input URL -> (URL) -> (Pending) -> (Media) -> (Downloadable) -> audio file
        self.pending: list[Pending] = []
        self.media: list[Media] = []
        self.config = config
        self.clients: dict[str, Client] = {
            "qobuz": QobuzClient(config),
            "tidal": TidalClient(config),
            "deezer": DeezerClient(config),
            "soundcloud": SoundcloudClient(config),
        }

        self.database: db.Database

        c = self.config.session.database
        downloads_db: db.DatabaseInterface
        if c.downloads_enabled:
            downloads_db = db.Downloads(c.downloads_path)
        else:
            downloads_db = db.Dummy()

        failed_downloads_db: db.DatabaseInterface
        if c.failed_downloads_enabled:
            failed_downloads_db = db.Failed(c.failed_downloads_path)
        else:
            failed_downloads_db = db.Dummy()

        self.database = db.Database(downloads_db, failed_downloads_db)

    async def add(self, url: str):
        """Add url as a pending item.

        Do not `asyncio.gather` calls to this! Use `add_all` for concurrency.
        """
        parsed = parse_url(url)
        if parsed is None:
            raise Exception(f"Unable to parse url {url}")

        client = await self.get_logged_in_client(parsed.source)
        self.pending.append(
            await parsed.into_pending(client, self.config, self.database),
        )
        logger.debug("Added url=%s", url)

    async def add_by_id(self, source: str, media_type: str, id: str):
        client = await self.get_logged_in_client(source)
        self._add_by_id_client(client, media_type, id)

    async def add_all_by_id(self, info: list[tuple[str, str, str]]):
        sources = set(s for s, _, _ in info)
        clients = {s: await self.get_logged_in_client(s) for s in sources}
        for source, media_type, id in info:
            self._add_by_id_client(clients[source], media_type, id)

    def _add_by_id_client(self, client: Client, media_type: str, id: str):
        self.pending.append(
            _pending_from_type(media_type, id, client, self.config, self.database)
        )

    async def add_all(self, urls: list[str]):
        """Add multiple urls concurrently as pending items."""
        parsed = []
        for i, url in enumerate(urls):
            p = parse_url(url)
            if p is None:
                console.print(f"[red]Found invalid url [cyan]{url}[/cyan], skipping.")
            else:
                parsed.append(p)

        unique_sources = {p.source for p in parsed}
        logged_in = await asyncio.gather(
            *[self.get_logged_in_client(s) for s in unique_sources]
        )
        clients = dict(zip(unique_sources, logged_in))

        pendings = await asyncio.gather(
            *[p.into_pending(clients[p.source], self.config, self.database) for p in parsed]
        )
        self.pending.extend(pendings)

    async def get_logged_in_client(self, source: str):
        """Return a functioning client instance for `source`."""
        client = self.clients.get(source)
        if client is None:
            raise Exception(
                f"No client named {source} available. Only have {self.clients.keys()}",
            )
        if client.logged_in:
            return client
        async with client._login_lock:
            if not client.logged_in:
                prompter = get_prompter(client, self.config)
                if not prompter.has_creds():
                    # Get credentials from user and log into client
                    await prompter.prompt_and_login()
                    prompter.save()
                else:
                    with console.status(f"[cyan]Logging into {source}", spinner="dots"):
                        # Log into client using credentials from config
                        await client.login()

        if not client.logged_in:
            raise RuntimeError(f"Failed to log into {source}")
        return client

    async def resolve(self):
        """Resolve all currently pending items."""
        with console.status("Resolving URLs...", spinner="dots"):
            coros = [p.resolve() for p in self.pending]
            new_media: list[Media] = [
                m for m in await asyncio.gather(*coros) if m is not None
            ]

        self.media.extend(new_media)
        self.pending.clear()

    async def rip(self):
        """Download all resolved items and print an end-of-session summary."""
        stats = DownloadStats()
        t0 = time.monotonic()

        results = await asyncio.gather(
            *[item.rip(stats) for item in self.media], return_exceptions=True
        )

        elapsed = time.monotonic() - t0

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error processing media item: {result}")

        console.print(self._format_summary(stats, elapsed))

    @staticmethod
    def _format_summary(stats: DownloadStats, elapsed: float) -> str:
        """Build a Rich-markup summary line for the end of a rip session.

        Args:
            stats: Accumulated download metrics.
            elapsed: Total wall-clock time in seconds.

        Returns:
            A Rich markup string ready to pass to console.print().
        """
        n = stats.bytes_downloaded
        if n >= 1_000_000_000:
            size_str = f"{n / 1_000_000_000:.2f} GB"
        elif n >= 1_000_000:
            size_str = f"{n / 1_000_000:.1f} MB"
        else:
            size_str = f"{n / 1_000:.0f} KB"

        s = int(elapsed)
        time_str = f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{s}s"

        parts = [f"[green]✔ {stats.tracks_downloaded} tracks[/green]"]
        if stats.tracks_failed:
            parts.append(f"[red]✘ {stats.tracks_failed} errors[/red]")
        parts += [f"[blue]↓ {size_str}[/blue]", f"[yellow]⏱ {time_str}[/yellow]"]
        return "  ".join(parts)

    async def search_interactive(self, source: str, media_type: str, query: str):
        client = await self.get_logged_in_client(source)

        with console.status(f"[bold]Searching {source}", spinner="dots"):
            pages = await client.search(media_type, query, limit=100)
            if len(pages) == 0:
                console.print(f"[red]No search results found for query {query}")
                return
            search_results = SearchResults.from_pages(source, media_type, pages)

        if platform.system() == "Windows":  # simple term menu not supported for windows
            from pick import pick

            choices = pick(
                search_results.results,
                title=(
                    f"{source.capitalize()} {media_type} search.\n"
                    "Press SPACE to select, RETURN to download, CTRL-C to exit."
                ),
                multiselect=True,
                min_selection_count=1,
            )
            assert isinstance(choices, list)

            await self.add_all_by_id(
                [(source, media_type, item.id) for item, _ in choices],
            )

        else:
            from simple_term_menu import TerminalMenu

            menu = TerminalMenu(
                search_results.summaries(),
                preview_command=search_results.preview,
                preview_size=0.5,
                title=(
                    f"Results for {media_type} '{query}' from {source.capitalize()}\n"
                    "SPACE - select, ENTER - download, ESC - exit"
                ),
                cycle_cursor=True,
                clear_screen=True,
                multi_select=True,
            )
            chosen_ind = menu.show()
            if chosen_ind is None:
                console.print("[yellow]No items chosen. Exiting.")
            else:
                choices = search_results.get_choices(chosen_ind)
                await self.add_all_by_id(
                    [(source, item.media_type(), item.id) for item in choices],
                )

    async def search_take_first(self, source: str, media_type: str, query: str):
        client = await self.get_logged_in_client(source)
        with console.status(f"[bold]Searching {source}", spinner="dots"):
            pages = await client.search(media_type, query, limit=1)

        if len(pages) == 0:
            console.print(f"[red]No search results found for query {query}")
            return

        search_results = SearchResults.from_pages(source, media_type, pages)
        if not search_results.results:
            console.print(f"[red]No search results found for query {query}")
            return
        first = search_results.results[0]
        await self.add_by_id(source, first.media_type(), first.id)

    async def search_output_file(
        self, source: str, media_type: str, query: str, filepath: str, limit: int
    ):
        client = await self.get_logged_in_client(source)
        with console.status(f"[bold]Searching {source}", spinner="dots"):
            pages = await client.search(media_type, query, limit=limit)

        if len(pages) == 0:
            console.print(f"[red]No search results found for query {query}")
            return

        search_results = SearchResults.from_pages(source, media_type, pages)
        file_contents = json.dumps(search_results.as_list(source), indent=4)
        async with aiofiles.open(filepath, "w") as f:
            await f.write(file_contents)

        console.print(
            f"Wrote [purple]{len(search_results.results)}[/purple] results to [cyan]{filepath} as JSON!"
        )

    async def resolve_lastfm(self, playlist_url: str):
        """Resolve a last.fm playlist."""
        c = self.config.session.lastfm
        client = await self.get_logged_in_client(c.source)

        if len(c.fallback_source) > 0:
            fallback_client = await self.get_logged_in_client(c.fallback_source)
        else:
            fallback_client = None

        pending_playlist = PendingLastfmPlaylist(
            playlist_url,
            client,
            fallback_client,
            self.config,
            self.database,
        )
        playlist = await pending_playlist.resolve()

        if playlist is not None:
            self.media.append(playlist)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        # Ensure all client sessions are closed
        for client in self.clients.values():
            if hasattr(client, "session"):
                await client.session.close()

        # close global progress bar manager
        clear_progress()
        # We remove artwork tempdirs here because multiple singles
        # may be able to share downloaded artwork in the same `rip` session
        # We don't know that a cover will not be used again until end of execution
        remove_artwork_tempdirs()
