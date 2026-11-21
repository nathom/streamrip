"""Wrapper over a database that stores item IDs."""

import logging
import os
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger("streamrip")


class DatabaseInterface(ABC):
    @abstractmethod
    def create(self):
        pass

    @abstractmethod
    def contains(self, **items) -> bool:
        pass

    @abstractmethod
    def add(self, kvs):
        pass

    @abstractmethod
    def remove(self, kvs):
        pass

    @abstractmethod
    def all(self) -> list:
        pass


class Dummy(DatabaseInterface):
    """This exists as a mock to use in case databases are disabled."""

    def create(self):
        pass

    def contains(self, **_):
        return ""

    def add(self, *_):
        pass

    def remove(self, *_):
        pass

    def all(self):
        return []


class DatabaseBase(DatabaseInterface):
    """A wrapper for an sqlite database."""

    structure: dict
    name: str

    def __init__(self, path: str):
        """Create a Database instance.

        :param path: Path to the database file.
        """
        assert self.structure != {}
        assert self.name
        assert path

        self.path = path

        if not os.path.exists(self.path):
            self.create()

    def create(self):
        """Create a database."""
        with sqlite3.connect(self.path) as conn:
            params = ", ".join(
                f"{key} {' '.join(map(str.upper, props))} NOT NULL"
                for key, props in self.structure.items()
            )
            command = f"CREATE TABLE {self.name} ({params})"

            logger.debug("executing %s", command)

            conn.execute(command)

    def keys(self):
        """Get the column names of the table."""
        return self.structure.keys()

    def contains(self, **items) -> bool:
        """Check whether items matches an entry in the table.

        :param items: a dict of column-name + expected value
        :rtype: bool
        """
        allowed_keys = set(self.structure.keys())
        assert all(
            key in allowed_keys for key in items.keys()
        ), f"Invalid key. Valid keys: {allowed_keys}"

        items = {k: str(v) for k, v in items.items()}

        with sqlite3.connect(self.path) as conn:
            conditions = " AND ".join(f"{key}=?" for key in items.keys())
            command = f"SELECT EXISTS(SELECT 1 FROM {self.name} WHERE {conditions})"

            logger.debug("Executing %s", command)

            return bool(conn.execute(command, tuple(items.values())).fetchone()[0])

    def add(self, items: tuple[str]):
        """Add a row to the table.

        :param items: Column-name + value. Values must be provided for all cols.
        :type items: Tuple[str]
        """
        assert len(items) == len(self.structure)

        params = ", ".join(self.structure.keys())
        question_marks = ", ".join("?" for _ in items)
        command = f"INSERT INTO {self.name} ({params}) VALUES ({question_marks})"

        logger.debug("Executing %s", command)
        logger.debug("Items to add: %s", items)

        with sqlite3.connect(self.path) as conn:
            try:
                conn.execute(command, tuple(items))
            except sqlite3.IntegrityError as e:
                # tried to insert an item that was already there
                logger.debug(e)

    def remove(self, **items):
        """Remove items from a table.

        Warning: NOT TESTED!

        :param items:
        """
        conditions = " AND ".join(f"{key}=?" for key in items.keys())
        command = f"DELETE FROM {self.name} WHERE {conditions}"

        with sqlite3.connect(self.path) as conn:
            logger.debug(command)
            conn.execute(command, tuple(items.values()))

    def all(self):
        """Iterate through the rows of the table."""
        with sqlite3.connect(self.path) as conn:
            return list(conn.execute(f"SELECT * FROM {self.name}"))

    def reset(self):
        """Delete the database file."""
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


class Downloads(DatabaseBase):
    """A table that stores the downloaded IDs."""

    name = "downloads"
    structure: Final[dict] = {
        "id": ["text", "unique"],
        "filepath": ["text"],
    }

    def get_path(self, **items) -> str:
        """Check whether items matches an entry in the table, return associated filepath

        :param items: a dict of column-name + expected value
        :rtype: string
        """
        allowed_keys = set(self.structure.keys())
        assert all(
            key in allowed_keys for key in items.keys()
        ), f"Invalid key. Valid keys: {allowed_keys}"

        items = {k: str(v) for k, v in items.items()}

        with sqlite3.connect(self.path) as conn:
            conditions = " AND ".join(f"{key}=?" for key in items.keys())
            command = f"SELECT filepath FROM {self.name} WHERE {conditions}"
            logger.debug("Executing %s", command)
            row = conn.execute(command, tuple(items.values())).fetchone()
            if row:
                return row[0]
            else:
                return ""


class Replacements(DatabaseBase):
    """A table that stores replacement IDs for original IDs."""

    name = "replacements"
    structure: Final[dict] = {
        "original_id": ["text", "unique"],
        "replacement_id": ["text"],
    }

    def __init__(self, path: str):
        # Ensure DB file exists (may be same file as downloads). Call parent's init
        # which will create file if missing. Then ensure the replacements table
        # exists in the database using IF NOT EXISTS to support existing DB files.
        self.path = path
        # Ensure file exists so sqlite can open it
        if not os.path.exists(self.path):
            # create an empty database file
            open(self.path, "a").close()

        # Create the replacements table if it doesn't exist
        with sqlite3.connect(self.path) as conn:
            params = ", ".join(
                f"{key} {' '.join(map(str.upper, props))} NOT NULL" for key, props in self.structure.items()
            )
            command = f"CREATE TABLE IF NOT EXISTS {self.name} ({params})"
            logger.debug("executing %s", command)
            conn.execute(command)

    def get_replacement(self, original_id: str) -> str:
        """Return the replacement id for an original id, or empty string if none."""
        with sqlite3.connect(self.path) as conn:
            command = f"SELECT replacement_id FROM {self.name} WHERE original_id=?"
            logger.debug("Executing %s", command)
            row = conn.execute(command, (str(original_id),)).fetchone()
            if row:
                return row[0]
            else:
                return ""

    def set_replacement(self, original_id: str, replacement_id: str):
        """Store a mapping from original_id -> replacement_id. Ignore duplicates."""
        try:
            self.add((original_id, replacement_id))
            logger.debug("Inserted replacement mapping %s -> %s", original_id, replacement_id)
        except Exception:
            # Ignore any integrity errors or others — mapping may already exist
            logger.debug("Could not insert replacement %s -> %s", original_id, replacement_id)


class Failed(DatabaseBase):
    """A table that stores information about failed downloads."""

    name = "failed_downloads"
    structure: Final[dict] = {
        "source": ["text"],
        "media_type": ["text"],
        "id": ["text", "unique"],
    }


@dataclass(slots=True)
class Database:
    downloads: Downloads
    failed: Failed
    replacements: Replacements

    def downloaded(self, item_id: str) -> str:
        # Check direct download first.
        # If the requested id was an old or invalid identifier, consult the
        # replacements table to find a mapped replacement id and return the
        # filepath for that replacement if it has already been downloaded.
        path = self.downloads.get_path(id=item_id)
        if path:
            return path
        # If not found, check replacements mapping
        rep = self.replacements.get_replacement(item_id)
        if rep:
            path = self.downloads.get_path(id=rep)
            if path:
                logger.info(
                    "Using replacement id %s for original id %s",
                    rep,
                    item_id,
                )
            return path
        return ""

    def set_downloaded(self, item_id, filepath: str):
        self.downloads.add((item_id,filepath,))

    def get_failed_downloads(self) -> list[tuple[str, str, str]]:
        return self.failed.all()

    def set_failed(self, source: str, media_type: str, id: str):
        self.failed.add((source, media_type, id))

    def get_replacement(self, original_id: str) -> str:
        return self.replacements.get_replacement(original_id)

    def set_replacement(self, original_id: str, replacement_id: str):
        self.replacements.set_replacement(original_id, replacement_id)
