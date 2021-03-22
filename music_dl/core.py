import logging
import os
import re
from getpass import getpass
from typing import Generator, Optional, Tuple, Union

import click

from .clients import DeezerClient, QobuzClient, TidalClient
from .config import Config
from .constants import CONFIG_PATH, DB_PATH, URL_REGEX
from .db import MusicDB
from .downloader import Album, Artist, Playlist, Track, Label
from .exceptions import AuthenticationError, ParsingError
from .utils import capitalize

logger = logging.getLogger(__name__)


MEDIA_CLASS = {"album": Album, "playlist": Playlist, "artist": Artist, "track": Track, "label": Label}
CLIENTS = {"qobuz": QobuzClient, "tidal": TidalClient, "deezer": DeezerClient}
Media = Union[Album, Playlist, Artist, Track]  # type hint

# TODO: add support for database


class MusicDL:
    def __init__(
        self,
        config: Optional[Config] = None,
        database: Optional[str] = None,
    ):
        logger.debug(locals())

        self.url_parse = re.compile(URL_REGEX)
        self.config = config
        if self.config is None:
            self.config = Config(CONFIG_PATH)

        self.clients = {
            "qobuz": QobuzClient(),
            "tidal": TidalClient(),
            "deezer": DeezerClient(),
        }

        if database is None:
            self.db = MusicDB(DB_PATH)
        else:
            assert isinstance(database, MusicDB)
            self.db = database

    def prompt_creds(self, source: str):
        """Prompt the user for credentials.

        :param source:
        :type source: str
        """
        click.secho(f"Enter {capitalize(source)} email:", fg="green")
        self.config[source]["email"] = input()
        click.secho(
            f"Enter {capitalize(source)} password (will not show on screen):",
            fg="green",
        )
        self.config[source]["password"] = getpass(
            prompt=""
        )  # does hashing work for tidal?

        self.config.save()
        click.secho(f'Credentials saved to config file at "{self.config._path}"')

    def assert_creds(self, source: str):
        assert source in ("qobuz", "tidal", "deezer"), f"Invalid source {source}"
        if source == "deezer":
            # no login for deezer
            return

        if (
            self.config[source]["email"] is None
            or self.config[source]["password"] is None
        ):
            self.prompt_creds(source)

    def handle_url(self, url: str):
        """Download an url

        :param url:
        :type url: str
        :raises InvalidSourceError
        :raises ParsingError
        """
        source, url_type, item_id = self.parse_url(url)
        if item_id in self.db:
            logger.info(f"{url} already downloaded, use --no-db to override.")
            return
        self.handle_item(source, url_type, item_id)

    def handle_item(self, source: str, media_type: str, item_id: str):
        self.assert_creds(source)

        arguments = {
            "database": self.db,
            "parent_folder": self.config.downloads["folder"],
            "quality": self.config.downloads["quality"],
            "embed_cover": self.config.metadata["embed_cover"],
        }

        client = self.clients[source]
        if not client.logged_in:
            while True:
                try:
                    client.login(**self.config.creds(source))
                    break
                except AuthenticationError:
                    click.secho("Invalid credentials, try again.")
                    self.prompt_creds(source)

        item = MEDIA_CLASS[media_type](client=client, id=item_id)
        if isinstance(item, Artist):
            keys = self.config.filters.keys()
            # TODO: move this to config.py
            filters_ = tuple(key for key in keys if self.config.filters[key])
            arguments["filters"] = filters_
            logger.debug("Added filter argument for artist/label: %s", filters_)

        logger.debug("Arguments from config: %s", arguments)

        item.load_meta()
        item.download(**arguments)

    def parse_url(self, url: str) -> Tuple[str, str]:
        """Returns the type of the url and the id.

        Compatible with urls of the form:
            https://www.qobuz.com/us-en/{type}/{name}/{id}
            https://open.qobuz.com/{type}/{id}
            https://play.qobuz.com/{type}/{id}
            /us-en/{type}/-/{id}

            https://www.deezer.com/us/{type}/{id}
            https://tidal.com/browse/{type}/{id}

        :raises exceptions.ParsingError
        """
        parsed = self.url_parse.search(url)

        if parsed is not None:
            parsed = parsed.groups()

            if len(parsed) == 3:
                return tuple(parsed)  # Convert from Seq for the sake of typing

        raise ParsingError(f"Error parsing URL: `{url}`")

    def from_txt(self, filepath: Union[str, os.PathLike]):
        """
        Handle a text file containing URLs. Lines starting with `#` are ignored.

        :param filepath:
        :type filepath: Union[str, os.PathLike]
        :raises OSError
        :raises exceptions.ParsingError
        """
        with open(filepath) as txt:
            lines = (
                line for line in txt.readlines() if not line.strip().startswith("#")
            )

            click.secho(f"URLs found in text file: {len(lines)}")

            for line in lines:
                self.handle_url(line)

    def search(
        self, query: str, media_type: str = "album", limit: int = 200
    ) -> Generator:
        results = self.client.search(query, media_type, limit)

        if isinstance(results, Generator):  # QobuzClient
            for page in results:
                for item in page[f"{media_type}s"]["items"]:
                    yield MEDIA_CLASS[media_type].from_api(item, self.client)
        else:
            for item in results.get("data") or results.get("items"):
                yield MEDIA_CLASS[media_type].from_api(item, self.client)
