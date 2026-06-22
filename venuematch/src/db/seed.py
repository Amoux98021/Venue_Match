from __future__ import annotations

from pathlib import Path

from src.db.database import get_connection, initialize_database
from src.utils.config import SAMPLE_DATA_PATH
from src.utils.io import read_json


def seed_sample_data(db_path: Path | None = None, overwrite: bool = True) -> Path:
    path = initialize_database(db_path)
    payload = read_json(SAMPLE_DATA_PATH)

    with get_connection(path) as connection:
        if overwrite:
            for table in [
                "recommendations",
                "events",
                "artist_genres",
                "venue_genre_history",
                "city_genre_signals",
                "city_demographics",
                "venues",
                "artists",
            ]:
                connection.execute(f"DELETE FROM {table}")

        for artist in payload["artists"]:
            connection.execute(
                """
                INSERT OR REPLACE INTO artists
                (id, name, popularity, monthly_listeners, home_city, home_state)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artist["id"],
                    artist["name"],
                    artist.get("popularity"),
                    artist.get("monthly_listeners"),
                    artist.get("home_city"),
                    artist.get("home_state"),
                ),
            )
            for genre in artist.get("genres", []):
                connection.execute(
                    "INSERT OR REPLACE INTO artist_genres (artist_id, genre) VALUES (?, ?)",
                    (artist["id"], genre),
                )

        for venue in payload["venues"]:
            connection.execute(
                """
                INSERT OR REPLACE INTO venues
                (id, name, city, state, capacity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (venue["id"], venue["name"], venue["city"], venue["state"], venue.get("capacity")),
            )

        for event in payload["events"]:
            connection.execute(
                """
                INSERT OR REPLACE INTO events
                (id, artist_id, venue_id, event_date, city, state, genre, attendance_estimate, outcome_label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["id"],
                    event["artist_id"],
                    event["venue_id"],
                    event.get("event_date"),
                    event.get("city"),
                    event.get("state"),
                    event.get("genre"),
                    event.get("attendance_estimate"),
                    event.get("outcome_label"),
                ),
            )

        for record in payload["city_demographics"]:
            connection.execute(
                """
                INSERT OR REPLACE INTO city_demographics
                (city, state, population, median_age, median_income)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record["city"],
                    record["state"],
                    record.get("population"),
                    record.get("median_age"),
                    record.get("median_income"),
                ),
            )

        for record in payload["city_genre_signals"]:
            connection.execute(
                """
                INSERT OR REPLACE INTO city_genre_signals
                (city, state, genre, signal_strength)
                VALUES (?, ?, ?, ?)
                """,
                (record["city"], record["state"], record["genre"], record["signal_strength"]),
            )

        for record in payload["venue_genre_history"]:
            connection.execute(
                """
                INSERT OR REPLACE INTO venue_genre_history
                (venue_id, genre, event_count)
                VALUES (?, ?, ?)
                """,
                (record["venue_id"], record["genre"], record["event_count"]),
            )

    return path
