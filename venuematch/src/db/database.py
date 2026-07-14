from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Union

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Connection, Engine

from src.db.schema import metadata
from src.utils.config import ensure_data_directories, get_database_url


DatabaseTarget = Union[str, Path, None]

ADDITIVE_COLUMNS = {
    "artists": {
        "lastfm_listeners": "FLOAT",
        "musicbrainz_id": "VARCHAR",
        "ticketmaster_id": "VARCHAR",
        "lastfm_url": "TEXT",
        "data_source": "VARCHAR",
        "updated_at": "TIMESTAMP",
    },
    "venues": {
        "ticketmaster_id": "VARCHAR",
        "latitude": "FLOAT",
        "longitude": "FLOAT",
        "capacity_source_url": "TEXT",
        "capacity_verified_at": "TIMESTAMP",
        "data_source": "VARCHAR",
        "updated_at": "TIMESTAMP",
    },
    "events": {
        "source": "VARCHAR",
        "external_id": "VARCHAR",
        "updated_at": "TIMESTAMP",
    },
    "city_demographics": {
        "data_source": "VARCHAR",
        "updated_at": "TIMESTAMP",
    },
    "city_genre_signals": {
        "data_source": "VARCHAR",
        "updated_at": "TIMESTAMP",
    },
    "venue_genre_history": {
        "data_source": "VARCHAR",
        "updated_at": "TIMESTAMP",
    },
}


def resolve_database_url(target: DatabaseTarget = None) -> str:
    if target is None:
        return get_database_url()
    if isinstance(target, Path):
        return f"sqlite:///{target.resolve()}"
    if target.startswith("sqlite:///") or target.startswith("postgres"):
        return target
    return f"sqlite:///{Path(target).resolve()}"


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache(maxsize=4)
def _create_engine(url: str) -> Engine:
    normalized_url = _normalize_postgres_url(url)
    connect_args = {"check_same_thread": False} if normalized_url.startswith("sqlite") else {}
    return create_engine(normalized_url, pool_pre_ping=True, connect_args=connect_args)


def get_engine(target: DatabaseTarget = None) -> Engine:
    ensure_data_directories()
    return _create_engine(resolve_database_url(target))


@contextmanager
def get_connection(target: DatabaseTarget = None) -> Iterator[Connection]:
    with get_engine(target).begin() as connection:
        yield connection


def initialize_database(target: DatabaseTarget = None) -> str:
    database_url = resolve_database_url(target)
    engine = get_engine(database_url)
    metadata.create_all(engine)
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, column_definitions in ADDITIVE_COLUMNS.items():
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in column_definitions.items():
                if column_name not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    )
    return database_url


def database_backend(target: DatabaseTarget = None) -> str:
    return get_engine(target).dialect.name
