from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date, datetime
from secrets import compare_digest
from typing import Any, Callable, Optional

import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from src.api.bootstrap import ensure_database_ready
from src.api.schemas import ArtistVenueRequest, RecommendationResponse, VenueArtistRequest
from src.db import repository
from src.db.database import database_backend
from src.ingestion import get_ingestion_status, run_live_ingestion
from src.scoring.recommender import WEIGHTS, recommend_artists_for_venue, recommend_venues_for_artist
from src.utils.config import credentials_available, get_env


def _allowed_origins() -> list[str]:
    configured = get_env("ALLOWED_ORIGINS", "") or ""
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return origins or ["http://localhost:3000", "http://127.0.0.1:3000"]


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return [
        {key: _json_value(value) for key, value in record.items()}
        for record in clean.to_dict("records")
    ]


def _data_mode() -> str:
    if repository.has_live_data():
        return "live"
    return "live-ready" if any(credentials_available().values()) else "sample"


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_database_ready()
    yield


app = FastAPI(
    title="VenueMatch API",
    version="1.0.0",
    description="Transparent artist-to-venue and venue-to-artist recommendations.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "VenueMatch API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict[str, Any]:
    ensure_database_ready()
    return {
        "status": "ok",
        "database": database_backend(),
        "data_mode": _data_mode(),
        "api_sources": credentials_available(),
    }


@app.get("/meta/options")
def options() -> dict[str, Any]:
    ensure_database_ready()
    artists = repository.get_artists()
    venues = repository.get_venues()
    city_rows = venues[["city", "state"]].drop_duplicates().sort_values(["city", "state"])
    cities = [
        {"city": row["city"], "state": row["state"], "label": f"{row['city']}, {row['state']}"}
        for row in city_rows.to_dict("records")
    ]
    venue_queries = sorted(set(venues["name"].tolist()) | set(venues["city"].tolist()))
    return {
        "artists": artists["name"].tolist(),
        "cities": cities,
        "venues": _records(venues),
        "venue_queries": venue_queries,
        "data_mode": _data_mode(),
        "api_sources": credentials_available(),
    }


@app.post("/recommendations/artist-to-venue", response_model=RecommendationResponse)
def artist_to_venue(payload: ArtistVenueRequest) -> RecommendationResponse:
    ensure_database_ready()
    try:
        result = recommend_venues_for_artist(payload.artist_name, payload.target_city, top_n=payload.top_n)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RecommendationResponse(
        explanation=result.explanation,
        results=_records(result.ranked),
        weights=WEIGHTS,
    )


@app.post("/recommendations/venue-to-artist", response_model=RecommendationResponse)
def venue_to_artist(payload: VenueArtistRequest) -> RecommendationResponse:
    ensure_database_ready()
    try:
        result = recommend_artists_for_venue(payload.venue_name_or_city, top_n=payload.top_n)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RecommendationResponse(
        explanation=result.explanation,
        results=_records(result.ranked),
        weights=WEIGHTS,
    )


@app.get("/cities/{city}/dashboard")
def city_dashboard(city: str, state: Optional[str] = Query(default=None, max_length=10)) -> dict[str, Any]:
    ensure_database_ready()
    demographics = repository.get_city_demographics()
    signals = repository.get_city_genre_signals()
    venues = repository.get_venues()

    city_mask = demographics["city"].str.casefold() == city.casefold()
    if state:
        city_mask &= demographics["state"].str.casefold() == state.casefold()
    city_demographics = demographics.loc[city_mask]
    if city_demographics.empty:
        raise HTTPException(status_code=404, detail=f"No city data found for {city}")

    selected = city_demographics.iloc[0]
    selected_city = str(selected["city"])
    selected_state = str(selected["state"])
    signal_mask = (signals["city"] == selected_city) & (signals["state"] == selected_state)
    venue_mask = (venues["city"] == selected_city) & (venues["state"] == selected_state)
    return {
        "city": selected_city,
        "state": selected_state,
        "demographics": _records(city_demographics.head(1))[0],
        "genre_signals": _records(signals.loc[signal_mask].sort_values("signal_strength", ascending=False)),
        "venues": _records(venues.loc[venue_mask]),
    }


RAW_DATASETS: dict[str, Callable[[], pd.DataFrame]] = {
    "artists": repository.get_artists,
    "venues": repository.get_venues,
    "events": repository.get_events,
    "artist_genres": repository.get_artist_genres,
    "city_demographics": repository.get_city_demographics,
    "city_genre_signals": repository.get_city_genre_signals,
    "venue_genre_history": repository.get_venue_genre_history,
    "venue_capacity_sources": repository.get_venue_capacity_sources,
    "recommendations": repository.get_recommendations,
    "ingestion_runs": repository.get_ingestion_runs,
}


@app.get("/raw/{dataset}")
def raw_preview(dataset: str, limit: int = Query(default=50, ge=1, le=250)) -> dict[str, Any]:
    ensure_database_ready()
    loader = RAW_DATASETS.get(dataset)
    if loader is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown dataset. Choose one of: {', '.join(RAW_DATASETS)}",
        )
    frame = loader().head(limit)
    return {"dataset": dataset, "count": len(frame), "rows": _records(frame)}


@app.get("/ingestion/status")
def ingestion_status() -> dict[str, Any]:
    ensure_database_ready()
    return get_ingestion_status()


@app.get("/ingestion/sync")
def ingestion_sync(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    secret = get_env("CRON_SECRET")
    expected = f"Bearer {secret}" if secret else ""
    if not authorization or not expected or not compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return asdict(run_live_ingestion())
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail="Live ingestion could not complete; inspect provider configuration and logs.",
        ) from error
