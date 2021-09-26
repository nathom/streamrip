"""Wrapper over a database that stores item IDs."""

import logging
import os
import sqlite3
from typing import Tuple, Union

logger = logging.getLogger("streamrip")


class Database:
    """A wrapper for an sqlite database."""

    structure: dict
    name: str

    def __init__(self, path, dummy=False):
        """Create a Database instance.

        :param path: Path to the database file.
        :param dummy: Make the database empty.
        """
        assert self.structure != []
        assert self.name

        if dummy or path is None:
            self.path = None
            self.is_dummy = True
            return
        self.is_dummy = False

        self.path = path
        if not os.path.exists(self.path):
            self.create()

    def create(self):
        """Create a database."""
        if self.is_dummy:
            return

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
        if self.is_dummy:
            return False

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

    def __contains__(self, keys: Union[str, dict]) -> bool:
        """Check whether a key-value pair exists in the database.

        :param keys: Either a dict with the structure {key: value_to_search_for, ...},
        or if there is only one key in the table, value_to_search_for can be
        passed in by itself.
        :type keys: Union[str, dict]
        :rtype: bool
        """
        if isinstance(keys, dict):
            return self.contains(**keys)

        if isinstance(keys, str) and len(self.structure) == 1:
            only_key = tuple(self.structure.keys())[0]
            query = {only_key: keys}
            logger.debug("Searching for %s in database", query)
            return self.contains(**query)

        raise TypeError(keys)

    def add(self, items: Union[str, Tuple[str]]):
        """Add a row to the table.

        :param items: Column-name + value. Values must be provided for all cols.
        :type items: Tuple[str]
        """
        if self.is_dummy:
            return

        if isinstance(items, str):
            if len(self.structure) == 1:
                items = (items,)
            else:
                raise TypeError(
                    "Only tables with 1 column can have string inputs. Use a list "
                    "where len(list) == len(structure)."
                )

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
        # not in use currently
        if self.is_dummy:
            return

        conditions = " AND ".join(f"{key}=?" for key in items.keys())
        command = f"DELETE FROM {self.name} WHERE {conditions}"

        with sqlite3.connect(self.path) as conn:
            logger.debug(command)
            conn.execute(command, tuple(items.values()))

    def __iter__(self):
        """Iterate through the rows of the table."""
        if self.is_dummy:
            return ()

        with sqlite3.connect(self.path) as conn:
            return conn.execute(f"SELECT * FROM {self.name}")

    def reset(self):
        """Delete the database file."""
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


class Downloads(Database):
    """A table that stores the downloaded IDs."""

    name = "downloads"
    structure = {
        "id": ["text", "unique"],
    }


class FailedDownloads(Database):
    """A table that stores information about failed downloads."""

    name = "failed_downloads"
    structure = {
        "source": ["text"],
        "media_type": ["text"],
        "id": ["text", "unique"],
    }


CLASS_MAP = {db.name: db for db in (Downloads, FailedDownloads)}
