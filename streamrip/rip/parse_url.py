from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

from ..client import Client, SoundcloudClient
from ..config import Config
from ..db import Database
from ..media import (
    Pending,
    PendingAlbum,
    PendingArtist,
    PendingLabel,
    PendingPlaylist,
    PendingSingle,
)

logger = logging.getLogger("streamrip")
URL_REGEX = re.compile(
    r"https?://(?:www|open|play|listen)?\.?(qobuz|tidal|deezer)\.com(?:(?:/(album|artist|track|playlist|video|label))|(?:\/[-\w]+?))+\/([-\w]+)",
)
SOUNDCLOUD_URL_REGEX = re.compile(r"https://soundcloud.com/[-\w:/]+")
LASTFM_URL_REGEX = re.compile(r"https://www.last.fm/user/\w+/playlists/\w+")
QOBUZ_INTERPRETER_URL_REGEX = re.compile(
    r"https?://www\.qobuz\.com/\w\w-\w\w/interpreter/[-\w]+/([-\w]+)",
)
YOUTUBE_URL_REGEX = re.compile(r"https://www\.youtube\.com/watch\?v=[-\w]+")


class URL(ABC):
    match: re.Match
    source: str

    def __init__(self, match: re.Match, source: str):
        self.match = match
        self.source = source

    @classmethod
    @abstractmethod
    def from_str(cls, url: str) -> URL | None:
        raise NotImplementedError

    @abstractmethod
    async def into_pending(
        self,
        client: Client,
        config: Config,
        db: Database,
    ) -> Pending:
        raise NotImplementedError


class GenericURL(URL):
    @classmethod
    def from_str(cls, url: str) -> URL | None:
        generic_url = URL_REGEX.match(url)
        if generic_url is None:
            return None

        source, media_type, item_id = generic_url.groups()
        if source is None or media_type is None or item_id is None:
            return None

        return cls(generic_url, source)

    async def into_pending(
        self,
        client: Client,
        config: Config,
        db: Database,
    ) -> Pending:
        source, media_type, item_id = self.match.groups()
        assert client.source == source

        if media_type == "track":
            return PendingSingle(item_id, client, config, db)
        elif media_type == "album":
            return PendingAlbum(item_id, client, config, db)
        elif media_type == "playlist":
            return PendingPlaylist(item_id, client, config, db)
        elif media_type == "artist":
            return PendingArtist(item_id, client, config, db)
        elif media_type == "label":
            return PendingLabel(item_id, client, config, db)
        raise NotImplementedError


class QobuzInterpreterURL(URL):
    interpreter_artist_regex = re.compile(r"getSimilarArtist\(\s*'(\w+)'")

    @classmethod
    def from_str(cls, url: str) -> URL | None:
        qobuz_interpreter_url = QOBUZ_INTERPRETER_URL_REGEX.match(url)
        if qobuz_interpreter_url is None:
            return None

        return cls(qobuz_interpreter_url, "qobuz")

    async def into_pending(
        self,
        client: Client,
        config: Config,
        db: Database,
    ) -> Pending:
        url = self.match.group(0)
        possible_id = self.match.group(1)
        if possible_id.isdigit():
            logger.debug("Found artist ID %s in interpreter url %s", possible_id, url)
            artist_id = possible_id
        else:
            artist_id = await self.extract_interpreter_url(url, client)
        return PendingArtist(artist_id, client, config, db)

    @staticmethod
    async def extract_interpreter_url(url: str, client: Client) -> str:
        """Extract artist ID from a Qobuz interpreter url.

        :param url: Urls of the form "https://www.qobuz.com/us-en/interpreter/{artist}/download-streaming-albums"
        :type url: str
        :rtype: str
        """
        async with client.session.get(url) as resp:
            match = QobuzInterpreterURL.interpreter_artist_regex.search(
                await resp.text(),
            )

        if match:
            return match.group(1)

        raise Exception(
            "Unable to extract artist id from interpreter url. Use a "
            "url that contains an artist id.",
        )


class DeezerDynamicURL(URL):
    standard_link_re = re.compile(
        r"https://www\.deezer\.com/[a-z]{2}/(album|artist|playlist|track)/(\d+)"
    )
    dynamic_link_re = re.compile(r"https://deezer\.page\.link/\w+")

    @classmethod
    def from_str(cls, url: str) -> URL | None:
        match = cls.dynamic_link_re.match(url)
        if match is None:
            return None

        return cls(match, "deezer")

    async def into_pending(
        self,
        client: Client,
        config: Config,
        db: Database,
    ) -> Pending:
        url = self.match.group(0)  # entire dynamic link
        media_type, item_id = await self._extract_info_from_dynamic_link(url, client)
        if media_type == "track":
            return PendingSingle(item_id, client, config, db)
        elif media_type == "album":
            return PendingAlbum(item_id, client, config, db)
        elif media_type == "playlist":
            return PendingPlaylist(item_id, client, config, db)
        elif media_type == "artist":
            return PendingArtist(item_id, client, config, db)
        elif media_type == "label":
            return PendingLabel(item_id, client, config, db)
        raise NotImplementedError

    @classmethod
    async def _extract_info_from_dynamic_link(
        cls, url: str, client: Client
    ) -> tuple[str, str]:
        """Extract the item's type and ID from a dynamic link.

        :param url:
        :type url: str
        :rtype: Tuple[str, str] (media type, item id)
        """
        async with client.session.get(url) as resp:
            match = cls.standard_link_re.search(await resp.text())

        if match:
            return match.group(1), match.group(2)

        raise Exception("Unable to extract Deezer dynamic link.")


class SoundcloudURL(URL):
    source = "soundcloud"

    def __init__(self, url: str):
        self.url = url

    async def into_pending(
        self,
        client: SoundcloudClient,
        config: Config,
        db: Database,
    ) -> Pending:
        resolved = await client.resolve_url(self.url)
        media_type = resolved["kind"]
        item_id = str(resolved["id"])
        if media_type == "track":
            return PendingSingle(item_id, client, config, db)
        elif media_type == "playlist":
            return PendingPlaylist(item_id, client, config, db)
        else:
            raise NotImplementedError(media_type)

    @classmethod
    def from_str(cls, url: str):
        soundcloud_url = SOUNDCLOUD_URL_REGEX.match(url)
        if soundcloud_url is None:
            return None
        return cls(soundcloud_url.group(0))


def parse_url(url: str) -> URL | None:
    """Return a URL type given a url string.

    Args:
    ----
        url (str): Url to parse

    Returns: A URL type, or None if nothing matched.
    """
    url = url.strip()
    parsed_urls: list[URL | None] = [
        GenericURL.from_str(url),
        QobuzInterpreterURL.from_str(url),
        SoundcloudURL.from_str(url),
        DeezerDynamicURL.from_str(url),
        # TODO: the rest of the url types
    ]
    return next((u for u in parsed_urls if u is not None), None)
