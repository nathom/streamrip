"""Extended SQLite database with WAL mode for the web application."""

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger("streamrip")

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_album_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    release_date TEXT,
    label TEXT,
    genre TEXT,
    track_count INTEGER,
    duration_seconds INTEGER,
    cover_url TEXT,
    cover_path TEXT,
    quality TEXT,
    file_size_bytes INTEGER,
    download_status TEXT NOT NULL DEFAULT 'not_downloaded',
    downloaded_at TEXT,
    added_to_library_at TEXT,
    user_id INTEGER NOT NULL DEFAULT 1,
    UNIQUE(source, source_album_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_albums_source_user ON albums(source, user_id);
CREATE INDEX IF NOT EXISTS idx_albums_download_status ON albums(download_status);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    source_track_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    track_number INTEGER,
    disc_number INTEGER DEFAULT 1,
    duration_seconds INTEGER,
    explicit BOOLEAN DEFAULT FALSE,
    isrc TEXT,
    format TEXT,
    bit_depth INTEGER,
    sample_rate INTEGER,
    file_path TEXT,
    download_status TEXT NOT NULL DEFAULT 'not_downloaded',
    UNIQUE(album_id, source_track_id)
);

CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    albums_found INTEGER DEFAULT 0,
    albums_new INTEGER DEFAULT 0,
    albums_removed INTEGER DEFAULT 0,
    albums_downloaded INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""


class AppDatabase:
    """Extended database for the web application."""

    def __init__(self, path: str):
        self.path = path
        self._persistent_conn: sqlite3.Connection | None = None
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        else:
            # In-memory databases are per-connection; keep one persistent
            # connection so the schema and data survive across calls.
            self._persistent_conn = sqlite3.connect(path, check_same_thread=False)
            self._persistent_conn.execute("PRAGMA foreign_keys=ON")
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )

    @contextmanager
    def _connect(self):
        if self._persistent_conn is not None:
            # Yield the persistent connection without closing it.
            conn = self._persistent_conn
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        else:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    # ── Albums ──

    def upsert_album(
        self,
        source: str,
        source_album_id: str,
        title: str,
        artist: str,
        release_date: str | None = None,
        label: str | None = None,
        genre: str | None = None,
        track_count: int | None = None,
        duration_seconds: int | None = None,
        cover_url: str | None = None,
        quality: str | None = None,
        added_to_library_at: str | None = None,
        user_id: int = 1,
    ) -> int:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO albums
                   (source, source_album_id, title, artist, release_date, label,
                    genre, track_count, duration_seconds, cover_url, quality,
                    added_to_library_at, user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, source_album_id, user_id)
                   DO UPDATE SET
                     title=excluded.title, artist=excluded.artist,
                     release_date=excluded.release_date, label=excluded.label,
                     genre=excluded.genre, track_count=excluded.track_count,
                     duration_seconds=excluded.duration_seconds,
                     cover_url=excluded.cover_url, quality=excluded.quality,
                     added_to_library_at=excluded.added_to_library_at
                """,
                (
                    source, source_album_id, title, artist, release_date,
                    label, genre, track_count, duration_seconds, cover_url,
                    quality, added_to_library_at, user_id,
                ),
            )
            row = conn.execute(
                "SELECT id FROM albums WHERE source=? AND source_album_id=? AND user_id=?",
                (source, source_album_id, user_id),
            ).fetchone()
            return row["id"]

    def get_albums(
        self,
        source: str,
        user_id: int = 1,
        status: str | None = None,
        search: str | None = None,
        sort_by: str = "added_to_library_at",
        sort_dir: str = "DESC",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["source = ?", "user_id = ?"]
        params: list = [source, user_id]

        if status and status != "all":
            conditions.append("download_status = ?")
            params.append(status)

        if search:
            conditions.append("(title LIKE ? OR artist LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        allowed_sorts = {
            "added_to_library_at", "title", "artist", "release_date", "downloaded_at"
        }
        if sort_by not in allowed_sorts:
            sort_by = "added_to_library_at"
        if sort_dir not in ("ASC", "DESC"):
            sort_dir = "DESC"

        where = " AND ".join(conditions)
        query = f"""
            SELECT * FROM albums
            WHERE {where}
            ORDER BY {sort_by} {sort_dir}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_album(self, album_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM albums WHERE id = ?", (album_id,)).fetchone()
            return dict(row) if row else None

    def get_album_by_source_id(self, source: str, source_album_id: str, user_id: int = 1) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM albums WHERE source=? AND source_album_id=? AND user_id=?",
                (source, source_album_id, user_id),
            ).fetchone()
            return dict(row) if row else None

    def update_album_status(self, album_id: int, status: str, downloaded_at: str | None = None):
        with self._connect() as conn:
            if downloaded_at:
                conn.execute(
                    "UPDATE albums SET download_status=?, downloaded_at=? WHERE id=?",
                    (status, downloaded_at, album_id),
                )
            else:
                conn.execute(
                    "UPDATE albums SET download_status=? WHERE id=?",
                    (status, album_id),
                )

    def count_albums(self, source: str, user_id: int = 1, status: str | None = None, search: str | None = None) -> int:
        conditions = ["source = ?", "user_id = ?"]
        params: list = [source, user_id]
        if status:
            conditions.append("download_status = ?")
            params.append(status)
        if search:
            conditions.append("(title LIKE ? OR artist LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        where = " AND ".join(conditions)
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM albums WHERE {where}", params).fetchone()
            return row["cnt"]

    # ── Tracks ──

    def upsert_track(
        self,
        album_id: int,
        source_track_id: str,
        title: str,
        artist: str,
        track_number: int | None = None,
        disc_number: int = 1,
        duration_seconds: int | None = None,
        explicit: bool = False,
        isrc: str | None = None,
    ) -> int:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO tracks
                   (album_id, source_track_id, title, artist, track_number,
                    disc_number, duration_seconds, explicit, isrc)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(album_id, source_track_id)
                   DO UPDATE SET
                     title=excluded.title, artist=excluded.artist,
                     track_number=excluded.track_number,
                     disc_number=excluded.disc_number,
                     duration_seconds=excluded.duration_seconds,
                     explicit=excluded.explicit, isrc=excluded.isrc
                """,
                (album_id, source_track_id, title, artist, track_number,
                 disc_number, duration_seconds, explicit, isrc),
            )
            row = conn.execute(
                "SELECT id FROM tracks WHERE album_id=? AND source_track_id=?",
                (album_id, source_track_id),
            ).fetchone()
            return row["id"]

    def get_tracks(self, album_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tracks WHERE album_id=? ORDER BY disc_number, track_number",
                (album_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_track_status(self, track_id: int, status: str, file_path: str | None = None,
                            format: str | None = None, bit_depth: int | None = None,
                            sample_rate: int | None = None):
        with self._connect() as conn:
            conn.execute(
                """UPDATE tracks SET download_status=?, file_path=?,
                   format=?, bit_depth=?, sample_rate=?
                   WHERE id=?""",
                (status, file_path, format, bit_depth, sample_rate, track_id),
            )

    # ── Sync Runs ──

    def create_sync_run(self, source: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO sync_runs (source, started_at) VALUES (?, ?)",
                (source, datetime.now().isoformat()),
            )
            return cursor.lastrowid

    def complete_sync_run(self, run_id: int, albums_found: int, albums_new: int,
                          albums_removed: int, albums_downloaded: int):
        with self._connect() as conn:
            conn.execute(
                """UPDATE sync_runs SET completed_at=?, albums_found=?,
                   albums_new=?, albums_removed=?, albums_downloaded=?,
                   status='complete'
                   WHERE id=?""",
                (datetime.now().isoformat(), albums_found, albums_new,
                 albums_removed, albums_downloaded, run_id),
            )

    def get_sync_history(self, source: str, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sync_runs WHERE source=? ORDER BY started_at DESC LIMIT ?",
                (source, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Config ──

    def get_config(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
            return row["value"] if row else None

    def set_config(self, key: str, value: str):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, value, datetime.now().isoformat()),
            )

    def get_all_config(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
            return {r["key"]: r["value"] for r in rows}
