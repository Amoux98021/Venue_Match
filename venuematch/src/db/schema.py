SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS artists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    popularity REAL,
    monthly_listeners REAL,
    home_city TEXT,
    home_state TEXT
);

CREATE TABLE IF NOT EXISTS venues (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    capacity INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    artist_id TEXT NOT NULL,
    venue_id TEXT NOT NULL,
    event_date TEXT,
    city TEXT,
    state TEXT,
    genre TEXT,
    attendance_estimate REAL,
    outcome_label INTEGER,
    FOREIGN KEY (artist_id) REFERENCES artists(id),
    FOREIGN KEY (venue_id) REFERENCES venues(id)
);

CREATE TABLE IF NOT EXISTS artist_genres (
    artist_id TEXT NOT NULL,
    genre TEXT NOT NULL,
    PRIMARY KEY (artist_id, genre),
    FOREIGN KEY (artist_id) REFERENCES artists(id)
);

CREATE TABLE IF NOT EXISTS city_demographics (
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    population INTEGER,
    median_age REAL,
    median_income REAL,
    PRIMARY KEY (city, state)
);

CREATE TABLE IF NOT EXISTS city_genre_signals (
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    genre TEXT NOT NULL,
    signal_strength REAL NOT NULL,
    PRIMARY KEY (city, state, genre)
);

CREATE TABLE IF NOT EXISTS venue_genre_history (
    venue_id TEXT NOT NULL,
    genre TEXT NOT NULL,
    event_count INTEGER NOT NULL,
    PRIMARY KEY (venue_id, genre),
    FOREIGN KEY (venue_id) REFERENCES venues(id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_type TEXT NOT NULL,
    query_value TEXT NOT NULL,
    target_id TEXT NOT NULL,
    city TEXT,
    state TEXT,
    genre_fit_score REAL,
    venue_history_score REAL,
    city_demand_score REAL,
    capacity_fit_score REAL,
    artist_popularity_score REAL,
    final_score REAL,
    explanation TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""
