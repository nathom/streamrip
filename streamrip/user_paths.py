import os
from pathlib import Path

from appdirs import user_config_dir

APPNAME = "streamrip"
APP_DIR = user_config_dir(APPNAME)
HOME = Path.home()

LOG_DIR = CACHE_DIR = CONFIG_DIR = APP_DIR

DEFAULT_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.toml")
DB_PATH = os.path.join(LOG_DIR, "downloads.db")
FAILED_DB_PATH = os.path.join(LOG_DIR, "failed_downloads.db")

DOWNLOADS_DIR = os.path.join(HOME, "StreamripDownloads")
