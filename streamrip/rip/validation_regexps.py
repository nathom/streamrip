import re

URL_REGEX = re.compile(
    r"https?://(?:www|open|play|listen)?\.?(qobuz|tidal|deezer)\.com(?:(?:/(album|artist|track|playlist|video|label))|(?:\/[-\w]+?))+\/([-\w]+)",
)
SOUNDCLOUD_URL_REGEX = re.compile(r"https://soundcloud.com/[-\w:/]+")
LASTFM_URL_REGEX = re.compile(r"https://www.last.fm/user/\w+/playlists/\w+")
QOBUZ_INTERPRETER_URL_REGEX = re.compile(
    r"https?://www\.qobuz\.com/\w\w-\w\w/interpreter/[-\w]+/[-\w]+",
)
DEEZER_DYNAMIC_LINK_REGEX = re.compile(r"https://deezer\.page\.link/\w+")
YOUTUBE_URL_REGEX = re.compile(r"https://www\.youtube\.com/watch\?v=[-\w]+")
