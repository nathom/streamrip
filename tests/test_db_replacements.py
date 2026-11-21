import os
import sqlite3
import tempfile
from types import SimpleNamespace
from typing import Final

import pytest

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


def test_legacy_downloads_table_adds_filepath_and_migration_is_idempotent():
    with tempfile.TemporaryDirectory() as tempdir:
        db_path = os.path.join(tempdir, "downloads.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE downloads (id TEXT UNIQUE NOT NULL)")
            conn.execute("INSERT INTO downloads (id) VALUES (?)", ("existing-id",))

        downloads = db.Downloads(db_path)

        assert downloads.all() == [("existing-id", "")]

        reopened = db.Downloads(db_path)
        assert reopened.all() == [("existing-id", "")]

        with sqlite3.connect(db_path) as conn:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(downloads)")]
        assert columns == ["id", "filepath"]


def test_download_table_is_created_when_database_file_already_exists():
    with tempfile.TemporaryDirectory() as tempdir:
        db_path = os.path.join(tempdir, "downloads.db")
        sqlite3.connect(db_path).close()

        downloads = db.Downloads(db_path)

        assert downloads.all() == []


def test_failed_table_adds_missing_column_using_shared_migration():
    with tempfile.TemporaryDirectory() as tempdir:
        db_path = os.path.join(tempdir, "failed.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE failed_downloads "
                "(source TEXT NOT NULL, id TEXT UNIQUE NOT NULL)"
            )
            conn.execute(
                "INSERT INTO failed_downloads (source, id) VALUES (?, ?)",
                ("qobuz", "track-id"),
            )

        failed = db.Failed(db_path)

        assert failed.all() == [("qobuz", "", "track-id")]


def test_missing_column_without_migration_default_fails_visibly():
    class CustomTable(db.DatabaseBase):
        name = "custom"
        structure: Final[dict] = {"id": ["text", "unique"], "label": ["text"]}

    with tempfile.TemporaryDirectory() as tempdir:
        db_path = os.path.join(tempdir, "custom.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE custom (id TEXT UNIQUE NOT NULL)")
            conn.execute("INSERT INTO custom (id) VALUES (?)", ("existing-id",))

        with pytest.raises(ValueError, match="migration default"):
            CustomTable(db_path)

        with sqlite3.connect(db_path) as conn:
            rows = list(conn.execute("SELECT id FROM custom"))
        assert rows == [("existing-id",)]
