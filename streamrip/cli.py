"""The streamrip command line interface."""

import logging
import os
from getpass import getpass
from hashlib import md5

import click
import requests

from . import __version__
from .clients import TidalClient
from .config import Config
from .constants import CACHE_DIR, CONFIG_DIR, CONFIG_PATH, QOBUZ_FEATURED_KEYS
from .core import MusicDL


logging.basicConfig(level="WARNING")
logger = logging.getLogger("streamrip")

if not os.path.isdir(CONFIG_DIR):
    os.makedirs(CONFIG_DIR, exist_ok=True)
if not os.path.isdir(CACHE_DIR):
    os.makedirs(CONFIG_DIR, exist_ok=True)


@click.group(invoke_without_command=True)
@click.option(
    "-c", "--convert", metavar="CODEC", help="alac, mp3, flac, or ogg"
)
@click.option(
    "-u",
    "--urls",
    metavar="URLS",
    help="Url from Qobuz, Tidal, SoundCloud, or Deezer",
)
@click.option(
    "-q",
    "--quality",
    metavar="INT",
    help="0: < 320kbps, 1: 320 kbps, 2: 16 bit/44.1 kHz, 3: 24 bit/<=96 kHz, 4: 24 bit/<=192 kHz",
)
@click.option("-t", "--text", metavar="PATH")
@click.option("-nd", "--no-db", is_flag=True)
@click.option("--debug", is_flag=True)
@click.version_option(prog_name="streamrip")
@click.pass_context
def cli(ctx, **kwargs):
    """Streamrip: The all-in-one Qobuz, Tidal, SoundCloud, and Deezer music downloader.

    To get started, try:

        $ rip -u https://www.deezer.com/en/album/6612814

    For customization down to the details, see the config file:

        $ rip config --open

    """
    global config
    global core

    if kwargs["debug"]:
        logger.setLevel("DEBUG")
        logger.debug("Starting debug log")

    config = Config()

    if ctx.invoked_subcommand == "config":
        return

    if config.session["check_for_updates"]:
        r = requests.get("https://pypi.org/pypi/streamrip/json").json()
        newest = r["info"]["version"]
        if __version__ != newest:
            click.secho(
                "A new version of streamrip is available! "
                "Run `pip3 install streamrip --upgrade` to update.",
                fg="yellow",
            )
        else:
            click.secho("streamrip is up-to-date!", fg="green")

    if kwargs["no_db"]:
        config.session["database"]["enabled"] = False
    if kwargs["convert"]:
        config.session["conversion"]["enabled"] = True
        config.session["conversion"]["codec"] = kwargs["convert"]
    if kwargs["quality"] is not None:
        quality = int(kwargs["quality"])
        if quality not in range(5):
            click.secho("Invalid quality", fg="red")
            return

        config.session["qobuz"]["quality"] = quality
        config.session["tidal"]["quality"] = quality
        config.session["deezer"]["quality"] = quality

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
    filters.pop("urls")
    config.session["filters"] = filters
    logger.debug(f"downloading {kwargs['urls']} with filters {filters}")
    core.handle_urls(" ".join(kwargs["urls"]))
    core.download()


@cli.command()
@click.option(
    "-t", "--type", default="album", help="album, playlist, track, or artist"
)
@click.option(
    "-s",
    "--source",
    default="qobuz",
    help="qobuz, tidal, soundcloud, or deezer",
)
@click.argument("QUERY", nargs=-1)
@click.pass_context
def search(ctx, **kwargs):
    """Search and download media in interactive mode.

    The QUERY must be surrounded in quotes if it contains spaces. If your query
    contains single quotes, use double quotes, and vice versa.

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
    """Search for albums in Qobuz's featured lists.

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
@click.option(
    "-s",
    "--source",
    help="Qobuz, Tidal, Deezer, or SoundCloud. Default: Qobuz.",
)
@click.argument("URL")
@click.pass_context
def lastfm(ctx, source, url):
    """Search for tracks from a last.fm playlist on a given source.

    Examples:

        $ rip lastfm https://www.last.fm/user/nathan3895/playlists/12059037

        Download a playlist using Qobuz as the source

        $ rip lastfm -s tidal https://www.last.fm/user/nathan3895/playlists/12059037

        Download a playlist using Tidal as the source
    """
    if source is not None:
        config.session["lastfm"]["source"] = source

    core.handle_lastfm_urls(url)
    core.download()


@cli.command()
@click.option("-o", "--open", is_flag=True, help="Open the config file")
@click.option(
    "-d", "--directory", is_flag=True, help="Open the config directory"
)
@click.option("-q", "--qobuz", is_flag=True, help="Set Qobuz credentials")
@click.option("-t", "--tidal", is_flag=True, help="Re-login into Tidal")
@click.option("--reset", is_flag=True, help="RESET the config file")
@click.option(
    "--update",
    is_flag=True,
    help="Reset the config file, keeping the credentials",
)
@click.option("-p", "--path", is_flag=True, help="Show the config file's path")
@click.option(
    "-ov",
    "--open-vim",
    is_flag=True,
    help="Open the config file in the vim text editor.",
)
@click.pass_context
def config(ctx, **kwargs):
    """Manage the streamrip configuration file."""
    if kwargs["reset"]:
        config.reset()

    if kwargs["update"]:
        config.update()

    if kwargs["path"]:
        print(CONFIG_PATH)

    if kwargs["open"]:
        click.secho(f"Opening {CONFIG_PATH}", fg="green")
        click.launch(CONFIG_PATH)

    if kwargs["open_vim"]:
        os.system(f"vim '{CONFIG_PATH}'")

    if kwargs["directory"]:
        config_dir = os.path.dirname(CONFIG_PATH)
        click.secho(f"Opening {config_dir}", fg="green")
        click.launch(config_dir)

    if kwargs["qobuz"]:
        config.file["qobuz"]["email"] = input(
            click.style("Qobuz email: ", fg="blue")
        )

        click.secho("Qobuz password (will not show on screen):", fg="blue")
        config.file["qobuz"]["password"] = md5(
            getpass(prompt="").encode("utf-8")
        ).hexdigest()

        config.save()
        click.secho(
            "Qobuz credentials hashed and saved to config.", fg="green"
        )

    if kwargs["tidal"]:
        client = TidalClient()
        client.login()
        config.file["tidal"].update(client.get_tokens())
        config.save()
        click.secho("Credentials saved to config.", fg="green")


def none_chosen():
    """Print message if nothing was chosen."""
    click.secho("No items chosen, exiting.", fg="bright_red")


def main():
    """Run the main program."""
    cli(obj={})
