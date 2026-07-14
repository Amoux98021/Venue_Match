from __future__ import annotations

from threading import Lock

from src.db.database import initialize_database
from src.db.repository import get_artists
from src.db.seed import seed_sample_data


_bootstrap_lock = Lock()
_database_ready = False


def ensure_database_ready() -> None:
    global _database_ready
    if _database_ready:
        return

    with _bootstrap_lock:
        if _database_ready:
            return
        database_url = initialize_database()
        if get_artists(database_url).empty:
            seed_sample_data(database_url, overwrite=True)
        _database_ready = True
