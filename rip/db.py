"""Wrapper over a database that stores item IDs."""

import logging
import os
import sqlite3
from typing import Union, List
import abc

logger = logging.getLogger("streamrip")


class Database:
    # list of table column names
    structure: list
    # name of table
    name: str

    def __init__(self, path, empty=False):
        assert self.structure != []
        assert self.name

        if empty:
            self.path = None
            return

        self.path = path
        if not os.path.exists(self.path):
            self.create()

    def create(self):
        if self.path is None:
            return

        with sqlite3.connect(self.path) as conn:
            try:
                params = ", ".join(
                    f"{key} TEXT UNIQUE NOT NULL" for key in self.structure
                )
                command = f"CREATE TABLE {self.name} ({params});"

                logger.debug(f"executing {command}")

                conn.execute(command)
            except sqlite3.OperationalError:
                pass

    def keys(self):
        return self.structure

    def contains(self, **items):
        allowed_keys = set(self.structure)
        assert all(
            key in allowed_keys for key in items.keys()
        ), f"Invalid key. Valid keys: {self.structure}"

        items = {k: str(v) for k, v in items.items()}

        if self.path is None:
            return False

        with sqlite3.connect(self.path) as conn:
            conditions = " AND ".join(f"{key}=?" for key in items.keys())
            command = f"SELECT {self.structure[0]} FROM {self.name} WHERE {conditions}"

            logger.debug(f"executing {command}")

            return conn.execute(command, tuple(items.values())).fetchone() is not None

    def __contains__(self, keys: dict) -> bool:
        return self.contains(**keys)

    def add(self, items: List[str]):
        assert len(items) == len(self.structure)
        if self.path is None:
            return

        params = ", ".join(self.structure)
        question_marks = ", ".join("?" for _ in items)
        command = f"INSERT INTO {self.name} ({params}) VALUES ({question_marks})"

        logger.debug(f"executing {command}")

        with sqlite3.connect(self.path) as conn:
            conn.execute(command, tuple(items))

    def __iter__(self):
        with sqlite3.connect(self.path) as conn:
            return conn.execute(f"SELECT * FROM {self.name}")


class Downloads(Database):
    structure = ["id"]
    name = "downloads"


class FailedDownloads(Database):
    structure = ["source", "type", "id"]
    name = "failed_downloads"
