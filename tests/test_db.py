import os
import tempfile

import pytest

import streamrip.db as db


@pytest.fixture
def tmp_path_str():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


class TestDummy:
    def test_contains_always_false(self):
        d = db.Dummy()
        assert d.contains(id="abc") is False

    def test_add_noop(self):
        d = db.Dummy()
        d.add(("abc",))  # should not raise

    def test_remove_noop(self):
        d = db.Dummy()
        d.remove("abc")  # positional — should not raise

    def test_all_empty(self):
        d = db.Dummy()
        assert d.all() == []


class TestDownloads:
    def test_add_and_contains(self, tmp_path_str):
        path = os.path.join(tmp_path_str, "downloads.db")
        d = db.Downloads(path)
        d.add(("track-123",))
        assert d.contains(id="track-123") is True

    def test_contains_missing(self, tmp_path_str):
        path = os.path.join(tmp_path_str, "downloads.db")
        d = db.Downloads(path)
        assert d.contains(id="nonexistent") is False

    def test_all_returns_added(self, tmp_path_str):
        path = os.path.join(tmp_path_str, "downloads.db")
        d = db.Downloads(path)
        d.add(("id-a",))
        d.add(("id-b",))
        rows = d.all()
        ids = [r[0] for r in rows]
        assert "id-a" in ids
        assert "id-b" in ids

    def test_reset_deletes_file(self, tmp_path_str):
        path = os.path.join(tmp_path_str, "downloads.db")
        d = db.Downloads(path)
        d.add(("id-x",))
        assert os.path.exists(path)
        d.reset()
        assert not os.path.exists(path)

    def test_duplicate_add_idempotent(self, tmp_path_str):
        path = os.path.join(tmp_path_str, "downloads.db")
        d = db.Downloads(path)
        d.add(("same-id",))
        d.add(("same-id",))  # unique constraint — should not raise
        assert len(d.all()) == 1

    def test_persistent_across_instances(self, tmp_path_str):
        path = os.path.join(tmp_path_str, "downloads.db")
        d1 = db.Downloads(path)
        d1.add(("persist-me",))
        d2 = db.Downloads(path)
        assert d2.contains(id="persist-me") is True


class TestFailed:
    def test_add_and_all(self, tmp_path_str):
        path = os.path.join(tmp_path_str, "failed.db")
        f = db.Failed(path)
        f.add(("deezer", "track", "fail-1"))
        rows = f.all()
        assert len(rows) == 1
        assert rows[0] == ("deezer", "track", "fail-1")

    def test_contains_by_id(self, tmp_path_str):
        path = os.path.join(tmp_path_str, "failed.db")
        f = db.Failed(path)
        f.add(("qobuz", "album", "album-42"))
        assert f.contains(id="album-42") is True
        assert f.contains(id="unknown") is False

    def test_reset_deletes_file(self, tmp_path_str):
        path = os.path.join(tmp_path_str, "failed.db")
        f = db.Failed(path)
        f.add(("tidal", "track", "t1"))
        assert os.path.exists(path)
        f.reset()
        assert not os.path.exists(path)


class TestDatabase:
    def test_downloaded_and_set_downloaded(self, tmp_path_str):
        dl_path = os.path.join(tmp_path_str, "dl.db")
        fail_path = os.path.join(tmp_path_str, "fail.db")
        database = db.Database(db.Downloads(dl_path), db.Failed(fail_path))
        assert database.downloaded("abc") is False
        database.set_downloaded("abc")
        assert database.downloaded("abc") is True

    def test_set_failed_and_get(self, tmp_path_str):
        dl_path = os.path.join(tmp_path_str, "dl.db")
        fail_path = os.path.join(tmp_path_str, "fail.db")
        database = db.Database(db.Downloads(dl_path), db.Failed(fail_path))
        database.set_failed("deezer", "track", "bad-id")
        rows = database.get_failed_downloads()
        assert len(rows) == 1
        assert rows[0] == ("deezer", "track", "bad-id")
