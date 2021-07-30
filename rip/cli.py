"""The streamrip command line interface."""
import logging

import click

from streamrip import __version__

logging.basicConfig(level="WARNING")
logger = logging.getLogger("streamrip")


class SkipArg(Group):
    def parse_args(self, ctx, args):
        if len(args) == 0:
            echo(self.get_help(ctx))
            exit()

        if args[0] in self.commands:
            print('command found')
            args.insert(0, "")
        # if args[0] in self.commands:
        #     if len(args) == 1 or args[1] not in self.commands:
        #         # This condition needs updating for multiple positional arguments
        #         args.insert(0, "")
        super(SkipArg, self).parse_args(ctx, args)


# @option(
#     "-u",
#     "--urls",
#     metavar="URLS",
#     help="Url from Qobuz, Tidal, SoundCloud, or Deezer",
#     multiple=True,
# )
@group(cls=SkipArg, invoke_without_command=True)
@option("-c", "--convert", metavar="CODEC", help="alac, mp3, flac, or ogg")
@option(
    "-q",
    "--quality",
    metavar="INT",
    help="0: < 320kbps, 1: 320 kbps, 2: 16 bit/44.1 kHz, 3: 24 bit/<=96 kHz, 4: 24 bit/<=192 kHz",
)
@option("-t", "--text", metavar="PATH", help="Download urls from a text file.")
@option("-nd", "--no-db", is_flag=True, help="Ignore the database.")
@option("--debug", is_flag=True, help="Show debugging logs.")
@argument("URLS", nargs=1)
@version_option(prog_name="rip", version=__version__)
@pass_context
def cli(ctx, **kwargs):
    """Streamrip: The all-in-one Qobuz, Tidal, SoundCloud, and Deezer music
    downloader.

    To get started, try:

        $ rip -u https://www.deezer.com/en/album/6612814

    For customization down to the details, see the config file:

        $ rip config --open

    \b
    Repository: https://github.com/nathom/streamrip
    Bug Reports & Feature Requests: https://github.com/nathom/streamrip/issues
    Release Notes: https://github.com/nathom/streamrip/releases
    """
    import os

    import requests

    from .config import Config
    from .constants import CONFIG_DIR
    from .core import RipCore

    print(kwargs)
    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)

    global config
    global core

    if kwargs["debug"]:
        logger.setLevel("DEBUG")
        logger.debug("Starting debug log")

    if ctx.invoked_subcommand is None and not ctx.params["urls"]:
        print(dir(cli))
        echo(cli.get_help(ctx))

    if ctx.invoked_subcommand not in {
        None,
        "lastfm",
        "search",
        "discover",
        "config",
        "repair",
    }:

        return

    config = Config()

    if ctx.invoked_subcommand == "config":
        return

    if config.session["misc"]["check_for_updates"]:
        r = requests.get("https://pypi.org/pypi/streamrip/json").json()
        newest = r["info"]["version"]
        if __version__ != newest:
            secho(
                "A new version of streamrip is available! "
                "Run `pip3 install streamrip --upgrade` to update.",
                fg="yellow",
            )
        else:
            secho("streamrip is up-to-date!", fg="green")

    if kwargs["no_db"]:
        config.session["database"]["enabled"] = False

    if kwargs["convert"]:
        config.session["conversion"]["enabled"] = True
        config.session["conversion"]["codec"] = kwargs["convert"]

    if kwargs["quality"] is not None:
        quality = int(kwargs["quality"])
        if quality not in range(5):
            secho("Invalid quality", fg="red")
            return

        config.session["qobuz"]["quality"] = quality
        config.session["tidal"]["quality"] = quality
        config.session["deezer"]["quality"] = quality

    core = RipCore(config)

    if kwargs["urls"]:
        logger.debug(f"handling {kwargs['urls']}")
        core.handle_urls(kwargs["urls"])

    if kwargs["text"] is not None:
        if os.path.isfile(kwargs["text"]):
            logger.debug(f"Handling {kwargs['text']}")
            core.handle_txt(kwargs["text"])
        else:
            secho(f"Text file {kwargs['text']} does not exist.")

    if ctx.invoked_subcommand is None:
        core.download()


@cli.command(name="filter")
@option("--repeats", is_flag=True)
@option("--non-albums", is_flag=True)
@option("--extras", is_flag=True)
@option("--features", is_flag=True)
@option("--non-studio-albums", is_flag=True)
@option("--non-remasters", is_flag=True)
@argument("URLS", nargs=-1)
@pass_context
def filter_discography(ctx, **kwargs):
    """Filter an artists discography (qobuz only).

    The Qobuz API returns a massive number of tangentially related
    albums when requesting an artist's discography. This command
    can filter out most of the junk.

    For basic filtering, use the `--repeats` and `--features` filters.
    """
    raise Exception
    filters = kwargs.copy()
    filters.pop("urls")
    config.session["filters"] = filters
    logger.debug(f"downloading {kwargs['urls']} with filters {filters}")
    core.handle_urls(" ".join(kwargs["urls"]))
    core.download()


@cli.command()
@option(
    "-t",
    "--type",
    default="album",
    help="album, playlist, track, or artist",
    show_default=True,
)
@option(
    "-s",
    "--source",
    default="qobuz",
    help="qobuz, tidal, soundcloud, deezer, or deezloader",
    show_default=True,
)
@argument("QUERY", nargs=-1)
@pass_context
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
        secho("No items chosen, exiting.", fg="bright_red")


@cli.command()
@option("-l", "--list", default="ideal-discography", show_default=True)
@option(
    "-s", "--scrape", is_flag=True, help="Download all of the items in a list."
)
@option(
    "-n", "--num-items", default=50, help="Number of items to parse.", show_default=True
)
@pass_context
def discover(ctx, **kwargs):
    """Search for albums in Qobuz's featured lists.

    Avaiable options for `--list`:

    \b
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
    from streamrip.constants import QOBUZ_FEATURED_KEYS

    assert (
        kwargs["list"] in QOBUZ_FEATURED_KEYS
    ), f"Invalid featured key {kwargs['list']}"

    if kwargs["scrape"]:
        core.scrape(kwargs["list"])
        core.download()
        return

    if core.interactive_search(
        kwargs["list"], "qobuz", "featured", limit=int(kwargs["num_items"])
    ):
        core.download()
    else:
        none_chosen()


@cli.command()
@option(
    "-s",
    "--source",
    help="qobuz, tidal, deezer, deezloader, or soundcloud",
)
@argument("URL")
@pass_context
def lastfm(ctx, source, url):
    """Search for tracks from a last.fm playlist on a given source.

    This can be used to download playlists from Spotify and Apple Music.
    To import a playlist from one of those services, go to https://www.last.fm,
    log in, and to to the playlists section to import a link.

    \b
    Examples:

        \b
        Download a playlist using Qobuz as the source
        $ rip lastfm https://www.last.fm/user/nathan3895/playlists/12059037

        \b
        Download a playlist using Tidal as the source
        $ rip lastfm -s tidal https://www.last.fm/user/nathan3895/playlists/12059037

    """
    if source is not None:
        config.session["lastfm"]["source"] = source

    core.handle_lastfm_urls(url)
    core.download()


@cli.command()
@option("-o", "--open", is_flag=True, help="Open the config file")
@option("-d", "--directory", is_flag=True, help="Open the config directory")
@option("-q", "--qobuz", is_flag=True, help="Set Qobuz credentials")
@option("-t", "--tidal", is_flag=True, help="Re-login into Tidal")
@option("-dz", "--deezer", is_flag=True, help="Set the Deezer ARL")
@option("--reset", is_flag=True, help="RESET the config file")
@option(
    "--update",
    is_flag=True,
    help="Reset the config file, keeping the credentials",
)
@option("-p", "--path", is_flag=True, help="Show the config file's path")
@option(
    "-ov",
    "--open-vim",
    is_flag=True,
    help="Open the config file in the nvim or vim text editor.",
)
@pass_context
def config(ctx, **kwargs):
    """Manage the streamrip configuration file."""
    import os
    import shutil
    from getpass import getpass
    from hashlib import md5

    from streamrip.clients import TidalClient

    from .constants import CONFIG_PATH

    global config
    if kwargs["reset"]:
        config.reset()

    if kwargs["update"]:
        config.update()

    if kwargs["path"]:
        echo(CONFIG_PATH)

    if kwargs["open"]:
        secho(f"Opening {CONFIG_PATH}", fg="green")
        launch(CONFIG_PATH)

    if kwargs["open_vim"]:
        if shutil.which("nvim") is not None:
            os.system(f"nvim '{CONFIG_PATH}'")
        else:
            os.system(f"vim '{CONFIG_PATH}'")

    if kwargs["directory"]:
        config_dir = os.path.dirname(CONFIG_PATH)
        secho(f"Opening {config_dir}", fg="green")
        launch(config_dir)

    if kwargs["qobuz"]:
        config.file["qobuz"]["email"] = input(style("Qobuz email: ", fg="blue"))

        secho("Qobuz password (will not show on screen):", fg="blue")
        config.file["qobuz"]["password"] = md5(
            getpass(prompt="").encode("utf-8")
        ).hexdigest()

        config.save()
        secho("Qobuz credentials hashed and saved to config.", fg="green")

    if kwargs["tidal"]:
        client = TidalClient()
        client.login()
        config.file["tidal"].update(client.get_tokens())
        config.save()
        secho("Credentials saved to config.", fg="green")

    if kwargs["deezer"]:
        secho(
            "If you're not sure how to find the ARL cookie, see the instructions at ",
            italic=True,
            nl=False,
            dim=True,
        )
        secho(
            "https://github.com/nathom/streamrip/wiki/Finding-your-Deezer-ARL-Cookie",
            underline=True,
            italic=True,
            fg="blue",
        )
        config.file["deezer"]["arl"] = input(style("ARL: ", fg="green"))
        config.save()


@cli.command()
@option(
    "-sr", "--sampling-rate", help="Downsample the tracks to this rate, in Hz."
)
@option("-bd", "--bit-depth", help="Downsample the tracks to this bit depth.")
@option(
    "-k",
    "--keep-source",
    is_flag=True,
    help="Do not delete the old file after conversion.",
)
@argument("CODEC")
@argument("PATH")
@pass_context
def convert(ctx, **kwargs):
    """Batch convert audio files.

    This is a tool that is included with the `rip` program that assists with
    converting audio files. This is essentially a wrapper over ffmpeg
    that is designed to be easy to use with sensible default options.

    Examples (assuming /my/music is filled with FLAC files):

        $ rip convert MP3 /my/music

        $ rip convert ALAC --sampling-rate 48000 /my/music

    """
    import concurrent.futures
    import os

    from tqdm import tqdm

    from streamrip import converter

    codec_map = {
        "FLAC": converter.FLAC,
        "ALAC": converter.ALAC,
        "OPUS": converter.OPUS,
        "MP3": converter.LAME,
        "AAC": converter.AAC,
    }

    codec = kwargs.get("codec").upper()
    assert codec in codec_map.keys(), f"Invalid codec {codec}"

    if s := kwargs.get("sampling_rate"):
        sampling_rate = int(s)
    else:
        sampling_rate = None

    if s := kwargs.get("bit_depth"):
        bit_depth = int(s)
    else:
        bit_depth = None

    converter_args = {
        "sampling_rate": sampling_rate,
        "bit_depth": bit_depth,
        "remove_source": not kwargs.get("keep_source", False),
    }
    if os.path.isdir(kwargs["path"]):
        import itertools
        from pathlib import Path

        dirname = kwargs["path"]
        audio_extensions = ("flac", "m4a", "aac", "opus", "mp3", "ogg")
        path_obj = Path(dirname)
        audio_files = (
            path.as_posix()
            for path in itertools.chain.from_iterable(
                (path_obj.rglob(f"*.{ext}") for ext in audio_extensions)
            )
        )

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            for file in audio_files:
                futures.append(
                    executor.submit(
                        codec_map[codec](
                            filename=os.path.join(dirname, file), **converter_args
                        ).convert
                    )
                )
            for future in tqdm(
                concurrent.futures.as_completed(futures),
                total=len(futures),
                desc="Converting",
            ):
                # Only show loading bar
                future.result()

    elif os.path.isfile(kwargs["path"]):
        codec_map[codec](filename=kwargs["path"], **converter_args).convert()
    else:
        secho(f"File {kwargs['path']} does not exist.", fg="red")


@cli.command()
@option(
    "-n", "--num-items", help="The number of items to atttempt downloads for."
)
@pass_context
def repair(ctx, **kwargs):
    """Retry failed downloads.

    If the failed downloads database is enabled in the config file (it is by default),
    when an item is not available for download, it is logged in the database.

    When this command is called, it tries to download those items again. This is useful
    for times when a temporary server error may miss a few tracks in an album.
    """
    core.repair(max_items=kwargs.get("num_items"))


def none_chosen():
    """Print message if nothing was chosen."""
    secho("No items chosen, exiting.", fg="bright_red")


def main():
    """Run the main program."""
    cli(obj={})
