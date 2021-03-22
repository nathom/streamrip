# For tests

import logging
import os

import click

from qobuz_dl_rewrite.config import Config
from qobuz_dl_rewrite.constants import CACHE_DIR, CONFIG_DIR, CONFIG_PATH
from qobuz_dl_rewrite.core import MusicDL
from qobuz_dl_rewrite.utils import init_log

logger = logging.getLogger(__name__)


def _get_config(ctx):
    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    if not os.path.isdir(CACHE_DIR):
        os.makedirs(CONFIG_DIR)

    config = Config(ctx.obj.get("config"))
    config.update_from_cli(**ctx.obj)
    return config


# fmt: off
@click.group()
@click.option("--debug", default=False, is_flag=True, help="Enable debug logging")
@click.option("--flush-cache", metavar="PATH", help="Flush the cache before running (only for extreme cases)")
@click.pass_context
# fmt: on
def cli(ctx, **kwargs):
    """cli.

    $ rip www.qobuz.com/album/id1089374 convert -c ALAC -sr 48000
    > download and convert to alac, downsample to 48kHz
    $ rip config --read
    > Config(...)
    $ rip config --qobuzpwd MyQobuzPwd123 --qobuzemail person@email.com
    $ rip config --tidalpwd MyTidalPwd123 --tidalemail person@email.com
    > sets the credentials
    $ rip www.qobuz.com/artist/id223049 filter --studio-albums --no-repeats
    > download discography with given filters

    :param ctx:
    :param kwargs:
    """
    ctx.ensure_object(dict)

    for key in kwargs.keys():
        ctx.obj[key] = kwargs.get(key)

    if ctx.obj["debug"]:
        init_log(path=ctx.obj.get("log_file"))
    else:
        click.secho("Debug is not enabled", fg="yellow")


@click.command(name="dl")
@click.option("-q", "--quality", metavar="INT", help="Quality integer ID (5, 6, 7, 27)")
@click.option("--large-cover", is_flag=True, help="Download large covers (it might fail with embed)")
@click.option("-f", "--folder", metavar="PATH", help="Custom download folder")
@click.argument("items", nargs=-1)
@click.pass_context
def download(ctx, items):
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


@click.command()
@click.argument("--path")
@click.argument("--read")
def config(path, read):
    if path:
        click.echo(CONFIG_PATH)
    if read:
        click.echo(repr(config))


@click.command()
@click.option("-t", '--type', default='album',
              help='Type to search for. Can be album, artist, playlist, track')
@click.argument("QUERY")
def search(media_type, query):
    pass


@click.command()
@click.option("-c", "--codec", default='ALAC')
@click.option("-sr", '--sampling-rate')
@click.option("-bd", "--bit-depth")
def convert(codec, sampling_rate, bit_depth):
    pass


@click.command()
def interactive():
    pass


@click.command()
@click.option("--no-extras", is_flag=True, help="Ignore extras")
@click.option("--no-features", is_flag=True, help="Ignore features")
@click.option("--studio-albums", is_flag=True, help="Ignore non-studio albums")
@click.option("--remaster-only", is_flag=True, help="Ignore non-remastered albums")
@click.option("--albums-only", is_flag=True, help="Ignore non-album downloads")
def filter():
    pass


@click.command()
@click.option("--default-comment", metavar="COMMENT", help="Custom comment tag for audio files")
def tags():
    pass


def main():
    cli.add_command(download)
    cli(obj={})


if __name__ == "__main__":
    main()
