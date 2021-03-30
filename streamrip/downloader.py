import logging
import os
import re
import shutil
# import sys
from pprint import pformat
# from pprint import pprint
from tempfile import gettempdir
from typing import Any, Callable, Optional, Tuple, Union

import click
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from pathvalidate import sanitize_filename, sanitize_filepath

from . import converter
from .clients import ClientInterface
from .constants import (
    ALBUM_KEYS,
    EXT,
    FLAC_MAX_BLOCKSIZE,
    FOLDER_FORMAT,
    TRACK_FORMAT,
)
from .db import MusicDB
from .exceptions import (
    InvalidQuality,
    InvalidSourceError,
    NonStreamable,
    TooLargeCoverArt,
)
from .metadata import TrackMetadata
from .utils import (
    clean_format,
    decrypt_mqa_file,
    get_quality_id,
    safe_get,
    tidal_cover_url,
    tqdm_download,
)

logger = logging.getLogger(__name__)

TIDAL_Q_MAP = {
    "LOW": 0,
    "HIGH": 1,
    "LOSSLESS": 2,
    "HI_RES": 3,
}

# used to homogenize cover size keys
COVER_SIZES = ("thumbnail", "small", "large")

TYPE_REGEXES = {
    "remaster": re.compile(r"(?i)(re)?master(ed)?"),
    "extra": re.compile(r"(?i)(anniversary|deluxe|live|collector|demo|expanded)"),
}


class Track:
    """Represents a downloadable track.

    Loading metadata as a single track:
    >>> t = Track(client, id='20252078')
    >>> t.load_meta()  # load metadata from api

    Loading metadata as part of an Album:
    >>> t = Track.from_album_meta(api_track_dict, client)

    where `api_track_dict` is a track entry in an album tracklist.

    Downloading and tagging:
    >>> t.download()
    >>> t.tag()
    """

    def __init__(self, client: ClientInterface, **kwargs):
        """Create a track object.

        The only required parameter is client, but passing at an id is
        highly recommended. Every value in kwargs will be set as an attribute
        of the object. (TODO: make this safer)

        :param track_id: track id returned by Qobuz API
        :type track_id: Optional[Union[str, int]]
        :param client: qopy client
        :type client: ClientInterface
        :param meta: TrackMetadata object
        :type meta: Optional[TrackMetadata]
        :param kwargs: id, filepath_format, meta, quality, folder
        """
        self.client = client
        self.__dict__.update(kwargs)

        # adjustments after blind attribute sets
        self.file_format = kwargs.get("track_format", TRACK_FORMAT)
        self.container = "FLAC"
        self.sampling_rate = 44100
        self.bit_depth = 16

        self._is_downloaded = False
        self._is_tagged = False
        for attr in ("quality", "folder", "meta"):
            setattr(self, attr, None)

        if isinstance(kwargs.get("meta"), TrackMetadata):
            self.meta = kwargs["meta"]
        else:
            self.meta = None
            # `load_meta` must be called at some point
            logger.debug("Track: meta not provided")

        if (u := kwargs.get("cover_url")) is not None:
            logger.debug(f"Cover url: {u}")
            self.cover_url = u

    def load_meta(self):
        """Send a request to the client to get metadata for this Track."""

        assert hasattr(self, "id"), "id must be set before loading metadata"

        track_meta = self.client.get(self.id, media_type="track")
        self.meta = TrackMetadata(
            track=track_meta, source=self.client.source
        )  # meta dict -> TrackMetadata object
        try:
            if self.client.source == "qobuz":
                self.cover_url = track_meta["album"]["image"]["small"]
            elif self.client.source == "tidal":
                self.cover_url = tidal_cover_url(track_meta["album"]["cover"], 320)
            elif self.client.source == "deezer":
                self.cover_url = track_meta["album"]["cover_medium"]
            else:
                raise InvalidSourceError(self.client.source)
        except KeyError:
            logger.debug("No cover found")
            self.cover_url = None

    @staticmethod
    def _get_tracklist(resp, source):
        if source == "qobuz":
            return resp["tracks"]["items"]
        elif source in ("tidal", "deezer"):
            return resp["tracks"]

        raise NotImplementedError(source)

    def download(
        self,
        quality: int = 7,
        parent_folder: str = "Downloads",
        progress_bar: bool = True,
        database: MusicDB = None,
        tag: bool = False,
    ):
        """
        Download the track.

        :param quality: (5, 6, 7, 27)
        :type quality: int
        :param folder: folder to download the files to
        :type folder: Optional[Union[str, os.PathLike]]
        :param progress_bar: turn on/off progress bar
        :type progress_bar: bool
        """
        self.quality, self.folder = (
            quality or self.quality,
            parent_folder or self.folder,
        )
        self.folder = sanitize_filepath(parent_folder, platform="auto")

        os.makedirs(self.folder, exist_ok=True)

        if database is not None:
            if self.id in database:
                self._is_downloaded = True
                self._is_tagged = True
                click.secho(
                    f"{self['title']} already logged in database, skipping.",
                    fg="magenta",
                )
                return

        if os.path.isfile(self.format_final_path()):
            self._is_downloaded = True
            self._is_tagged = True
            click.secho(f"Track already downloaded: {self.final_path}", fg="magenta")
            return False

        if hasattr(self, "cover_url"):
            self.download_cover()

        dl_info = self.client.get_file_url(self.id, quality)  # dict

        temp_file = os.path.join(gettempdir(), f"~{self.id}_{quality}.tmp")
        logger.debug("Temporary file path: %s", temp_file)

        if self.client.source == "qobuz":
            if not (dl_info.get("sampling_rate") and dl_info.get("url")) or dl_info.get(
                "sample"
            ):
                logger.debug("Track is not downloadable: %s", dl_info)
                click.secho("Track is not available for download", fg="red")
                return False

            self.sampling_rate = dl_info.get("sampling_rate")
            self.bit_depth = dl_info.get("bit_depth")

        if os.path.isfile(temp_file):
            logger.debug("Temporary file found: %s", temp_file)
            self._is_downloaded = True
            self._is_tagged = False

        click.secho(f"\nDownloading {self!s}", fg="blue")

        if self.client.source in ("qobuz", "tidal"):
            logger.debug("Downloadable URL found: %s", dl_info.get("url"))
            tqdm_download(dl_info["url"], temp_file)  # downloads file
        elif isinstance(dl_info, str):  # Deezer
            logger.debug("Downloadable URL found: %s", dl_info)
            try:
                tqdm_download(dl_info, temp_file)  # downloads file
            except NonStreamable:
                logger.debug(f"Track is not downloadable {dl_info}")
                click.secho("Track is not available for download", fg="red")
                return False
        else:
            raise InvalidSourceError(self.client.source)

        if isinstance(dl_info, dict) and dl_info.get("enc_key"):
            decrypt_mqa_file(temp_file, self.final_path, dl_info["enc_key"])
        else:
            shutil.move(temp_file, self.final_path)

        if isinstance(database, MusicDB):
            database.add(self.id)
            logger.debug(f"{self.id} added to database")

        logger.debug("Downloaded: %s -> %s", temp_file, self.final_path)

        self._is_downloaded = True

        if tag:
            self.tag()

        return True

    def download_cover(self):
        """Downloads the cover art, if cover_url is given."""

        assert hasattr(self, "cover_url"), "must pass cover_url parameter"

        self.cover_path = os.path.join(self.folder, f"cover{hash(self.id)}.jpg")
        logger.debug(f"Downloading cover from {self.cover_url}")
        if not os.path.exists(self.cover_path):
            tqdm_download(self.cover_url, self.cover_path)
        else:
            logger.debug("Cover already exists, skipping download")

        self.cover = Tracklist.get_cover_obj(self.cover_path, self.quality)
        logger.debug(f"Cover obj: {self.cover}")

    def format_final_path(self) -> str:
        """Return the final filepath of the downloaded file.

        This uses the `get_formatter` method of TrackMetadata, which returns
        a dict with the keys allowed in formatter strings, and their values in
        the TrackMetadata object.
        """
        formatter = self.meta.get_formatter()
        logger.debug("Track meta formatter %s", pformat(formatter))
        # filename = sanitize_filepath(self.file_format.format(**formatter))
        filename = clean_format(self.file_format, formatter)
        self.final_path = (
            os.path.join(self.folder, filename)[:250].strip()
            + EXT[self.quality]  # file extension dict
        )

        logger.debug("Formatted path: %s", self.final_path)

        return self.final_path

    @classmethod
    def from_album_meta(cls, album: dict, pos: int, client: ClientInterface):
        """Return a new Track object initialized with info from the album dicts
        returned by client.get calls.

        :param album: album metadata returned by API
        :param pos: index of the track
        :param client: qopy client object
        :type client: ClientInterface
        :raises IndexError
        """

        tracklist = cls._get_tracklist(album, client.source)
        track = tracklist[pos]
        meta = TrackMetadata(album=album, track=track, source=client.source)
        return cls(client=client, meta=meta, id=track["id"])

    @classmethod
    def from_api(cls, item: dict, client: ClientInterface):
        meta = TrackMetadata(track=item, source=client.source)
        try:
            if client.source == "qobuz":
                cover_url = item["album"]["image"]["small"]
            elif client.source == "tidal":
                cover_url = tidal_cover_url(item["album"]["cover"], 320)
            elif client.source == "deezer":
                cover_url = item["album"]["cover_medium"]
            else:
                raise InvalidSourceError(client.source)
        except KeyError:
            logger.debug("No cover found")
            cover_url = None

        return cls(
            client=client,
            meta=meta,
            id=item["id"],
            cover_url=cover_url,
        )

    def tag(
        self,
        album_meta: dict = None,
        cover: Union[Picture, APIC] = None,
        embed_cover: bool = False,
    ):
        """Tag the track using the stored metadata.

        The info stored in the TrackMetadata object (self.meta) can be updated
        with album metadata if necessary. The cover must be a mutagen cover-type
        object that already has the bytes loaded.

        :param album_meta: album metadata to update Track with
        :type album_meta: dict
        :param cover: initialized mutagen cover object
        :type cover: Union[Picture, APIC]
        """
        assert isinstance(self.meta, TrackMetadata), "meta must be TrackMetadata"
        if not self._is_downloaded:
            logger.info(
                "Track %s not tagged because it was not downloaded", self["title"]
            )
            return

        if self._is_tagged:
            logger.info(
                "Track %s not tagged because it is already tagged", self["title"]
            )
            return

        if album_meta is not None:
            self.meta.add_album_meta(album_meta)  # extend meta with album info

        if self.quality in (2, 3, 4):
            self.container = "FLAC"
            logger.debug("Tagging file with %s container", self.container)
            audio = FLAC(self.final_path)
        elif self.quality == 1:
            self.container = "MP3"
            logger.debug("Tagging file with %s container", self.container)
            try:
                audio = ID3(self.final_path)
            except ID3NoHeaderError:
                audio = ID3()
        elif self.quality == 0:  # tidal and deezer
            # TODO: add compatibility with MP4 container
            raise NotImplementedError("Qualities < 320kbps not implemented")
        else:
            raise InvalidQuality(f'Invalid quality: "{self.quality}"')

        # automatically generate key, value pairs based on container
        for k, v in self.meta.tags(self.container):
            audio[k] = v

        if cover is None:
            assert hasattr(self, "cover")
            cover = self.cover

        if isinstance(audio, FLAC):
            audio.add_picture(cover)
            audio.save()
        elif isinstance(audio, ID3):
            audio.add(cover)
            audio.save(self.final_path, "v2_version=3")
        else:
            raise ValueError(f"Unknown container type: {audio}")

        self._is_tagged = True

    def convert(self, codec: str = "ALAC", **kwargs):
        """Converts the track to another codec.

        Valid values for codec:
            * FLAC
            * ALAC
            * MP3
            * OPUS
            * OGG
            * VORBIS
            * AAC
            * M4A

        :param codec: the codec to convert the track to
        :type codec: str
        :param kwargs:
        """
        if not self._is_downloaded:
            logger.debug("Track not downloaded, skipping conversion")
            click.secho("Track not downloaded, skipping conversion", fg="magenta")
            return

        CONV_CLASS = {
            "FLAC": converter.FLAC,
            "ALAC": converter.ALAC,
            "MP3": converter.LAME,
            "OPUS": converter.OPUS,
            "OGG": converter.Vorbis,
            "VORBIS": converter.Vorbis,
            "AAC": converter.AAC,
            "M4A": converter.AAC,
        }

        self.container = codec.upper()
        if not hasattr(self, "final_path"):
            self.format_final_path()

        if not os.path.isfile(self.final_path):
            logger.debug(f"File {self.final_path} does not exist. Skipping conversion.")
            click.secho(f"{self!s} does not exist. Skipping conversion.", fg="red")
            return

        engine = CONV_CLASS[codec.upper()](
            filename=self.final_path,
            sampling_rate=kwargs.get("sampling_rate"),
            remove_source=kwargs.get("remove_source", True),
        )
        click.secho(f"Converting {self!s}", fg="blue")
        engine.convert()

    def get(self, *keys, default=None):
        """Safe get method that allows for layered access.

        :param keys:
        :param default:
        """
        return safe_get(self.meta, *keys, default=default)

    def set(self, key, val):
        """Equivalent to __setitem__. Implemented only for
        consistency.

        :param key:
        :param val:
        """
        self.__setitem__(key, val)

    def __getitem__(self, key):
        """Dict-like interface for Track metadata.

        :param key:
        """
        return getattr(self.meta, key)

    def __setitem__(self, key, val):
        """Dict-like interface for Track metadata.

        :param key:
        :param val:
        """
        setattr(self.meta, key, val)

    def __repr__(self) -> str:
        """Return a string representation of the track.

        :rtype: str
        """
        return f"<Track - {self['title']}>"

    def __str__(self) -> str:
        """Return a readable string representation of
        this track.

        :rtype: str
        """
        return f"{self['artist']} - {self['title']}"


class Tracklist(list):
    """A base class for tracklist-like objects.

    Implements methods to give it dict-like behavior. If a Tracklist
    subclass is subscripted with [s: str], it will return an attribute s.
    If it is subscripted with [i: int] it will return the i'th track in
    the tracklist.

    >>> tlist = Tracklist()
    >>> tlist.tracklistname = 'my tracklist'
    >>> tlist.append('first track')
    >>> tlist[0]
    'first track'
    >>> tlist['tracklistname']
    'my tracklist'
    >>> tlist[2]
    IndexError
    """

    def get(self, key: Union[str, int], default: Optional[Any]):
        if isinstance(key, str):
            if hasattr(self, key):
                return getattr(self, key)

            return default

        if isinstance(key, int):
            if 0 <= key < len(self):
                return super().__getitem__(key)

            return default

    def set(self, key, val):
        self.__setitem__(key, val)

    def convert(self, codec="ALAC", **kwargs):
        if (sr := kwargs.get("sampling_rate")) :
            if sr < 44100:
                logger.warning(
                    "Sampling rate %d is lower than 44.1kHz."
                    "This may cause distortion and ruin the track.",
                    kwargs["sampling_rate"],
                )
            else:
                logger.debug(f"Downsampling to {sr/1000}kHz")

        for track in self:
            track.convert(codec, **kwargs)

    @classmethod
    def from_api(cls, item: dict, client: ClientInterface):
        """Create an Album object from the api response of Qobuz, Tidal,
        or Deezer.

        :param resp: response dict
        :type resp: dict
        :param source: in ('qobuz', 'deezer', 'tidal')
        :type source: str
        """
        info = cls._parse_get_resp(item, client=client)

        # equivalent to Album(client=client, **info)
        return cls(client=client, **info)

    @staticmethod
    def get_cover_obj(cover_path: str, quality: int) -> Union[Picture, APIC]:
        """Given the path to an image and a quality id, return an initialized
        cover object that can be used for every track in the album.

        :param cover_path:
        :type cover_path: str
        :param quality:
        :type quality: int
        :rtype: Union[Picture, APIC]
        """
        cover_type = {1: APIC, 2: Picture, 3: Picture, 4: Picture}

        cover = cover_type.get(quality)
        if cover is Picture:
            size_ = os.path.getsize(cover_path)
            if size_ > FLAC_MAX_BLOCKSIZE:
                raise TooLargeCoverArt(
                    "Not suitable for Picture embed: {size_ * 10 ** 6}MB"
                )
        elif cover is None:
            raise InvalidQuality(f"Quality {quality} not allowed")

        cover_obj = cover()
        cover_obj.type = 3
        cover_obj.mime = "image/jpeg"
        with open(cover_path, "rb") as img:
            cover_obj.data = img.read()

        return cover_obj

    def download_message(self):
        click.secho(
            f"\nDownloading {self.title} ({self.__class__.__name__})\n",
            fg="blue",
        )

    @staticmethod
    def _parse_get_resp(item, client):
        pass

    def download(self, **kwargs):
        pass

    @staticmethod
    def essence(album: str) -> str:
        """Ignore text in parens/brackets, return all lowercase.
        Used to group two albums that may be named similarly, but not exactly
        the same.
        """
        # fixme: compile this first
        match = re.match(r"([^\(]+)(?:\s*[\(\[][^\)][\)\]])*", album)
        if match:
            return match.group(1).strip().lower()

        return album

    def __getitem__(self, key: Union[str, int]):
        if isinstance(key, str):
            return getattr(self, key)

        if isinstance(key, int):
            return super().__getitem__(key)

    def __setitem__(self, key: Union[str, int], val: Any):
        if isinstance(key, str):
            setattr(self, key, val)

        if isinstance(key, int):
            super().__setitem__(key, val)


class Album(Tracklist):
    """Represents a downloadable album.

    Usage:

    >>> resp = client.get('fleetwood mac rumours', 'album')
    >>> album = Album.from_api(resp['items'][0], client)
    >>> album.load_meta()
    >>> album.download()
    """

    def __init__(self, client: ClientInterface, **kwargs):
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

        self.folder_format = kwargs.get("album_format", FOLDER_FORMAT)
        for k, v in kwargs.items():
            setattr(self, k, v)

        # to improve from_api method speed
        if kwargs.get("load_on_init"):
            self.load_meta()

        self.downloaded = False

    def load_meta(self):
        assert hasattr(self, "id"), "id must be set to load metadata"
        self.meta = self.client.get(self.id, media_type="album")

        # update attributes based on response
        for k, v in self._parse_get_resp(self.meta, self.client).items():
            setattr(self, k, v)  # prefer to __dict__.update for properties

        if not self.get("streamable", False):
            raise NonStreamable(f"This album is not streamable ({self.id} ID)")

        self._load_tracks()

    @classmethod
    def from_api(cls, resp, client):
        info = cls._parse_get_resp(resp, client)
        return cls(client, **info)

    @staticmethod
    def _parse_get_resp(resp: dict, client: ClientInterface) -> dict:
        """Parse information from a client.get(query, 'album') call.

        :param resp:
        :type resp: dict
        :rtype: dict
        """
        if client.source == "qobuz":
            return {
                "id": resp.get("id"),
                "title": resp.get("title"),
                "_artist": resp.get("artist") or resp.get("performer"),
                "albumartist": resp.get("artist", {}).get("name"),
                "year": str(resp.get("release_date_original"))[:4],
                "version": resp.get("version"),
                "release_type": resp.get("release_type", "album"),
                "cover_urls": resp.get("image"),
                "streamable": resp.get("streamable"),
                "quality": get_quality_id(
                    resp.get("maximum_bit_depth"), resp.get("maximum_sampling_rate")
                ),
                "bit_depth": resp.get("maximum_bit_depth"),
                "sampling_rate": resp.get("maximum_sampling_rate") * 1000,
                "tracktotal": resp.get("tracks_count"),
            }
        elif client.source == "tidal":
            return {
                "id": resp.get("id"),
                "title": resp.get("title"),
                "_artist": safe_get(resp, "artist", "name"),
                "albumartist": safe_get(resp, "artist", "name"),
                "year": resp.get("releaseDate")[:4],
                "version": resp.get("version"),
                "cover_urls": {
                    size: tidal_cover_url(resp.get("cover"), x)
                    for size, x in zip(COVER_SIZES, (160, 320, 1280))
                },
                "streamable": resp.get("allowStreaming"),
                "quality": TIDAL_Q_MAP[resp.get("audioQuality")],
                "bit_depth": 24 if resp.get("audioQuality") == "HI_RES" else 16,
                "sampling_rate": 44100,  # always 44.1 kHz
                "tracktotal": resp.get("numberOfTracks"),
            }
        elif client.source == "deezer":
            logger.debug(pformat(resp))
            return {
                "id": resp.get("id"),
                "title": resp.get("title"),
                "_artist": safe_get(resp, "artist", "name"),
                "albumartist": safe_get(resp, "artist", "name"),
                "year": str(resp.get("year"))[:4],
                # version not given by API
                "cover_urls": {
                    sk: resp.get(rk)  # size key, resp key
                    for sk, rk in zip(
                        COVER_SIZES, ("cover", "cover_medium", "cover_xl")
                    )
                },
                "url": resp.get("link"),
                "streamable": True,  # api only returns streamables
                "quality": 2,  # all tracks are 16/44.1 streamable
                "bit_depth": 16,
                "sampling_rate": 44100,
                "tracktotal": resp.get("track_total") or resp.get("nb_tracks"),
            }

        raise InvalidSourceError(client.source)

    def _load_tracks(self):
        """Given an album metadata dict returned by the API, append all of its
        tracks to `self`.

        This uses a classmethod to convert an item into a Track object, which
        stores the metadata inside a TrackMetadata object.
        """
        logging.debug(f"Loading {self.tracktotal} tracks to album")
        for i in range(self.tracktotal):
            # append method inherited from superclass list
            self.append(
                Track.from_album_meta(album=self.meta, pos=i, client=self.client)
            )

    @property
    def title(self) -> str:
        """Return the title of the album.

        It is formatted so that "version" keys are included.

        :rtype: str
        """
        album_title = self._title
        if hasattr(self, "version") and isinstance(self.version, str):
            if self.version.lower() not in album_title.lower():
                album_title = f"{album_title} ({self.version})"

        return album_title

    @title.setter
    def title(self, val):
        """Sets the internal _title attribute to the given value.

        :param val: title to set
        """
        self._title = val

    def download(
        self,
        quality: int = 7,
        parent_folder: Union[str, os.PathLike] = "StreamripDownloads",
        database: MusicDB = None,
        **kwargs,
    ):
        """Download all of the tracks in the album.

        :param quality: (5, 6, 7, 27)
        :type quality: int
        :param parent_folder: the folder to download the album to
        :type parent_folder: Union[str, os.PathLike]
        :param progress_bar: turn on/off a tqdm progress bar
        :type progress_bar: bool
        :param large_cover: Download the large cover. This may fail when
        embedding covers.
        :param tag_tracks: Tag the tracks after downloading, True by default
        :param keep_cover: Keep the cover art image after downloading.
        True by default.
        """
        folder = self._get_formatted_folder(parent_folder)

        os.makedirs(folder, exist_ok=True)
        logger.debug("Directory created: %s", folder)

        # choose optimal cover size and download it
        cover = None
        cover_path = os.path.join(folder, "cover.jpg")

        if os.path.isfile(cover_path):
            logger.debug("Cover already downloaded: %s. Skipping", cover_path)
        else:
            click.secho("Downloading cover art", fg="magenta")
            if kwargs.get("large_cover", False):
                cover_url = self.cover_urls.get("large")
                if self.client.source == "qobuz":
                    tqdm_download(cover_url.replace("600", "org"), cover_path)
                else:
                    tqdm_download(cover_url, cover_path)

                if os.path.getsize(cover_path) > FLAC_MAX_BLOCKSIZE:  # 16.7 MB
                    click.secho(
                        "Large cover is too large to embed, embedding small cover instead.",
                        fg="yellow",
                    )
                    large_cover_path = cover_path.replace(".jpg", "_large") + ".jpg"
                    shutil.move(cover_path, large_cover_path)
                    tqdm_download(self.cover_urls["small"], cover_path)
            else:
                tqdm_download(self.cover_urls["small"], cover_path)

        if self.client.source != "deezer":
            cover = self.get_cover_obj(cover_path, quality)

        self.download_message()
        for track in self:
            logger.debug("Downloading track to %s", folder)
            track.download(
                quality, folder, kwargs.get("progress_bar", True), database=database
            )
            if kwargs.get("tag_tracks", True) and self.client.source != "deezer":
                track.tag(cover=cover)

        if not kwargs.get("keep_cover", True):
            logger.debug(f"Removing cover at {cover_path}")
            try:
                os.remove(cover_path)
                os.remove(large_cover_path)
            except Exception as e:
                logger.debug(e)

        self.downloaded = True

    def _get_formatter(self) -> dict:
        dict_ = dict()
        for key in ALBUM_KEYS:
            if hasattr(self, key):
                dict_[key] = getattr(self, key)
            else:
                dict_[key] = None

        dict_["sampling_rate"] /= 1000
        # 48.0kHz -> 48kHz, 44.1kHz -> 44.1kHz
        if dict_["sampling_rate"] % 1 == 0.0:
            dict_["sampling_rate"] = int(dict_["sampling_rate"])

        return dict_

    def _get_formatted_folder(self, parent_folder: str) -> str:
        if self.bit_depth is not None and self.sampling_rate is not None:
            self.container = "FLAC"
        elif self.client.source == "qobuz":
            self.container = "MP3"
        elif self.client.source == "tidal":
            self.container = "AAC"
        else:
            raise Exception(f"{self.bit_depth=}, {self.sampling_rate=}")

        formatted_folder = clean_format(self.folder_format, self._get_formatter())

        return os.path.join(parent_folder, formatted_folder)

    def __repr__(self) -> str:
        """Return a string representation of this Album object.
        Useful for pprint and json.dumps.

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


class Playlist(Tracklist):
    """Represents a downloadable playlist.

    Usage:
    >>> resp = client.get('hip hop', 'playlist')
    >>> pl = Playlist.from_api(resp['items'][0], client)
    >>> pl.load_meta()
    >>> pl.download()
    """

    def __init__(self, client: ClientInterface, **kwargs):
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

    @classmethod
    def from_api(cls, resp: dict, client: ClientInterface):
        """Return a Playlist object initialized with information from
        a search result returned by the API.

        :param resp: a single search result entry of a playlist
        :type resp: dict
        :param client:
        :type client: ClientInterface
        """
        info = cls._parse_get_resp(resp, client)
        return cls(client, **info)

    def load_meta(self, **kwargs):
        """Send a request to fetch the tracklist from the api.

        :param new_tracknumbers: replace the tracknumber with playlist position
        :type new_tracknumbers: bool
        :param kwargs:
        """
        self.meta = self.client.get(self.id, "playlist")
        self.name = self.meta.get("title")
        self._load_tracks(**kwargs)

    def _load_tracks(self, new_tracknumbers: bool = True):
        """Parses the tracklist returned by the API.

        :param new_tracknumbers: replace tracknumber tag with playlist position
        :type new_tracknumbers: bool
        """
        if self.client.source == "qobuz":
            tracklist = self.meta["tracks"]["items"]

            def gen_cover(track):  # ?
                return track["album"]["image"]["small"]

            def meta_args(track):
                return {"track": track, "album": track["album"]}

        elif self.client.source == "tidal":
            tracklist = self.meta["tracks"]

            def gen_cover(track):
                cover_url = tidal_cover_url(track["album"]["cover"], 320)
                return cover_url

            def meta_args(track):
                return {
                    "track": track,
                    "source": self.client.source,
                }

        elif self.client.source == "deezer":
            tracklist = self.meta["tracks"]

            def gen_cover(track):
                return track["album"]["cover_medium"]

            def meta_args(track):
                return {"track": track, "source": self.client.source}

        else:
            raise NotImplementedError

        for i, track in enumerate(tracklist):
            # TODO: This should be managed with .m3u files and alike. Arbitrary
            # tracknumber tags might cause conflicts if the playlist files are
            # inside of a library folder
            meta = TrackMetadata(**meta_args(track))
            if new_tracknumbers:
                meta["tracknumber"] = str(i + 1)

            self.append(
                Track(
                    self.client,
                    id=track.get("id"),
                    meta=meta,
                    cover_url=gen_cover(track),
                )
            )

        logger.debug(f"Loaded {len(self)} tracks from playlist {self.name}")

    def download(
        self,
        parent_folder: str = "Downloads",
        quality: int = 6,
        filters: Callable = None,
        database: MusicDB = None,
    ):
        """Download and tag all of the tracks.

        :param parent_folder:
        :type parent_folder: str
        :param quality:
        :type quality: int
        :param filters:
        :type filters: Callable
        """
        folder = sanitize_filename(self.name)
        folder = os.path.join(parent_folder, folder)
        logger.debug(f"Parent folder {folder}")

        self.download_message()
        for track in self:
            track.download(parent_folder=folder, quality=quality, database=database)
            if self.client.source != "deezer":
                track.tag()

    @staticmethod
    def _parse_get_resp(item: dict, client: ClientInterface):
        """Parses information from a search result returned
        by a client.search call.

        :param item:
        :type item: dict
        :param client:
        :type client: ClientInterface
        """
        if client.source == "qobuz":
            return {
                "name": item.get("name"),
                "id": item.get("id"),
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

        raise InvalidSourceError(client.source)

    def __repr__(self) -> str:
        """Return a string representation of this Playlist object.
        Useful for pprint and json.dumps.

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

    def __init__(self, client: ClientInterface, **kwargs):
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

    def load_meta(self):
        """Send an API call to get album info based on id."""
        self.meta = self.client.get(self.id, media_type="artist")
        self._load_albums()

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

    def download(
        self,
        parent_folder: str = "Downloads",
        filters: Optional[Tuple] = None,
        no_repeats: bool = False,
        quality: int = 6,
        database: MusicDB = None,
        **kwargs,
    ):
        """Download all albums in the discography.

        :param filters: Filters to apply to discography, see options below.
        These only work for Qobuz.
        :type filters: Optional[Tuple]
        :param no_repeats: Remove repeats
        :type no_repeats: bool
        :param quality: in (4, 5, 6, 7, 27)
        :type quality: int
        """
        folder = sanitize_filename(self.name)
        folder = os.path.join(parent_folder, folder)

        logger.debug("Artist folder: %s", folder)

        logger.debug(f"Length of tracklist {len(self)}")
        if no_repeats:
            final = self._remove_repeats(bit_depth=max, sampling_rate=min)
        else:
            final = self

        if isinstance(filters, tuple) and self.client.source == "qobuz":
            filters = [getattr(self, filter_) for filter_ in filters]
            logger.debug("Filters: %s", filters)
            for filter_ in filters:

                def inter(album):
                    """Intermediate function to pass self into f"""
                    return filter_(self, album)

                final = filter(inter, final)

        self.download_message()
        for album in final:
            click.secho(f"Downloading album: {album}", fg="blue")
            try:
                album.load_meta()
            except NonStreamable:
                logger.info("Skipping album, not available to stream.")
            album.download(
                parent_folder=folder,
                quality=quality,
                database=database,
                **kwargs,
            )

    @property
    def title(self):
        return self.name

    @classmethod
    def from_api(cls, item: dict, client: ClientInterface, source: str = "qobuz"):
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

    def _remove_repeats(self, bit_depth=max, sampling_rate=max):
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

    @staticmethod
    def _parse_get_resp(item: dict, client: ClientInterface):
        """Parse a result from a client.search call.

        :param item: the item to parse
        :type item: dict
        :param client:
        :type client: ClientInterface
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

    @staticmethod
    def studio_albums(artist, album: Album) -> bool:
        """Passed as a parameter by the user.

        >>> artist.download(filters=Artist.studio_albums)

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

    @staticmethod
    def no_features(artist, album):
        """Passed as a parameter by the user.

        >>> artist.download(filters=Artist.no_features)

        This will download only albums where the requested
        artist is the album artist.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return artist["name"] == album["albumartist"]

    @staticmethod
    def no_extras(artist, album):
        """Passed as a parameter by the user.

        >>> artist.download(filters=Artist.no_extras)

        This will skip any extras.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return TYPE_REGEXES["extra"].search(album.title) is None

    @staticmethod
    def remaster_only(artist, album):
        """Passed as a parameter by the user.

        >>> artist.download(filters=Artist.remaster_only)

        This will download only remasterd albums.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return TYPE_REGEXES["remaster"].search(album.title) is not None

    @staticmethod
    def albums_only(artist, album):
        """This will ignore non-album releases.

        >>> artist.download(filters=(albums_only))

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
        Useful for pprint and json.dumps.

        :rtype: str
        """
        return f"<Artist: {self.name}>"

    def __str__(self) -> str:
        """Return a readable string representation of
        this Artist.

        :rtype: str
        """
        return self.name


class Label(Artist):
    def load_meta(self):
        assert self.client.source == "qobuz", "Label source must be qobuz"

        resp = self.client.get(self.id, "label")
        self.name = resp["name"]
        for album in resp["albums"]["items"]:
            self.append(Album.from_api(album, client=self.client))

    def __repr__(self):
        return f"<Label - {self.name}>"

    def __str__(self) -> str:
        """Return a readable string representation of
        this track.

        :rtype: str
        """
        return self.name
