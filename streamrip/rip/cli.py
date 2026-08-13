import asyncio
import json
import logging
import os
import shutil
import subprocess
from functools import wraps
from typing import Any

import aiofiles
import aiohttp
import click
from click_help_colors import HelpColorsGroup  # type: ignore
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.prompt import Confirm
from rich.traceback import install

from .. import __version__, db
from ..config import DEFAULT_CONFIG_PATH, Config, OutdatedConfigError, set_user_defaults
from ..console import console
from ..utils.ssl_utils import get_aiohttp_connector_kwargs
from .main import Main


def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@click.group(
    cls=HelpColorsGroup,
    help_headers_color="yellow",
    help_options_color="green",
)
@click.version_option(version=__version__)
@click.option(
    "--config-path",
    default=DEFAULT_CONFIG_PATH,
    help="Path to the configuration file",
    type=click.Path(readable=True, writable=True),
)
@click.option(
    "-f",
    "--folder",
    help="The folder to download items into.",
    type=click.Path(file_okay=False, dir_okay=True),
)
@click.option(
    "-ndb",
    "--no-db",
    help="Download items even if they have been logged in the database",
    default=False,
    is_flag=True,
)
@click.option(
    "-q",
    "--quality",
    help="The maximum quality allowed to download",
    type=click.IntRange(min=0, max=4),
)
@click.option(
    "-c",
    "--codec",
    help="Convert the downloaded files to an audio codec (ALAC, FLAC, MP3, AAC, or OGG)",
)
@click.option(
    "--no-progress",
    help="Do not show progress bars",
    is_flag=True,
    default=False,
)
@click.option(
    "--no-ssl-verify",
    help="Disable SSL certificate verification (use if you encounter SSL errors)",
    is_flag=True,
    default=False,
)
@click.option(
    "-v",
    "--verbose",
    help="Enable verbose output (debug mode)",
    is_flag=True,
)
@click.pass_context
def rip(
    ctx, config_path, folder, no_db, quality, codec, no_progress, no_ssl_verify, verbose
):
    """Streamrip: the all in one music downloader."""
    global logger
    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler()],
    )
    logger = logging.getLogger("streamrip")
    if verbose:
        install(
            console=console,
            suppress=[
                click,
            ],
            show_locals=True,
            locals_hide_sunder=False,
        )
        logger.setLevel(logging.DEBUG)
        logger.debug("Showing all debug logs")
    else:
        install(console=console, suppress=[click, asyncio], max_frames=1)
        logger.setLevel(logging.INFO)

    if not os.path.isfile(config_path):
        console.print(
            f"No file found at [bold cyan]{config_path}[/bold cyan], creating default config.",
        )
        set_user_defaults(config_path)

    # pass to subcommands
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path

    try:
        c = Config(config_path)
    except OutdatedConfigError as e:
        console.print(e)
        console.print("Auto-updating config file...")
        Config.update_file(config_path)
        c = Config(config_path)
    except Exception as e:
        console.print(
            f"Error loading config from [bold cyan]{config_path}[/bold cyan]: {e}\n"
            "Try running [bold]rip config reset[/bold]",
        )
        ctx.obj["config"] = None
        return

    # set session config values to command line args
    if no_db:
        c.session.database.downloads_enabled = False
    if folder is not None:
        c.session.downloads.folder = folder

    if quality is not None:
        c.session.qobuz.quality = quality
        c.session.tidal.quality = quality
        c.session.deezer.quality = quality
        c.session.soundcloud.quality = quality

    if codec is not None:
        c.session.conversion.enabled = True
        assert codec.upper() in ("ALAC", "FLAC", "OGG", "MP3", "AAC")
        c.session.conversion.codec = codec.upper()

    if no_progress:
        c.session.cli.progress_bars = False

    if no_ssl_verify:
        c.session.downloads.verify_ssl = False

    ctx.obj["config"] = c


@rip.command()
@click.argument("urls", nargs=-1, required=True)
@click.pass_context
@coro
async def url(ctx, urls):
    """Download content from URLs."""
    if ctx.obj["config"] is None:
        return

    try:
        with ctx.obj["config"] as cfg:
            cfg: Config
            updates = cfg.session.misc.check_for_updates
            if updates:
                # Run in background
                version_coro = asyncio.create_task(
                    latest_streamrip_version(
                        verify_ssl=cfg.session.downloads.verify_ssl
                    )
                )
            else:
                version_coro = None

            async with Main(cfg) as main:
                await main.add_all(urls)
                await main.resolve()
                await main.rip()

            if version_coro is not None:
                latest_version, notes = await version_coro
                if latest_version != __version__:
                    console.print(
                        f"\n[green]A new version of streamrip [cyan]v{latest_version}[/cyan]"
                        " is available! Run [white][bold]pip3 install streamrip --upgrade[/bold][/white]"
                        " to update.[/green]\n"
                    )

                    console.print(Markdown(notes))

    except aiohttp.ClientConnectorCertificateError as e:
        from ..utils.ssl_utils import print_ssl_error_help

        console.print(f"[red]SSL Certificate verification error: {e}[/red]")
        print_ssl_error_help()


@rip.command()
@click.argument(
    "path",
    required=True,
    type=click.Path(exists=True, readable=True, file_okay=True, dir_okay=False),
)
@click.pass_context
@coro
async def file(ctx, path):
    """Download content from URLs in a file.

    Example usage:

        rip file urls.txt
    """
    try:
        with ctx.obj["config"] as cfg:
            async with Main(cfg) as main:
                async with aiofiles.open(path, "r") as f:
                    content = await f.read()
                    try:
                        items: Any = json.loads(content)
                        loaded = True
                    except json.JSONDecodeError:
                        items = content.split()
                        loaded = False
                if loaded:
                    console.print(
                        f"Detected json file. Loading [yellow]{len(items)}[/yellow] items"
                    )
                    await main.add_all_by_id(
                        [(i["source"], i["media_type"], i["id"]) for i in items]
                    )
                else:
                    s = set(items)
                    if len(s) < len(items):
                        console.print(
                            f"Found [orange]{len(items)-len(s)}[/orange] repeated URLs!"
                        )
                        items = list(s)
                    console.print(
                        f"Detected list of urls. Loading [yellow]{len(items)}[/yellow] items"
                    )
                    await main.add_all(items)

                await main.resolve()
                await main.rip()
    except aiohttp.ClientConnectorCertificateError as e:
        from ..utils.ssl_utils import print_ssl_error_help

        console.print(f"[red]SSL Certificate verification error: {e}[/red]")
        print_ssl_error_help()


@rip.group()
def config():
    """Manage configuration files."""


@config.command("open")
@click.option("-v", "--vim", help="Open in (Neo)Vim", is_flag=True)
@click.pass_context
def config_open(ctx, vim):
    """Open the config file in a text editor."""
    config_path = ctx.obj["config_path"]

    console.print(f"Opening file at [bold cyan]{config_path}")
    if vim:
        if shutil.which("nvim") is not None:
            subprocess.run(["nvim", config_path])
        elif shutil.which("vim") is not None:
            subprocess.run(["vim", config_path])
        else:
            logger.error("Could not find nvim or vim. Using default launcher.")
            click.launch(config_path)
    else:
        click.launch(config_path)


@config.command("reset")
@click.option("-y", "--yes", help="Don't ask for confirmation.", is_flag=True)
@click.pass_context
def config_reset(ctx, yes):
    """Reset the config file."""
    config_path = ctx.obj["config_path"]
    if not yes:
        if not Confirm.ask(
            f"Are you sure you want to reset the config file at {config_path}?",
        ):
            console.print("[green]Reset aborted")
            return

    set_user_defaults(config_path)
    console.print(f"Reset the config file at [bold cyan]{config_path}!")


@config.command("path")
@click.pass_context
def config_path(ctx):
    """Display the path of the config file."""
    config_path = ctx.obj["config_path"]
    console.print(f"Config path: [bold cyan]'{config_path}'")


@rip.group()
def database():
    """View and modify the downloads and failed downloads databases."""


@database.command("browse")
@click.argument("table")
@click.pass_context
def database_browse(ctx, table):
    """Browse the contents of a table.

    Available tables:

        * Downloads

        * Failed
    """
    from rich.table import Table

    cfg: Config = ctx.obj["config"]

    if table.lower() == "downloads":
        downloads = db.Downloads(cfg.session.database.downloads_path)
        t = Table(title="Downloads database")
        t.add_column("Row")
        t.add_column("ID")
        for i, row in enumerate(downloads.all()):
            t.add_row(f"{i:02}", *row)
        console.print(t)

    elif table.lower() == "failed":
        failed = db.Failed(cfg.session.database.failed_downloads_path)
        t = Table(title="Failed downloads database")
        t.add_column("Source")
        t.add_column("Media Type")
        t.add_column("ID")
        for i, row in enumerate(failed.all()):
            t.add_row(f"{i:02}", *row)
        console.print(t)

    else:
        console.print(
            f"[red]Invalid database[/red] [bold]{table}[/bold]. [red]Choose[/red] [bold]downloads "
            "[red]or[/red] failed[/bold].",
        )


@rip.command()
@click.option("-y", "--yes", help="Don't ask for confirmation.", is_flag=True)
@click.option(
    "--flat",
    help="Put repaired tracks straight in the download folder instead of "
    "their album folder.",
    is_flag=True,
)
@click.pass_context
@coro
async def repair(ctx, yes, flat):
    """Retry downloads that previously failed.

    Reads the failed downloads database, retries each item, and clears it
    from the failed database on success. Items that fail again stay logged
    so they can be retried later.

    Failed tracks are retried individually, but are placed in their album's
    folder so they rejoin the album they were originally missing from. Pass
    --flat to put them in the download folder instead.
    """
    if ctx.obj["config"] is None:
        return

    with ctx.obj["config"] as cfg:
        cfg: Config
        # A repaired track is nearly always a track missing from an album that
        # was otherwise downloaded, so it needs to land in that album's folder
        # rather than loose in the download root. This only touches the
        # in-memory session copy, so config.toml is left alone.
        if not flat:
            cfg.session.filepaths.add_singles_to_folder = True
        failed_db = db.Failed(cfg.session.database.failed_downloads_path)
        downloads_db = db.Downloads(cfg.session.database.downloads_path)
        failed_items = failed_db.all()

        if not failed_items:
            console.print("[green]No failed downloads to repair!")
            return

        console.print(
            f"Found [yellow]{len(failed_items)}[/yellow] failed download(s)."
        )
        if not yes and not Confirm.ask("Retry them now?"):
            console.print("[green]Repair aborted")
            return

        # A failed item should never also be logged as downloaded, but older
        # versions of streamrip could mark one downloaded even after it
        # failed. Clear that stale state so the retry below isn't skipped.
        for _source, _media_type, item_id in failed_items:
            downloads_db.remove(id=item_id)

        async with Main(cfg) as main:
            await main.add_all_by_id(failed_items)
            await main.resolve()
            await main.rip()

        # Nothing in the download pipeline removes rows from the failed db, so
        # success can't be detected by diffing it. Instead rely on the
        # invariant this patch establishes: set_downloaded() is only reached
        # via postprocess(), which a failed download never gets to. So an item
        # present in the downloads db now is one that just succeeded.
        repaired = [
            item_id
            for _, _, item_id in failed_items
            if downloads_db.contains(id=item_id)
        ]
        for item_id in repaired:
            failed_db.remove(id=item_id)

        console.print(
            f"[green]Repaired {len(repaired)}/{len(failed_items)} item(s).[/green]"
        )
        if len(repaired) < len(failed_items):
            console.print(
                f"[yellow]{len(failed_items) - len(repaired)} item(s) failed again "
                "and are still logged. Run [bold]rip repair[/bold] to try again."
            )


@rip.command()
@click.option(
    "-f",
    "--first",
    help="Automatically download the first search result without showing the menu.",
    is_flag=True,
)
@click.option(
    "-o",
    "--output-file",
    help="Write search results to a file instead of showing interactive menu.",
    type=click.Path(writable=True),
)
@click.option(
    "-n",
    "--num-results",
    help="Maximum number of search results to show",
    default=100,
    type=click.IntRange(min=1),
)
@click.argument("source", required=True)
@click.argument("media-type", required=True)
@click.argument("query", required=True)
@click.pass_context
@coro
async def search(ctx, first, output_file, num_results, source, media_type, query):
    """Search for content using a specific source.

    Example:

        rip search qobuz album 'rumours'
    """
    if first and output_file:
        console.print("Cannot choose --first and --output-file!")
        return
    with ctx.obj["config"] as cfg:
        async with Main(cfg) as main:
            if first:
                await main.search_take_first(source, media_type, query)
            elif output_file:
                await main.search_output_file(
                    source, media_type, query, output_file, num_results
                )
            else:
                await main.search_interactive(source, media_type, query)
            await main.resolve()
            await main.rip()


@rip.command()
@click.option("-s", "--source", help="The source to search tracks on.")
@click.option(
    "-fs",
    "--fallback-source",
    help="The source to search tracks on if no results were found with the main source.",
)
@click.argument("url", required=True)
@click.pass_context
@coro
async def lastfm(ctx, source, fallback_source, url):
    """Download tracks from a last.fm playlist."""
    config = ctx.obj["config"]
    if source is not None:
        config.session.lastfm.source = source
    if fallback_source is not None:
        config.session.lastfm.fallback_source = fallback_source
    with config as cfg:
        async with Main(cfg) as main:
            await main.resolve_lastfm(url)
            await main.rip()


@rip.command()
@click.argument("source")
@click.argument("media-type")
@click.argument("id")
@click.pass_context
@coro
async def id(ctx, source, media_type, id):
    """Download an item by ID."""
    with ctx.obj["config"] as cfg:
        async with Main(cfg) as main:
            await main.add_by_id(source, media_type, id)
            await main.resolve()
            await main.rip()


async def latest_streamrip_version(verify_ssl: bool = True) -> tuple[str, str | None]:
    """Get the latest streamrip version from PyPI and release notes from GitHub.

    Args:
        verify_ssl: Whether to verify SSL certificates

    Returns:
        A tuple of (version, release_notes)
    """
    # Create connector with appropriate SSL settings
    connector_kwargs = get_aiohttp_connector_kwargs(verify_ssl=verify_ssl)
    connector = aiohttp.TCPConnector(**connector_kwargs)

    async with aiohttp.ClientSession(connector=connector) as s:
        async with s.get("https://pypi.org/pypi/streamrip/json") as resp:
            data = await resp.json()
        version = data["info"]["version"]

        if version == __version__:
            return version, None

        async with s.get(
            "https://api.github.com/repos/nathom/streamrip/releases/latest"
        ) as resp:
            json = await resp.json()
        notes = json["body"]
    return version, notes


if __name__ == "__main__":
    rip()
