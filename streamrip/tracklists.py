"""These classes parse information from Clients into a universal,
downloadable form.
"""

import functools
import logging
import os
import re
from tempfile import gettempdir
from typing import Generator, Iterable, Union

import click
from pathvalidate import sanitize_filename

from .bases import Booklet, Track, Tracklist, Video
from .clients import Client
from .constants import ALBUM_KEYS, FLAC_MAX_BLOCKSIZE, FOLDER_FORMAT
from .db import MusicDB
from .exceptions import InvalidSourceError, NonStreamable
from .metadata import TrackMetadata
from .utils import (
    clean_format,
    get_container,
    safe_get,
    tidal_cover_url,
    tqdm_download,
)

logger = logging.getLogger(__name__)

TYPE_REGEXES = {
    "remaster": re.compile(r"(?i)(re)?master(ed)?"),
    "extra": re.compile(r"(?i)(anniversary|deluxe|live|collector|demo|expanded|remix)"),
}


class Album(Tracklist):
    """Represents a downloadable album.

    Usage:

    >>> resp = client.get('fleetwood mac rumours', 'album')
    >>> album = Album.from_api(resp['items'][0], client)
    >>> album.load_meta()
    >>> album.download()
    """

    def __init__(self, client: Client, **kwargs):
        """Create a new Album object.

        :param client: a qopy client instance
        :param album_id: album id returned by qobuz api
        :type album_id: Union[str, int]
        :param kwargs:
        """
        self.client = client

        self.sampling_rate = None
        self.bit_depth = None
        self.container = None

        # usually an unpacked TrackMetadata.asdict()
        self.__dict__.update(kwargs)

        # to improve from_api method speed
        if kwargs.get("load_on_init", False):
            self.load_meta()

        self.loaded = False
        self.downloaded = False

    def load_meta(self):
        """Load detailed metadata from API using the id."""

        assert hasattr(self, "id"), "id must be set to load metadata"
        resp = self.client.get(self.id, media_type="album")

        # update attributes based on response
        self.meta = self._parse_get_resp(resp, self.client)
        self.__dict__.update(self.meta.asdict())  # used for identification

        if not self.get("streamable", False):
            raise NonStreamable(f"This album is not streamable ({self.id} ID)")

        self._load_tracks(resp)
        self.loaded = True

    @classmethod
    def from_api(cls, resp: dict, client: Client):
        if client.source == "soundcloud":
            return Playlist.from_api(resp, client)

        info = cls._parse_get_resp(resp, client)
        return cls(client, **info.asdict())

    def _prepare_download(self, **kwargs):
        # Generate the folder name
        self.folder_format = kwargs.get("folder_format", FOLDER_FORMAT)
        self.quality = min(kwargs.get("quality", 3), self.client.max_quality)
        self.folder = self._get_formatted_folder(
            kwargs.get("parent_folder", "StreamripDownloads"), self.quality
        )
        os.makedirs(self.folder, exist_ok=True)

        self.download_message()

        # choose optimal cover size and download it
        click.secho("Downloading cover art", fg="magenta")
        cover_path = os.path.join(gettempdir(), f"cover_{hash(self)}.jpg")
        embed_cover_size = kwargs.get("embed_cover_size", "large")

        assert (
            embed_cover_size in self.cover_urls
        ), f"Invalid cover size. Must be in {self.cover_urls.keys()}"

        embed_cover_url = self.cover_urls[embed_cover_size]
        if embed_cover_url is not None:
            tqdm_download(embed_cover_url, cover_path)
        else:  # sometimes happens with Deezer
            cover_url = functools.reduce(
                lambda c1, c2: c1 or c2, self.cover_urls.values()
            )
            tqdm_download(cover_url, cover_path)

        if kwargs.get("keep_hires_cover", True):
            tqdm_download(
                self.cover_urls["original"], os.path.join(self.folder, "cover.jpg")
            )

        cover_size = os.path.getsize(cover_path)
        if cover_size > FLAC_MAX_BLOCKSIZE:  # 16.77 MB
            click.secho(
                "Downgrading embedded cover size, too large ({cover_size}).",
                fg="bright_yellow",
            )
            # large is about 600x600px which is guaranteed < 16.7 MB
            tqdm_download(self.cover_urls["large"], cover_path)

        embed_cover = kwargs.get("embed_cover", True)  # embed by default
        if self.client.source != "deezer" and embed_cover:
            # container generated when formatting folder name
            self.cover_obj = self.get_cover_obj(
                cover_path, self.container, self.client.source
            )
        else:
            self.cover_obj = None

        # Download the booklet if applicable
        if self.get("booklets") and kwargs.get("download_booklets", True):
            click.secho("\nDownloading booklets", fg="blue")
            for item in self.booklets:
                Booklet(item).download(parent_folder=self.folder)

    def _download_item(
        self,
        track: Union[Track, Video],
        quality: int = 3,
        database: MusicDB = None,
        **kwargs,
    ) -> bool:
        logger.debug("Downloading track to %s", self.folder)
        if self.disctotal > 1 and isinstance(track, Track):
            disc_folder = os.path.join(self.folder, f"Disc {track.meta.discnumber}")
            kwargs["parent_folder"] = disc_folder
        else:
            kwargs["parent_folder"] = self.folder

        if not track.download(quality=quality, database=database, **kwargs):
            return False

        logger.debug("tagging tracks")
        # deezer tracks come tagged
        if kwargs.get("tag_tracks", True) and self.client.source != "deezer":
            track.tag(cover=self.cover_obj, embed_cover=kwargs.get("embed_cover", True))

        return True

    @staticmethod
    def _parse_get_resp(resp: dict, client: Client) -> dict:
        """Parse information from a client.get(query, 'album') call.

        :param resp:
        :type resp: dict
        :rtype: dict
        """
        meta = TrackMetadata(album=resp, source=client.source)
        meta.id = resp["id"]
        return meta

    def _load_tracks(self, resp):
        """Given an album metadata dict returned by the API, append all of its
        tracks to `self`.

        This uses a classmethod to convert an item into a Track object, which
        stores the metadata inside a TrackMetadata object.
        """
        logging.debug(f"Loading {self.tracktotal} tracks to album")
        for track in _get_tracklist(resp, self.client.source):
            if track.get("type") == "Music Video":
                self.append(
                    Video.from_album_meta(
                        track,
                        self.client,
                    )
                )
            else:
                self.append(
                    Track.from_album_meta(
                        album=self.meta,
                        track=track,
                        client=self.client,
                    )
                )

    def _get_formatter(self) -> dict:
        fmt = dict()
        for key in ALBUM_KEYS:
            # default to None
            fmt[key] = self.get(key)

        if fmt.get("sampling_rate", False):
            fmt["sampling_rate"] /= 1000
            # change 48.0kHz -> 48kHz, 44.1kHz -> 44.1kHz
            if fmt["sampling_rate"] % 1 == 0.0:
                fmt["sampling_rate"] = int(fmt["sampling_rate"])

        return fmt

    def _get_formatted_folder(self, parent_folder: str, quality: int) -> str:
        # necessary to format the folder
        self.container = get_container(quality, self.client.source)
        if self.container in ("AAC", "MP3"):
            # lossy codecs don't have these metrics
            self.bit_depth = self.sampling_rate = None

        formatted_folder = clean_format(self.folder_format, self._get_formatter())

        return os.path.join(parent_folder, formatted_folder)

    @property
    def title(self) -> str:
        return self.album

    @title.setter
    def title(self, val: str):
        self.album = val

    def __repr__(self) -> str:
        """Return a string representation of this Album object.

        :rtype: str
        """
        # Avoid AttributeError if load_on_init key is not set
        if hasattr(self, "albumartist"):
            return f"<Album: {self.albumartist} - {self.title}>"

        return f"<Album: V/A - {self.title}>"

    def __str__(self) -> str:
        """Return a readable string representation of
        this album.

        :rtype: str
        """
        return f"{self['albumartist']} - {self['title']}"

    def __len__(self) -> int:
        return self.tracktotal

    def __hash__(self):
        return hash(self.id)


class Playlist(Tracklist):
    """Represents a downloadable playlist.

    Usage:
    >>> resp = client.search('hip hop', 'playlist')
    >>> pl = Playlist.from_api(resp['items'][0], client)
    >>> pl.load_meta()
    >>> pl.download()
    """

    def __init__(self, client: Client, **kwargs):
        """Create a new Playlist object.

        :param client: a qopy client instance
        :param album_id: playlist id returned by qobuz api
        :type album_id: Union[str, int]
        :param kwargs:
        """
        self.client = client

        for k, v in kwargs.items():
            setattr(self, k, v)

        # to improve from_api method speed
        if kwargs.get("load_on_init"):
            self.load_meta()

        self.loaded = False

    @classmethod
    def from_api(cls, resp: dict, client: Client):
        """Return a Playlist object initialized with information from
        a search result returned by the API.

        :param resp: a single search result entry of a playlist
        :type resp: dict
        :param client:
        :type client: Client
        """
        info = cls._parse_get_resp(resp, client)
        return cls(client, **info)

    def load_meta(self, **kwargs):
        """Send a request to fetch the tracklist from the api.

        :param new_tracknumbers: replace the tracknumber with playlist position
        :type new_tracknumbers: bool
        :param kwargs:
        """
        self.meta = self.client.get(self.id, media_type="playlist")
        logger.debug(self.meta)
        self._load_tracks(**kwargs)
        self.loaded = True

    def _load_tracks(self, new_tracknumbers: bool = True):
        """Parses the tracklist returned by the API.

        :param new_tracknumbers: replace tracknumber tag with playlist position
        :type new_tracknumbers: bool
        """
        if self.client.source == "qobuz":
            self.name = self.meta["name"]
            self.image = self.meta["images"]
            self.creator = safe_get(self.meta, "owner", "name", default="Qobuz")

            tracklist = self.meta["tracks"]["items"]

            def gen_cover(track):
                return track["album"]["image"]["small"]

            def meta_args(track):
                return {"track": track, "album": track["album"]}

        elif self.client.source == "tidal":
            self.name = self.meta["title"]
            self.image = tidal_cover_url(self.meta["image"], 640)
            self.creator = safe_get(self.meta, "creator", "name", default="TIDAL")

            tracklist = self.meta["tracks"]

            def gen_cover(track):
                cover_url = tidal_cover_url(track["album"]["cover"], 640)
                return cover_url

            def meta_args(track):
                return {
                    "track": track,
                    "source": self.client.source,
                }

        elif self.client.source == "deezer":
            self.name = self.meta["title"]
            self.image = self.meta["picture_big"]
            self.creator = safe_get(self.meta, "creator", "name", default="Deezer")

            tracklist = self.meta["tracks"]

            def gen_cover(track):
                return track["album"]["cover_medium"]

        elif self.client.source == "soundcloud":
            self.name = self.meta["title"]
            # self.image = self.meta.get("artwork_url").replace("large", "t500x500")
            self.creator = self.meta["user"]["username"]
            tracklist = self.meta["tracks"]

            def gen_cover(track):
                return track["artwork_url"].replace("large", "t500x500")

        else:
            raise NotImplementedError

        self.tracktotal = len(tracklist)
        if self.client.source == "soundcloud":
            # No meta is included in soundcloud playlist
            # response, so it is loaded at download time
            for track in tracklist:
                self.append(Track(self.client, id=track["id"]))
        else:
            for track in tracklist:
                # TODO: This should be managed with .m3u files and alike. Arbitrary
                # tracknumber tags might cause conflicts if the playlist files are
                # inside of a library folder
                meta = TrackMetadata(track=track, source=self.client.source)

                self.append(
                    Track(
                        self.client,
                        id=track.get("id"),
                        meta=meta,
                        cover_url=gen_cover(track),
                    )
                )

        logger.debug(f"Loaded {len(self)} tracks from playlist {self.name}")

    def _prepare_download(self, parent_folder: str = "StreamripDownloads", **kwargs):
        fname = sanitize_filename(self.name)
        self.folder = os.path.join(parent_folder, fname)

        self.__download_index = 1  # used for tracknumbers
        self.download_message()

    def _download_item(self, item: Track, **kwargs):
        kwargs['parent_folder'] = self.folder
        if self.client.source == "soundcloud":
            item.load_meta()
            click.secho(f"Downloading {item!s}", fg='blue')

        if kwargs.get("set_playlist_to_album", False):
            item["album"] = self.name
            item["albumartist"] = self.creator

        if kwargs.get("new_tracknumbers", True):
            item["tracknumber"] = self.__download_index
            item["discnumber"] = 1
            self.__download_index += 1

        self.downloaded = item.download(**kwargs)

        if self.downloaded and self.client.source != "deezer":
            item.tag(embed_cover=kwargs.get("embed_cover", True))

        return self.downloaded

    @staticmethod
    def _parse_get_resp(item: dict, client: Client) -> dict:
        """Parses information from a search result returned
        by a client.search call.

        :param item:
        :type item: dict
        :param client:
        :type client: Client
        """
        if client.source == "qobuz":
            return {
                "name": item["name"],
                "id": item["id"],
            }
        elif client.source == "tidal":
            return {
                "name": item["title"],
                "id": item["uuid"],
            }
        elif client.source == "deezer":
            return {
                "name": item["title"],
                "id": item["id"],
            }
        elif client.source == "soundcloud":
            return {
                "name": item["title"],
                "id": item["permalink_url"],
                "description": item["description"],
                "popularity": f"{item['likes_count']} likes",
                "tracktotal": len(item["tracks"]),
            }

        raise InvalidSourceError(client.source)

    @property
    def title(self) -> str:
        return self.name

    def __repr__(self) -> str:
        """Return a string representation of this Playlist object.

        :rtype: str
        """
        return f"<Playlist: {self.name}>"

    def __str__(self) -> str:
        """Return a readable string representation of
        this track.

        :rtype: str
        """
        return f"{self.name} ({len(self)} tracks)"


class Artist(Tracklist):
    """Represents a downloadable artist.

    Usage:
    >>> resp = client.get('fleetwood mac', 'artist')
    >>> artist = Artist.from_api(resp['items'][0], client)
    >>> artist.load_meta()
    >>> artist.download()
    """

    def __init__(self, client: Client, **kwargs):
        """Create a new Artist object.

        :param client: a qopy client instance
        :param album_id: artist id returned by qobuz api
        :type album_id: Union[str, int]
        :param kwargs:
        """
        self.client = client

        for k, v in kwargs.items():
            setattr(self, k, v)

        # to improve from_api method speed
        if kwargs.get("load_on_init"):
            self.load_meta()

        self.loaded = False

    def load_meta(self):
        """Send an API call to get album info based on id."""
        self.meta = self.client.get(self.id, media_type="artist")
        self._load_albums()
        self.loaded = True

    # override
    def download(self, **kwargs):
        iterator = self._prepare_download(**kwargs)
        for item in iterator:
            self._download_item(item, **kwargs)

    def _load_albums(self):
        """From the discography returned by client.get(query, 'artist'),
        generate album objects and append them to self.
        """
        if self.client.source == "qobuz":
            self.name = self.meta["name"]
            albums = self.meta["albums"]["items"]

        elif self.client.source == "tidal":
            self.name = self.meta["name"]
            albums = self.meta["albums"]

        elif self.client.source == "deezer":
            # TODO: load artist name
            albums = self.meta["albums"]

        else:
            raise InvalidSourceError(self.client.source)

        for album in albums:
            logger.debug("Appending album: %s", album.get("title"))
            self.append(Album.from_api(album, self.client))

    def _prepare_download(
        self, parent_folder: str = "StreamripDownloads", filters: tuple = (), **kwargs
    ) -> Iterable:
        folder = sanitize_filename(self.name)
        folder = os.path.join(parent_folder, folder)

        logger.debug("Artist folder: %s", folder)
        logger.debug(f"Length of tracklist {len(self)}")
        logger.debug(f"Filters: {filters}")

        if "repeats" in filters:
            final = self._remove_repeats(bit_depth=max, sampling_rate=min)
            filters = tuple(f for f in filters if f != "repeats")
        else:
            final = self

        if isinstance(filters, tuple) and self.client.source == "qobuz":
            filter_funcs = (getattr(self, f"_{filter_}") for filter_ in filters)
            for func in filter_funcs:
                final = filter(func, final)

        self.download_message()
        return final

    def _download_item(
        self,
        item,
        parent_folder: str = "StreamripDownloads",
        quality: int = 3,
        database: MusicDB = None,
        **kwargs,
    ) -> bool:
        try:
            item.load_meta()
        except NonStreamable:
            logger.info("Skipping album, not available to stream.")
            return

        # always an Album
        status = item.download(
            parent_folder=parent_folder,
            quality=quality,
            database=database,
            **kwargs,
        )
        return status

    @property
    def title(self) -> str:
        return self.name

    @classmethod
    def from_api(cls, item: dict, client: Client, source: str = "qobuz"):
        """Create an Artist object from the api response of Qobuz, Tidal,
        or Deezer.

        :param resp: response dict
        :type resp: dict
        :param source: in ('qobuz', 'deezer', 'tidal')
        :type source: str
        """
        logging.debug("Loading item from API")
        info = cls._parse_get_resp(item, client)

        # equivalent to Artist(client=client, **info)
        return cls(client=client, **info)

    @staticmethod
    def _parse_get_resp(item: dict, client: Client) -> dict:
        """Parse a result from a client.search call.

        :param item: the item to parse
        :type item: dict
        :param client:
        :type client: Client
        """
        if client.source in ("qobuz", "deezer"):
            info = {
                "name": item.get("name"),
                "id": item.get("id"),
            }
        elif client.source == "tidal":
            info = {
                "name": item["name"],
                "id": item["id"],
            }
        else:
            raise InvalidSourceError(client.source)

        return info

    # ----------- Filters --------------

    def _remove_repeats(self, bit_depth=max, sampling_rate=max) -> Generator:
        """Remove the repeated albums from self. May remove different
        versions of the same album.

        :param bit_depth: either max or min functions
        :param sampling_rate: either max or min functions
        """
        groups = dict()
        for album in self:
            if (t := self.essence(album.title)) not in groups:
                groups[t] = []
            groups[t].append(album)

        for group in groups.values():
            assert bit_depth in (min, max) and sampling_rate in (min, max)
            best_bd = bit_depth(a["bit_depth"] for a in group)
            best_sr = sampling_rate(a["sampling_rate"] for a in group)
            for album in group:
                if album["bit_depth"] == best_bd and album["sampling_rate"] == best_sr:
                    yield album
                    break

    def _non_studio_albums(self, album: Album) -> bool:
        """Passed as a parameter by the user.

        This will download only studio albums.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return (
            album["albumartist"] != "Various Artists"
            and TYPE_REGEXES["extra"].search(album.title) is None
        )

    def _features(self, album: Album) -> bool:
        """Passed as a parameter by the user.

        This will download only albums where the requested
        artist is the album artist.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return self["name"] == album["albumartist"]

    def _extras(self, album: Album) -> bool:
        """Passed as a parameter by the user.

        This will skip any extras.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return TYPE_REGEXES["extra"].search(album.title) is None

    def _non_remasters(self, album: Album) -> bool:
        """Passed as a parameter by the user.

        This will download only remasterd albums.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return TYPE_REGEXES["remaster"].search(album.title) is not None

    def _non_albums(self, album: Album) -> bool:
        """This will ignore non-album releases.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        # Doesn't work yet
        return album["release_type"] == "album"

    # --------- Magic Methods --------

    def __repr__(self) -> str:
        """Return a string representation of this Artist object.

        :rtype: str
        """
        return f"<Artist: {self.name}>"

    def __str__(self) -> str:
        """Return a readable string representation of
        this Artist.

        :rtype: str
        """
        return self.name

    def __hash__(self) -> int:
        return hash(self.id)


class Label(Artist):
    def load_meta(self):
        assert self.client.source == "qobuz", "Label source must be qobuz"

        resp = self.client.get(self.id, "label")
        self.name = resp["name"]
        for album in resp["albums"]["items"]:
            self.append(Album.from_api(album, client=self.client))

        self.loaded = True

    def __repr__(self):
        return f"<Label - {self.name}>"

    def __str__(self) -> str:
        """Return a readable string representation of
        this track.

        :rtype: str
        """
        return self.name


# ---------- misc utility functions -----------


def _get_tracklist(resp: dict, source: str) -> list:
    """Returns the tracklist from an API response.

    :param resp:
    :type resp: dict
    :param source:
    :type source: str
    :rtype: list
    """
    if source == "qobuz":
        return resp["tracks"]["items"]
    if source in ("tidal", "deezer"):
        return resp["tracks"]

    raise NotImplementedError(source)
