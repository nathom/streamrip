"""Tests for the extended web application database."""

import os
import tempfile
import pytest

from backend.models.database import AppDatabase


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    database = AppDatabase(path)
    yield database
    os.unlink(path)


class TestAlbums:
    def test_upsert_and_get_album(self, db):
        album_id = db.upsert_album(
            source="qobuz",
            source_album_id="abc123",
            title="In Rainbows",
            artist="Radiohead",
            release_date="2007-10-10",
            quality="FLAC 24/44",
        )
        assert album_id > 0

        album = db.get_album(album_id)
        assert album["title"] == "In Rainbows"
        assert album["download_status"] == "not_downloaded"

    def test_upsert_updates_existing(self, db):
        id1 = db.upsert_album("qobuz", "abc123", "Old Title", "Artist")
        id2 = db.upsert_album("qobuz", "abc123", "New Title", "Artist")
        assert id1 == id2
        album = db.get_album(id1)
        assert album["title"] == "New Title"

    def test_get_albums_with_filter(self, db):
        db.upsert_album("qobuz", "a1", "Album A", "Artist A")
        db.upsert_album("qobuz", "a2", "Album B", "Artist B")
        db.update_album_status(
            db.get_album_by_source_id("qobuz", "a1")["id"],
            "complete",
        )

        complete = db.get_albums("qobuz", status="complete")
        assert len(complete) == 1
        assert complete[0]["title"] == "Album A"

    def test_get_albums_with_search(self, db):
        db.upsert_album("qobuz", "a1", "In Rainbows", "Radiohead")
        db.upsert_album("qobuz", "a2", "Kid A", "Radiohead")
        db.upsert_album("qobuz", "a3", "Blue Train", "John Coltrane")

        results = db.get_albums("qobuz", search="Radiohead")
        assert len(results) == 2

    def test_count_albums(self, db):
        db.upsert_album("qobuz", "a1", "A", "B")
        db.upsert_album("qobuz", "a2", "C", "D")
        db.upsert_album("tidal", "a3", "E", "F")

        assert db.count_albums("qobuz") == 2
        assert db.count_albums("tidal") == 1


class TestTracks:
    def test_upsert_and_get_tracks(self, db):
        album_id = db.upsert_album("qobuz", "a1", "Album", "Artist")
        db.upsert_track(album_id, "t1", "Track 1", "Artist", track_number=1)
        db.upsert_track(album_id, "t2", "Track 2", "Artist", track_number=2)

        tracks = db.get_tracks(album_id)
        assert len(tracks) == 2
        assert tracks[0]["title"] == "Track 1"
        assert tracks[1]["title"] == "Track 2"

    def test_update_track_status(self, db):
        album_id = db.upsert_album("qobuz", "a1", "Album", "Artist")
        track_id = db.upsert_track(album_id, "t1", "Track", "Artist")
        db.update_track_status(track_id, "complete", "/music/track.flac", "FLAC", 24, 96000)

        tracks = db.get_tracks(album_id)
        assert tracks[0]["download_status"] == "complete"
        assert tracks[0]["file_path"] == "/music/track.flac"


class TestSyncRuns:
    def test_create_and_complete_sync_run(self, db):
        run_id = db.create_sync_run("qobuz")
        db.complete_sync_run(run_id, albums_found=100, albums_new=5,
                             albums_removed=1, albums_downloaded=4)

        history = db.get_sync_history("qobuz")
        assert len(history) == 1
        assert history[0]["albums_new"] == 5
        assert history[0]["status"] == "complete"


class TestConfig:
    def test_set_and_get_config(self, db):
        db.set_config("qobuz.quality", "3")
        assert db.get_config("qobuz.quality") == "3"

    def test_get_all_config(self, db):
        db.set_config("qobuz.quality", "3")
        db.set_config("downloads.path", "/music")
        cfg = db.get_all_config()
        assert cfg["qobuz.quality"] == "3"
        assert cfg["downloads.path"] == "/music"

    def test_upsert_config(self, db):
        db.set_config("key", "old")
        db.set_config("key", "new")
        assert db.get_config("key") == "new"
