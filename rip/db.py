"""Wrapper over a database that stores item IDs."""

import logging
import os
import sqlite3
from typing import List

logger = logging.getLogger("streamrip")


class Database:
    structure: dict
    # name of table
    name: str

    def __init__(self, path, dummy=False):
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
        if self.is_dummy:
            return

        with sqlite3.connect(self.path) as conn:
            params = ", ".join(
                f"{key} {' '.join(map(str.upper, props))}"
                for key, props in self.structure.items()
            )
            command = f"CREATE TABLE {self.name} ({params})"

            logger.debug(f"executing {command}")

            conn.execute(command)

    def keys(self):
        return self.structure.keys()

    def contains(self, **items):
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

            logger.debug(f"executing {command}")

            result = conn.execute(command, tuple(items.values()))
            return result

    def __contains__(self, keys: dict) -> bool:
        return self.contains(**keys)

    def add(self, items: List[str]):
        if self.is_dummy:
            return

        assert len(items) == len(self.structure)

        params = ", ".join(self.structure.keys())
        question_marks = ", ".join("?" for _ in items)
        command = f"INSERT INTO {self.name} ({params}) VALUES ({question_marks})"

        logger.debug(f"executing {command}")

        with sqlite3.connect(self.path) as conn:
            try:
                conn.execute(command, tuple(items))
            except sqlite3.IntegrityError as e:
                # tried to insert an item that was already there
                logger.debug(e)

    def __iter__(self):
        if self.is_dummy:
            return ()

        with sqlite3.connect(self.path) as conn:
            return conn.execute(f"SELECT * FROM {self.name}")

    def reset(self):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


class Downloads(Database):
    name = "downloads"
    structure = {
        "id": ["unique", "text"],
    }


class FailedDownloads(Database):
    name = "failed_downloads"
    structure = {
        "source": ["text"],
        "media_type": ["text"],
        "id": ["text", "unique"],
    }


CLASS_MAP = {db.name: db for db in (Downloads, FailedDownloads)}
