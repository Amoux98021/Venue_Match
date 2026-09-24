from __future__ import annotations

import json
import math
from datetime import date, timedelta
from typing import Any

import requests
from sqlalchemy import func, select

from src.clients.jambase_client import JamBaseClient
from src.db.database import DatabaseTarget, get_connection, initialize_database
from src.db.schema import artists, events, venues
from src.utils.api_quota import (
    ProviderQuotaExceeded,
    get_provider_usage,
    reserve_provider_call,
)
from src.utils.config import credentials_available


MAX_PROBE_CALLS = 12
PROBE_LOCK_PROVIDER = "jambase_history_probe_v1"
EXISTING_HISTORY_START = date(2026, 7, 14)
WINDOWS = {
    "3_months_ago": (120, 90),
    "6_months_ago": (210, 180),
    "9_months_ago": (300, 270),
    "12_months_ago": (365, 335),
}


def _usage_for(provider: str, usage: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((row for row in usage if row["provider"] == provider), None)


def _select_probe_entities(
    as_of: date,
    db_target: DatabaseTarget = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    as_of_iso = as_of.isoformat()
    with get_connection(db_target) as connection:
        artist_rows = connection.execute(
            select(
                artists.c.id,
                artists.c.name,
                artists.c.jambase_id,
                func.count(events.c.id).label("historical_relationships"),
            )
            .join(events, events.c.artist_id == artists.c.id)
            .where(
                artists.c.jambase_id.is_not(None),
                artists.c.jambase_id != "",
                events.c.event_date.is_not(None),
                events.c.event_date <= as_of_iso,
            )
            .group_by(artists.c.id, artists.c.name, artists.c.jambase_id)
            .order_by(func.count(events.c.id).desc(), artists.c.name)
            .limit(5)
        ).mappings()
        venue_rows = connection.execute(
            select(
                venues.c.id,
                venues.c.name,
                venues.c.city,
                venues.c.state,
                venues.c.jambase_id,
                func.count(events.c.id).label("historical_relationships"),
            )
            .join(events, events.c.venue_id == venues.c.id)
            .where(
                venues.c.jambase_id.is_not(None),
                venues.c.jambase_id != "",
                events.c.event_date.is_not(None),
                events.c.event_date <= as_of_iso,
            )
            .group_by(
                venues.c.id,
                venues.c.name,
                venues.c.city,
                venues.c.state,
                venues.c.jambase_id,
            )
            .order_by(func.count(events.c.id).desc(), venues.c.name)
            .limit(3)
        ).mappings()
        universe = {
            "artists": int(connection.scalar(select(func.count()).select_from(artists)) or 0),
            "venues": int(connection.scalar(select(func.count()).select_from(venues)) or 0),
            "jambase_resolved_artists": int(
                connection.scalar(
                    select(func.count()).select_from(artists).where(
                        artists.c.jambase_id.is_not(None), artists.c.jambase_id != ""
                    )
                )
                or 0
            ),
            "jambase_resolved_venues": int(
                connection.scalar(
                    select(func.count()).select_from(venues).where(
                        venues.c.jambase_id.is_not(None), venues.c.jambase_id != ""
                    )
                )
                or 0
            ),
        }
    return [dict(row) for row in artist_rows], [dict(row) for row in venue_rows], universe


def _window(as_of: date, label: str) -> dict[str, str]:
    older_days, newer_days = WINDOWS[label]
    return {
        "label": label,
        "from": (as_of - timedelta(days=older_days)).isoformat(),
        "to": (as_of - timedelta(days=newer_days)).isoformat(),
    }


def build_probe_plan(
    artist_rows: list[dict[str, Any]],
    venue_rows: list[dict[str, Any]],
    as_of: date,
) -> list[dict[str, Any]]:
    if len(artist_rows) < 5 or len(venue_rows) < 3:
        raise RuntimeError("The probe requires five resolved artists and three resolved venues")

    window_labels = list(WINDOWS)
    plan: list[dict[str, Any]] = []
    for index, artist in enumerate(artist_rows):
        requested_window = (
            _window(as_of, window_labels[index])
            if index < len(window_labels)
            else {
                "label": "one_year_span",
                "from": (as_of - timedelta(days=365)).isoformat(),
                "to": (as_of - timedelta(days=1)).isoformat(),
            }
        )
        plan.append(
            {
                "query_type": "artist_id",
                "entity": artist,
                "window": requested_window,
            }
        )

    one_year_window = {
        "label": "one_year_span",
        "from": (as_of - timedelta(days=365)).isoformat(),
        "to": (as_of - timedelta(days=1)).isoformat(),
    }
    for venue in venue_rows:
        plan.append({"query_type": "venue_id", "entity": venue, "window": one_year_window})
    for label in window_labels:
        plan.append(
            {
                "query_type": "venue_id",
                "entity": venue_rows[0],
                "window": _window(as_of, label),
            }
        )

    if len(plan) > MAX_PROBE_CALLS:
        raise RuntimeError("JamBase history probe plan exceeds its hard request ceiling")
    return plan


def _event_dates(payload: dict[str, Any]) -> list[str]:
    dates: list[str] = []
    for event in payload.get("events", []) or []:
        value = event.get("startDate") if isinstance(event, dict) else None
        if value:
            dates.append(str(value)[:10])
    return sorted(dates)


def _pagination_value(payload: dict[str, Any], *keys: str) -> int | None:
    pagination = payload.get("pagination") or {}
    for key in keys:
        value = pagination.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _safe_error_message(error: Exception, api_key: str | None) -> str:
    response = getattr(error, "response", None)
    if response is not None:
        try:
            message = json.dumps(response.json(), sort_keys=True)
        except (ValueError, TypeError):
            message = response.text or str(error)
    else:
        message = str(error)
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return message[:800]


def _appears_plan_restricted(status_code: int | None, message: str | None) -> bool:
    if status_code in {402, 403}:
        return True
    normalized = (message or "").casefold()
    return any(
        term in normalized
        for term in (
            "entitlement",
            "historical access",
            "past events",
            "plan does not",
            "upgrade",
            "not included",
            "date range",
        )
    )


def classify_probe(results: list[dict[str, Any]], as_of: date) -> tuple[str, int | None]:
    returned_dates = [
        value
        for result in results
        for value in (result.get("oldest_event_date"), result.get("newest_event_date"))
        if value
    ]
    if not returned_dates:
        return "JAMBASE_HISTORY_NOT_AVAILABLE", None

    oldest = date.fromisoformat(min(returned_dates))
    depth_days = (as_of - oldest).days
    if depth_days >= 180:
        return "JAMBASE_HISTORY_AVAILABLE", depth_days
    if oldest < EXISTING_HISTORY_START or any(
        result.get("appears_plan_restricted") for result in results
    ):
        return "JAMBASE_HISTORY_PARTIAL", depth_days
    return "JAMBASE_HISTORY_NOT_AVAILABLE", depth_days


def _estimate_backfill(
    results: list[dict[str, Any]],
    universe: dict[str, int],
    remaining_calls: int,
) -> dict[str, Any]:
    successful_year_queries = [
        result
        for result in results
        if result["requested_window"]["label"] == "one_year_span"
        and result["http_status"] == 200
    ]
    observed_pages = [
        max(int(result.get("total_pages") or 1), 1) for result in successful_year_queries
    ]
    pages_per_entity = (
        max(1, math.ceil(sum(observed_pages) / len(observed_pages)))
        if observed_pages
        else 1
    )
    venue_calls = universe["jambase_resolved_venues"] * pages_per_entity
    artist_calls = universe["jambase_resolved_artists"] * pages_per_entity
    return {
        "basis": "one ID-filtered request per resolved entity, adjusted by observed pagination",
        "observed_pages_per_entity": pages_per_entity,
        "venue_lookup_estimate": venue_calls,
        "artist_lookup_estimate": artist_calls,
        "recommended_strategy": "venue_id lookups",
        "fits_remaining_monthly_quota": venue_calls <= remaining_calls,
        "remaining_monthly_calls": remaining_calls,
    }


def run_jambase_history_probe(
    as_of: date | None = None,
    db_target: DatabaseTarget = None,
    client: Any | None = None,
    enforce_single_run: bool = True,
) -> dict[str, Any]:
    initialize_database(db_target)
    if client is None and not credentials_available()["jambase"]:
        raise RuntimeError("JamBase credentials are required for the history probe")
    if enforce_single_run:
        try:
            reserve_provider_call(PROBE_LOCK_PROVIDER, 1, db_target)
        except ProviderQuotaExceeded as error:
            raise RuntimeError("The bounded JamBase history probe has already run this month") from error

    probe_as_of = as_of or date.today()
    artist_rows, venue_rows, universe = _select_probe_entities(probe_as_of, db_target)
    plan = build_probe_plan(artist_rows, venue_rows, probe_as_of)
    usage_before = _usage_for("jambase", get_provider_usage(db_target)) or {"calls_used": 0}
    jambase = client or JamBaseClient(db_target=db_target)
    api_key = getattr(jambase, "api_key", None)
    results: list[dict[str, Any]] = []

    for request_spec in plan:
        entity = request_spec["entity"]
        requested_window = request_spec["window"]
        result = {
            "endpoint": "/v3/events",
            "query_type": request_spec["query_type"],
            "entity": {
                key: entity[key]
                for key in ("name", "city", "state", "jambase_id", "historical_relationships")
                if key in entity
            },
            "requested_window": requested_window,
            "http_status": None,
            "events_returned": 0,
            "total_items": None,
            "total_pages": None,
            "oldest_event_date": None,
            "newest_event_date": None,
            "appears_plan_restricted": False,
            "entitlement_or_error_message": None,
        }
        try:
            lookup = {
                "event_date_from": requested_window["from"],
                "event_date_to": requested_window["to"],
                "page": 1,
                "per_page": 100,
                "expand_past_events": True,
            }
            if request_spec["query_type"] == "artist_id":
                payload = jambase.search_artist_events(artist_id=entity["jambase_id"], **lookup)
            else:
                payload = jambase.search_events(venue_id=entity["jambase_id"], **lookup)
            dates = _event_dates(payload)
            result.update(
                {
                    "http_status": 200,
                    "events_returned": len(payload.get("events", []) or []),
                    "total_items": _pagination_value(payload, "totalItems", "total_items"),
                    "total_pages": _pagination_value(payload, "totalPages", "total_pages"),
                    "oldest_event_date": dates[0] if dates else None,
                    "newest_event_date": dates[-1] if dates else None,
                }
            )
        except requests.HTTPError as error:
            status_code = error.response.status_code if error.response is not None else None
            message = _safe_error_message(error, api_key)
            result.update(
                {
                    "http_status": status_code,
                    "appears_plan_restricted": _appears_plan_restricted(status_code, message),
                    "entitlement_or_error_message": message,
                }
            )
        except ProviderQuotaExceeded as error:
            result["entitlement_or_error_message"] = str(error)
            results.append(result)
            break
        except requests.RequestException as error:
            result["entitlement_or_error_message"] = _safe_error_message(error, api_key)
        results.append(result)

    usage_after = _usage_for("jambase", get_provider_usage(db_target)) or {
        "calls_used": 0,
        "remaining": 0,
    }
    calls_consumed = max(
        int(usage_after.get("calls_used", 0)) - int(usage_before.get("calls_used", 0)),
        0,
    )
    classification, history_depth_days = classify_probe(results, probe_as_of)
    oldest_retrieved = min(
        (result["oldest_event_date"] for result in results if result["oldest_event_date"]),
        default=None,
    )
    entitlement_errors = sorted(
        {
            result["entitlement_or_error_message"]
            for result in results
            if result["entitlement_or_error_message"]
            and result["appears_plan_restricted"]
        }
    )
    recommendation = (
        "Plan a one-year venue-ID backfill only if the quota estimate fits; do not start it from this probe."
        if classification == "JAMBASE_HISTORY_AVAILABLE"
        else "Proceed with Setlist.fm historical enrichment before the historical recommendation benchmark."
    )
    response = {
        "probe": "jambase_history_access_v1",
        "read_only_product_data": True,
        "as_of": probe_as_of.isoformat(),
        "hard_call_ceiling": MAX_PROBE_CALLS,
        "api_calls_consumed": calls_consumed,
        "artists_tested": [row["name"] for row in artist_rows],
        "venues_tested": [
            f'{row["name"]} ({row["city"]}, {row["state"]})' for row in venue_rows
        ],
        "oldest_event_successfully_retrieved": oldest_retrieved,
        "apparent_history_depth_days": history_depth_days,
        "apparent_history_depth_months": (
            round(history_depth_days / 30.44, 1) if history_depth_days is not None else None
        ),
        "entitlement_errors": entitlement_errors,
        "classification": classification,
        "recommended_next_action": recommendation,
        "universe": universe,
        "requests": results,
        "provider_usage_after": usage_after,
    }
    if classification != "JAMBASE_HISTORY_NOT_AVAILABLE":
        response["one_year_backfill_estimate"] = _estimate_backfill(
            results,
            universe,
            int(usage_after.get("remaining", 0)),
        )
    return response
