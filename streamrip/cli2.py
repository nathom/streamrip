import asyncio
import logging
import os
import shutil
import subprocess
from functools import wraps

import click
from click import secho
from click_help_colors import HelpColorsGroup  # type: ignore
from rich.logging import RichHandler
from rich.prompt import Confirm
from rich.traceback import install

from .config import Config, set_user_defaults
from .console import console
from .main import Main
from .user_paths import BLANK_CONFIG_PATH, CONFIG_PATH


def echo_i(msg, **kwargs):
    secho(msg, fg="green", **kwargs)


def echo_w(msg, **kwargs):
    secho(msg, fg="yellow", **kwargs)


def echo_e(msg, **kwargs):
    secho(msg, fg="yellow", **kwargs)


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
@click.version_option(version="2.0")
@click.option(
    "-c", "--config-path", default=CONFIG_PATH, help="Path to the configuration file"
)
@click.option(
    "-v", "--verbose", help="Enable verbose output (debug mode)", is_flag=True
)
@click.pass_context
def rip(ctx, config_path, verbose):
    """
    Streamrip: the all in one music downloader.
    """
    global logger
    FORMAT = "%(message)s"
    logging.basicConfig(
        level="WARNING", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
    )
    logger = logging.getLogger("streamrip")
    if verbose:
        install(
            console=console,
            suppress=[click],
            show_locals=True,
            locals_hide_sunder=False,
        )
        logger.setLevel(logging.DEBUG)
        logger.debug("Showing all debug logs")
    else:
        install(console=console, suppress=[click, asyncio], max_frames=1)
        logger.setLevel(logging.WARNING)

    ctx.ensure_object(dict)
    if not os.path.isfile(config_path):
        echo_i(f"No file found at {config_path}, creating default config.")
        shutil.copy(BLANK_CONFIG_PATH, config_path)
        set_user_defaults(config_path)

    ctx.obj["config_path"] = config_path
    ctx.obj["verbose"] = verbose


@rip.command()
@click.argument("urls", nargs=-1, required=True)
@click.pass_context
@coro
async def url(ctx, urls):
    """Download content from URLs.

    Example usage:

        rip url TODO: find url
    """
    config_path = ctx.obj["config_path"]
    with Config(config_path) as cfg:
        main = Main(cfg)
        for u in urls:
            await main.add(u)
        await main.resolve()
        await main.rip()


@rip.command()
@click.argument("path", required=True)
@click.pass_context
@coro
async def file(ctx, path):
    """Download content from URLs in a file seperated by newlines.

    Example usage:

        rip file urls.txt
    """
    config_path = ctx.obj["config_path"]
    with Config(config_path) as cfg:
        main = Main(cfg)
        with open(path) as f:
            for url in f:
                await main.add(url)
        await main.resolve()
        await main.rip()


@rip.group()
def config():
    """Manage configuration files."""
    pass


@config.command("open")
@click.option("-v", "--vim", help="Open in (Neo)Vim", is_flag=True)
@click.pass_context
def config_open(ctx, vim):
    """Open the config file in a text editor."""
    config_path = ctx.obj["config_path"]
    echo_i(f"Opening file at {config_path}")
    if vim:
        if shutil.which("nvim") is not None:
            subprocess.run(["nvim", config_path])
        else:
            subprocess.run(["vim", config_path])
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
            f"Are you sure you want to reset the config file at {config_path}?"
        ):
            console.print("[green]Reset aborted")
            return

    shutil.copy(BLANK_CONFIG_PATH, config_path)
    set_user_defaults(config_path)
    echo_i(f"Reset the config file at {config_path}!")


@rip.command()
@click.argument("query", required=True)
@click.argument("source", required=True)
@coro
async def search(query, source):
    """
    Search for content using a specific source.
    """
    echo_i(f'Searching for "{query}" in source: {source}')


@rip.command()
@click.argument("url", required=True)
def lastfm(url):
    pass


if __name__ == "__main__":
    rip()
