import json
import logging
import re
import sys
from typing import Generator, Optional, Tuple, Union

from .constants import (
    COPYRIGHT,
    FLAC_KEY,
    MP3_KEY,
    MP4_KEY,
    PHON_COPYRIGHT,
    TRACK_KEYS,
)
from .exceptions import InvalidContainerError

logger = logging.getLogger(__name__)


class TrackMetadata:
    """Contains all of the metadata needed to tag the file.
    Available attributes:

        * title
        * artist
        * album
        * albumartist
        * composer
        * year
        * comment
        * description
        * purchase_date
        * grouping
        * genre
        * lyrics
        * encoder
        * copyright
        * compilation
        * cover
        * tracknumber
        * discnumber

    """

    def __init__(
        self, track: Optional[dict] = None, album: Optional[dict] = None, source="qobuz"
    ):
        """Creates a TrackMetadata object optionally initialized with
        dicts returned by the Qobuz API.

        :param track: track dict from API
        :type track: Optional[dict]
        :param album: album dict from API
        :type album: Optional[dict]
        """
        self.album = None
        self.albumartist = None
        self.composer = None
        self.comment = None
        self.description = None
        self.purchase_date = None
        self.grouping = None
        self.lyrics = None
        self.encoder = None
        self.compilation = None
        self.cover = None
        self.tracknumber = None
        self.discnumber = None

        self.__source = source  # not included in tags

        if track is None and album is None:
            logger.debug("No params passed, returning")
            return

        if track is not None:
            self.add_track_meta(track)

        if album is not None:
            self.add_album_meta(album)

    def add_album_meta(self, resp: dict):
        """Parse the metadata from an resp dict returned by the
        Qobuz API.

        :param dict resp: from the Qobuz API
        """
        if self.__source == "qobuz":
            self.album = resp.get("title")
            self.tracktotal = str(resp.get("tracks_count", 1))
            self.genre = resp.get("genres_list", [])
            self.date = resp.get("release_date_original") or resp.get("release_date")
            self.copyright = resp.get("copyright")
            self.albumartist = resp.get("artist", {}).get("name")
            self.label = resp.get("label")

            if isinstance(self.label, dict):
                self.label = self.label.get("name")

        elif self.__source == "tidal":
            self.album = resp.get("title")
            self.tracktotal = resp.get("numberOfTracks")
            # genre not returned by API
            self.date = resp.get("releaseDate")
            self.copyright = resp.get("copyright")
            self.albumartist = resp.get("artist", {}).get("name")
            # label not returned by API

        elif self.__source == "deezer":
            self.album = resp.get("title")
            self.tracktotal = resp.get("track_total")
            self.genre = resp.get("genres", {}).get("data")
            self.date = resp.get("release_date")
            self.albumartist = resp.get("artist", {}).get("name")
            self.label = resp.get("label")

        else:
            raise ValueError

    def add_track_meta(self, track: dict):
        """Parse the metadata from a track dict returned by the
        Qobuz API.

        :param track:
        """
        if self.__source == "qobuz":
            self.title = track.get("title").strip()
            self._mod_title(track.get("version"), track.get("work"))
            self.composer = track.get("composer", {}).get("name")

            self.tracknumber = f"{int(track.get('track_number', 1)):02}"
            self.discnumber = str(track.get("media_number", 1))
            try:
                self.artist = track["performer"]["name"]
            except KeyError:
                if hasattr(self, "albumartist"):
                    self.artist = self.albumartist

        elif self.__source == "tidal":
            self.title = track.get("title").strip()
            self._mod_title(track.get("version"), None)
            self.tracknumber = f"{int(track.get('trackNumber', 1)):02}"
            self.discnumber = str(track.get("volumeNumber"))
            self.artist = track.get("artist", {}).get("name")

        elif self.__source == "deezer":
            self.title = track.get("title").strip()
            self._mod_title(track.get("version"), None)
            self.tracknumber = f"{int(track.get('track_position', 1)):02}"
            self.discnumber = track.get("disk_number")
            self.artist = track.get("artist", {}).get("name")

        else:
            raise ValueError

        if track.get("album"):
            self.add_album_meta(track["album"])

    def _mod_title(self, version, work):
        if version is not None:
            logger.debug("Version found: %s", version)
            self.title = f"{self.title} ({version})"
        if work is not None:
            logger.debug("Work found: %s", work)
            self.title = f"{work}: {self.title}"

    @property
    def artist(self) -> Union[str, None]:
        """Returns the value to set for the artist tag. Defaults to
        `self.albumartist` if there is no track artist.

        :rtype: str
        """
        if self._artist is None and self.albumartist is not None:
            return self.albumartist

        if self._artist is not None:
            return self._artist

    @artist.setter
    def artist(self, val: str):
        """Sets the internal artist variable to val.

        :param val:
        :type val: str
        """
        self._artist = val

    @property
    def genre(self) -> Union[str, None]:
        """Formats the genre list returned by the Qobuz API.
        >>> g = ['Pop/Rock', 'Pop/Rock→Rock', 'Pop/Rock→Rock→Alternatif et Indé']
        >>> _format_genres(g)
        'Pop, Rock, Alternatif et Indé'

        :rtype: str
        """
        if not self.get("_genres"):
            return None

        if isinstance(self._genres, list):
            genres = re.findall(r"([^\u2192\/]+)", "/".join(self._genres))
            no_repeats = []
            [no_repeats.append(g) for g in genres if g not in no_repeats]
            return ", ".join(no_repeats)
        elif isinstance(self._genres, str):
            return self._genres

        raise TypeError(f"Genre must be list or str, not {type(self._genres)}")

    @genre.setter
    def genre(self, val: Union[str, list]):
        """Sets the internal `genre` field to the given list.
        It is not formatted until it is requested with `meta.genre`.

        :param val:
        :type val: Union[str, list]
        """
        self._genres = val

    @property
    def copyright(self) -> Union[str, None]:
        """Formats the copyright string to use nice-looking unicode
        characters.

        :rtype: str, None
        """
        if hasattr(self, "_copyright"):
            if self._copyright is None:
                return None
            cr = self._copyright.replace("(P)", PHON_COPYRIGHT)
            cr = cr.replace("(C)", COPYRIGHT)
            return cr

        logger.debug("Accessed copyright tag before setting, return None")
        return None

    @copyright.setter
    def copyright(self, val: str):
        """Sets the internal copyright variable to the given value.
        Only formatted when requested.

        :param val:
        :type val: str
        """
        self._copyright = val

    @property
    def year(self) -> Union[str, None]:
        """Returns the year published of the track.

        :rtype: str
        """
        if hasattr(self, "_year"):
            return self._year

        if hasattr(self, "date"):
            if self.date is not None:
                return self.date[:4]

    @year.setter
    def year(self, val):
        """Sets the internal year variable to val.

        :param val:
        """
        self._year = val

    def get_formatter(self) -> dict:
        """Returns a dict that is used to apply values to file format strings.

        :rtype: dict
        """
        # the keys in the tuple are the possible keys for format strings
        return {k: getattr(self, k) for k in TRACK_KEYS}

    def tags(self, container: str = "flac") -> Generator:
        """Return a generator of (key, value) pairs to use for tagging
        files with mutagen. The *_KEY dicts are organized in the format

        >>> {attribute_name: key_to_use_for_metadata}

        They are then converted to the format

        >>> {key_to_use_for_metadata: value_of_attribute}

        so that they can be used like this:

        >>> audio = MP4(path)
        >>> for k, v in meta.tags(container='MP4'):
        ...     audio[k] = v
        >>> audio.save()

        :param container: the container format
        :type container: str
        :rtype: Generator
        """
        container = container.lower()
        if container in ("flac", "vorbis"):
            return self.__gen_flac_tags()
        elif container in ("mp3", "id3"):
            return self.__gen_mp3_tags()
        elif container in ("alac", "m4a", "mp4", "aac"):
            return self.__gen_mp4_tags()
        else:
            raise InvalidContainerError(f"Invalid container {container}")

    def __gen_flac_tags(self) -> Tuple[str, str]:
        """Generate key, value pairs to tag FLAC files.

        :rtype: Tuple[str, str]
        """
        for k, v in FLAC_KEY.items():
            tag = getattr(self, k)
            if tag:
                logger.debug(f"Adding tag {v}: {repr(tag)}")
                yield (v, str(tag))

    def __gen_mp3_tags(self) -> Tuple[str, str]:
        """Generate key, value pairs to tag MP3 files.

        :rtype: Tuple[str, str]
        """
        for k, v in MP3_KEY.items():
            if k == "tracknumber":
                text = f"{self.tracknumber}/{self.tracktotal}"
            elif k == "discnumber":
                text = str(self.discnumber)
            else:
                text = getattr(self, k)

            if text is not None:
                yield (v.__name__, v(encoding=3, text=text))

    def __mp4_tags(self) -> Tuple[str, str]:
        """Generate key, value pairs to tag ALAC or AAC files in
        an MP4 container.

        :rtype: Tuple[str, str]
        """
        for k, v in MP4_KEY.items():
            return (v, getattr(self, k))

    def __setitem__(self, key, val):
        """Dict-like access for tags.

        :param key:
        :param val:
        """
        setattr(self, key, val)

    def __getitem__(self, key):
        """Dict-like access for tags.

        :param key:
        """
        return getattr(self, key)

    def get(self, key, default=None) -> str:
        """Returns the requested attribute of the object, with
        a default value.

        :param key:
        :param default:
        """
        if hasattr(self, key):
            res = self.__getitem__(key)
            if res is not None:
                return res

            return default

        return default

    def set(self, key, val) -> str:
        """Equivalent to
        >>> meta[key] = val

        :param key:
        :param val:
        :rtype: str
        """
        return self.__setitem__(key, val)

    def __repr__(self) -> str:
        """Returns the string representation of the metadata object.

        :rtype: str
        """
        # TODO: make a more readable repr
        return json.dumps(self.__dict__, indent=2)
