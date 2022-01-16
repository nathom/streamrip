import concurrent.futures
import logging
import os
import threading
from typing import Optional

import requests
from cleo.application import Application as BaseApplication
from cleo.commands.command import Command
from cleo.formatters.style import Style
from cleo.helpers import argument, option
from click import launch

from streamrip import __version__

from .config import Config
from .core import RipCore

logging.basicConfig(level="WARNING")
logger = logging.getLogger("streamrip")

outdated = False
newest_version = __version__


class DownloadCommand(Command):
    name = "url"
    description = "Download items using urls."

    arguments = [
        argument(
            "urls",
            "One or more Qobuz, Tidal, Deezer, or SoundCloud urls",
            optional=True,
            multiple=True,
        )
    ]
    options = [
        option(
            "file",
            "-f",
            "Path to a text file containing urls",
            flag=False,
            default="None",
        ),
        option(
            "codec",
            "-c",
            "Convert the downloaded files to <cmd>ALAC</cmd>, <cmd>FLAC</cmd>, <cmd>MP3</cmd>, <cmd>AAC</cmd>, or <cmd>OGG</cmd>",
            flag=False,
            default="None",
        ),
        option(
            "max-quality",
            "m",
            "The maximum quality to download. Can be <cmd>0</cmd>, <cmd>1</cmd>, <cmd>2</cmd>, <cmd>3 </cmd>or <cmd>4</cmd>",
            flag=False,
            default="None",
        ),
        option(
            "ignore-db",
            "-i",
            description="Download items even if they have been logged in the database.",
        ),
        option("config", description="Path to config file.", flag=False),
        option("directory", "-d", "Directory to download items into.", flag=False),
    ]

    help = (
        "\nDownload <title>Dreams</title> by <title>Fleetwood Mac</title>:\n"
        "$ <cmd>rip url https://www.deezer.com/us/track/67549262</cmd>\n\n"
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

        path, codec, quality, no_db, directory, config = clean_options(
            self.option("file"),
            self.option("codec"),
            self.option("max-quality"),
            self.option("ignore-db"),
            self.option("directory"),
            self.option("config"),
        )

        config = Config(config)

        if directory is not None:
            config.session["downloads"]["folder"] = directory

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
            import re
            import subprocess

            self.line(
                f"\n<info>A new version of streamrip <title>v{newest_version}</title>"
                " is available! Run <cmd>pip3 install streamrip --upgrade</cmd>"
                " to update.</info>\n"
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

        return 0


class SearchCommand(Command):
    name = "search"
    description = "Search for an item"
    arguments = [
        argument(
            "query",
            "The name to search for",
            optional=False,
            multiple=False,
        )
    ]
    options = [
        option(
            "source",
            "-s",
            "Qobuz, Tidal, Soundcloud, Deezer, or Deezloader",
            flag=False,
            default="qobuz",
        ),
        option(
            "type",
            "-t",
            "Album, Playlist, Track, or Artist",
            flag=False,
            default="album",
        ),
    ]

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
    name = "discover"
    description = "Download items from the charts or a curated playlist"
    arguments = [
        argument(
            "list",
            "The list to fetch",
            optional=True,
            multiple=False,
            default="ideal-discography",
        )
    ]
    options = [
        option(
            "scrape",
            description="Download all of the items in the list",
        ),
        option(
            "max-items",
            "-m",
            description="The number of items to fetch",
            flag=False,
            default=50,
        ),
        option(
            "source",
            "-s",
            description="The source to download from (<cmd>qobuz</cmd> or <cmd>deezer</cmd>)",
            flag=False,
            default="qobuz",
        ),
    ]
    help = (
        "\nBrowse the Qobuz ideal-discography list\n"
        "$ <cmd>rip discover</cmd>\n\n"
        "Browse the best-sellers list\n"
        "$ <cmd>rip discover best-sellers</cmd>\n\n"
        "Available options for Qobuz <cmd>list</cmd>:\n\n"
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
        "    • universal-chanson\n\n"
        "Browse the Deezer editorial releases list\n"
        "$ <cmd>rip discover --source deezer</cmd>\n\n"
        "Browse the Deezer charts\n"
        "$ <cmd>rip discover --source deezer charts</cmd>\n\n"
        "Available options for Deezer <cmd>list</cmd>:\n\n"
        "    • releases\n"
        "    • charts\n"
        "    • selection\n"
    )

    def handle(self):
        source = self.option("source")
        scrape = self.option("scrape")
        chosen_list = self.argument("list")
        max_items = self.option("max-items")

        if source == "qobuz":
            from streamrip.constants import QOBUZ_FEATURED_KEYS

            if chosen_list not in QOBUZ_FEATURED_KEYS:
                self.line(f'<error>Error: list "{chosen_list}" not available</error>')
                self.line(self.help)
                return 1
        elif source == "deezer":
            from streamrip.constants import DEEZER_FEATURED_KEYS

            if chosen_list not in DEEZER_FEATURED_KEYS:
                self.line(f'<error>Error: list "{chosen_list}" not available</error>')
                self.line(self.help)
                return 1

        else:
            self.line(
                "<error>Invalid source. Choose either <cmd>qobuz</cmd> or <cmd>deezer</cmd></error>"
            )
            return 1

        config = Config()
        core = RipCore(config)

        if scrape:
            core.scrape(chosen_list, max_items)
            core.download()
            return 0

        if core.interactive_search(
            chosen_list, source, "featured", limit=int(max_items)
        ):
            core.download()
        else:
            self.line("<error>No items chosen, exiting.</error>")

        return 0


class LastfmCommand(Command):
    name = "lastfm"
    description = "Search for tracks from a last.fm playlist and download them."

    arguments = [
        argument(
            "urls",
            "Last.fm playlist urls",
            optional=False,
            multiple=True,
        )
    ]
    options = [
        option(
            "source",
            "-s",
            description="The source to search for items on",
            flag=False,
            default="qobuz",
        ),
    ]
    help = (
        "You can use this command to download Spotify, Apple Music, and YouTube "
        "playlists.\nTo get started, create an account at "
        "<url>https://www.last.fm</url>. Once you have\nreached the home page, "
        "go to <path>Profile Icon</path> => <path>View profile</path> => "
        "<path>Playlists</path> => <path>IMPORT</path>\nand paste your url.\n\n"
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
    name = "config"
    description = "Manage the configuration file."

    options = [
        option(
            "open",
            "-o",
            description="Open the config file in the default application",
            flag=True,
        ),
        option(
            "open-vim",
            "-O",
            description="Open the config file in (neo)vim",
            flag=True,
        ),
        option(
            "directory",
            "-d",
            description="Open the directory that the config file is located in",
            flag=True,
        ),
        option("path", "-p", description="Show the config file's path", flag=True),
        option("qobuz", description="Set the credentials for Qobuz", flag=True),
        option("tidal", description="Log into Tidal", flag=True),
        option("deezer", description="Set the Deezer ARL", flag=True),
        option(
            "music-app",
            description="Configure the config file for usage with the macOS Music App",
            flag=True,
        ),
        option("reset", description="Reset the config file", flag=True),
        option(
            "--update",
            description="Reset the config file, keeping the credentials",
            flag=True,
        ),
    ]
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
        {--music-app : Configure the config file for usage with the macOS Music App}
        {--reset : Reset the config file}
        {--update : Reset the config file, keeping the credentials}
    """

    _config: Optional[Config]

    def handle(self):
        import shutil

        from .constants import CONFIG_DIR, CONFIG_PATH

        self._config = Config()

        if self.option("path"):
            self.line(f"<info>{CONFIG_PATH}</info>")

        if self.option("open"):
            self.line(f"Opening <url>{CONFIG_PATH}</url> in default application")
            launch(CONFIG_PATH)

        if self.option("reset"):
            self._config.reset()

        if self.option("update"):
            self._config.update()

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
            self._config.file["tidal"].update(client.get_tokens())
            self._config.save()
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
                self._config.file["deezer"]["arl"] = given_arl
                self._config.save()
                self.line("<b>Sucessfully logged in!</b>")

            except AuthenticationError:
                self.line("<error>Could not log in. Double check your ARL</error>")

        if self.option("qobuz"):
            import getpass
            import hashlib

            self._config.file["qobuz"]["email"] = self.ask("Qobuz email:")
            self._config.file["qobuz"]["password"] = hashlib.md5(
                getpass.getpass("Qobuz password (won't show on screen): ").encode()
            ).hexdigest()
            self._config.save()

        if self.option("music-app"):
            self._conf_music_app()

    def _conf_music_app(self):
        import subprocess
        import xml.etree.ElementTree as ET
        from pathlib import Path
        from tempfile import mktemp

        # Find the Music library folder
        temp_file = mktemp()
        music_pref_plist = Path(Path.home()) / Path(
            "Library/Preferences/com.apple.Music.plist"
        )
        # copy preferences to tempdir
        subprocess.run(["cp", music_pref_plist, temp_file])
        # convert binary to xml for parsing
        subprocess.run(["plutil", "-convert", "xml1", temp_file])
        items = iter(ET.parse(temp_file).getroot()[0])

        for item in items:
            if item.text == "NSNavLastRootDirectory":
                break

        library_folder = Path(next(items).text)
        os.remove(temp_file)

        # cp ~/library/preferences/com.apple.music.plist music.plist
        # plutil -convert xml1 music.plist
        # cat music.plist | pbcopy

        self._config.file["downloads"]["folder"] = os.path.join(
            library_folder, "Automatically Add to Music.localized"
        )

        conversion_config = self._config.file["conversion"]
        conversion_config["enabled"] = True
        conversion_config["codec"] = "ALAC"
        conversion_config["sampling_rate"] = 48000
        conversion_config["bit_depth"] = 24

        self._config.file["filepaths"]["folder_format"] = ""
        self._config.file["artwork"]["keep_hires_cover"] = False
        self._config.save()


class ConvertCommand(Command):
    name = "convert"
    description = (
        "A standalone tool that converts audio files to other codecs en masse."
    )
    arguments = [
        argument(
            "codec",
            description="<cmd>FLAC</cmd>, <cmd>ALAC</cmd>, <cmd>OPUS</cmd>, <cmd>MP3</cmd>, or <cmd>AAC</cmd>.",
        ),
        argument(
            "path",
            description="The path to the audio file or a directory that contains audio files.",
        ),
    ]
    options = [
        option(
            "sampling-rate",
            "-s",
            description="Downsample the tracks to this rate, in Hz.",
            default=192000,
            flag=False,
        ),
        option(
            "bit-depth",
            "-b",
            description="Downsample the tracks to this bit depth.",
            default=24,
            flag=False,
        ),
        option(
            "keep-source", "-k", description="Keep the original file after conversion."
        ),
    ]

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
                                filename=os.path.join(dirname, file),
                                **converter_args,
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
                f'<error>Path <path>"{path}"</path> does not exist.</error>',
                fg="red",
            )


class RepairCommand(Command):
    name = "repair"
    description = "Retry failed downloads."

    options = [
        option(
            "max-items",
            "-m",
            flag=False,
            description="The maximum number of tracks to download}",
            default="None",
        )
    ]

    help = "\nRetry up to 20 failed downloads\n$ <cmd>rip repair --max-items 20</cmd>\n"

    def handle(self):
        max_items = next(clean_options(self.option("max-items")))
        config = Config()
        RipCore(config).repair(max_items=max_items)


class DatabaseCommand(Command):
    name = "db"
    description = "View and manage rip's databases."

    arguments = [
        argument(
            "name", description="<cmd>downloads</cmd> or <cmd>failed-downloads</cmd>."
        )
    ]
    options = [
        option("list", "-l", description="Display the contents of the database."),
        option("reset", description="Reset the database."),
    ]

    _table_style = "box-double"

    def handle(self) -> None:
        from . import db
        from .config import Config

        config = Config()
        db_name = self.argument("name").replace("-", "_")

        self._path = config.file["database"][db_name]["path"]
        self._db = db.CLASS_MAP[db_name](self._path)

        if self.option("list"):
            getattr(self, f"_render_{db_name}")()

        if self.option("reset"):
            os.remove(self._path)

    def _render_downloads(self):
        from cleo.ui.table import Table

        id_table = Table(self._io)
        id_table.set_style(self._table_style)
        id_table.set_header_title("IDs")
        id_table.set_headers(list(self._db.structure.keys()))
        id_table.add_rows(id for id in iter(self._db) if id[0].isalnum())
        if id_table._rows:
            id_table.render()

        url_table = Table(self._io)
        url_table.set_style(self._table_style)
        url_table.set_header_title("URLs")
        url_table.set_headers(list(self._db.structure.keys()))
        url_table.add_rows(id for id in iter(self._db) if not id[0].isalnum())
        # prevent wierd formatting
        if url_table._rows:
            url_table.render()

    def _render_failed_downloads(self):
        from cleo.ui.table import Table

        id_table = Table(self._io)
        id_table.set_style(self._table_style)
        id_table.set_header_title("Failed Downloads")
        id_table.set_headers(["Source", "Media Type", "ID"])
        id_table.add_rows(iter(self._db))
        id_table.render()


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
    application.add(DatabaseCommand())
    application.run()


if __name__ == "__main__":
    main()
