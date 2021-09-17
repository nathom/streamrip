"""A config class that manages arguments between the config file and CLI."""

import copy
import logging
import os
import shutil
from pprint import pformat
from typing import Any, Dict, List, Union

import tomlkit
from click import secho

from streamrip.exceptions import InvalidSourceError

from .constants import CONFIG_DIR, CONFIG_PATH, DOWNLOADS_DIR

logger = logging.getLogger("streamrip")


class Config:
    """Config class that handles command line args and config files.

    Usage:

        >>> config = Config('test_config.toml')
        >>> config.defaults['qobuz']['quality']
        3

    If test_config was already initialized with values, this will load them
    into `config`. Otherwise, a new config file is created with the default
    values.
    """

    default_config_path = os.path.join(os.path.dirname(__file__), "config.toml")

    with open(default_config_path) as cfg:
        defaults: Dict[str, Any] = tomlkit.parse(cfg.read().strip())

    def __init__(self, path: str = None):
        """Create a Config object with state.

        A TOML file is created at `path` if there is none.

        :param path:
        :type path: str
        """
        # to access settings loaded from toml file
        self.file: Dict[str, Any] = copy.deepcopy(self.defaults)
        self.session: Dict[str, Any] = copy.deepcopy(self.defaults)

        if path is None:
            self._path = CONFIG_PATH
        else:
            self._path = path

        if os.path.isfile(self._path):
            self.load()
            if self.file["misc"]["version"] != self.defaults["misc"]["version"]:
                secho(
                    "Updating config file to new version. Some settings may be lost.",
                    fg="yellow",
                )
                self.update()
                self.load()
        else:
            logger.debug("Creating toml config file at '%s'", self._path)
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            shutil.copy(self.default_config_path, self._path)
            self.load()
            self.file["downloads"]["folder"] = DOWNLOADS_DIR

    def update(self):
        """Reset the config file except for credentials."""
        # Save original credentials
        cached_info = self._cache_info(
            [
                "qobuz",
                "tidal",
                "deezer",
                "downloads.folder",
                "filepaths.folder_format",
                "filepaths.track_format",
            ]
        )

        # Reset and load config file
        shutil.copy(self.default_config_path, self._path)
        self.load()

        self._dump_cached(cached_info)

        self.save()

    def _dot_get(self, dot_key: str) -> Union[dict, str]:
        """Get a key from a toml file using section.key format."""
        item = self.file
        for key in dot_key.split("."):
            item = item[key]
        return item

    def _dot_set(self, dot_key, val):
        """Set a key in the toml file using the section.key format."""
        keys = dot_key.split(".")
        item = self.file
        for key in keys[:-1]:  # stop at the last one in case it's an immutable
            item = item[key]

        item[keys[-1]] = val

    def _cache_info(self, keys: List[str]):
        """Return a deepcopy of the values from the config to be saved."""
        return {key: copy.deepcopy(self._dot_get(key)) for key in keys}

    def _dump_cached(self, cached_values):
        """Set cached values into the current config file."""
        for k, v in cached_values.items():
            self._dot_set(k, v)

    def save(self):
        """Save the config state to file."""
        self.dump(self.file)

    def reset(self):
        """Reset the config file."""
        if not os.path.isdir(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)

        shutil.copy(self.default_config_path, self._path)
        self.load()
        self.file["downloads"]["folder"] = DOWNLOADS_DIR
        self.save()

    def load(self):
        """Load infomation from the config files, making a deepcopy."""
        with open(self._path) as cfg:
            for k, v in tomlkit.loads(cfg.read().strip()).items():
                self.file[k] = v
                if hasattr(v, "copy"):
                    self.session[k] = v.copy()
                else:
                    self.session[k] = v

        logger.debug("Config loaded")

    def dump(self, info):
        """Given a state of the config, save it to the file.

        :param info:
        """
        with open(self._path, "w") as cfg:
            logger.debug("Config saved: %s", self._path)
            cfg.write(tomlkit.dumps(info))

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
        if source == "deezer":
            return {"arl": self.file["deezer"]["arl"]}
        if source == "soundcloud":
            soundcloud = self.file["soundcloud"]
            return {
                "client_id": soundcloud["client_id"],
                "app_version": soundcloud["app_version"],
            }

        raise InvalidSourceError(source)

    def __repr__(self) -> str:
        """Return a string representation of the config."""
        return f"Config({pformat(self.session)})"
