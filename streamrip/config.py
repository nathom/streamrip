"""A config class that manages arguments between the config file and CLI."""

import copy
import logging
import os
from pprint import pformat

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


logger = logging.getLogger(__name__)


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

    defaults = {
        "qobuz": {
            "quality": 3,
            "email": None,
            "password": None,
            "app_id": "",
            "secrets": [],
        },
        "tidal": {
            "quality": 3,
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
        "lastfm": {"source": "qobuz"},
        "concurrent_downloads": False,
    }

    def __init__(self, path: str = None):
        # to access settings loaded from yaml file
        self.file = copy.deepcopy(self.defaults)
        self.session = copy.deepcopy(self.defaults)

        if path is None:
            self._path = CONFIG_PATH
        else:
            self._path = path

        if not os.path.isfile(self._path):
            logger.debug("Creating yaml config file at '%s'", self._path)
            self.dump(self.defaults)
        else:
            self.load()

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

    @property
    def tidal_creds(self):
        """Return a TidalClient compatible dict of credentials."""
        creds = dict(self.file["tidal"])
        logger.debug(creds)
        del creds["quality"]  # should not be included in creds
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
        if source == "deezer":
            return dict()

        raise InvalidSourceError(source)

    def __getitem__(self, key):
        assert key in ("file", "defaults", "session")
        return getattr(self, key)

    def __setitem__(self, key, val):
        assert key in ("file", "session")
        setattr(self, key, val)

    def __repr__(self):
        return f"Config({pformat(self.session)})"
