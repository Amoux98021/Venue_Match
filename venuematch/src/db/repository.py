from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.db.database import get_connection


def fetch_dataframe(query: str, params: tuple = (), db_path: Path | None = None) -> pd.DataFrame:
    with get_connection(db_path) as connection:
        return pd.read_sql_query(query, connection, params=params)


def get_artists(db_path: Path | None = None) -> pd.DataFrame:
    return fetch_dataframe("SELECT * FROM artists ORDER BY popularity DESC, name", db_path=db_path)


def get_venues(db_path: Path | None = None) -> pd.DataFrame:
    return fetch_dataframe("SELECT * FROM venues ORDER BY city, name", db_path=db_path)


def get_events(db_path: Path | None = None) -> pd.DataFrame:
    return fetch_dataframe("SELECT * FROM events ORDER BY event_date DESC", db_path=db_path)


def get_artist_genres(db_path: Path | None = None) -> pd.DataFrame:
    return fetch_dataframe("SELECT * FROM artist_genres ORDER BY artist_id, genre", db_path=db_path)


def get_city_genre_signals(db_path: Path | None = None) -> pd.DataFrame:
    return fetch_dataframe(
        "SELECT * FROM city_genre_signals ORDER BY city, state, signal_strength DESC",
        db_path=db_path,
    )


def get_venue_genre_history(db_path: Path | None = None) -> pd.DataFrame:
    return fetch_dataframe(
        "SELECT * FROM venue_genre_history ORDER BY venue_id, event_count DESC",
        db_path=db_path,
    )


def get_city_demographics(db_path: Path | None = None) -> pd.DataFrame:
    return fetch_dataframe("SELECT * FROM city_demographics ORDER BY state, city", db_path=db_path)


def upsert_recommendations(records: list[dict], db_path: Path | None = None) -> None:
    if not records:
        return

    with get_connection(db_path) as connection:
        for record in records:
            connection.execute(
                """
                INSERT INTO recommendations
                (
                    query_type, query_value, target_id, city, state,
                    genre_fit_score, venue_history_score, city_demand_score,
                    capacity_fit_score, artist_popularity_score, final_score, explanation
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["query_type"],
                    record["query_value"],
                    record["target_id"],
                    record.get("city"),
                    record.get("state"),
                    record.get("genre_fit_score"),
                    record.get("venue_history_score"),
                    record.get("city_demand_score"),
                    record.get("capacity_fit_score"),
                    record.get("artist_popularity_score"),
                    record.get("final_score"),
                    record.get("explanation"),
                ),
            )
