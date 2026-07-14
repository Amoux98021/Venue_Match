from __future__ import annotations

from dataclasses import dataclass
from math import log10

import pandas as pd

from src.db.database import DatabaseTarget
from src.db.repository import upsert_recommendations
from src.features.prepare import load_feature_frames


WEIGHTS = {
    "genre_fit_score": 0.35,
    "venue_history_score": 0.25,
    "city_demand_score": 0.20,
    "capacity_fit_score": 0.10,
    "artist_popularity_score": 0.10,
}


@dataclass
class RecommendationResult:
    ranked: pd.DataFrame
    explanation: str


def _normalize(text: str) -> str:
    return text.strip().lower()


def _safe_set(values: list[str] | pd.Series) -> set[str]:
    return {_normalize(value) for value in values if isinstance(value, str) and value.strip()}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _artist_genre_map(frames: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    grouped = frames["artist_genres"].groupby("artist_id")["genre"].apply(list)
    return grouped.to_dict()


def _venue_genre_map(frames: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    grouped = frames["venue_genre_history"].groupby("venue_id")["genre"].apply(list)
    return grouped.to_dict()


def _venue_history_strength_map(frames: dict[str, pd.DataFrame]) -> dict[str, dict[str, float]]:
    history = frames["venue_genre_history"].copy()
    history["max_events"] = history.groupby("venue_id")["event_count"].transform("max")
    history["normalized"] = history["event_count"] / history["max_events"]
    grouped: dict[str, dict[str, float]] = {}
    for row in history.to_dict("records"):
        grouped.setdefault(row["venue_id"], {})[_normalize(row["genre"])] = float(row["normalized"])
    return grouped


def _city_genre_signal_map(frames: dict[str, pd.DataFrame]) -> dict[tuple[str, str], dict[str, float]]:
    grouped: dict[tuple[str, str], dict[str, float]] = {}
    for row in frames["city_genre_signals"].to_dict("records"):
        key = (_normalize(row["city"]), _normalize(row["state"]))
        grouped.setdefault(key, {})[_normalize(row["genre"])] = float(row["signal_strength"])
    return grouped


def _artist_popularity_score(
    popularity: float | int | None,
    monthly_listeners: float | int | None = None,
) -> float:
    if popularity is not None and not pd.isna(popularity):
        return min(max(float(popularity) / 100.0, 0.0), 1.0)
    if monthly_listeners is not None and not pd.isna(monthly_listeners):
        # Log scaling keeps independent and emerging artists meaningful.
        return min(max(log10(max(float(monthly_listeners), 1.0)) / 7.0, 0.0), 1.0)
    return 0.5


def _capacity_fit_score(artist_popularity_score: float, capacity: float | int | None) -> tuple[float, str]:
    if capacity is None or pd.isna(capacity):
        return 0.45, "capacity unavailable, so confidence is reduced"

    target_capacity = 200 + (artist_popularity_score * 5800)
    difference_ratio = min(abs(float(capacity) - target_capacity) / max(target_capacity, 1.0), 1.0)
    return 1.0 - difference_ratio, f"capacity of {int(capacity)} compared against estimated draw"


def recommend_venues_for_artist(
    artist_name: str,
    target_city: str,
    db_path: DatabaseTarget = None,
    top_n: int = 10,
) -> RecommendationResult:
    frames = load_feature_frames(db_path)
    artists = frames["artists"].copy()
    venues = frames["venues"].copy()
    artist_row = artists.loc[artists["name"].str.lower() == artist_name.strip().lower()]
    if artist_row.empty:
        raise ValueError(f"Unknown artist: {artist_name}")

    artist = artist_row.iloc[0].to_dict()
    target_city_normalized = target_city.strip().lower()
    city_venues = venues.loc[venues["city"].str.lower() == target_city_normalized].copy()
    if city_venues.empty:
        city_venues = venues.copy()

    artist_genres = _safe_set(_artist_genre_map(frames).get(artist["id"], []))
    venue_genres = _venue_genre_map(frames)
    venue_history_strength = _venue_history_strength_map(frames)
    city_signals = _city_genre_signal_map(frames)
    artist_pop_score = _artist_popularity_score(
        artist.get("popularity"),
        artist.get("monthly_listeners"),
    )

    rows: list[dict] = []
    for _, venue in city_venues.iterrows():
        venue_id = venue["id"]
        venue_genre_set = _safe_set(venue_genres.get(venue_id, []))
        venue_history_score = _jaccard(artist_genres, venue_genre_set)

        city_key = (_normalize(venue["city"]), _normalize(venue["state"]))
        signal_map = city_signals.get(city_key, {})
        demand_values = [signal_map[genre] for genre in artist_genres if genre in signal_map]
        city_demand_score = sum(demand_values) / len(demand_values) if demand_values else 0.25

        history_weight_values = [
            venue_history_strength.get(venue_id, {}).get(genre, 0.0) for genre in artist_genres
        ]
        historical_match_score = (
            sum(history_weight_values) / len(history_weight_values) if history_weight_values else venue_history_score
        )
        genre_fit_score = (venue_history_score + city_demand_score) / 2.0
        capacity_fit_score, capacity_note = _capacity_fit_score(artist_pop_score, venue.get("capacity"))
        final_score = (
            WEIGHTS["genre_fit_score"] * genre_fit_score
            + WEIGHTS["venue_history_score"] * historical_match_score
            + WEIGHTS["city_demand_score"] * city_demand_score
            + WEIGHTS["capacity_fit_score"] * capacity_fit_score
            + WEIGHTS["artist_popularity_score"] * artist_pop_score
        )

        matched_genres = ", ".join(sorted(artist_genres & venue_genre_set)) or "limited direct overlap"
        explanation = (
            f"{venue['name']} ranks well for {artist['name']} because matched genres are {matched_genres}, "
            f"local demand in {venue['city']} is {city_demand_score:.2f}, and {capacity_note}."
        )

        rows.append(
            {
                "artist_name": artist["name"],
                "venue_id": venue_id,
                "venue_name": venue["name"],
                "city": venue["city"],
                "state": venue["state"],
                "capacity": venue["capacity"],
                "genre_fit_score": round(genre_fit_score, 4),
                "venue_history_score": round(historical_match_score, 4),
                "city_demand_score": round(city_demand_score, 4),
                "capacity_fit_score": round(capacity_fit_score, 4),
                "artist_popularity_score": round(artist_pop_score, 4),
                "final_score": round(final_score, 4),
                "explanation": explanation,
            }
        )

    ranked = pd.DataFrame(rows).sort_values("final_score", ascending=False).head(top_n).reset_index(drop=True)
    upsert_recommendations(
        [
            {
                "query_type": "artist_to_venue",
                "query_value": artist["name"],
                "target_id": row["venue_id"],
                "city": row["city"],
                "state": row["state"],
                "genre_fit_score": row["genre_fit_score"],
                "venue_history_score": row["venue_history_score"],
                "city_demand_score": row["city_demand_score"],
                "capacity_fit_score": row["capacity_fit_score"],
                "artist_popularity_score": row["artist_popularity_score"],
                "final_score": row["final_score"],
                "explanation": row["explanation"],
            }
            for row in ranked.to_dict("records")
        ],
        db_path,
    )
    explanation = (
        "Scores combine transparent genre overlap, venue history, city demand, capacity fit, and artist popularity."
    )
    return RecommendationResult(ranked=ranked, explanation=explanation)


def recommend_artists_for_venue(
    venue_name_or_city: str,
    db_path: DatabaseTarget = None,
    top_n: int = 10,
) -> RecommendationResult:
    frames = load_feature_frames(db_path)
    artists = frames["artists"].copy()
    venues = frames["venues"].copy()
    query_normalized = venue_name_or_city.strip().lower()

    matched_venues = venues.loc[
        (venues["name"].str.lower() == query_normalized) | (venues["city"].str.lower() == query_normalized)
    ].copy()
    if matched_venues.empty:
        raise ValueError(f"No venue or city match for: {venue_name_or_city}")

    artist_genres = _artist_genre_map(frames)
    venue_genres = _venue_genre_map(frames)
    city_signals = _city_genre_signal_map(frames)

    rows: list[dict] = []
    for _, artist in artists.iterrows():
        artist_genre_set = _safe_set(artist_genres.get(artist["id"], []))
        artist_pop_score = _artist_popularity_score(
            artist.get("popularity"),
            artist.get("monthly_listeners"),
        )

        best_result: dict | None = None
        for _, venue in matched_venues.iterrows():
            venue_genre_set = _safe_set(venue_genres.get(venue["id"], []))
            venue_history_score = _jaccard(artist_genre_set, venue_genre_set)
            city_key = (_normalize(venue["city"]), _normalize(venue["state"]))
            signal_map = city_signals.get(city_key, {})
            demand_values = [signal_map[genre] for genre in artist_genre_set if genre in signal_map]
            city_demand_score = sum(demand_values) / len(demand_values) if demand_values else 0.25
            genre_fit_score = (venue_history_score + city_demand_score) / 2.0
            capacity_fit_score, _ = _capacity_fit_score(artist_pop_score, venue.get("capacity"))
            final_score = (
                WEIGHTS["genre_fit_score"] * genre_fit_score
                + WEIGHTS["venue_history_score"] * venue_history_score
                + WEIGHTS["city_demand_score"] * city_demand_score
                + WEIGHTS["capacity_fit_score"] * capacity_fit_score
                + WEIGHTS["artist_popularity_score"] * artist_pop_score
            )
            candidate = {
                "artist_id": artist["id"],
                "artist_name": artist["name"],
                "home_city": artist["home_city"],
                "home_state": artist["home_state"],
                "venue_name": venue["name"],
                "city": venue["city"],
                "state": venue["state"],
                "genres": ", ".join(sorted(artist_genre_set)),
                "genre_fit_score": round(genre_fit_score, 4),
                "venue_history_score": round(venue_history_score, 4),
                "city_demand_score": round(city_demand_score, 4),
                "capacity_fit_score": round(capacity_fit_score, 4),
                "artist_popularity_score": round(artist_pop_score, 4),
                "final_score": round(final_score, 4),
                "explanation": (
                    f"{artist['name']} aligns with {venue['name']} because its genres map to local demand "
                    f"and the venue's booking history."
                ),
            }
            if best_result is None or candidate["final_score"] > best_result["final_score"]:
                best_result = candidate

        if best_result is not None:
            rows.append(best_result)

    ranked = pd.DataFrame(rows).sort_values("final_score", ascending=False).head(top_n).reset_index(drop=True)
    upsert_recommendations(
        [
            {
                "query_type": "venue_to_artist",
                "query_value": venue_name_or_city,
                "target_id": row["artist_id"],
                "city": row["city"],
                "state": row["state"],
                "genre_fit_score": row["genre_fit_score"],
                "venue_history_score": row["venue_history_score"],
                "city_demand_score": row["city_demand_score"],
                "capacity_fit_score": row["capacity_fit_score"],
                "artist_popularity_score": row["artist_popularity_score"],
                "final_score": row["final_score"],
                "explanation": row["explanation"],
            }
            for row in ranked.to_dict("records")
        ],
        db_path,
    )
    explanation = "Venue-side ranking selects the best venue fit per artist and returns the strongest candidates."
    return RecommendationResult(ranked=ranked, explanation=explanation)
