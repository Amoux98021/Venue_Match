from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.db.database import initialize_database
from src.db.repository import (
    get_artists,
    get_city_demographics,
    get_city_genre_signals,
    get_events,
    get_venues,
)
from src.db.seed import seed_sample_data
from src.scoring.recommender import recommend_artists_for_venue, recommend_venues_for_artist
from src.utils.config import credentials_available


def _bootstrap_database() -> Path:
    path = initialize_database()
    artists = get_artists(path)
    if artists.empty:
        seed_sample_data(path, overwrite=True)
    return path


def _format_score_table(frame: pd.DataFrame) -> pd.DataFrame:
    display = frame.copy()
    score_columns = [
        "genre_fit_score",
        "venue_history_score",
        "city_demand_score",
        "capacity_fit_score",
        "artist_popularity_score",
        "final_score",
    ]
    for column in score_columns:
        if column in display.columns:
            display[column] = display[column].map(lambda value: f"{value:.2f}")
    return display


def _render_artist_tab(db_path: Path) -> None:
    st.subheader("Artist to venue")
    artists = get_artists(db_path)
    venues = get_venues(db_path)
    selected_artist = st.selectbox("Artist name", artists["name"].tolist())
    selected_city = st.selectbox("Target city", sorted(venues["city"].dropna().unique().tolist()))

    if st.button("Find venues", type="primary"):
        result = recommend_venues_for_artist(selected_artist, selected_city, db_path=db_path)
        st.markdown(result.explanation)
        st.dataframe(
            _format_score_table(
                result.ranked[
                    [
                        "venue_name",
                        "city",
                        "state",
                        "capacity",
                        "genre_fit_score",
                        "venue_history_score",
                        "city_demand_score",
                        "capacity_fit_score",
                        "artist_popularity_score",
                        "final_score",
                        "explanation",
                    ]
                ]
            ),
            use_container_width=True,
        )


def _render_venue_tab(db_path: Path) -> None:
    st.subheader("Venue to artist")
    venues = get_venues(db_path)
    options = sorted(set(venues["name"].tolist()) | set(venues["city"].tolist()))
    selected_query = st.selectbox("Venue name or city", options)

    if st.button("Find artists", type="primary"):
        result = recommend_artists_for_venue(selected_query, db_path=db_path)
        st.markdown(result.explanation)
        st.dataframe(
            _format_score_table(
                result.ranked[
                    [
                        "artist_name",
                        "venue_name",
                        "city",
                        "state",
                        "genres",
                        "genre_fit_score",
                        "venue_history_score",
                        "city_demand_score",
                        "capacity_fit_score",
                        "artist_popularity_score",
                        "final_score",
                        "explanation",
                    ]
                ]
            ),
            use_container_width=True,
        )


def _render_city_tab(db_path: Path) -> None:
    st.subheader("City dashboard")
    demographics = get_city_demographics(db_path)
    signals = get_city_genre_signals(db_path)
    selected_city = st.selectbox(
        "City",
        demographics.apply(lambda row: f"{row['city']}, {row['state']}", axis=1).tolist(),
        key="city_dashboard",
    )
    city_name, state_code = [part.strip() for part in selected_city.split(",", 1)]
    city_demo = demographics.loc[(demographics["city"] == city_name) & (demographics["state"] == state_code)]
    city_signals = signals.loc[(signals["city"] == city_name) & (signals["state"] == state_code)]

    col1, col2, col3 = st.columns(3)
    col1.metric("Population", f"{int(city_demo.iloc[0]['population']):,}")
    col2.metric("Median age", f"{city_demo.iloc[0]['median_age']:.1f}")
    col3.metric("Median income", f"${int(city_demo.iloc[0]['median_income']):,}")
    st.dataframe(city_signals.sort_values("signal_strength", ascending=False), use_container_width=True)


def _render_raw_data_tab(db_path: Path) -> None:
    st.subheader("Raw data preview")
    artists = get_artists(db_path)
    venues = get_venues(db_path)
    events = get_events(db_path)
    st.write("Artists")
    st.dataframe(artists, use_container_width=True)
    st.write("Venues")
    st.dataframe(venues, use_container_width=True)
    st.write("Events")
    st.dataframe(events, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="VenueMatch", page_icon="🎵", layout="wide")
    db_path = _bootstrap_database()
    creds = credentials_available()

    st.title("VenueMatch")
    st.caption("MVP venue and artist recommender using a transparent rules engine and local SQLite storage.")

    with st.sidebar:
        st.header("Environment")
        st.write(f"Database: `{db_path}`")
        st.write("API credential status")
        st.json(creds)
        if st.button("Reseed sample data"):
            seed_sample_data(db_path, overwrite=True)
            st.success("Sample data reloaded.")

    artist_tab, venue_tab, city_tab, explanation_tab, raw_tab = st.tabs(
        ["Artist to venue", "Venue to artist", "City dashboard", "Explanation panel", "Raw data preview"]
    )

    with artist_tab:
        _render_artist_tab(db_path)
    with venue_tab:
        _render_venue_tab(db_path)
    with city_tab:
        _render_city_tab(db_path)
    with explanation_tab:
        st.markdown(
            """
            ### How scoring works

            - `genre_fit_score`: average of venue-history overlap and city demand alignment
            - `venue_history_score`: Jaccard overlap between artist genres and the venue's historical genre mix
            - `city_demand_score`: mean local demand signal for the artist's genres
            - `capacity_fit_score`: how closely venue capacity matches an artist popularity-based draw estimate
            - `artist_popularity_score`: artist popularity normalized to a 0-1 range

            Final score:

            `0.35 * genre_fit + 0.25 * venue_history + 0.20 * city_demand + 0.10 * capacity_fit + 0.10 * artist_popularity`
            """
        )
    with raw_tab:
        _render_raw_data_tab(db_path)
