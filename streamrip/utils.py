"""Miscellaneous utility functions."""

from __future__ import annotations

import base64
import logging
from string import Formatter
from typing import Dict, Hashable, Iterator, Optional, Tuple, Union

import requests
from click import secho, style
from pathvalidate import sanitize_filename
from requests.packages import urllib3
from tqdm import tqdm

from .constants import COVER_SIZES, TIDAL_COVER_URL
from .exceptions import InvalidQuality, InvalidSourceError

urllib3.disable_warnings()
logger = logging.getLogger("streamrip")


def safe_get(d: dict, *keys: Hashable, default=None):
    """Traverse dict layers safely.

    Usage:
        >>> d = {'foo': {'bar': 'baz'}}
        >>> safe_get(d, 'baz')
        None
        >>> safe_get(d, 'foo', 'bar')
        'baz'

    :param d:
    :type d: dict
    :param keys:
    :type keys: Hashable
    :param default: the default value to use if a key isn't found
    """
    curr = d
    res = default
    for key in keys:
        res = curr.get(key, default)
        if res == default or not hasattr(res, "__getitem__"):
            return res
        else:
            curr = res
    return res


def clean_filename(fn: str, restrict=False) -> str:
    path = sanitize_filename(fn)
    if restrict:
        from string import printable

        allowed_chars = set(printable)
        path = "".join(c for c in path if c in allowed_chars)

    return path


__QUALITY_MAP: Dict[str, Dict[int, Union[int, str, Tuple[int, str]]]] = {
    "qobuz": {
        1: 5,
        2: 6,
        3: 7,
        4: 27,
    },
    "deezer": {
        0: (9, "MP3_128"),
        1: (3, "MP3_320"),
        2: (1, "FLAC"),
    },
    "tidal": {
        0: "LOW",  # AAC
        1: "HIGH",  # AAC
        2: "LOSSLESS",  # CD Quality
        3: "HI_RES",  # MQA
    },
    "deezloader": {
        0: 128,
        1: 320,
        2: 1411,
    },
}


def get_quality(quality_id: int, source: str) -> Union[str, int, Tuple[int, str]]:
    """Get the source-specific quality id.

    :param quality_id: the universal quality id (0, 1, 2, 4)
    :type quality_id: int
    :param source: qobuz, tidal, or deezer
    :type source: str
    :rtype: Union[str, int]
    """
    return __QUALITY_MAP[source][quality_id]


def get_quality_id(bit_depth: Optional[int], sampling_rate: Optional[int]):
    """Get the universal quality id from bit depth and sampling rate.

    :param bit_depth:
    :type bit_depth: Optional[int]
    :param sampling_rate:
    :type sampling_rate: Optional[int]
    """
    # XXX: Should `0` quality be supported?
    if bit_depth is None or sampling_rate is None:  # is lossy
        return 1

    if bit_depth == 16:
        return 2

    if bit_depth == 24:
        if sampling_rate <= 96:
            return 3

        return 4


def get_stats_from_quality(
    quality_id: int,
) -> Tuple[Optional[int], Optional[int]]:
    """Get bit depth and sampling rate based on the quality id.

    :param quality_id:
    :type quality_id: int
    :rtype: Tuple[Optional[int], Optional[int]]
    """
    if quality_id <= 1:
        return (None, None)
    elif quality_id == 2:
        return (16, 44100)
    elif quality_id == 3:
        return (24, 96000)
    elif quality_id == 4:
        return (24, 192000)
    else:
        raise InvalidQuality(quality_id)


def clean_format(formatter: str, format_info, restrict: bool = False):
    """Format track or folder names sanitizing every formatter key.

    :param formatter:
    :type formatter: str
    :param kwargs:
    """
    fmt_keys = filter(None, (i[1] for i in Formatter().parse(formatter)))
    # fmt_keys = (i[1] for i in Formatter().parse(formatter) if i[1] is not None)

    logger.debug("Formatter keys: %s", formatter)

    clean_dict = {}
    for key in fmt_keys:
        logger.debug(repr(key))
        logger.debug(format_info.get(key))
        if isinstance(format_info.get(key), (str, float)):
            logger.debug("1")
            clean_dict[key] = clean_filename(str(format_info[key]), restrict=restrict)
        elif key == "explicit":
            logger.debug("3")
            clean_dict[key] = " (Explicit) " if format_info.get(key, False) else ""
        elif isinstance(format_info.get(key), int):  # track/discnumber
            logger.debug("2")
            clean_dict[key] = f"{format_info[key]:02}"
        else:
            clean_dict[key] = "Unknown"

    return formatter.format(**clean_dict)


def tidal_cover_url(uuid, size):
    """Generate a tidal cover url.

    :param uuid:
    :param size:
    """
    possibles = (80, 160, 320, 640, 1280)
    assert size in possibles, f"size must be in {possibles}"

    return TIDAL_COVER_URL.format(uuid=uuid.replace("-", "/"), height=size, width=size)


def init_log(path: Optional[str] = None, level: str = "DEBUG"):
    """Create a log.

    :param path:
    :type path: Optional[str]
    :param level:
    :type level: str
    :param rotate:
    :type rotate: str
    """
    # path = os.path.join(LOG_DIR, "streamrip.log")
    level = logging.getLevelName(level)
    logging.basicConfig(level=level)


def decrypt_mqa_file(in_path, out_path, encryption_key):
    """Decrypt an MQA file.

    :param in_path:
    :param out_path:
    :param encryption_key:
    """
    try:
        from Crypto.Cipher import AES
        from Crypto.Util import Counter
    except (ImportError, ModuleNotFoundError):
        secho(
            "To download this item in MQA, you need to run ",
            fg="yellow",
            nl=False,
        )
        secho("pip3 install pycryptodome --upgrade", fg="blue", nl=False)
        secho(".")
        exit()

    # Do not change this
    master_key = "UIlTTEMmmLfGowo/UC60x2H45W6MdGgTRfo/umg4754="

    # Decode the base64 strings to ascii strings
    master_key = base64.b64decode(master_key)
    security_token = base64.b64decode(encryption_key)

    # Get the IV from the first 16 bytes of the securityToken
    iv = security_token[:16]
    encrypted_st = security_token[16:]

    # Initialize decryptor
    decryptor = AES.new(master_key, AES.MODE_CBC, iv)

    # Decrypt the security token
    decrypted_st = decryptor.decrypt(encrypted_st)

    # Get the audio stream decryption key and nonce from the decrypted security token
    key = decrypted_st[:16]
    nonce = decrypted_st[16:24]

    counter = Counter.new(64, prefix=nonce, initial_value=0)
    decryptor = AES.new(key, AES.MODE_CTR, counter=counter)

    with open(in_path, "rb") as enc_file:
        dec_bytes = decryptor.decrypt(enc_file.read())
        with open(out_path, "wb") as dec_file:
            dec_file.write(dec_bytes)


def ext(quality: int, source: str):
    """Get the extension of an audio file.

    :param quality:
    :type quality: int
    :param source:
    :type source: str
    """
    if quality <= 1:
        if source == "tidal":
            return ".m4a"
        else:
            return ".mp3"
    else:
        return ".flac"


def gen_threadsafe_session(
    headers: dict = None, pool_connections: int = 100, pool_maxsize: int = 100
) -> requests.Session:
    """Create a new Requests session with a large poolsize.

    :param headers:
    :type headers: dict
    :param pool_connections:
    :type pool_connections: int
    :param pool_maxsize:
    :type pool_maxsize: int
    :rtype: requests.Session
    """
    if headers is None:
        headers = {}

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
    session.mount("https://", adapter)
    session.headers.update(headers)
    return session


def decho(message, fg=None):
    """Debug echo the message.

    :param message:
    :param fg: ANSI color with which to display the message on the
    screen
    """
    secho(message, fg=fg)
    logger.debug(message)


def get_container(quality: int, source: str) -> str:
    """Get the file container given the quality.

    `container` can also be the the codec; both work.

    :param quality: quality id
    :type quality: int
    :param source:
    :type source: str
    :rtype: str
    """
    if quality >= 2:
        return "FLAC"

    if source == "tidal":
        return "AAC"

    return "MP3"


def get_cover_urls(resp: dict, source: str) -> dict:
    """Parse a response dict containing cover info according to the source.

    :param resp:
    :type resp: dict
    :param source:
    :type source: str
    :rtype: dict
    """

    if source == "qobuz":
        cover_urls = resp["image"]
        cover_urls["original"] = cover_urls["large"].replace("600", "org")
        return cover_urls

    if source == "tidal":
        uuid = resp["cover"]
        return {
            sk: tidal_cover_url(uuid, size)
            for sk, size in zip(COVER_SIZES, (160, 320, 640, 1280))
        }

    if source == "deezer":
        resp_keys = ("cover", "cover_medium", "cover_large", "cover_xl")
        resp_keys_fallback = (
            "picture",
            "picture_medium",
            "picture_large",
            "picture_xl",
        )
        cover_urls = {
            sk: resp.get(rk, resp.get(rkf))  # size key, resp key, resp key fallback
            for sk, rk, rkf in zip(
                COVER_SIZES,
                resp_keys,
                resp_keys_fallback,
            )
        }

        if cover_urls["large"] is None and resp.get("cover_big") is not None:
            cover_urls["large"] = resp["cover_big"]

        return cover_urls

    if source == "soundcloud":
        cover_url = (resp["artwork_url"] or resp["user"].get("avatar_url")).replace(
            "large", "t500x500"
        )

        cover_urls = {"large": cover_url}

        return cover_urls

    raise InvalidSourceError(source)


def downsize_image(filepath: str, width: int, height: int):
    """Downsize an image.

    If either the width or the height is greater than the image's width or
    height, that dimension will not be changed.

    :param filepath:
    :type filepath: str
    :param width:
    :type width: int
    :param height:
    :type height: int
    :raises: ValueError
    """
    if width == -1 or height == -1:
        return

    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(filepath)
    except UnidentifiedImageError:
        secho("Cover art not found, skipping downsize.", fg="red")
        return

    width = min(width, image.width)
    height = min(height, image.height)

    resized_image = image.resize((width, height))
    resized_image.save(filepath)


TQDM_THEMES = {
    "plain": None,
    "dainty": (
        "{desc} |{bar}| "
        + style("{remaining}", fg="magenta")
        + " left at "
        + style("{rate_fmt}{postfix} ", fg="cyan", bold=True)
    ),
}

TQDM_DEFAULT_THEME = "dainty"

TQDM_BAR_FORMAT = TQDM_THEMES["dainty"]


def set_progress_bar_theme(theme: str):
    """Set the theme of the tqdm progress bar.

    :param theme:
    :type theme: str
    """
    global TQDM_BAR_FORMAT
    TQDM_BAR_FORMAT = TQDM_THEMES[theme]


def tqdm_stream(iterator, desc: Optional[str] = None) -> Iterator[bytes]:
    """Return a tqdm bar with presets appropriate for downloading large files.

    :param iterator:
    :type iterator: DownloadStream
    :param desc: Description to add for the progress bar
    :type desc: Optional[str]
    :rtype: Iterator
    """
    with get_tqdm_bar(len(iterator), desc=desc) as bar:
        for chunk in iterator:
            bar.update(len(chunk))
            yield chunk


def get_tqdm_bar(total, desc: Optional[str] = None, unit="B"):
    return tqdm(
        total=total,
        unit=unit,
        unit_scale=True,
        unit_divisor=1024,
        desc=desc,
        dynamic_ncols=True,
        bar_format=TQDM_BAR_FORMAT,
    )
