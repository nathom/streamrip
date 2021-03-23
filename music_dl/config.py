import logging
import os
from pprint import pformat

from ruamel.yaml import YAML

from .constants import CONFIG_PATH, FOLDER_FORMAT, TRACK_FORMAT
from .exceptions import InvalidSourceError

yaml = YAML()


logger = logging.getLogger(__name__)


class Config:
    """Config class that handles command line args and config files.

    Usage:
    >>> config = Config('test_config.yaml')

    If test_config was already initialized with values, this will load them
    into `config`. Otherwise, a new config file is created with the default
    values.

    >>> config.update_from_cli(**args)

    This will update the config values based on command line args.
    """

    def __init__(self, path: str):

        # DEFAULTS
        folder = "Downloads"
        quality = 6
        folder_format = FOLDER_FORMAT
        track_format = TRACK_FORMAT

        self.qobuz = {
            "enabled": True,
            "email": None,
            "password": None,
            "app_id": "",  # Avoid NoneType error
            "secrets": [],
        }
        self.tidal = {"enabled": True, "email": None, "password": None}
        self.deezer = {"enabled": True}
        self.downloads_database = None
        self.conversion = {"codec": None, "sampling_rate": None, "bit_depth": None}
        self.filters = {
            "no_extras": False,
            "albums_only": False,
            "no_features": False,
            "studio_albums": False,
            "remaster_only": False,
        }
        self.downloads = {"folder": folder, "quality": quality}
        self.metadata = {
            "embed_cover": True,
            "large_cover": False,
            "default_comment": None,
            "remove_extra_tags": False,
        }
        self.path_format = {"folder": folder_format, "track": track_format}

        if path is None:
            self._path = CONFIG_PATH
        else:
            self._path = path

        if not os.path.exists(self._path):
            logger.debug(f"Creating yaml config file at {self._path}")
            self.dump(self.info)
        else:
            # sometimes the file gets erased, this will reset it
            with open(self._path) as f:
                if f.read().strip() == "":
                    logger.debug(f"Config file {self._path} corrupted, resetting.")
                    self.dump(self.info)
                else:
                    self.load()

    def save(self):
        self.dump(self.info)

    def reset(self):
        os.remove(self._path)
        # re initialize with default info
        self.__init__(self._path)

    def load(self):
        with open(self._path) as cfg:
            for k, v in yaml.load(cfg).items():
                setattr(self, k, v)

        logger.debug("Config loaded")
        self.__loaded = True

    def update_from_cli(self, **kwargs):
        for category in (self.downloads, self.metadata, self.filters):
            for key in category.keys():
                if kwargs.get(key) is None:
                    continue

                # For debugging's sake
                og_value = category[key]
                new_value = kwargs[key] or og_value
                category[key] = new_value

                if og_value != new_value:
                    logger.debug("Updated %s config key from args: %s", key, new_value)

    def dump(self, info):
        with open(self._path, "w") as cfg:
            logger.debug("Config saved: %s", self._path)
            yaml.dump(info, cfg)

    @property
    def tidal_creds(self):
        return {
            "email": self.tidal["email"],
            "pwd": self.tidal["password"],
        }

    @property
    def qobuz_creds(self):
        return {
            "email": self.qobuz["email"],
            "pwd": self.qobuz["password"],
            "app_id": self.qobuz["app_id"],
            "secrets": self.qobuz["secrets"],
        }

    def creds(self, source: str):
        if source == "qobuz":
            return self.qobuz_creds
        elif source == "tidal":
            return self.tidal_creds
        elif source == "deezer":
            return dict()
        else:
            raise InvalidSourceError(source)

    @property
    def info(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    @info.setter
    def info(self, val):
        for k, v in val.items():
            setattr(self, k, v)

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, val):
        setattr(self, key, val)

    def __repr__(self):
        return f"Config({pformat(self.info)})"
