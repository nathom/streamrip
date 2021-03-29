import logging
import os
from getpass import getpass

import click

from .config import Config
from .constants import CACHE_DIR, CONFIG_DIR, CONFIG_PATH, QOBUZ_FEATURED_KEYS
from .core import MusicDL
from .utils import init_log

logger = logging.getLogger(__name__)
config = Config(CONFIG_PATH)

if not os.path.isdir(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)
if not os.path.isdir(CACHE_DIR):
    os.makedirs(CONFIG_DIR)


@click.group(invoke_without_command=True)
@click.option("-c", "--convert", metavar="CODEC")
@click.option("-u", "--urls", metavar="URLS")
@click.option("-t", "--text", metavar="PATH")
@click.option("-nd", "--no-db", is_flag=True)
@click.option("--debug", is_flag=True)
@click.pass_context
def cli(ctx, **kwargs):
    """"""
    global config
    global core

    if kwargs["debug"]:
        init_log()

    config = Config()

    if kwargs["no_db"]:
        config.session["database"]["enabled"] = False
    if kwargs["convert"]:
        config.session["conversion"]["enabled"] = True
        config.session["conversion"]["codec"] = kwargs["convert"]

    core = MusicDL(config)

    if kwargs["urls"]:
        logger.debug(f"handling {kwargs['urls']}")
        core.handle_urls(kwargs["urls"])

    if kwargs["text"] is not None:
        if os.path.isfile(kwargs["text"]):
            logger.debug(f"Handling {kwargs['text']}")
            core.handle_txt(kwargs["text"])
        else:
            click.secho(f"Text file {kwargs['text']} does not exist.")

    if ctx.invoked_subcommand is None:
        core.download()


@cli.command(name="filter")
@click.option("--repeats", is_flag=True)
@click.option("--non-albums", is_flag=True)
@click.option("--extras", is_flag=True)
@click.option("--features", is_flag=True)
@click.option("--non-studio-albums", is_flag=True)
@click.option("--non-remasters", is_flag=True)
@click.argument("URLS", nargs=-1)
@click.pass_context
def filter_discography(ctx, **kwargs):
    """Filter an artists discography (qobuz only).

    The Qobuz API returns a massive number of tangentially related
    albums when requesting an artist's discography. This command
    can filter out most of the junk.

    For basic filtering, use the `--repeats` and `--features` filters.
    """

    filters = kwargs.copy()
    filters.remove("urls")
    config.session["filters"] = filters
    logger.debug(f"downloading {kwargs['urls']} with filters {filters}")
    core.handle_urls(" ".join(kwargs["urls"]))
    core.download()


@cli.command()
@click.option("-t", "--type", default="album", help="album, playlist, track, or artist")
@click.option("-s", "--source", default="qobuz", help="qobuz, tidal, or deezer")
@click.argument("QUERY", nargs=-1)
@click.pass_context
def search(ctx, **kwargs):
    """Search and download media in interactive mode.

    Example usage:

        $ rip search 'fleetwood mac rumours'

        Search for a Qobuz album that matches 'fleetwood mac rumours'

        $ rip search -t track 'back in the ussr'

        Search for a Qobuz track with the given query

        $ rip search -s tidal 'jay z 444'

        Search for a Tidal album that matches 'jay z 444'

    """
    if isinstance(kwargs["query"], (list, tuple)):
        query = " ".join(kwargs["query"])
    elif isinstance(kwargs["query"], str):
        query = kwargs["query"]
    else:
        raise ValueError("Invalid query type" + type(kwargs["query"]))

    if core.interactive_search(query, kwargs["source"], kwargs["type"]):
        core.download()
    else:
        click.secho("No items chosen, exiting.", fg="bright_red")


@cli.command()
@click.option("-l", "--list", default="ideal-discography")
@click.pass_context
def discover(ctx, **kwargs):
    """Searches for albums in Qobuz's featured lists.

    Avaiable options for `--list`:

        * most-streamed

        * recent-releases

        * best-sellers

        * press-awards

        * ideal-discography

        * editor-picks

        * most-featured

        * qobuzissims

        * new-releases

        * new-releases-full

        * harmonia-mundi

        * universal-classic

        * universal-jazz

        * universal-jeunesse

        * universal-chanson
    """
    assert (
        kwargs["list"] in QOBUZ_FEATURED_KEYS
    ), f"Invalid featured key {kwargs['list']}"

    if core.interactive_search(kwargs["list"], "qobuz", "featured"):
        core.download()
    else:
        none_chosen()


@cli.command()
@click.option("-o", "--open", is_flag=True, help="Open the config file")
@click.option("-q", "--qobuz", is_flag=True, help="Set Qobuz credentials")
@click.option("--reset", is_flag=True, help="RESET the config file")
@click.pass_context
def config(ctx, **kwargs):
    """Manage the streamrip configuration."""
    if kwargs["reset"]:
        config.reset()

    if kwargs["open"]:
        click.launch(CONFIG_PATH)

    if kwargs["qobuz"]:
        config.file["qobuz"]["email"] = input("Qobuz email: ")
        config.file["qobuz"]["password"] = getpass()
        config.save()


def none_chosen():
    click.secho("No items chosen, exiting.", fg="bright_red")


def parse_urls(arg: str):
    if os.path.isfile(arg):
        return arg, "txt"
    if "http" in arg:
        return arg, "urls"

    raise ValueError(f"Invalid argument {arg}")


def main():
    cli(obj={})
