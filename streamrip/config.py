import copy
import logging
import os
from pprint import pformat

from ruamel.yaml import YAML

from .constants import (CONFIG_PATH, DOWNLOADS_DIR, FOLDER_FORMAT, TRACK_FORMAT, CONFIG_DIR)
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

    defaults = {
        "qobuz": {
            "quality": 2,
            "email": None,
            "password": None,
            "app_id": "",  # Avoid NoneType error
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
        "downloads": {"folder": DOWNLOADS_DIR},
        "metadata": {
            "embed_cover": True,
            "large_cover": False,
            "default_comment": None,
            "remove_extra_tags": False,
        },
        "keep_cover": True,
        "path_format": {"folder": FOLDER_FORMAT, "track": TRACK_FORMAT},
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
            logger.debug(f"Creating yaml config file at '{self._path}'")
            self.dump(self.defaults)
        else:
            self.load()

    def save(self):
        self.dump(self.file)

    def reset(self):
        if not os.path.isdir(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)

        self.dump(self.defaults)

    def load(self):
        with open(self._path) as cfg:
            for k, v in yaml.load(cfg).items():
                self.file[k] = v
                if hasattr(v, "copy"):
                    self.session[k] = v.copy()
                else:
                    self.session[k] = v

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
        creds = dict(self.file["tidal"])
        logger.debug(creds)
        del creds["quality"]  # should not be included in creds
        return creds

    @property
    def qobuz_creds(self):
        return {
            "email": self.file["qobuz"]["email"],
            "pwd": self.file["qobuz"]["password"],
            "app_id": self.file["qobuz"]["app_id"],
            "secrets": self.file["qobuz"]["secrets"],
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

    def __getitem__(self, key):
        assert key in ("file", "defaults", "session")
        return getattr(self, key)

    def __setitem__(self, key, val):
        assert key in ("file", "session")
        setattr(self, key, val)

    def __repr__(self):
        return f"Config({pformat(self.session)})"
