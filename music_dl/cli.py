# For tests

import logging
from getpass import getpass
import os

import click

from .config import Config
from .constants import CACHE_DIR, CONFIG_DIR, CONFIG_PATH
from .core import MusicDL

logger = logging.getLogger(__name__)
config = Config(CONFIG_PATH)


def _get_config(ctx):
    print(f"{ctx.obj=}")
    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    if not os.path.isdir(CACHE_DIR):
        os.makedirs(CONFIG_DIR)

    config = Config(CONFIG_PATH)
    config.update_from_cli(**ctx.obj)
    return config


@click.group()
@click.option("--debug", default=False, is_flag=True, help="Enable debug logging")
@click.option("--flush-cache", metavar="PATH", help="Flush the cache before running (only for extreme cases)")
@click.option("-c", '--convert', metavar='CODEC')
@click.pass_context
def cli(ctx, **kwargs):
    """cli.

    $ rip www.qobuz.com/album/id1089374 convert -c ALAC -sr 48000

    > download and convert to alac, downsample to 48kHz

    $ rip config --read

    > Config(...)

    $ rip www.qobuz.com/artist/id223049 filter --studio-albums --no-repeats

    > download discography with given filters
    """
    print(f"{ctx=}")
    print(f"{kwargs=}")


@click.command(name="dl")
@click.option("-q", "--quality", metavar="INT", help="Quality integer ID (5, 6, 7, 27)")
@click.option("-f", "--folder", metavar="PATH", help="Custom download folder")
@click.option("-s", "--search", metavar='QUERY')
@click.option("-nd", "--no-db", is_flag=True)
@click.argument("items", nargs=-1)
@click.pass_context
def download(ctx, quality, folder, search, items):
    """
    Download an URL, space separated URLs or a text file with URLs.
    Mixed arguments are also supported.

    Examples:

        * `qobuz-dl dl https://some.url/some_type/some_id`

        * `qobuz-dl dl file_with_urls.txt`

        * `qobuz-dl dl URL URL URL`

    Supported sources and their types:

        * Deezer (album, artist, track, playlist)

        * Qobuz (album, artist, label, track, playlist)

        * Tidal (album, artist, track, playlist)
    """
    ctx.ensure_object(dict)
    config = _get_config(ctx)
    core = MusicDL(config)
    for item in items:
        try:
            if os.path.isfile(item):
                core.from_txt(item)
                click.secho(f"File input found: {item}", fg="yellow")
            else:
                core.handle_url(item)
        except Exception as error:
            logger.error(error, exc_info=True)
            click.secho(
                f"{type(error).__name__} raised processing {item}: {error}", fg="red"
            )


@click.command(name='config')
@click.option('-o', "--open", is_flag=True)
@click.option("-q", '--qobuz', is_flag=True)
@click.option("-t", '--tidal', is_flag=True)
def edit_config(open, qobuz, tidal):
    if open:
        # open in text editor
        click.launch(CONFIG_PATH)
        return

    if qobuz:
        config['qobuz']['email'] = input("Qobuz email: ")
        config['qobuz']['password'] = getpass("Qobuz password: ")
        config.save()
        click.secho(f"Config saved at {CONFIG_PATH}", fg='green')

    if tidal:
        config['tidal']['email'] = input("Tidal email: ")
        config['tidal']['password'] = getpass("Tidal password: ")
        config.save()
        click.secho(f"Config saved at {CONFIG_PATH}", fg='green')


@click.command()
@click.option("-t", '--type', default='album',
              help='Type to search for. Can be album, artist, playlist, track')
@click.argument("QUERY")
def search(media_type, query):
    print(f"searching for {media_type} with {query=}")


@click.command()
@click.option("-sr", '--sampling-rate')
@click.option("-bd", "--bit-depth")
@click.argument("codec")
def convert(sampling_rate, bit_depth, codec):
    print(codec, sampling_rate, bit_depth)


@click.command()
def interactive():
    pass


@click.command()
@click.option("--no-extras", is_flag=True, help="Ignore extras")
@click.option("--no-features", is_flag=True, help="Ignore features")
@click.option("--studio-albums", is_flag=True, help="Ignore non-studio albums")
@click.option("--remaster-only", is_flag=True, help="Ignore non-remastered albums")
@click.option("--albums-only", is_flag=True, help="Ignore non-album downloads")
def filter(*args):
    print(f"filter {args=}")


@click.command()
@click.option("--default-comment", metavar="COMMENT", help="Custom comment tag for audio files")
@click.option("--no-cover", help='Do not embed cover into audio file.')
def tags(default_comment, no_cover):
    print(f"{default_comment=}, {no_cover=}")


def main():
    cli.add_command(download)
    cli.add_command(filter)
    cli.add_command(tags)
    cli.add_command(edit_config)
    cli.add_command(convert)
    cli(obj={})


if __name__ == "__main__":
    main()
