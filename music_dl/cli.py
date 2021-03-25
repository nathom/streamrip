import logging
import os

import click

from .config import Config
from .constants import CACHE_DIR, CONFIG_DIR, CONFIG_PATH
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
@click.option("-nd", "--no-db", is_flag=True)
@click.option("--debug", is_flag=True)
@click.option("--reset-config", is_flag=True)
@click.pass_context
def cli(ctx, **kwargs):
    """
    Examples:

        $ rip {url} --convert alac

        Download the url and convert to alac

        $ rip {artist_url} -c alac filter --repeats --non-albums

        Download a discography, filtering repeats and non-albums

        $ rip interactive --search

        Start an interactive search session

        $ rip interactive --discover

        Start an interactive discover session

        $ rip config --open

        Open config file

        $ rip config --qobuz

        Set qobuz credentials

    """
    global config
    global core

    if kwargs["debug"]:
        init_log()

    config = Config()
    if kwargs["reset_config"]:
        config.reset()
        return

    if kwargs["no_db"]:
        config.session["database"]["enabled"] = False
    if kwargs["convert"]:
        config.session["conversion"]["enabled"] = True
        config.session["conversion"]["codec"] = kwargs["convert"]

    core = MusicDL(config)

    if kwargs["urls"]:
        logger.debug(f"handling {kwargs['urls']}")
        core.handle_urls(kwargs["urls"])

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
    """ONLY AVAILABLE FOR QOBUZ

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
@click.option("-t", "--type", default="album")
@click.option("-s", "--source", default="qobuz")
@click.option("-d", "--discover", is_flag=True)
@click.argument("QUERY", nargs=-1)
@click.pass_context
def interactive(ctx, **kwargs):
    """Interactive search for a query. This will display a menu
    from which you can choose an item to download.

    If the source is Qobuz, you can use the `--discover` option with
    one of the following queries to fetch and interactively download
    the featured albums.

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

    logger.debug(f"starting interactive mode for type {kwargs['type']}")
    if kwargs["discover"]:
        if kwargs["query"] == ():
            kwargs["query"] = ["ideal-discography"]
        kwargs["type"] = "featured"

    query = " ".join(kwargs["query"])

    if core.interactive_search(query, kwargs["source"], kwargs["type"]):
        core.download()
    else:
        click.secho("No items chosen, exiting.", fg="bright_red")


def parse_urls(arg: str):
    if os.path.isfile(arg):
        return arg, "txt"
    if "http" in arg:
        return arg, "urls"

    raise ValueError(f"Invalid argument {arg}")


def main():
    cli.add_command(filter_discography)
    cli.add_command(interactive)
    cli(obj={})


if __name__ == "__main__":
    main()
