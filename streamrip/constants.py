"""Constants that are kept in one place."""

import mutagen.id3 as id3

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0"

TIDAL_COVER_URL = "https://resources.tidal.com/images/{uuid}/{width}x{height}.jpg"
# Get this from (base64encoded)
# aHR0cHM6Ly9hLXYyLnNuZGNkbi5jb20vYXNzZXRzLzItYWIxYjg1NjguanM=
# Don't know if this is a static url yet
SOUNDCLOUD_CLIENT_ID = "qHsjZaNbdTcABbiIQnVfW07cEPGLNjIh"
SOUNDCLOUD_USER_ID = "672320-86895-162383-801513"
SOUNDCLOUD_APP_VERSION = "1630917744"


QUALITY_DESC = {
    0: "128kbps",
    1: "320kbps",
    2: "16bit/44.1kHz",
    3: "24bit/96kHz",
    4: "24bit/192kHz",
}

QOBUZ_FEATURED_KEYS = (
    "most-streamed",
    "recent-releases",
    "best-sellers",
    "press-awards",
    "ideal-discography",
    "editor-picks",
    "most-featured",
    "qobuzissims",
    "new-releases",
    "new-releases-full",
    "harmonia-mundi",
    "universal-classic",
    "universal-jazz",
    "universal-jeunesse",
    "universal-chanson",
)

__MP4_KEYS = (
    "\xa9nam",
    "\xa9ART",
    "\xa9alb",
    r"aART",
    "\xa9day",
    "\xa9day",
    "\xa9cmt",
    "desc",
    "purd",
    "\xa9grp",
    "\xa9gen",
    "\xa9lyr",
    "\xa9too",
    "cprt",
    "cpil",
    "covr",
    "trkn",
    "disk",
    None,
    None,
    None,
)

__MP3_KEYS = (
    id3.TIT2,
    id3.TPE1,
    id3.TALB,
    id3.TPE2,
    id3.TCOM,
    id3.TYER,
    id3.COMM,
    id3.TT1,
    id3.TT1,
    id3.GP1,
    id3.TCON,
    id3.USLT,
    id3.TEN,
    id3.TCOP,
    id3.TCMP,
    None,
    id3.TRCK,
    id3.TPOS,
    None,
    None,
    None,
)

__METADATA_TYPES = (
    "title",
    "artist",
    "album",
    "albumartist",
    "composer",
    "year",
    "comment",
    "description",
    "purchase_date",
    "grouping",
    "genre",
    "lyrics",
    "encoder",
    "copyright",
    "compilation",
    "cover",
    "tracknumber",
    "discnumber",
    "tracktotal",
    "disctotal",
    "date",
)


FLAC_KEY = {v: v.upper() for v in __METADATA_TYPES}
MP4_KEY = dict(zip(__METADATA_TYPES, __MP4_KEYS))
MP3_KEY = dict(zip(__METADATA_TYPES, __MP3_KEYS))

COPYRIGHT = "\u2117"
PHON_COPYRIGHT = "\u00a9"
FLAC_MAX_BLOCKSIZE = 16777215  # 16.7 MB

# TODO: give these more descriptive names
TRACK_KEYS = (
    "tracknumber",
    "artist",
    "albumartist",
    "composer",
    "title",
    "albumcomposer",
    "explicit",
)
ALBUM_KEYS = (
    "albumartist",
    "title",
    "year",
    "bit_depth",
    "sampling_rate",
    "container",
    "albumcomposer",
    "id",
)
# TODO: rename these to DEFAULT_FOLDER_FORMAT etc
FOLDER_FORMAT = (
    "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
)
TRACK_FORMAT = "{tracknumber}. {artist} - {title}"


TIDAL_MAX_Q = 7

TIDAL_Q_MAP = {
    "LOW": 0,
    "HIGH": 1,
    "LOSSLESS": 2,
    "HI_RES": 3,
}

DEEZER_MAX_Q = 6
DEEZER_FEATURED_KEYS = {"releases", "charts", "selection"}
AVAILABLE_QUALITY_IDS = (0, 1, 2, 3, 4)
DEEZER_FORMATS = {
    "AAC_64",
    "MP3_64",
    "MP3_128",
    "MP3_256",
    "MP3_320",
    "FLAC",
}
# video only for tidal
MEDIA_TYPES = {"track", "album", "artist", "label", "playlist", "video"}

# used to homogenize cover size keys
COVER_SIZES = ("thumbnail", "small", "large", "original")

TIDAL_CLIENT_INFO = {
    "id": "Pzd0ExNVHkyZLiYN",
    "secret": "W7X6UvBaho+XOi1MUeCX6ewv2zTdSOV3Y7qC3p3675I=",
}

QOBUZ_BASE = "https://www.qobuz.com/api.json/0.2"

TIDAL_BASE = "https://api.tidalhifi.com/v1"
TIDAL_AUTH_URL = "https://auth.tidal.com/v1/oauth2"

DEEZER_BASE = "https://api.deezer.com"
DEEZER_DL = "http://dz.loaderapp.info/deezer"

SOUNDCLOUD_BASE = "https://api-v2.soundcloud.com"
