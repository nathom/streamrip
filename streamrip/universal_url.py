from __future__ import annotations

import re
from abc import ABC, abstractmethod

from .album import PendingAlbum
from .client import Client
from .config import Config
from .media import Pending
from .playlist import PendingPlaylist
from .soundcloud_client import SoundcloudClient
from .track import PendingSingle
from .validation_regexps import (
    DEEZER_DYNAMIC_LINK_REGEX,
    LASTFM_URL_REGEX,
    QOBUZ_INTERPRETER_URL_REGEX,
    SOUNDCLOUD_URL_REGEX,
    URL_REGEX,
    YOUTUBE_URL_REGEX,
)


class URL(ABC):
    match: re.Match
    source: str

    def __init__(self, match: re.Match, source: str):
        self.match = match
        self.source = source

    @abstractmethod
    def from_str(cls, url: str) -> URL | None:
        raise NotImplementedError

    @abstractmethod
    async def into_pending(self, client: Client, config: Config) -> Pending:
        raise NotImplementedError


class GenericURL(URL):
    @classmethod
    def from_str(cls, url: str) -> URL | None:
        generic_url = URL_REGEX.match(url)
        if generic_url is None:
            return None
        source = generic_url.group(1)
        return cls(generic_url, source)

    async def into_pending(self, client: Client, config: Config) -> Pending:
        source, media_type, item_id = self.match.groups()
        assert client.source == source

        if media_type == "track":
            return PendingSingle(item_id, client, config)
        elif media_type == "album":
            return PendingAlbum(item_id, client, config)
        else:
            raise NotImplementedError


class QobuzInterpreterURL(URL):
    interpreter_artist_regex = re.compile(r"getSimilarArtist\(\s*'(\w+)'")

    @classmethod
    def from_str(cls, url: str) -> URL | None:
        qobuz_interpreter_url = QOBUZ_INTERPRETER_URL_REGEX.match(url)
        if qobuz_interpreter_url is None:
            return None
        return cls(qobuz_interpreter_url, "qobuz")

    async def into_pending(self, client: Client, config: Config) -> Pending:
        url = self.match.group(0)
        artist_id = await self.extract_interpreter_url(url, client)
        raise NotImplementedError
        # return PendingArtist()

    @staticmethod
    async def extract_interpreter_url(url: str, client: Client) -> str:
        """Extract artist ID from a Qobuz interpreter url.

        :param url: Urls of the form "https://www.qobuz.com/us-en/interpreter/{artist}/download-streaming-albums"
        :type url: str
        :rtype: str
        """
        async with client.session.get(url) as resp:
            match = QobuzInterpreterURL.interpreter_artist_regex.search(
                await resp.text()
            )

        if match:
            return match.group(1)

        raise Exception(
            "Unable to extract artist id from interpreter url. Use a "
            "url that contains an artist id."
        )


class DeezerDynamicURL(URL):
    pass


class SoundcloudURL(URL):
    source = "soundcloud"

    def __init__(self, url: str):
        self.url = url

    async def into_pending(self, client: SoundcloudClient, config: Config) -> Pending:
        resolved = await client._resolve_url(self.url)
        media_type = resolved["kind"]
        item_id = str(resolved["id"])
        if media_type == "track":
            return PendingSingle(item_id, client, config)
        elif media_type == "playlist":
            return PendingPlaylist(item_id, client, config)
        else:
            raise NotImplementedError(media_type)

    @classmethod
    def from_str(cls, url: str):
        soundcloud_url = SOUNDCLOUD_URL_REGEX.match(url)
        if soundcloud_url is None:
            return None
        return cls(soundcloud_url.group(0))


class LastFmURL(URL):
    pass


def parse_url(url: str) -> URL | None:
    """Return a URL type given a url string.

    Args:
        url (str): Url to parse

    Returns: A URL type, or None if nothing matched.
    """
    url = url.strip()
    parsed_urls: list[URL | None] = [
        GenericURL.from_str(url),
        QobuzInterpreterURL.from_str(url),
        SoundcloudURL.from_str(url),
        # TODO: the rest of the url types
    ]
    return next((u for u in parsed_urls if u is not None), None)


# TODO: recycle this class
class UniversalURL:
    """
    >>> u = UniversalURL.from_str('https://sampleurl.com')
    >>> if u is not None:
    >>>     pending = await u.into_pending_item()
    """

    source: str
    media_type: str | None
    match: re.Match | None

    def __init__(self, url: str):
        url = url.strip()
        qobuz_interpreter_url = QOBUZ_INTERPRETER_URL_REGEX.match(url)
        if qobuz_interpreter_url is not None:
            self.source = "qobuz"
            self.media_type = "artist"
            self.url_type = "interpreter"
            self.match = qobuz_interpreter_url
            return

        deezer_dynamic_url = DEEZER_DYNAMIC_LINK_REGEX.match(url)
        if deezer_dynamic_url is not None:
            self.match = deezer_dynamic_url
            self.source = "deezer"
            self.media_type = None
            self.url_type = "deezer_dynamic"
            return

        soundcloud_url = SOUNDCLOUD_URL_REGEX.match(url)
        if soundcloud_url is not None:
            self.match = soundcloud_url
            self.source = "soundcloud"
            self.media_type = None
            self.url_type = "soundcloud"
            return

        generic_url = URL_REGEX.match(url)
        if generic_url is not None:
            self.match = generic_url
            self.source = self.match.group(1)
            self.media_type = self.match.group(2)
            self.url_type = "generic"

    async def into_pending_item(self, client: Client, config: Config) -> Pending | None:
        if self.url_type == "generic":
            assert self.match is not None
            item_id = self.match.group(3)
            assert isinstance(item_id, str)
            assert client.source == self.source

            if self.media_type == "track":
                return PendingSingle(item_id, client, config)
            elif self.media_type == "album":
                return PendingAlbum(item_id, client, config)
            else:
                raise NotImplementedError

        else:
            raise NotImplementedError
