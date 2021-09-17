import os
import time
from pprint import pprint

from streamrip.downloadtools import DownloadPool


def test_downloadpool(tmpdir):
    start = time.perf_counter()
    with DownloadPool(
        (f"https://pokeapi.co/api/v2/pokemon/{number}" for number in range(1, 151)),
        tempdir=tmpdir,
    ) as pool:
        pool.download()
        assert len(os.listdir(tmpdir)) == 151

    # the tempfiles should be removed at this point
    assert len(os.listdir(tmpdir)) == 0

    print(f"Finished in {time.perf_counter() - start}s")
