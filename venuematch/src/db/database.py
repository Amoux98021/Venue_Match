from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.db.schema import SCHEMA_SQL
from src.utils.config import ensure_data_directories, get_database_path


def resolve_db_path(db_path: Path | None = None) -> Path:
    ensure_data_directories()
    return db_path or get_database_path()


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = resolve_db_path(db_path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database(db_path: Path | None = None) -> Path:
    path = resolve_db_path(db_path)
    with get_connection(path) as connection:
        connection.executescript(SCHEMA_SQL)
    return path
