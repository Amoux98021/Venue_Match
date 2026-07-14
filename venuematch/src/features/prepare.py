from __future__ import annotations

import pandas as pd

from src.db import repository
from src.db.database import DatabaseTarget


def load_feature_frames(db_path: DatabaseTarget = None) -> dict[str, pd.DataFrame]:
    return {
        "artists": repository.get_artists(db_path),
        "venues": repository.get_venues(db_path),
        "events": repository.get_events(db_path),
        "artist_genres": repository.get_artist_genres(db_path),
        "city_genre_signals": repository.get_city_genre_signals(db_path),
        "venue_genre_history": repository.get_venue_genre_history(db_path),
        "city_demographics": repository.get_city_demographics(db_path),
    }
