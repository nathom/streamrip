import logging
import sqlite3

from qobuz_dl.color import RED, YELLOW

logger = logging.getLogger(__name__)


def create_db(db_path):
    with sqlite3.connect(db_path) as conn:
        try:
            conn.execute("CREATE TABLE downloads (id TEXT UNIQUE NOT NULL);")
            logger.info(f"{YELLOW}Download-IDs database created")
        except sqlite3.OperationalError:
            pass
        return db_path


def handle_download_id(db_path, item_id, add_id=False):
    if not db_path:
        return

    with sqlite3.connect(db_path) as conn:
        # If add_if is False return a string to know if the ID is in the DB
        # Otherwise just add the ID to the DB
        if add_id:
            try:
                conn.execute(
                    "INSERT INTO downloads (id) VALUES (?)",
                    (item_id,),
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"{RED}Unexpected DB error: {e}")
        else:
            return conn.execute(
                "SELECT id FROM downloads where id=?",
                (item_id,),
            ).fetchone()
