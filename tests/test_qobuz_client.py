import logging

import pytest
from util import afor, arun

from streamrip.config import Config
from streamrip.downloadable import BasicDownloadable
from streamrip.exceptions import MissingCredentials
from streamrip.qobuz_client import QobuzClient

logger = logging.getLogger("streamrip")


@pytest.fixture()
def client(qobuz_client):
    return qobuz_client


def test_client_raises_missing_credentials():
    c = Config.defaults()
    with pytest.raises(MissingCredentials):
        arun(QobuzClient(c).login())


def test_client_get_metadata(client):
    meta = arun(client.get_metadata("lzpf67e8f4h1a", "album"))
    assert meta["title"] == "I Killed Your Dog"
    assert len(meta["tracks"]["items"]) == 16
    assert meta["maximum_bit_depth"] == 24


def test_client_get_downloadable(client):
    d = arun(client.get_downloadable("19512574", 3))
    assert isinstance(d, BasicDownloadable)
    assert d.extension == "flac"
    assert isinstance(d.url, str)
    assert "https://" in d.url


def test_client_search_limit(client):
    res = client.search("rumours", "album", limit=5)
    total = 0
    for r in afor(res):
        total += len(r["albums"]["items"])
    assert total == 5


def test_client_search_no_limit(client):
    res = client.search("rumours", "album", limit=None)
    correct_total = 0
    total = 0
    for r in afor(res):
        total += len(r["albums"]["items"])
        correct_total = max(correct_total, r["albums"]["total"])
    assert total == correct_total
