from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, insert, select, text

from src.db.database import DatabaseTarget, get_connection
from src.db.schema import artists, ingestion_runs, recommendations


RECOMMENDATION_RETENTION_DAYS = 30


def fetch_dataframe(
    query: str,
    params: Mapping[str, Any] | None = None,
    db_target: DatabaseTarget = None,
) -> pd.DataFrame:
    with get_connection(db_target) as connection:
        return pd.read_sql_query(text(query), connection, params=params)


def get_artists(db_target: DatabaseTarget = None) -> pd.DataFrame:
    return fetch_dataframe("SELECT * FROM artists ORDER BY popularity DESC, name", db_target=db_target)


def get_venues(db_target: DatabaseTarget = None) -> pd.DataFrame:
    return fetch_dataframe("SELECT * FROM venues ORDER BY city, name", db_target=db_target)


def get_events(db_target: DatabaseTarget = None) -> pd.DataFrame:
    return fetch_dataframe("SELECT * FROM events ORDER BY event_date DESC", db_target=db_target)


def get_artist_genres(db_target: DatabaseTarget = None) -> pd.DataFrame:
    return fetch_dataframe("SELECT * FROM artist_genres ORDER BY artist_id, genre", db_target=db_target)


def get_city_genre_signals(db_target: DatabaseTarget = None) -> pd.DataFrame:
    return fetch_dataframe(
        "SELECT * FROM city_genre_signals ORDER BY city, state, signal_strength DESC",
        db_target=db_target,
    )


def get_venue_genre_history(db_target: DatabaseTarget = None) -> pd.DataFrame:
    return fetch_dataframe(
        "SELECT * FROM venue_genre_history ORDER BY venue_id, event_count DESC",
        db_target=db_target,
    )


def get_venue_capacity_sources(db_target: DatabaseTarget = None) -> pd.DataFrame:
    return fetch_dataframe(
        "SELECT * FROM venue_capacity_sources ORDER BY venue_id, source",
        db_target=db_target,
    )


def get_city_demographics(db_target: DatabaseTarget = None) -> pd.DataFrame:
    return fetch_dataframe("SELECT * FROM city_demographics ORDER BY state, city", db_target=db_target)


def get_recommendations(db_target: DatabaseTarget = None) -> pd.DataFrame:
    return fetch_dataframe(
        "SELECT * FROM recommendations ORDER BY created_at DESC, id DESC",
        db_target=db_target,
    )


def get_ingestion_runs(db_target: DatabaseTarget = None) -> pd.DataFrame:
    return fetch_dataframe(
        "SELECT * FROM ingestion_runs ORDER BY started_at DESC, id DESC",
        db_target=db_target,
    )


def has_live_data(db_target: DatabaseTarget = None) -> bool:
    with get_connection(db_target) as connection:
        count = connection.scalar(
            select(func.count()).select_from(artists).where(artists.c.data_source != "sample")
        )
    return bool(count)


def upsert_recommendations(records: list[dict[str, Any]], db_target: DatabaseTarget = None) -> None:
    if not records:
        return

    with get_connection(db_target) as connection:
        if connection.dialect.name == "sqlite":
            cutoff = func.datetime("now", f"-{RECOMMENDATION_RETENTION_DAYS} days")
        else:
            cutoff = func.now() - text(f"INTERVAL '{RECOMMENDATION_RETENTION_DAYS} days'")
        connection.execute(delete(recommendations).where(recommendations.c.created_at < cutoff))
        connection.execute(insert(recommendations), records)
