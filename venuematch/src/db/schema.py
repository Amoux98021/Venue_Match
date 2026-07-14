from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)


metadata = MetaData()

artists = Table(
    "artists",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False, unique=True),
    Column("popularity", Float),
    Column("monthly_listeners", Float),
    Column("lastfm_listeners", Float),
    Column("home_city", String),
    Column("home_state", String),
    Column("musicbrainz_id", String),
    Column("ticketmaster_id", String),
    Column("lastfm_url", Text),
    Column("data_source", String),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

venues = Table(
    "venues",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("city", String, nullable=False),
    Column("state", String, nullable=False),
    Column("capacity", Integer),
    Column("ticketmaster_id", String),
    Column("jambase_id", String),
    Column("latitude", Float),
    Column("longitude", Float),
    Column("capacity_source_url", Text),
    Column("capacity_source", String),
    Column("capacity_verified_at", DateTime(timezone=True)),
    Column("capacity_checked_at", DateTime(timezone=True)),
    Column("data_source", String),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
    UniqueConstraint("name", "city", "state", name="uq_venue_location"),
)

venue_capacity_sources = Table(
    "venue_capacity_sources",
    metadata,
    Column("venue_id", String, ForeignKey("venues.id"), primary_key=True),
    Column("source", String, primary_key=True),
    Column("source_record_id", String),
    Column("capacity", Integer, nullable=False),
    Column("capacity_type", String, nullable=False, server_default="maximum"),
    Column("source_url", Text),
    Column("retrieved_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

events = Table(
    "events",
    metadata,
    Column("id", String, primary_key=True),
    Column("artist_id", String, ForeignKey("artists.id"), nullable=False),
    Column("venue_id", String, ForeignKey("venues.id"), nullable=False),
    Column("event_date", String),
    Column("city", String),
    Column("state", String),
    Column("genre", String),
    Column("attendance_estimate", Float),
    Column("outcome_label", Integer),
    Column("source", String),
    Column("external_id", String),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

artist_genres = Table(
    "artist_genres",
    metadata,
    Column("artist_id", String, ForeignKey("artists.id"), primary_key=True),
    Column("genre", String, primary_key=True),
)

city_demographics = Table(
    "city_demographics",
    metadata,
    Column("city", String, primary_key=True),
    Column("state", String, primary_key=True),
    Column("population", Integer),
    Column("median_age", Float),
    Column("median_income", Float),
    Column("data_source", String),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

city_genre_signals = Table(
    "city_genre_signals",
    metadata,
    Column("city", String, primary_key=True),
    Column("state", String, primary_key=True),
    Column("genre", String, primary_key=True),
    Column("signal_strength", Float, nullable=False),
    Column("data_source", String),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

venue_genre_history = Table(
    "venue_genre_history",
    metadata,
    Column("venue_id", String, ForeignKey("venues.id"), primary_key=True),
    Column("genre", String, primary_key=True),
    Column("event_count", Integer, nullable=False),
    Column("data_source", String),
    Column("updated_at", DateTime(timezone=True), server_default=func.now()),
)

ingestion_runs = Table(
    "ingestion_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("status", String, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("artists_upserted", Integer, nullable=False, server_default="0"),
    Column("venues_upserted", Integer, nullable=False, server_default="0"),
    Column("events_upserted", Integer, nullable=False, server_default="0"),
    Column("cities_updated", Integer, nullable=False, server_default="0"),
    Column("details", Text),
)

recommendations = Table(
    "recommendations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("query_type", String, nullable=False),
    Column("query_value", String, nullable=False),
    Column("target_id", String, nullable=False),
    Column("city", String),
    Column("state", String),
    Column("genre_fit_score", Float),
    Column("venue_history_score", Float),
    Column("city_demand_score", Float),
    Column("capacity_fit_score", Float),
    Column("artist_popularity_score", Float),
    Column("final_score", Float),
    Column("explanation", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


TABLES = {
    table.name: table
    for table in (
        artists,
        venues,
        venue_capacity_sources,
        events,
        artist_genres,
        city_demographics,
        city_genre_signals,
        venue_genre_history,
        recommendations,
        ingestion_runs,
    )
}
