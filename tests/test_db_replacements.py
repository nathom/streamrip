import os
import tempfile
from types import SimpleNamespace

import streamrip.db as db
from streamrip.media.track import Track


def test_replacement_mapping_for_downloaded_id():
    with tempfile.TemporaryDirectory() as tempdir:
        db_path = os.path.join(tempdir, "downloads.db")

        downloads = db.Downloads(db_path)
        replacements = db.Replacements(db_path)
        database = db.Database(downloads, db.Dummy(), replacements)

        assert database.downloaded("old-id") == ""

        database.set_downloaded("new-id", "/tmp/new-id.flac")
        database.set_replacement("old-id", "new-id")

        assert database.get_replacement("old-id") == "new-id"
        assert database.downloaded("old-id") == "/tmp/new-id.flac"
        assert database.downloaded("new-id") == "/tmp/new-id.flac"


def test_track_postprocess_records_replacement(monkeypatch):
    with tempfile.TemporaryDirectory() as tempdir:
        db_path = os.path.join(tempdir, "downloads.db")

        downloads = db.Downloads(db_path)
        replacements = db.Replacements(db_path)
        database = db.Database(downloads, db.Dummy(), replacements)

        meta = SimpleNamespace(info=SimpleNamespace(id="new-id"))
        downloadable = SimpleNamespace(_size=1)
        config = SimpleNamespace(session=SimpleNamespace(conversion=SimpleNamespace(enabled=False)))

        track = Track(
            meta=meta,
            downloadable=downloadable,
            config=config,
            folder=tempdir,
            m3u8="",
            cover_path=None,
            db=database,
            original_id="old-id",
            download_path=os.path.join(tempdir, "new-id.flac"),
        )

        async def fake_tag_file(path, meta_obj, cover_path):
            return None

        monkeypatch.setattr("streamrip.media.track.tag_file", fake_tag_file)

        from tests.util import arun

        arun(track.postprocess())

        assert database.get_replacement("old-id") == "new-id"
        assert database.downloaded("old-id") == os.path.join(tempdir, "new-id.flac")
        assert database.downloaded("new-id") == os.path.join(tempdir, "new-id.flac")


def test_replacements_table_persists_in_same_database_file():
    with tempfile.TemporaryDirectory() as tempdir:
        db_path = os.path.join(tempdir, "downloads.db")

        db.Downloads(db_path)
        db.Replacements(db_path).set_replacement("original", "replacement")

        # Re-open the same database file and verify the replacement was stored
        replacements = db.Replacements(db_path)
        assert replacements.get_replacement("original") == "replacement"
