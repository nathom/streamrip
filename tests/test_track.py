import os
import shutil

import pytest
from util import arun

import streamrip.db as db
from streamrip.client.downloadable import Downloadable
from streamrip.client.qobuz import QobuzClient
from streamrip.media.track import PendingSingle, Track


@pytest.mark.skipif(
    "QOBUZ_EMAIL" not in os.environ, reason="Qobuz credentials not found in env."
)
def test_pending_resolve(qobuz_client: QobuzClient):
    qobuz_client.config.session.downloads.folder = "./tests"
    p = PendingSingle(
        "19512574",
        qobuz_client,
        qobuz_client.config,
        db.Database(db.Dummy(), db.Dummy()),
    )
    t = arun(p.resolve())
    dir = "tests/tests/Fleetwood Mac - Rumours (1977) [FLAC] [24B-96kHz]"
    assert os.path.isdir(dir)
    assert os.path.isfile(os.path.join(dir, "cover.jpg"))
    assert os.path.isfile(t.cover_path)
    assert isinstance(t, Track)
    assert isinstance(t.downloadable, Downloadable)
    assert t.cover_path is not None
    shutil.rmtree(dir)
