import logging
import os

from cleo.application import Application as BaseApplication
from cleo.commands.command import Command

from streamrip import __version__

from .config import Config
from .core import RipCore

logging.basicConfig(level="WARNING")
logger = logging.getLogger("streamrip")


class DownloadCommand(Command):
    """
    Download items from a url

    url
        {--f|file=None : Path to a text file containing urls}
        {urls?* : One or more Qobuz, Tidal, Deezer, or SoundCloud urls}
    """

    help = (
        '\nDownload "Dreams" by Fleetwood Mac:\n'
        "$ <fg=magenta>rip url https://www.deezer.com/en/track/63480987</>\n\n"
        "Batch download urls from a text file named urls.txt:\n"
        "$ <fg=magenta>rip --file urls.txt</>\n"
    )

    def handle(self):
        config = Config()
        core = RipCore(config)

        urls = self.argument("urls")
        path = self.option("file")
        if path != "None":
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
        elif not urls and path == "None":
            self.line("<error>Must pass arguments. See </><info>rip url -h</info>.")

        return 0


class SearchCommand(Command):
    """
    Search for and download items in interactive mode.

    search
        {query : The name to search for}
        {--s|source=qobuz : Qobuz, Tidal, Soundcloud, Deezer, or Deezloader}
        {--t|type=album : Album, Playlist, Track, or Artist}
    """

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
    Browse and download items in interactive mode.

    discover
        {--s|scrape : Download all of the items in the list}
        {--m|max-items=50 : The number of items to fetch}
        {list=ideal-discography : The list to fetch}
    """

    help = (
        "\nAvailable options for <info>list</info>:\n\n"
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
    Manage the configuration file

    {--o|open : Open the config file in the default application}
    {--ov|open-vim : Open the config file in (neo)vim}
    {--d|directory : Open the directory that the config file is located in}
    {--p|path : Show the config file's path}
    {--q|qobuz : Set the credentials for Qobuz}
    {--t|tidal : Log into Tidal}
    {--dz|deezer : Set the Deezer ARL}
    {--reset : Reset the config file}
    {--update : Reset the config file, keeping the credentials}
    """


class Application(BaseApplication):
    def __init__(self):
        super().__init__("rip", __version__)

    def _run(self, io):
        if io.is_debug():
            logger.setLevel(logging.DEBUG)

        super()._run(io)

    # @property
    # def _default_definition(self):
    #     default_globals = super()._default_definition
    #     default_globals.add_option(Option("convert", shortcut="c", flag=False))
    #     return default_globals


# class ConvertCommand(Command):
#     pass


# class RepairCommand(Command):
#     pass


def clean_options(*opts):
    return tuple(o.replace("=", "").strip() for o in opts)


def main():
    application = Application()
    application.add(DownloadCommand())
    application.add(SearchCommand())
    application.add(DiscoverCommand())
    application.add(LastfmCommand())
    # application.add(ConfigCommand())
    application.run()


if __name__ == "__main__":
    main()
