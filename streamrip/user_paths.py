import os
from pathlib import Path

from appdirs import user_config_dir

APPNAME = "streamrip"
APP_DIR = user_config_dir(APPNAME)
HOME = Path.home()

LOG_DIR = CACHE_DIR = CONFIG_DIR = APP_DIR

CONFIG_PATH = os.path.join(CONFIG_DIR, "config.toml")
DB_PATH = os.path.join(LOG_DIR, "downloads.db")
FAILED_DB_PATH = os.path.join(LOG_DIR, "failed_downloads.db")

DOWNLOADS_DIR = os.path.join(HOME, "StreamripDownloads")
# file shipped with script
BLANK_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")

DEFAULT_DOWNLOADS_FOLDER = os.path.join(HOME, "StreamripDownloads")
DEFAULT_DOWNLOADS_DB_PATH = os.path.join(LOG_DIR, "downloads.db")
DEFAULT_FAILED_DOWNLOADS_DB_PATH = os.path.join(LOG_DIR, "failed_downloads.db")
DEFAULT_YOUTUBE_VIDEO_DOWNLOADS_FOLDER = os.path.join(
    HOME, "StreamripDownloads", "YouTubeVideos"
)
