"""A config class that manages arguments between the config file and CLI."""

import copy
import logging
import os
import re
from collections import OrderedDict
from pprint import pformat
from typing import Any, Dict, List

from ruamel.yaml import YAML

from .constants import (
    CONFIG_DIR,
    CONFIG_PATH,
    DOWNLOADS_DIR,
    FOLDER_FORMAT,
    TRACK_FORMAT,
)
from .exceptions import InvalidSourceError

yaml = YAML()


logger = logging.getLogger("streamrip")


class Config:
    """Config class that handles command line args and config files.

    Usage:

        >>> config = Config('test_config.yaml')
        >>> config.defaults['qobuz']['quality']
        3

    If test_config was already initialized with values, this will load them
    into `config`. Otherwise, a new config file is created with the default
    values.
    """

    defaults: Dict[str, Any] = {
        "qobuz": {
            "quality": 3,
            "download_booklets": True,
            "email": None,
            "password": None,
            "app_id": "",
            "secrets": [],
        },
        "tidal": {
            "quality": 3,
            "download_videos": True,
            "user_id": None,
            "country_code": None,
            "access_token": None,
            "refresh_token": None,
            "token_expiry": 0,
        },
        "deezer": {
            "quality": 2,
        },
        "soundcloud": {
            "quality": 0,
        },
        "youtube": {
            "quality": 0,
            "download_videos": False,
            "video_downloads_folder": DOWNLOADS_DIR,
        },
        "database": {"enabled": True, "path": None},
        "conversion": {
            "enabled": False,
            "codec": None,
            "sampling_rate": None,
            "bit_depth": None,
        },
        "filters": {
            "extras": False,
            "repeats": False,
            "non_albums": False,
            "features": False,
            "non_studio_albums": False,
            "non_remaster": False,
        },
        "downloads": {"folder": DOWNLOADS_DIR, "source_subdirectories": False},
        "artwork": {
            "embed": True,
            "size": "large",
            "keep_hires_cover": True,
        },
        "metadata": {
            "set_playlist_to_album": False,
            "new_playlist_tracknumbers": True,
        },
        "path_format": {"folder": FOLDER_FORMAT, "track": TRACK_FORMAT},
        "check_for_updates": True,
        "lastfm": {"source": "qobuz", "fallback_source": "deezer"},
        "concurrent_downloads": False,
    }

    def __init__(self, path: str = None):
        """Create a Config object with state.

        A YAML file is created at `path` if there is none.

        :param path:
        :type path: str
        """
        # to access settings loaded from yaml file
        self.file: Dict[str, Any] = copy.deepcopy(self.defaults)
        self.session: Dict[str, Any] = copy.deepcopy(self.defaults)

        if path is None:
            self._path = CONFIG_PATH
        else:
            self._path = path

        if not os.path.isfile(self._path):
            logger.debug("Creating yaml config file at '%s'", self._path)
            self.dump(self.defaults)
        else:
            self.load()

    def update(self):
        """Reset the config file except for credentials."""
        self.reset()
        temp = copy.deepcopy(self.defaults)
        temp["qobuz"].update(self.file["qobuz"])
        temp["tidal"].update(self.file["tidal"])
        self.dump(temp)

    def save(self):
        """Save the config state to file."""
        self.dump(self.file)

    def reset(self):
        """Reset the config file."""
        if not os.path.isdir(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)

        self.dump(self.defaults)

    def load(self):
        """Load infomation from the config files, making a deepcopy."""
        with open(self._path) as cfg:
            for k, v in yaml.load(cfg).items():
                self.file[k] = v
                if hasattr(v, "copy"):
                    self.session[k] = v.copy()
                else:
                    self.session[k] = v

        logger.debug("Config loaded")
        self.__loaded = True

    def dump(self, info):
        """Given a state of the config, save it to the file.

        :param info:
        """
        with open(self._path, "w") as cfg:
            logger.debug("Config saved: %s", self._path)
            yaml.dump(info, cfg)

        docs = ConfigDocumentation()
        docs.dump(self._path)

    @property
    def tidal_creds(self):
        """Return a TidalClient compatible dict of credentials."""
        creds = dict(self.file["tidal"])
        logger.debug(creds)
        del creds["quality"]  # should not be included in creds
        del creds["download_videos"]
        return creds

    @property
    def qobuz_creds(self):
        """Return a QobuzClient compatible dict of credentials."""
        return {
            "email": self.file["qobuz"]["email"],
            "pwd": self.file["qobuz"]["password"],
            "app_id": self.file["qobuz"]["app_id"],
            "secrets": self.file["qobuz"]["secrets"],
        }

    def creds(self, source: str):
        """Return a Client compatible dict of credentials.

        :param source:
        :type source: str
        """
        if source == "qobuz":
            return self.qobuz_creds
        if source == "tidal":
            return self.tidal_creds
        if source == "deezer" or source == "soundcloud":
            return {}

        raise InvalidSourceError(source)

    def __repr__(self):
        """Return a string representation of the config."""
        return f"Config({pformat(self.session)})"


class ConfigDocumentation:
    """Documentation is stored in this docstring.

    qobuz:
        quality: 1: 320kbps MP3, 2: 16/44.1, 3: 24/<=96, 4: 24/>=96
        download_booklets: This will download booklet pdfs that are included with some albums
        password: This is an md5 hash of the plaintext password
        app_id: Do not change
        secrets: Do not change
    tidal:
        quality: 0: 256kbps AAC, 1: 320kbps AAC, 2: 16/44.1 "HiFi" FLAC, 3: 24/44.1 "MQA" FLAC
        download_videos: This will download videos included in Video Albums.
        user_id: Do not change any of the fields below
        token_expiry: Tokens last 1 week after refresh. This is the Unix timestamp of the expiration time.
    deezer: Deezer doesn't require login
        quality: 0, 1, or 2
    soundcloud:
        quality: Only 0 is available
    youtube:
        quality: Only 0 is available for now
        download_videos: Download the video along with the audio
        video_downloads_folder: The path to download the videos to
    database: This stores a list of item IDs so that repeats are not downloaded.
    conversion: Convert tracks to a codec after downloading them.
        codec: FLAC, ALAC, OPUS, MP3, VORBIS, or AAC
        sampling_rate: In Hz. Tracks are downsampled if their sampling rate is greater than this. Values greater than 48000 are only recommended if the audio will be processed. It is otherwise a waste of space as the human ear cannot discern higher frequencies.
        bit_depth: Only 16 and 24 are available. It is only applied when the bit depth is higher than this value.
    filters: Filter a Qobuz artist's discography. Set to 'true' to turn on a filter.
        extras: Remove Collectors Editions, live recordings, etc.
        repeats: Picks the highest quality out of albums with identical titles.
        non_albums: Remove EPs and Singles
        features: Remove albums whose artist is not the one requested
        non_remaster: Only download remastered albums
    downloads:
        folder: Folder where tracks are downloaded to
        source_subdirectories: Put Qobuz albums in a 'Qobuz' folder, Tidal albums in 'Tidal' etc.
    artwork:
        embed: Write the image to the audio file
        size: The size of the artwork to embed. Options: thumbnail, small, large, original. 'original' images can be up to 30MB, and may fail embedding. Using 'large' is recommended.
        keep_hires_cover: Save the cover image at the highest quality as a seperate jpg file
    metadata: Only applicable for playlist downloads.
        set_playlist_to_album: Sets the value of the 'ALBUM' field in the metadata to the playlist's name. This is useful if your music library software organizes tracks based on album name.
        new_playlist_tracknumbers: Replaces the original track's tracknumber with it's position in the playlist
    path_format: Changes the folder and file names generated by streamrip.
        folder: Available keys: "albumartist", "title", "year", "bit_depth", "sampling_rate", and "container"
        track: Available keys: "tracknumber", "artist", "albumartist", "composer", and "title"
    lastfm: Last.fm playlists are downloaded by searching for the titles of the tracks
        source: The source on which to search for the tracks.
        fallback_source: If no results were found with the primary source, the item is searched for on this one.
    concurrent_downloads: Download (and convert) tracks all at once, instead of sequentially. If you are converting the tracks, and/or have fast internet, this will substantially improve processing speed.
    """

    def __init__(self):
        """Create a new ConfigDocumentation object."""
        # not using ruamel because its super slow
        self.docs = []
        doctext = self.__doc__
        # get indent level, key, and documentation
        keyval = re.compile(r"( *)([\w_]+):\s*(.*)")
        lines = (line[4:] for line in doctext.split("\n")[2:-1])

        for line in lines:
            info = list(keyval.match(line).groups())
            if len(info) == 3:
                info[0] = len(info[0]) // 4  # here use standard 4 spaces/tab
            else:  # line doesn't start with spaces
                info.insert(0, 0)

            self.docs.append(info)

    def dump(self, path: str):
        """Write comments to an uncommented YAML file.

        :param path:
        :type path: str
        """
        is_comment = re.compile(r"^\s*#.*")
        with open(path) as f:
            # includes newline at the end
            lines = f.readlines()

        with open(path, "w") as f:
            while lines != []:
                line = lines.pop(0)
                found = False
                to_remove = None
                for level, key, doc in self.docs:
                    # using 1 indent = 2 spaces like ruamel.yaml
                    spaces = level * "  "
                    comment = f"{spaces}# {doc}"

                    if is_comment.match(line):
                        # update comment
                        found = True
                        break

                    re_obj = self._get_key_regex(spaces, key)
                    match = re_obj.match(line)
                    if match is not None:  # line contains the key
                        if doc != "":
                            f.write(f"{comment}\n{line}")
                            found = True
                        to_remove = [level, key, doc]
                        break

                if not found:  # field with no comment
                    f.write(line)

                if to_remove is not None:
                    # key, doc pairs are unique
                    self.docs.remove(to_remove)

    def _get_key_regex(self, spaces: str, key: str) -> re.Pattern:
        """Get a regex that matches a key in YAML.

        :param spaces: a string spaces that represent the indent level.
        :type spaces: str
        :param key: the key to match.
        :type key: str
        :rtype: re.Pattern
        """
        regex = rf"{spaces}{key}:(?:$|\s+?(.+))"
        return re.compile(regex)

    def strip_comments(self, path: str):
        """Remove single-line comments from a file.

        :param path:
        :type path: str
        """
        with open(path, "r") as f:
            lines = [
                line
                for line in f.readlines()
                if not line.strip().startswith("#")
            ]

        with open(path, "w") as f:
            f.write("".join(lines))


# ------------- ~~ Experimental ~~ ----------------- #


def load_yaml(path: str):
    """Load a streamrip config YAML file.

    Warning: this is not fully compliant with YAML. It was made for use
    with streamrip.

    :param path:
    :type path: str
    """
    with open(path) as f:
        lines = f.readlines()

    settings = OrderedDict()
    type_dict = {t.__name__: t for t in (list, dict, str)}
    for line in lines:
        key_l: List[str] = []
        val_l: List[str] = []

        chars = StringWalker(line)
        level = 0

        # get indent level of line
        while next(chars).isspace():
            level += 1

        chars.prev()
        if (c := next(chars)) == "#":
            # is a comment
            continue

        elif c == "-":
            # is an item in a list
            next(chars)
            val_l = list(chars)
            level += 2  # it is a child of the previous key
            item_type = "list"
        else:
            # undo char read
            chars.prev()

        if not val_l:
            while (c := next(chars)) != ":":
                key_l.append(c)
            val_l = list("".join(chars).strip())

        if val_l:
            val = "".join(val_l)
        else:
            # start of a section
            item_type = "dict"
            val = type_dict[item_type]()

        key = "".join(key_l)
        if level == 0:
            settings[key] = val
        elif level == 2:
            parent = settings[tuple(settings.keys())[-1]]
            if isinstance(parent, dict):
                parent[key] = val
            elif isinstance(parent, list):
                parent.append(val)
        else:
            raise Exception(f"level too high: {level}")

    return settings


class StringWalker:
    """A fancier str iterator."""

    def __init__(self, s: str):
        """Create a StringWalker object.

        :param s:
        :type s: str
        """
        self.__val = s.replace("\n", "")
        self.__pos = 0

    def __next__(self) -> str:
        """Get the next char.

        :rtype: str
        """
        try:
            c = self.__val[self.__pos]
            self.__pos += 1
            return c
        except IndexError:
            raise StopIteration

    def __iter__(self):
        """Get an iterator."""
        return self

    def prev(self, step: int = 1):
        """Un-read a character.

        :param step: The number of steps backward to take.
        :type step: int
        """
        self.__pos -= step
