import logging
import os

import pytest
from util import arun

from streamrip.client.downloadable import BasicDownloadable
from streamrip.client.qobuz import QobuzClient
from streamrip.config import Config
from streamrip.exceptions import MissingCredentialsError

logger = logging.getLogger("streamrip")


@pytest.fixture()
def client(qobuz_client):
    return qobuz_client


def test_client_raises_missing_credentials():
    c = Config.defaults()
    with pytest.raises(MissingCredentialsError):
        arun(QobuzClient(c).login())


@pytest.mark.skipif(
    "QOBUZ_EMAIL" not in os.environ, reason="Qobuz credentials not found in env."
)
def test_client_get_metadata(client):
    meta = arun(client.get_metadata("s9nzkwg2rh1nc", "album"))
    assert meta["title"] == "I Killed Your Dog"
    assert len(meta["tracks"]["items"]) == 16
    assert meta["maximum_bit_depth"] == 24


@pytest.mark.skipif(
    "QOBUZ_EMAIL" not in os.environ, reason="Qobuz credentials not found in env."
)
def test_client_get_downloadable(client):
    d = arun(client.get_downloadable("19512574", 3))
    assert isinstance(d, BasicDownloadable)
    assert d.extension == "flac"
    assert isinstance(d.url, str)
    assert "https://" in d.url


@pytest.mark.skipif(
    "QOBUZ_EMAIL" not in os.environ, reason="Qobuz credentials not found in env."
)
def test_client_search_limit(client):
    res = client.search("album", "rumours", limit=5)
    total = 0
    for r in arun(res):
        total += len(r["albums"]["items"])
    assert total == 5


@pytest.mark.skipif(
    "QOBUZ_EMAIL" not in os.environ, reason="Qobuz credentials not found in env."
)
def test_client_search_no_limit(client):
    # Setting no limit has become impossible because `limit: int` now
    res = client.search("album", "rumours", limit=10000)
    correct_total = 0
    total = 0
    for r in arun(res):
        total += len(r["albums"]["items"])
        correct_total = max(correct_total, r["albums"]["total"])
    assert total == correct_total
