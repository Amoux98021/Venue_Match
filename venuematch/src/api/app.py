from __future__ import annotations

import json
import logging
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
from src.clients.setlistfm_client import SetlistFmClient
from src.db import repository
from src.db.database import database_backend
from src.evaluation import (
    build_setlist_probe_input,
    run_historical_data_audit,
    run_jambase_history_probe,
    run_setlist_history_probe,
)
from src.ingestion import (
    get_ingestion_status,
    run_jambase_history_backfill,
    run_live_ingestion,
)
from src.scoring.recommender import WEIGHTS, recommend_artists_for_venue, recommend_venues_for_artist
from src.utils.config import credentials_available, get_env


logger = logging.getLogger(__name__)


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


def _require_cron_secret(authorization: Optional[str]) -> None:
    secret = get_env("CRON_SECRET")
    expected = f"Bearer {secret}" if secret else ""
    if not authorization or not expected or not compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _require_probe_export_secret(authorization: Optional[str]) -> None:
    secret = get_env("PROBE_EXPORT_SECRET")
    expected = f"Bearer {secret}" if secret else ""
    if not authorization or not expected or not compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


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


@app.get("/evaluation/historical-audit")
def historical_data_audit(as_of: Optional[date] = Query(default=None)) -> dict[str, Any]:
    """Return aggregate, read-only benchmark-readiness statistics."""
    ensure_database_ready()
    return run_historical_data_audit(as_of=as_of)


@app.get("/evaluation/setlist-probe-batch")
def setlist_probe_batch(
    authorization: Optional[str] = Header(default=None),
    as_of: Optional[date] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    batch_size: int = Query(default=4, ge=1, le=4),
    max_pages: int = Query(default=8, ge=1, le=8),
) -> dict[str, Any]:
    """Run one bounded, aggregate-only Setlist probe batch without persistence."""
    _require_probe_export_secret(authorization)
    ensure_database_ready()
    if not get_env("SETLISTFM_API_KEY"):
        raise HTTPException(status_code=503, detail="Setlist.fm is not configured")
    snapshot = build_setlist_probe_input(as_of=as_of)
    full_sample = snapshot["sample_artists"]
    snapshot["sample_artists"] = full_sample[offset : offset + batch_size]
    if not snapshot["sample_artists"]:
        raise HTTPException(status_code=404, detail="Probe batch offset is past the sample")
    client = SetlistFmClient(minimum_interval=1.0, max_retries=1)
    try:
        result = run_setlist_history_probe(
            snapshot,
            client,
            max_pages_per_artist=max_pages,
        )
    except (RuntimeError, ValueError) as error:
        logger.warning("setlist_probe_provider_error type=%s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Setlist.fm request failed") from error
    result["metadata"].update(
        {
            "batch_offset": offset,
            "batch_size": len(snapshot["sample_artists"]),
            "total_sample_size": len(full_sample),
        }
    )
    return result


@app.get("/evaluation/jambase-history-probe")
def jambase_history_probe(
    authorization: Optional[str] = Header(default=None),
    as_of: Optional[date] = Query(default=None),
) -> dict[str, Any]:
    """Run the single-use, quota-bounded JamBase entitlement probe."""
    _require_cron_secret(authorization)
    ensure_database_ready()
    try:
        try:
            result = run_jambase_history_probe(as_of=as_of)
        except RuntimeError as error:
            if "already run this month" not in str(error):
                raise
            result = run_jambase_history_probe(as_of=as_of, recovery=True)
        logger.info(
            "jambase_history_probe_result=%s",
            json.dumps(result, default=str, separators=(",", ":")),
        )
        return result
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/ingestion/sync")
def ingestion_sync(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _require_cron_secret(authorization)
    try:
        return asdict(run_live_ingestion())
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail="Live ingestion could not complete; inspect provider configuration and logs.",
        ) from error


@app.get("/ingestion/jambase-history")
def jambase_history_backfill(
    authorization: Optional[str] = Header(default=None),
    batch_size: int = Query(default=10, ge=1, le=25),
    include_history: bool = Query(default=True),
) -> dict[str, Any]:
    _require_cron_secret(authorization)
    try:
        return asdict(
            run_jambase_history_backfill(
                batch_size=batch_size,
                include_history=include_history,
            )
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail="JamBase history backfill could not complete; inspect provider configuration.",
        ) from error
