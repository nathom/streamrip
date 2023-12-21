import os
import shutil

from util import arun

from streamrip.downloadable import Downloadable
from streamrip.qobuz_client import QobuzClient
from streamrip.track import PendingSingle, Track


def test_pending_resolve(qobuz_client: QobuzClient):
    qobuz_client.config.session.downloads.folder = "./tests"
    p = PendingSingle("19512574", qobuz_client, qobuz_client.config)
    t = arun(p.resolve())
    dir = "tests/Fleetwood Mac - Rumours (1977) [FLAC] [24B-96kHz]"
    assert os.path.isdir(dir)
    assert os.path.isfile(os.path.join(dir, "cover.jpg"))
    assert os.path.isfile(os.path.join(dir, "embed_cover.jpg"))
    assert isinstance(t, Track)
    assert isinstance(t.downloadable, Downloadable)
    assert t.cover_path is not None
    shutil.rmtree(dir)


# def test_pending_resolve_mp3(qobuz_client: QobuzClient):
#     qobuz_client.config.session.qobuz.quality = 1
#     p = PendingSingle("19512574", qobuz_client, qobuz_client.config)
#     t = arun(p.resolve())
#     assert isinstance(t, Track)
#     assert False
