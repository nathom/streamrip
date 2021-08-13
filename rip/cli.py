import concurrent.futures
import logging
import os
import threading

import requests
from cleo.application import Application as BaseApplication
from cleo.commands.command import Command
from cleo.formatters.style import Style
from click import launch

from streamrip import __version__

from .config import Config
from .core import RipCore

logging.basicConfig(level="WARNING")
logger = logging.getLogger("streamrip")

outdated = False
newest_version = __version__


class DownloadCommand(Command):
    """
    Download items using urls.

    url
        {--f|file=None : Path to a text file containing urls}
        {--c|codec=None : Convert the downloaded files to <cmd>ALAC</cmd>, <cmd>FLAC</cmd>, <cmd>MP3</cmd>, <cmd>AAC</cmd>, or <cmd>OGG</cmd>}
        {--m|max-quality=None : The maximum quality to download. Can be <cmd>0</cmd>, <cmd>1</cmd>, <cmd>2</cmd>, <cmd>3 </cmd>or <cmd>4</cmd>}
        {--i|ignore-db : Download items even if they have been logged in the database.}
        {urls?* : One or more Qobuz, Tidal, Deezer, or SoundCloud urls}
    """

    help = (
        "\nDownload <title>Dreams</title> by <title>Fleetwood Mac</title>:\n"
        "$ <cmd>rip url https://www.deezer.com/en/track/63480987</cmd>\n\n"
        "Batch download urls from a text file named <path>urls.txt</path>:\n"
        "$ <cmd>rip url --file urls.txt</cmd>\n\n"
        "For more information on Quality IDs, see\n"
        "<url>https://github.com/nathom/streamrip/wiki/Quality-IDs</url>\n"
    )

    def handle(self):
        global outdated
        global newest_version

        # Use a thread so that it doesn't slow down startup
        update_check = threading.Thread(target=is_outdated, daemon=True)
        update_check.start()

        config = Config()
        path, codec, quality, no_db = clean_options(
            self.option("file"),
            self.option("codec"),
            self.option("max-quality"),
            self.option("ignore-db"),
        )

        if no_db:
            config.session["database"]["enabled"] = False

        if quality is not None:
            for source in ("qobuz", "tidal", "deezer"):
                config.session[source]["quality"] = quality

        core = RipCore(config)

        urls = self.argument("urls")

        if path is not None:
            if os.path.isfile(path):
                core.handle_txt(path)
            else:
                self.line(
                    f"<error>File <comment>{path}</comment> does not exist.</error>"
                )
                return 1

        if urls:
            core.handle_urls(";".join(urls))

        if len(core) > 0:
            core.download()
        elif not urls and path is None:
            self.line("<error>Must pass arguments. See </><cmd>rip url -h</cmd>.")

        update_check.join()
        if outdated:
            import subprocess
            import re

            self.line(
                f"<info>Updating streamrip to <title>v{newest_version}</title>...</info>\n"
            )

            # update in background
            update_p = subprocess.Popen(
                ["pip3", "install", "streamrip", "--upgrade"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            md_header = re.compile(r"#\s+(.+)")
            bullet_point = re.compile(r"-\s+(.+)")
            code = re.compile(r"`([^`]+)`")
            issue_reference = re.compile(r"(#\d+)")

            release_notes = requests.get(
                "https://api.github.com/repos/nathom/streamrip/releases/latest"
            ).json()["body"]

            release_notes = md_header.sub(r"<header>\1</header>", release_notes)
            release_notes = bullet_point.sub(r"<options=bold>•</> \1", release_notes)
            release_notes = code.sub(r"<cmd>\1</cmd>", release_notes)
            release_notes = issue_reference.sub(r"<options=bold>\1</>", release_notes)

            self.line(release_notes)

            update_p.wait()

        return 0


class SearchCommand(Command):
    """
    Search for and download items in interactive mode.

    search
        {query : The name to search for}
        {--s|source=qobuz : Qobuz, Tidal, Soundcloud, Deezer, or Deezloader}
        {--t|type=album : Album, Playlist, Track, or Artist}
    """

    help = (
        "\nSearch for <title>Rumours</title> by <title>Fleetwood Mac</title>\n"
        "$ <cmd>rip search 'rumours fleetwood mac'</cmd>\n\n"
        "Search for <title>444</title> by <title>Jay-Z</title> on TIDAL\n"
        "$ <cmd>rip search --source tidal '444'</cmd>\n\n"
        "Search for <title>Bob Dylan</title> on Deezer\n"
        "$ <cmd>rip search --type artist --source deezer 'bob dylan'</cmd>\n"
    )

    def handle(self):
        query = self.argument("query")
        source, type = clean_options(self.option("source"), self.option("type"))

        config = Config()
        core = RipCore(config)

        if core.interactive_search(query, source, type):
            core.download()
        else:
            self.line("<error>No items chosen, exiting.</error>")


class DiscoverCommand(Command):
    """
    Browse and download items in interactive mode (Qobuz only).

    discover
        {--s|scrape : Download all of the items in the list}
        {--m|max-items=50 : The number of items to fetch}
        {list=ideal-discography : The list to fetch}
    """

    help = (
        "\nBrowse the Qobuz ideal-discography list\n"
        "$ <cmd>rip discover</cmd>\n\n"
        "Browse the best-sellers list\n"
        "$ <cmd>rip discover best-sellers</cmd>\n\n"
        "Available options for <info>list</info>:\n\n"
        "    • most-streamed\n"
        "    • recent-releases\n"
        "    • best-sellers\n"
        "    • press-awards\n"
        "    • ideal-discography\n"
        "    • editor-picks\n"
        "    • most-featured\n"
        "    • qobuzissims\n"
        "    • new-releases\n"
        "    • new-releases-full\n"
        "    • harmonia-mundi\n"
        "    • universal-classic\n"
        "    • universal-jazz\n"
        "    • universal-jeunesse\n"
        "    • universal-chanson\n"
    )

    def handle(self):
        from streamrip.constants import QOBUZ_FEATURED_KEYS

        chosen_list = self.argument("list")
        scrape = self.option("scrape")
        max_items = self.option("max-items")

        if chosen_list not in QOBUZ_FEATURED_KEYS:
            self.line(f'<error>Error: list "{chosen_list}" not available</error>')
            self.line(self.help)
            return 1

        config = Config()
        core = RipCore(config)

        if scrape:
            core.scrape(chosen_list, max_items)
            core.download()
            return 0

        if core.interactive_search(
            chosen_list, "qobuz", "featured", limit=int(max_items)
        ):
            core.download()
        else:
            self.line("<error>No items chosen, exiting.</error>")


class LastfmCommand(Command):
    """
    Search for tracks from a list.fm playlist and download them.

    lastfm
        {--s|source=qobuz : The source to search for items on}
        {urls* : Last.fm playlist urls}
    """

    help = (
        "You can use this command to download Spotify, Apple Music, and YouTube "
        "playlists.\nTo get started, create an account at "
        "<url>https://www.last.fm</url>. Once you have\nreached the home page, "
        "go to <path>Profile Icon</path> ⟶  <path>View profile</path> ⟶  "
        "<path>Playlists</path> ⟶  <path>IMPORT</path>\nand paste your url.\n\n"
        "Download the <info>young & free</info> Apple Music playlist (already imported)\n"
        "$ <cmd>rip lastfm https://www.last.fm/user/nathan3895/playlists/12089888</cmd>\n"
    )

    def handle(self):
        source = self.option("source")
        urls = self.argument("urls")

        config = Config()
        core = RipCore(config)
        config.session["lastfm"]["source"] = source
        core.handle_lastfm_urls(";".join(urls))
        core.download()


class ConfigCommand(Command):
    """
    Manage the configuration file.

    config
        {--o|open : Open the config file in the default application}
        {--O|open-vim : Open the config file in (neo)vim}
        {--d|directory : Open the directory that the config file is located in}
        {--p|path : Show the config file's path}
        {--qobuz : Set the credentials for Qobuz}
        {--tidal : Log into Tidal}
        {--deezer : Set the Deezer ARL}
        {--reset : Reset the config file}
        {--update : Reset the config file, keeping the credentials}
    """

    def handle(self):
        import shutil

        from .constants import CONFIG_DIR, CONFIG_PATH

        config = Config()

        if self.option("path"):
            self.line(f"<info>{CONFIG_PATH}</info>")

        if self.option("open"):
            self.line(f"Opening <url>{CONFIG_PATH}</url> in default application")
            launch(CONFIG_PATH)

        if self.option("reset"):
            config.reset()

        if self.option("update"):
            config.update()

        if self.option("open-vim"):
            if shutil.which("nvim") is not None:
                os.system(f"nvim '{CONFIG_PATH}'")
            else:
                os.system(f"vim '{CONFIG_PATH}'")

        if self.option("directory"):
            self.line(f"Opening <url>{CONFIG_DIR}</url>")
            launch(CONFIG_DIR)

        if self.option("tidal"):
            from streamrip.clients import TidalClient

            client = TidalClient()
            client.login()
            config.file["tidal"].update(client.get_tokens())
            config.save()
            self.line("<info>Credentials saved to config.</info>")

        if self.option("deezer"):
            from streamrip.clients import DeezerClient
            from streamrip.exceptions import AuthenticationError

            self.line(
                "Follow the instructions at <url>https://github.com"
                "/nathom/streamrip/wiki/Finding-your-Deezer-ARL-Cookie</url>"
            )

            given_arl = self.ask("Paste your ARL here: ").strip()
            self.line("<comment>Validating arl...</comment>")

            try:
                DeezerClient().login(arl=given_arl)
                config.file["deezer"]["arl"] = given_arl
                config.save()
                self.line("<b>Sucessfully logged in!</b>")

            except AuthenticationError:
                self.line("<error>Could not log in. Double check your ARL</error>")

        if self.option("qobuz"):
            import hashlib
            import getpass

            config.file["qobuz"]["email"] = self.ask("Qobuz email:")
            config.file["qobuz"]["password"] = hashlib.md5(
                getpass.getpass("Qobuz password (won't show on screen): ").encode()
            ).hexdigest()
            config.save()


class ConvertCommand(Command):
    """
    A standalone tool that converts audio files to other codecs en masse.

    convert
        {--s|sampling-rate=192000 : Downsample the tracks to this rate, in Hz.}
        {--b|bit-depth=24 : Downsample the tracks to this bit depth.}
        {--k|keep-source : Keep the original file after conversion.}
        {codec : <cmd>FLAC</cmd>, <cmd>ALAC</cmd>, <cmd>OPUS</cmd>, <cmd>MP3</cmd>, or <cmd>AAC</cmd>.}
        {path : The path to the audio file or a directory that contains audio files.}
    """

    help = (
        "\nConvert all of the audio files in <path>/my/music</path> to MP3s\n"
        "$ <cmd>rip convert MP3 /my/music</cmd>\n\n"
        "Downsample the audio to 48kHz after converting them to ALAC\n"
        "$ <cmd>rip convert --sampling-rate 48000 ALAC /my/music\n"
    )

    def handle(self):
        from streamrip import converter

        CODEC_MAP = {
            "FLAC": converter.FLAC,
            "ALAC": converter.ALAC,
            "OPUS": converter.OPUS,
            "MP3": converter.LAME,
            "AAC": converter.AAC,
        }

        codec = self.argument("codec")
        path = self.argument("path")

        ConverterCls = CODEC_MAP.get(codec.upper())
        if ConverterCls is None:
            self.line(
                f'<error>Invalid codec "{codec}". See </error><cmd>rip convert'
                " -h</cmd>."
            )
            return 1

        sampling_rate, bit_depth, keep_source = clean_options(
            self.option("sampling-rate"),
            self.option("bit-depth"),
            self.option("keep-source"),
        )

        converter_args = {
            "sampling_rate": sampling_rate,
            "bit_depth": bit_depth,
            "remove_source": not keep_source,
        }

        if os.path.isdir(path):
            import itertools
            from pathlib import Path

            from tqdm import tqdm

            dirname = path
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
                            ConverterCls(
                                filename=os.path.join(dirname, file), **converter_args
                            ).convert
                        )
                    )
                from streamrip.utils import TQDM_BAR_FORMAT

                for future in tqdm(
                    concurrent.futures.as_completed(futures),
                    total=len(futures),
                    desc="Converting",
                    bar_format=TQDM_BAR_FORMAT,
                ):
                    # Only show loading bar
                    future.result()

        elif os.path.isfile(path):
            ConverterCls(filename=path, **converter_args).convert()
        else:
            self.line(
                f'<error>Path <path>"{path}"</path> does not exist.</error>', fg="red"
            )


class RepairCommand(Command):
    """
    Retry failed downloads.

    repair
        {--m|max-items=None : The maximum number of tracks to download}
    """

    help = "\nRetry up to 20 failed downloads\n$ <cmd>rip repair --max-items 20</cmd>\n"

    def handle(self):
        max_items = clean_options(self.option("repair"))
        config = Config()
        RipCore(config).repair(max_items=max_items)


STRING_TO_PRIMITIVE = {
    "None": None,
    "True": True,
    "False": False,
}


class Application(BaseApplication):
    def __init__(self):
        super().__init__("rip", __version__)

    def _run(self, io):
        if io.is_debug():
            from .constants import CONFIG_DIR

            logger.setLevel(logging.DEBUG)
            fh = logging.FileHandler(os.path.join(CONFIG_DIR, "streamrip.log"))
            fh.setLevel(logging.DEBUG)
            logger.addHandler(fh)

        super()._run(io)

    def create_io(self, input=None, output=None, error_output=None):
        io = super().create_io(input, output, error_output)
        # Set our own CLI styles
        formatter = io.output.formatter
        formatter.set_style("url", Style("blue", options=["underline"]))
        formatter.set_style("path", Style("green", options=["bold"]))
        formatter.set_style("cmd", Style("magenta"))
        formatter.set_style("title", Style("yellow", options=["bold"]))
        formatter.set_style("header", Style("yellow", options=["bold", "underline"]))
        io.output.set_formatter(formatter)
        io.error_output.set_formatter(formatter)

        self._io = io

        return io

    @property
    def _default_definition(self):
        default_globals = super()._default_definition
        # as of 1.0.0a3, the descriptions don't wrap properly
        # so I'm truncating the description for help as a hack
        default_globals._options["help"]._description = (
            default_globals._options["help"]._description.split(".")[0] + "."
        )

        return default_globals

    def render_error(self, error, io):
        super().render_error(error, io)
        io.write_line(
            "\n<error>If this was unexpected, please open a <path>Bug Report</path> at </error>"
            "<url>https://github.com/nathom/streamrip/issues/new/choose</url>"
        )


def clean_options(*opts):
    for opt in opts:
        if isinstance(opt, str):
            if opt.startswith("="):
                opt = opt[1:]

            opt = opt.strip()
            if opt.isdigit():
                opt = int(opt)
            else:
                opt = STRING_TO_PRIMITIVE.get(opt, opt)

        yield opt


def is_outdated():
    global outdated
    global newest_version
    r = requests.get("https://pypi.org/pypi/streamrip/json").json()
    newest_version = r["info"]["version"]
    outdated = newest_version != __version__


def main():
    application = Application()
    application.add(DownloadCommand())
    application.add(SearchCommand())
    application.add(DiscoverCommand())
    application.add(LastfmCommand())
    application.add(ConfigCommand())
    application.add(ConvertCommand())
    application.add(RepairCommand())
    application.run()


if __name__ == "__main__":
    main()
