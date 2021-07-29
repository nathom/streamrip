"""Utility functions for RipCore."""

import re
from typing import Tuple

from streamrip.constants import AGENT
from streamrip.utils import gen_threadsafe_session

interpreter_artist_regex = re.compile(r"getSimilarArtist\(\s*'(\w+)'")


def extract_interpreter_url(url: str) -> str:
    """Extract artist ID from a Qobuz interpreter url.

    :param url: Urls of the form "https://www.qobuz.com/us-en/interpreter/{artist}/download-streaming-albums"
    :type url: str
    :rtype: str
    """
    session = gen_threadsafe_session({"User-Agent": AGENT})
    r = session.get(url)
    match = interpreter_artist_regex.search(r.text)
    if match:
        return match.group(1)

    raise Exception(
        "Unable to extract artist id from interpreter url. Use a "
        "url that contains an artist id."
    )


deezer_id_link_regex = re.compile(
    r"https://www\.deezer\.com/[a-z]{2}/(album|artist|playlist|track)/(\d+)"
)


def extract_deezer_dynamic_link(url: str) -> Tuple[str, str]:
    """Extract a deezer url that includes an ID from a deezer.page.link url.

    :param url:
    :type url: str
    :rtype: Tuple[str, str]
    """
    session = gen_threadsafe_session({"User-Agent": AGENT})
    r = session.get(url)
    match = deezer_id_link_regex.search(r.text)
    if match:
        return match.group(1), match.group(2)

    raise Exception("Unable to extract Deezer dynamic link.")
