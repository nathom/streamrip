import base64
import contextlib
import logging
import os
import re
import sys
from string import Formatter
from typing import Hashable, Optional, Union

import click
import requests
from Crypto.Cipher import AES
from Crypto.Util import Counter
from pathvalidate import sanitize_filename
from requests.packages import urllib3
from tqdm import tqdm
from tqdm.contrib import DummyTqdmFile

from .constants import AGENT, LOG_DIR, TIDAL_COVER_URL
from .exceptions import InvalidSourceError, NonStreamable

urllib3.disable_warnings()
logger = logging.getLogger(__name__)


def safe_get(d: dict, *keys: Hashable, default=None):
    """A replacement for chained `get()` statements on dicts:
    >>> d = {'foo': {'bar': 'baz'}}
    >>> _safe_get(d, 'baz')
    None
    >>> _safe_get(d, 'foo', 'bar')
    'baz'
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


def get_quality(quality_id: int, source: str) -> Union[str, int]:
    """Given the quality id in (0, 1, 2, 3, 4), return the streaming quality
    value to send to the api for a given source.

    :param quality_id: the quality id
    :type quality_id: int
    :param source: qobuz, tidal, or deezer
    :type source: str
    :rtype: Union[str, int]
    """
    if source == "qobuz":
        q_map = {
            1: 5,
            2: 6,
            3: 7,
            4: 27,
        }
    elif source == "tidal":
        q_map = {
            0: "LOW",  # AAC
            1: "HIGH",  # AAC
            2: "LOSSLESS",  # CD Quality
            3: "HI_RES",  # MQA
        }
    elif source == "deezer":
        q_map = {
            0: 128,
            1: 320,
            2: 1411,
        }
    else:
        raise InvalidSourceError(source)

    possible_keys = set(q_map.keys())
    assert quality_id in possible_keys, f"{quality_id} must be in {possible_keys}"
    return q_map[quality_id]


def get_quality_id(bit_depth: Optional[int], sampling_rate: Optional[int]):
    """Return a quality id in (5, 6, 7, 27) from bit depth and
    sampling rate. If None is provided, mp3/lossy is assumed.

    :param bit_depth:
    :type bit_depth: Optional[int]
    :param sampling_rate:
    :type sampling_rate: Optional[int]
    """
    if not (bit_depth or sampling_rate):  # is lossy
        return 1

    if bit_depth == 16:
        return 2

    if bit_depth == 24:
        if sampling_rate <= 96:
            return 3

        return 4


@contextlib.contextmanager
def std_out_err_redirect_tqdm():
    orig_out_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = map(DummyTqdmFile, orig_out_err)
        yield orig_out_err[0]
    # Relay exceptions
    except Exception as exc:
        raise exc
    # Always restore sys.stdout/err if necessary
    finally:
        sys.stdout, sys.stderr = orig_out_err


def tqdm_download(url: str, filepath: str, params: dict = None, desc: str = None):
    """Downloads a file with a progress bar.

    :param url: url to direct download
    :param filepath: file to write
    :type url: str
    :type filepath: str
    """
    logger.debug(f"Downloading {url} to {filepath} with params {params}")
    if params is None:
        params = {}

    session = gen_threadsafe_session()
    r = session.get(url, allow_redirects=True, stream=True, params=params)
    total = int(r.headers.get("content-length", 0))
    logger.debug(f"File size = {total}")
    if total < 1000 and not url.endswith("jpg") and not url.endswith("png"):
        raise NonStreamable(url)

    try:
        with open(filepath, "wb") as file, tqdm(
            total=total,
            unit="iB",
            unit_scale=True,
            unit_divisor=1024,
            desc=desc,
            dynamic_ncols=True,
            # leave=False,
        ) as bar:
            for data in r.iter_content(chunk_size=1024):
                size = file.write(data)
                bar.update(size)
    except Exception:
        try:
            os.remove(filepath)
        except OSError:
            pass
        raise


def clean_format(formatter: str, format_info):
    """Formats track or folder names sanitizing every formatter key.

    :param formatter:
    :type formatter: str
    :param kwargs:
    """
    fmt_keys = [i[1] for i in Formatter().parse(formatter) if i[1] is not None]

    logger.debug("Formatter keys: %s", fmt_keys)

    clean_dict = dict()
    for key in fmt_keys:
        if isinstance(format_info.get(key), (str, float)):
            clean_dict[key] = sanitize_filename(str(format_info[key]))
        elif isinstance(format_info.get(key), int):  # track/discnumber
            clean_dict[key] = f"{format_info[key]:02}"
        else:
            clean_dict[key] = "Unknown"

    return formatter.format(**clean_dict)


def tidal_cover_url(uuid, size):
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
    path = os.path.join(LOG_DIR, "streamrip.log")
    level = logging.getLevelName(level)
    logging.basicConfig(filename=path, filemode="a", level=level)


def decrypt_mqa_file(in_path, out_path, encryption_key):
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
    click.secho(message, fg=fg)
    logger.debug(message)


def extract_interpreter_url(url: str) -> str:
    """Extract artist ID from a Qobuz interpreter url.

    :param url: Urls of the form "https://www.qobuz.com/us-en/interpreter/{artist}/download-streaming-albums"
    :type url: str
    :rtype: str
    """
    session = gen_threadsafe_session({"User-Agent": AGENT})
    r = session.get(url)
    artist_id = re.search(r"getSimilarArtist\(\s*'(\w+)'", r.text).group(1)
    return artist_id


def get_container(quality: int, source: str) -> str:
    """Get the "container" given the quality. `container` can also be the
    the codec; both work.

    :param quality: quality id
    :type quality: int
    :param source:
    :type source: str
    :rtype: str
    """
    if quality >= 2:
        container = "FLAC"
    else:
        if source == "tidal":
            container = "AAC"
        else:
            container = "MP3"

    return container
