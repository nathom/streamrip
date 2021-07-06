"""A config class that manages arguments between the config file and CLI."""

import copy
import logging
import os
import shutil
from pprint import pformat
from typing import Any, Dict

import click
import tomlkit

from .constants import CONFIG_DIR, CONFIG_PATH, DOWNLOADS_DIR
from streamrip.exceptions import InvalidSourceError

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
                click.secho(
                    "Updating config file to new version. Some settings may be lost.",
                    fg="yellow",
                )
                self.update()
                self.load()
        else:
            logger.debug("Creating toml config file at '%s'", self._path)
            shutil.copy(self.default_config_path, self._path)
            self.load()
            self.file["downloads"]["folder"] = DOWNLOADS_DIR

    def update(self):
        """Reset the config file except for credentials."""
        self.reset()
        temp = copy.deepcopy(self.defaults)
        temp["qobuz"].update(self.file["qobuz"])
        temp["tidal"].update(self.file["tidal"])
        self.dump(temp)
        del temp

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
        self.__loaded = True

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
        if source == "deezer" or source == "soundcloud":
            return {}

        raise InvalidSourceError(source)

    def __repr__(self):
        """Return a string representation of the config."""
        return f"Config({pformat(self.session)})"
