from __future__ import annotations

from sqlalchemy import delete, func, insert, select

from src.db.database import DatabaseTarget, get_connection, initialize_database
from src.db.schema import (
    artist_genres,
    artists,
    city_demographics,
    city_genre_signals,
    events,
    recommendations,
    venue_genre_history,
    venues,
)
from src.utils.config import SAMPLE_DATA_PATH
from src.utils.io import read_json


DELETE_ORDER = (
    recommendations,
    events,
    artist_genres,
    venue_genre_history,
    city_genre_signals,
    city_demographics,
    venues,
    artists,
)


def seed_sample_data(db_target: DatabaseTarget = None, overwrite: bool = True) -> str:
    database_url = initialize_database(db_target)
    payload = read_json(SAMPLE_DATA_PATH)

    with get_connection(database_url) as connection:
        artist_count = connection.scalar(select(func.count()).select_from(artists)) or 0
        if artist_count and not overwrite:
            return database_url

        if overwrite:
            for table in DELETE_ORDER:
                connection.execute(delete(table))

        artist_rows = [
            {
                "id": artist["id"],
                "name": artist["name"],
                "popularity": artist.get("popularity"),
                "monthly_listeners": artist.get("monthly_listeners"),
                "home_city": artist.get("home_city"),
                "home_state": artist.get("home_state"),
                "data_source": "sample",
            }
            for artist in payload["artists"]
        ]
        genre_rows = [
            {"artist_id": artist["id"], "genre": genre}
            for artist in payload["artists"]
            for genre in artist.get("genres", [])
        ]
        venue_rows = [
            {
                "id": venue["id"],
                "name": venue["name"],
                "city": venue["city"],
                "state": venue["state"],
                "capacity": venue.get("capacity"),
            }
            for venue in payload["venues"]
        ]

        connection.execute(insert(artists), artist_rows)
        connection.execute(insert(artist_genres), genre_rows)
        connection.execute(insert(venues), venue_rows)
        connection.execute(insert(events), payload["events"])
        connection.execute(insert(city_demographics), payload["city_demographics"])
        connection.execute(insert(city_genre_signals), payload["city_genre_signals"])
        connection.execute(insert(venue_genre_history), payload["venue_genre_history"])

    return database_url
