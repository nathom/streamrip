"""Various constant values that are used by RipCore."""

import os
import re
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

URL_REGEX = re.compile(
    r"https?://(?:www|open|play|listen)?\.?(qobuz|tidal|deezer)\.com(?:(?:/(album|artist|track|playlist|video|label))|(?:\/[-\w]+?))+\/([-\w]+)"
)
SOUNDCLOUD_URL_REGEX = re.compile(r"https://soundcloud.com/[-\w:/]+")
LASTFM_URL_REGEX = re.compile(r"https://www.last.fm/user/\w+/playlists/\w+")
QOBUZ_INTERPRETER_URL_REGEX = re.compile(
    r"https?://www\.qobuz\.com/\w\w-\w\w/interpreter/[-\w]+/[-\w]+"
)
DEEZER_DYNAMIC_LINK_REGEX = re.compile(r"https://deezer\.page\.link/\w+")
YOUTUBE_URL_REGEX = re.compile(r"https://www\.youtube\.com/watch\?v=[-\w]+")
