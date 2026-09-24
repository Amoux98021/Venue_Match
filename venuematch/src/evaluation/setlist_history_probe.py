from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from hashlib import sha256
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
import re
from typing import Any
import unicodedata

import pandas as pd

from src.clients.setlistfm_client import SetlistFmClient, normalize_setlist_performance
from src.db import repository
from src.db.database import DatabaseTarget


PROBE_SAMPLE_SIZE = 200
MAX_PAGES_PER_ARTIST = 8
DENSE_MARKET_RELATIONSHIPS = 20
MBID_PATTERN = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)
WINDOW_LABELS = (
    "0-3 months",
    "3-6 months",
    "6-12 months",
    "12-24 months",
    "24+ months",
)


class ProbeRequestCapReached(RuntimeError):
    """Stop the transient probe before its provider-request ceiling is exceeded."""


def _clean(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def normalize_entity(value: Any) -> str:
    cleaned = _clean(value) or ""
    ascii_value = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def valid_mbid(value: Any) -> bool:
    return bool(value and MBID_PATTERN.fullmatch(str(value).strip()))


def _market(city: Any, state: Any) -> str | None:
    city_value = _clean(city)
    state_value = _clean(state)
    return f"{city_value}, {state_value}" if city_value and state_value else None


def _stable_order(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def historical_bucket(event_date: str | date, as_of: date) -> str | None:
    parsed = date.fromisoformat(str(event_date)[:10]) if not isinstance(event_date, date) else event_date
    age_days = (as_of - parsed).days
    if age_days < 0:
        return None
    if age_days <= 90:
        return "0-3 months"
    if age_days <= 180:
        return "3-6 months"
    if age_days <= 365:
        return "6-12 months"
    if age_days <= 730:
        return "12-24 months"
    return "24+ months"


def _mode(values: list[str]) -> str | None:
    if not values:
        return None
    counts = Counter(values)
    return sorted(counts, key=lambda value: (-counts[value], value))[0]


def _provider_bias(ticketmaster_count: int, jambase_count: int) -> str:
    if ticketmaster_count > jambase_count:
        return "ticketmaster-heavy"
    if jambase_count > ticketmaster_count:
        return "jambase-heavy"
    return "balanced"


def _greedy_sample(candidates: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    if len(candidates) <= size:
        return sorted(candidates, key=lambda row: _stable_order(row["id"]))
    selected: list[dict[str, Any]] = []
    remaining = {row["id"]: row for row in candidates}
    counters = {field: Counter() for field in ("market", "history_band", "provider_bias", "primary_genre")}
    while remaining and len(selected) < size:
        scored = []
        for row in remaining.values():
            score = sum(
                weight / (1 + counters[field][row.get(field) or "unknown"])
                for field, weight in (
                    ("market", 5.0),
                    ("history_band", 3.0),
                    ("provider_bias", 2.0),
                    ("primary_genre", 1.0),
                )
            )
            scored.append((score, _stable_order(row["id"]), row))
        _, _, chosen = max(scored, key=lambda item: (item[0], item[1]))
        selected.append(chosen)
        remaining.pop(chosen["id"])
        for field in counters:
            counters[field][chosen.get(field) or "unknown"] += 1
    return selected


def build_setlist_probe_input(
    db_target: DatabaseTarget = None,
    as_of: date | None = None,
    sample_size: int = PROBE_SAMPLE_SIZE,
) -> dict[str, Any]:
    from src.ingestion.service import TARGET_CITIES

    reference_date = as_of or datetime.now(timezone.utc).date()
    artists = repository.get_artists(db_target)
    venues = repository.get_venues(db_target)
    events = repository.get_events(db_target)
    genres = repository.get_artist_genres(db_target)
    genre_map = (
        genres.groupby("artist_id")["genre"].apply(lambda values: sorted(set(values))).to_dict()
        if not genres.empty
        else {}
    )
    venue_market = {
        row["id"]: _market(row["city"], row["state"])
        for row in venues.to_dict("records")
    }
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"history_count": 0, "ticketmaster_count": 0, "jambase_count": 0, "markets": []}
    )
    for row in events.to_dict("records"):
        artist_stats = stats[str(row["artist_id"])]
        artist_stats["history_count"] += 1
        source = normalize_entity(row.get("source"))
        if "ticketmaster" in source:
            artist_stats["ticketmaster_count"] += 1
        if "jambase" in source:
            artist_stats["jambase_count"] += 1
        market = venue_market.get(row["venue_id"])
        if market:
            artist_stats["markets"].append(market)

    mapped = artists.loc[artists["musicbrainz_id"].map(valid_mbid)].copy()
    positive_counts = [
        stats[str(artist_id)]["history_count"]
        for artist_id in mapped["id"]
        if stats[str(artist_id)]["history_count"] > 0
    ]
    medium_cut = float(pd.Series(positive_counts).quantile(0.50)) if positive_counts else 1.0
    high_cut = float(pd.Series(positive_counts).quantile(0.80)) if positive_counts else 2.0
    candidates = []
    for row in mapped.to_dict("records"):
        artist_stats = stats[str(row["id"])]
        count = int(artist_stats["history_count"])
        history_band = "low" if count == 0 else "high" if count >= high_cut else "medium"
        artist_genres = genre_map.get(row["id"], [])
        candidates.append(
            {
                "id": row["id"],
                "name": row["name"],
                "musicbrainz_id": row["musicbrainz_id"],
                "genres": artist_genres,
                "primary_genre": artist_genres[0] if artist_genres else "unknown",
                "history_count": count,
                "history_band": history_band,
                "ticketmaster_count": int(artist_stats["ticketmaster_count"]),
                "jambase_count": int(artist_stats["jambase_count"]),
                "provider_bias": _provider_bias(
                    int(artist_stats["ticketmaster_count"]),
                    int(artist_stats["jambase_count"]),
                ),
                "market": _mode(artist_stats["markets"])
                or _market(row.get("home_city"), row.get("home_state")),
                "established_or_sparse": "established" if count >= medium_cut else "sparse",
            }
        )
    sample = _greedy_sample(candidates, min(sample_size, len(candidates)))

    return {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "as_of": reference_date.isoformat(),
            "read_only": True,
            "sample_method": "all mapped artists when <=200; otherwise deterministic greedy stratification",
        },
        "sample_artists": sample,
        "artist_index": [
            {
                "id": row["id"],
                "name": row["name"],
                "musicbrainz_id": _clean(row.get("musicbrainz_id")),
                "ticketmaster_id": _clean(row.get("ticketmaster_id")),
                "jambase_id": _clean(row.get("jambase_id")),
            }
            for row in artists.to_dict("records")
        ],
        "venue_index": [
            {
                "id": row["id"],
                "name": row["name"],
                "city": row["city"],
                "state": row["state"],
                "latitude": None if pd.isna(row.get("latitude")) else row.get("latitude"),
                "longitude": None if pd.isna(row.get("longitude")) else row.get("longitude"),
                "ticketmaster_id": _clean(row.get("ticketmaster_id")),
                "jambase_id": _clean(row.get("jambase_id")),
            }
            for row in venues.to_dict("records")
        ],
        "existing_relationships": [
            {
                "artist_id": row["artist_id"],
                "venue_id": row["venue_id"],
                "event_date": _clean(row.get("event_date")),
                "source": _clean(row.get("source")),
            }
            for row in events.to_dict("records")
        ],
        "target_markets": [
            {"city": item.city, "state": item.state, "market": _market(item.city, item.state)}
            for item in TARGET_CITIES
        ],
        "counts": {
            "artists": int(len(artists)),
            "musicbrainz_mapped_artists": int(len(mapped)),
            "venues": int(len(venues)),
            "relationships": int(len(events)),
        },
    }


def resolve_artist(
    performance: dict[str, Any],
    artist_by_mbid: dict[str, dict[str, Any]],
    artists_by_name: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    mbid = performance.get("artist_mbid")
    if mbid in artist_by_mbid:
        row = artist_by_mbid[mbid]
        return {"artist_id": row["id"], "match_quality": "exact"}
    name_matches = artists_by_name.get(normalize_entity(performance.get("artist_name")), [])
    if len(name_matches) == 1:
        return {"artist_id": name_matches[0]["id"], "match_quality": "medium"}
    return {"artist_id": None, "match_quality": "unresolved"}


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    value = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(value))


def resolve_market(
    performance: dict[str, Any],
    target_markets: list[dict[str, Any]],
    venues: list[dict[str, Any]],
) -> dict[str, Any]:
    country = normalize_entity(performance.get("country_code") or performance.get("country_name"))
    if country and country not in {"us", "usa", "united states"}:
        return {"market": None, "status": "outside", "method": "country"}
    city = normalize_entity(performance.get("city"))
    state = normalize_entity(performance.get("state"))
    matches = [
        row
        for row in target_markets
        if normalize_entity(row["city"]) == city and normalize_entity(row["state"]) == state
    ]
    if len(matches) == 1:
        return {"market": matches[0]["market"], "status": "current", "method": "city_state"}

    latitude = performance.get("latitude")
    longitude = performance.get("longitude")
    if latitude is not None and longitude is not None:
        distances = []
        for venue in venues:
            if venue.get("latitude") is None or venue.get("longitude") is None:
                continue
            distance = _haversine_miles(
                float(latitude),
                float(longitude),
                float(venue["latitude"]),
                float(venue["longitude"]),
            )
            distances.append((distance, venue["market"]))
        if distances:
            distance, market = min(distances, key=lambda item: item[0])
            if distance <= 35:
                return {"market": market, "status": "current", "method": "coordinates"}
    if city or state or country:
        return {"market": None, "status": "outside", "method": "no_current_market_match"}
    return {"market": None, "status": "unresolved", "method": "missing_location"}


def resolve_venue(
    performance: dict[str, Any],
    market: str | None,
    venues: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = [row for row in venues if market and row["market"] == market]
    name = normalize_entity(performance.get("venue_name"))
    city = normalize_entity(performance.get("city"))
    exact_name_city = [
        row
        for row in candidates
        if normalize_entity(row["name"]) == name and normalize_entity(row["city"]) == city
    ]
    if len(exact_name_city) == 1:
        return {"venue_id": exact_name_city[0]["id"], "match_quality": "high"}

    latitude = performance.get("latitude")
    longitude = performance.get("longitude")
    if name and latitude is not None and longitude is not None:
        coordinate_matches = []
        for row in candidates:
            if normalize_entity(row["name"]) != name:
                continue
            if row.get("latitude") is None or row.get("longitude") is None:
                continue
            distance = _haversine_miles(
                float(latitude), float(longitude), float(row["latitude"]), float(row["longitude"])
            )
            if distance <= 2:
                coordinate_matches.append((distance, row))
        if len(coordinate_matches) == 1:
            return {"venue_id": coordinate_matches[0][1]["id"], "match_quality": "high"}

    fuzzy = sorted(
        (
            (
                SequenceMatcher(None, name, normalize_entity(row["name"])).ratio(),
                row,
            )
            for row in candidates
            if name
        ),
        key=lambda item: (item[0], str(item[1]["id"])),
    )
    fuzzy = [item for item in fuzzy if item[0] >= 0.90]
    if fuzzy and (len(fuzzy) == 1 or fuzzy[-1][0] > fuzzy[-2][0]):
        return {"venue_id": fuzzy[-1][1]["id"], "match_quality": "medium"}
    return {"venue_id": None, "match_quality": "unresolved"}


def classify_overlap(
    row: dict[str, Any],
    existing_keys: dict[tuple[str, str, str], set[str]],
    existing_date_artist: set[tuple[str, str]],
    musicbrainz_keys: set[tuple[str, str, str]],
    musicbrainz_date_artist: set[tuple[str, str]],
    venue_name_by_id: dict[str, str],
) -> tuple[str, list[str]]:
    event_date = row.get("event_date")
    artist_id = row.get("artist_id")
    venue_id = row.get("venue_id")
    if event_date and artist_id and venue_id:
        sources = sorted(existing_keys.get((event_date, artist_id, venue_id), set()))
        if sources:
            return "already_known", sources
    venue_name = normalize_entity(venue_name_by_id.get(venue_id) or row.get("venue_name"))
    mbid = row.get("artist_mbid")
    if event_date and mbid and venue_name and (event_date, mbid, venue_name) in musicbrainz_keys:
        return "already_known_musicbrainz", ["musicbrainz"]
    if event_date and artist_id and (event_date, artist_id) in existing_date_artist:
        return "likely_duplicate", []
    if event_date and mbid and (event_date, mbid) in musicbrainz_date_artist:
        return "likely_duplicate", []
    if (
        row.get("market_status") == "current"
        and row.get("artist_match_quality") in {"exact", "high"}
        and row.get("venue_match_quality") in {"exact", "high"}
    ):
        return "setlist_only", []
    return "ambiguous", []


def _musicbrainz_overlap_keys(
    prior: dict[str, Any] | None,
    venue_names: set[str],
) -> tuple[set[tuple[str, str, str]], set[tuple[str, str]]]:
    keys: set[tuple[str, str, str]] = set()
    date_artist: set[tuple[str, str]] = set()
    for event in (prior or {}).get("normalized_events", []):
        event_date = event.get("begin_date")
        place_name = normalize_entity((event.get("place") or {}).get("name"))
        if not event_date:
            continue
        for performer in event.get("performers", []):
            mbid = performer.get("musicbrainz_id")
            if not mbid:
                continue
            date_artist.add((event_date, mbid))
            if place_name:
                keys.add((event_date, mbid, place_name))
            for venue_name in venue_names:
                if place_name and SequenceMatcher(None, place_name, venue_name).ratio() >= 0.96:
                    keys.add((event_date, mbid, venue_name))
    return keys, date_artist


def run_setlist_history_probe(
    snapshot: dict[str, Any],
    client: SetlistFmClient,
    musicbrainz_prior: dict[str, Any] | None = None,
    max_pages_per_artist: int = MAX_PAGES_PER_ARTIST,
) -> dict[str, Any]:
    as_of = date.fromisoformat(snapshot["metadata"]["as_of"])
    artists = snapshot["sample_artists"]
    artist_by_mbid = {
        row["musicbrainz_id"]: row
        for row in snapshot["artist_index"]
        if valid_mbid(row.get("musicbrainz_id"))
    }
    artists_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in snapshot["artist_index"]:
        artists_by_name[normalize_entity(row["name"])].append(row)
    venues = [
        {**row, "market": _market(row["city"], row["state"])}
        for row in snapshot["venue_index"]
    ]
    venue_name_by_id = {row["id"]: row["name"] for row in venues}
    target_markets = snapshot["target_markets"]
    current_markets = {row["market"] for row in target_markets}

    existing_keys: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    existing_date_artist: set[tuple[str, str]] = set()
    for row in snapshot["existing_relationships"]:
        if row.get("event_date") and row.get("artist_id") and row.get("venue_id"):
            existing_keys[(row["event_date"], row["artist_id"], row["venue_id"])].add(
                row.get("source") or "unknown"
            )
            existing_date_artist.add((row["event_date"], row["artist_id"]))
    normalized_venue_names = {normalize_entity(row["name"]) for row in venues}
    musicbrainz_keys, musicbrainz_date_artist = _musicbrainz_overlap_keys(
        musicbrainz_prior, normalized_venue_names
    )

    transient_performances: dict[str, dict[str, Any]] = {}
    artists_queried = 0
    artists_with_history = 0
    artist_failures = 0
    page_depths: list[int] = []
    raw_records_returned = 0
    truncated_artists = 0
    order_violations = 0
    cutoff_24_months = as_of - timedelta(days=730)
    for artist in artists:
        artists_queried += 1
        pages = 0
        artist_records = 0
        previous_oldest: date | None = None
        crossed_cutoff = False
        artist_order_violation = False
        try:
            for page_number in range(1, max_pages_per_artist + 1):
                payload = client.get_artist_setlists(artist["musicbrainz_id"], page=page_number)
                pages += 1
                rows = payload["setlist"]
                raw_records_returned += len(rows)
                artist_records += len(rows)
                page_dates = []
                for raw in rows:
                    normalized = normalize_setlist_performance(raw)
                    if normalized:
                        transient_performances.setdefault(normalized["setlist_id"], normalized)
                        page_dates.append(date.fromisoformat(normalized["event_date"]))
                if page_dates:
                    newest = max(page_dates)
                    oldest = min(page_dates)
                    if previous_oldest is not None and newest > previous_oldest:
                        order_violations += 1
                        artist_order_violation = True
                    previous_oldest = oldest
                    crossed_cutoff = oldest < cutoff_24_months
                total = int(payload["total"])
                items_per_page = max(int(payload["itemsPerPage"]), 1)
                if not rows or page_number * items_per_page >= total:
                    break
                if crossed_cutoff and not artist_order_violation:
                    break
                if page_number == max_pages_per_artist:
                    truncated_artists += 1
        except ProbeRequestCapReached:
            raise
        except Exception:
            artist_failures += 1
        page_depths.append(pages)
        if artist_records:
            artists_with_history += 1

    resolved_rows: list[dict[str, Any]] = []
    for performance in transient_performances.values():
        event_date = performance["event_date"]
        if date.fromisoformat(event_date) >= as_of:
            continue
        artist_match = resolve_artist(performance, artist_by_mbid, artists_by_name)
        market_match = resolve_market(performance, target_markets, venues)
        venue_match = resolve_venue(performance, market_match["market"], venues)
        row = {
            **performance,
            "artist_id": artist_match["artist_id"],
            "artist_match_quality": artist_match["match_quality"],
            "market": market_match["market"],
            "market_status": market_match["status"],
            "market_method": market_match["method"],
            "venue_id": venue_match["venue_id"],
            "venue_match_quality": venue_match["match_quality"],
            "historical_window": historical_bucket(event_date, as_of),
        }
        overlap, sources = classify_overlap(
            row,
            existing_keys,
            existing_date_artist,
            musicbrainz_keys,
            musicbrainz_date_artist,
            venue_name_by_id,
        )
        row["provider_overlap"] = overlap
        row["existing_sources"] = sources
        resolved_rows.append(row)

    overlap_counts = Counter(row["provider_overlap"] for row in resolved_rows)
    overlap_source_counts = Counter(
        source for row in resolved_rows for source in row.get("existing_sources", [])
    )
    additional = [row for row in resolved_rows if row["provider_overlap"] == "setlist_only"]
    current_market_rows = [row for row in resolved_rows if row["market_status"] == "current"]
    exact_high_venues = [
        row for row in current_market_rows if row["venue_match_quality"] in {"exact", "high"}
    ]

    window_rows = []
    for label in WINDOW_LABELS:
        rows = [row for row in resolved_rows if row["historical_window"] == label]
        additions = [row for row in additional if row["historical_window"] == label]
        window_rows.append(
            {
                "historical_window": label,
                "unique_performances": len(rows),
                "performances_in_current_markets": sum(
                    row["market_status"] == "current" for row in rows
                ),
                "additional_relationships": len(additions),
                "exact_high_venue_resolutions": sum(
                    row["venue_match_quality"] in {"exact", "high"} for row in rows
                ),
            }
        )

    venue_counts_by_market = Counter(row["market"] for row in venues if row.get("market"))
    market_rows = []
    for market in sorted(current_markets):
        rows = [row for row in current_market_rows if row["market"] == market]
        additions = [row for row in additional if row["market"] == market]
        if not rows:
            continue
        dates = sorted(row["event_date"] for row in additions)
        resolved = [
            row for row in rows if row["venue_match_quality"] in {"exact", "high"}
        ]
        depth_months = (
            round((as_of - date.fromisoformat(dates[0])).days / 30.44, 1) if dates else 0.0
        )
        unique_artists = len({row["artist_id"] for row in additions if row.get("artist_id")})
        unique_venues = len({row["venue_id"] for row in additions if row.get("venue_id")})
        dense = (
            len(additions) >= DENSE_MARKET_RELATIONSHIPS
            and unique_artists >= 5
            and unique_venues >= 3
            and venue_counts_by_market[market] >= 5
        )
        market_rows.append(
            {
                "market": market,
                "historical_performances": len(rows),
                "additional_relationships": len(additions),
                "unique_artists": unique_artists,
                "unique_resolved_venues": unique_venues,
                "oldest_event_date": dates[0] if dates else None,
                "newest_event_date": dates[-1] if dates else None,
                "months_of_temporal_depth": depth_months,
                "exact_high_venue_resolutions": len(resolved),
                "exact_high_venue_resolution_rate": round(len(resolved) / len(rows), 4),
                "candidate_venues": venue_counts_by_market[market],
                "dense_6_month_coverage": dense and depth_months >= 6,
                "dense_12_month_coverage": dense and depth_months >= 12,
            }
        )

    provider_rows = [
        {"category": label, "performance_count": overlap_counts[label]}
        for label in (
            "already_known",
            "already_known_musicbrainz",
            "setlist_only",
            "likely_duplicate",
            "ambiguous",
        )
    ]
    provider_rows.extend(
        {"category": f"already_known_{source}", "performance_count": count}
        for source, count in sorted(overlap_source_counts.items())
    )

    sample_count = len(artists)
    mapped_count = int(snapshot["counts"]["musicbrainz_mapped_artists"])
    projection_factor = mapped_count / sample_count if sample_count else 0.0
    projected_additional = round(len(additional) * projection_factor)
    projected_pre_dense_period = round(
        sum(row["event_date"] < "2026-07-14" for row in additional) * projection_factor
    )
    dense_6 = sum(row["dense_6_month_coverage"] for row in market_rows)
    dense_12 = sum(row["dense_12_month_coverage"] for row in market_rows)
    represented_markets = [row for row in market_rows if row["additional_relationships"]]
    mean_candidates = (
        sum(row["candidate_venues"] for row in represented_markets) / len(represented_markets)
        if represented_markets
        else 0.0
    )
    average_pages = sum(page_depths) / len(page_depths) if page_depths else 0.0
    estimated_mapped_calls = round(average_pages * mapped_count)
    all_artist_call_estimate = round(average_pages * int(snapshot["counts"]["artists"]))
    combined_usable = 8_671 + 372 + projected_additional
    held_out = 8_531 if projected_pre_dense_period else 0
    projection = {
        "eligible_musicbrainz_mapped_artists": mapped_count,
        "projected_additional_usable_relationships": projected_additional,
        "projected_pre_july_2026_training_relationships": projected_pre_dense_period,
        "combined_usable_historical_relationships": combined_usable,
        "projected_held_out_relationships": held_out,
        "projected_markets_with_dense_6_month_coverage": dense_6,
        "projected_markets_with_dense_12_month_coverage": dense_12,
        "average_historical_events_per_represented_market": round(
            sum(row["additional_relationships"] for row in represented_markets)
            / len(represented_markets),
            2,
        ) if represented_markets else 0.0,
        "average_candidate_venues_per_represented_market": round(mean_candidates, 2),
        "candidate_set_viable": mean_candidates >= 5,
        "estimated_requests_for_all_current_mbid_artists": estimated_mapped_calls,
        "theoretical_requests_if_all_artists_had_mbids": all_artist_call_estimate,
        "estimated_runtime_minutes_current_mbid_artists": round(
            estimated_mapped_calls * client.minimum_interval / 60, 1
        ),
        "current_allowance_appears_sufficient": (
            artists_queried == sample_count and artist_failures == 0 and client.throttle_count == 0
        ),
        "allowance_note": (
            "Probe completed without throttling; no provider quota headers were observed."
            if not client.rate_limit_observations
            else "Provider rate-limit headers were observed and retained only as aggregate health metadata."
        ),
    }
    checks = {
        "usable_historical_examples": combined_usable >= 5_000,
        "held_out_examples": held_out >= 1_000,
        "markets_with_6_months": dense_6 >= 4,
        "markets_with_12_months_preferred": dense_12 >= 4,
        "candidate_venues": mean_candidates >= 5,
    }
    coverage_sufficient = all(
        checks[key]
        for key in (
            "usable_historical_examples",
            "held_out_examples",
            "markets_with_6_months",
            "candidate_venues",
        )
    )
    if coverage_sufficient:
        decision = "SETLIST_PERMISSION_REQUIRED_FOR_TRAINING"
    elif projected_additional >= 500 or dense_6 > 0:
        decision = "SETLIST_PARTIAL_ENRICHMENT_ONLY"
    else:
        decision = "SETLIST_HISTORY_INSUFFICIENT"

    dates = sorted(row["event_date"] for row in resolved_rows)
    health = client.health_summary()
    result = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "as_of": as_of.isoformat(),
            "read_only": True,
            "transient_event_data_deleted_after_aggregation": True,
            "max_pages_per_artist": max_pages_per_artist,
            "dense_market_definition": (
                f">={DENSE_MARKET_RELATIONSHIPS} additional relationships, >=5 artists, "
                ">=3 resolved venues, and >=5 candidate venues"
            ),
        },
        "summary": {
            "artists_sampled": sample_count,
            "artists_queried": artists_queried,
            "artists_with_history": artists_with_history,
            "artist_query_failures": artist_failures,
            "total_performance_records_returned": raw_records_returned,
            "unique_historical_performances": len(resolved_rows),
            "performances_in_current_markets": len(current_market_rows),
            "performances_outside_current_markets": sum(
                row["market_status"] == "outside" for row in resolved_rows
            ),
            "performances_with_unresolved_market": sum(
                row["market_status"] == "unresolved" for row in resolved_rows
            ),
            "exact_high_venue_resolutions": len(exact_high_venues),
            "current_market_venue_resolution_rate": round(
                len(exact_high_venues) / len(current_market_rows), 4
            ) if current_market_rows else 0.0,
            "additional_historical_relationships": len(additional),
            "additional_pre_july_2026_relationships": sum(
                row["event_date"] < "2026-07-14" for row in additional
            ),
            "oldest_event_date": dates[0] if dates else None,
            "newest_event_date": dates[-1] if dates else None,
            "september_2025_through_june_2026_relationships": sum(
                "2025-09-01" <= row["event_date"] <= "2026-06-30" for row in additional
            ),
            "truncated_artists": truncated_artists,
            "chronology_order_violations": order_violations,
        },
        "sample_profile": {
            "history_bands": dict(sorted(Counter(row["history_band"] for row in artists).items())),
            "provider_bias": dict(sorted(Counter(row["provider_bias"] for row in artists).items())),
            "established_or_sparse": dict(
                sorted(Counter(row["established_or_sparse"] for row in artists).items())
            ),
            "represented_markets": len({row["market"] for row in artists if row.get("market")}),
            "represented_primary_genres": len({row["primary_genre"] for row in artists}),
        },
        "request_metrics": {
            **health,
            "average_records_per_request": round(
                raw_records_returned / health["requests"], 3
            ) if health["requests"] else 0.0,
            "average_pages_per_artist": round(average_pages, 3),
            "maximum_pages_for_one_artist": max(page_depths, default=0),
            "artists_at_page_cap": truncated_artists,
        },
        "historical_window_summary": window_rows,
        "market_coverage_summary": market_rows,
        "provider_overlap_summary": provider_rows,
        "projected_full_coverage": projection,
        "decision_checks": checks,
        "decision": decision,
        "permission_required_before_storage_or_training": True,
    }
    transient_performances.clear()
    resolved_rows.clear()
    additional.clear()
    return result


def consolidate_setlist_probe_batches(
    batches: list[dict[str, Any]],
    hard_request_cap: int = 500,
    unaggregated_successful_requests: int = 0,
) -> dict[str, Any]:
    """Combine aggregate-only server batches without reconstructing event rows."""
    if not batches:
        raise ValueError("At least one Setlist probe batch is required")
    if unaggregated_successful_requests < 0:
        raise ValueError("Unaggregated request count cannot be negative")
    as_of = date.fromisoformat(batches[0]["metadata"]["as_of"])
    if any(batch["metadata"]["as_of"] != as_of.isoformat() for batch in batches):
        raise ValueError("Setlist probe batches must share one as-of date")

    additive_summary_fields = (
        "artists_sampled",
        "artists_queried",
        "artists_with_history",
        "artist_query_failures",
        "total_performance_records_returned",
        "unique_historical_performances",
        "performances_in_current_markets",
        "performances_outside_current_markets",
        "performances_with_unresolved_market",
        "exact_high_venue_resolutions",
        "additional_historical_relationships",
        "additional_pre_july_2026_relationships",
        "september_2025_through_june_2026_relationships",
        "truncated_artists",
        "chronology_order_violations",
    )
    summary = {
        field: sum(int(batch["summary"].get(field, 0)) for batch in batches)
        for field in additive_summary_fields
    }
    oldest_dates = [batch["summary"].get("oldest_event_date") for batch in batches]
    newest_dates = [batch["summary"].get("newest_event_date") for batch in batches]
    summary["oldest_event_date"] = min((value for value in oldest_dates if value), default=None)
    summary["newest_event_date"] = max((value for value in newest_dates if value), default=None)
    current_market_count = summary["performances_in_current_markets"]
    summary["current_market_venue_resolution_rate"] = round(
        summary["exact_high_venue_resolutions"] / current_market_count, 4
    ) if current_market_count else 0.0

    window_totals = {
        label: {
            "historical_window": label,
            "unique_performances": 0,
            "performances_in_current_markets": 0,
            "additional_relationships": 0,
            "exact_high_venue_resolutions": 0,
        }
        for label in WINDOW_LABELS
    }
    for batch in batches:
        for row in batch["historical_window_summary"]:
            target = window_totals[row["historical_window"]]
            for field in target:
                if field != "historical_window":
                    target[field] += int(row.get(field, 0))
    window_rows = [window_totals[label] for label in WINDOW_LABELS]

    market_totals: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for row in batch["market_coverage_summary"]:
            market = row["market"]
            target = market_totals.setdefault(
                market,
                {
                    "market": market,
                    "historical_performances": 0,
                    "additional_relationships": 0,
                    "unique_artists": 0,
                    "unique_resolved_venues": 0,
                    "oldest_event_date": None,
                    "newest_event_date": None,
                    "exact_high_venue_resolutions": 0,
                    "candidate_venues": int(row["candidate_venues"]),
                },
            )
            target["historical_performances"] += int(row["historical_performances"])
            target["additional_relationships"] += int(row["additional_relationships"])
            # Sample artists do not repeat across batches. Venue count uses a conservative
            # lower bound because aggregate batches intentionally omit venue identifiers.
            target["unique_artists"] += int(row["unique_artists"])
            target["unique_resolved_venues"] = max(
                target["unique_resolved_venues"], int(row["unique_resolved_venues"])
            )
            target["exact_high_venue_resolutions"] += int(
                row.get("exact_high_venue_resolutions", 0)
            )
            for field, chooser in (
                ("oldest_event_date", min),
                ("newest_event_date", max),
            ):
                value = row.get(field)
                if value:
                    target[field] = value if not target[field] else chooser(target[field], value)

    market_rows = []
    for market in sorted(market_totals):
        row = market_totals[market]
        depth_months = (
            round((as_of - date.fromisoformat(row["oldest_event_date"])).days / 30.44, 1)
            if row["oldest_event_date"]
            else 0.0
        )
        dense = (
            row["additional_relationships"] >= DENSE_MARKET_RELATIONSHIPS
            and row["unique_artists"] >= 5
            and row["unique_resolved_venues"] >= 3
            and row["candidate_venues"] >= 5
        )
        market_rows.append(
            {
                **row,
                "months_of_temporal_depth": depth_months,
                "exact_high_venue_resolution_rate": round(
                    row["exact_high_venue_resolutions"] / row["historical_performances"], 4
                ) if row["historical_performances"] else 0.0,
                "dense_6_month_coverage": dense and depth_months >= 6,
                "dense_12_month_coverage": dense and depth_months >= 12,
            }
        )

    overlap_totals = Counter()
    for batch in batches:
        overlap_totals.update(
            {
                row["category"]: int(row["performance_count"])
                for row in batch["provider_overlap_summary"]
            }
        )
    provider_rows = [
        {"category": category, "performance_count": count}
        for category, count in sorted(overlap_totals.items())
    ]

    health_fields = ("requests", "retries", "throttles", "not_found")
    request_metrics = {
        field: sum(int(batch["request_metrics"].get(field, 0)) for batch in batches)
        for field in health_fields
    }
    request_metrics["requests"] += unaggregated_successful_requests
    status_counts = Counter()
    rate_limit_headers: dict[str, str] = {}
    weighted_pages = 0.0
    maximum_pages = 0
    artists_at_cap = 0
    for batch in batches:
        metrics = batch["request_metrics"]
        status_counts.update(
            {int(key): int(value) for key, value in metrics.get("status_counts", {}).items()}
        )
        rate_limit_headers.update(metrics.get("rate_limit_headers", {}))
        weighted_pages += float(metrics.get("average_pages_per_artist", 0)) * int(
            batch["summary"]["artists_queried"]
        )
        maximum_pages = max(maximum_pages, int(metrics.get("maximum_pages_for_one_artist", 0)))
        artists_at_cap += int(metrics.get("artists_at_page_cap", 0))
    if unaggregated_successful_requests:
        status_counts[200] += unaggregated_successful_requests
    request_metrics.update(
        {
            "status_counts": dict(sorted(status_counts.items())),
            "rate_limit_headers": dict(sorted(rate_limit_headers.items())),
            "average_records_per_request": round(
                summary["total_performance_records_returned"] / request_metrics["requests"], 3
            ) if request_metrics["requests"] else 0.0,
            "average_pages_per_artist": round(
                weighted_pages / summary["artists_queried"], 3
            ) if summary["artists_queried"] else 0.0,
            "maximum_pages_for_one_artist": maximum_pages,
            "artists_at_page_cap": artists_at_cap,
            "unaggregated_successful_requests": unaggregated_successful_requests,
            "hard_request_cap": hard_request_cap,
            "request_cap_respected": request_metrics["requests"] <= hard_request_cap,
        }
    )

    first_projection = batches[0]["projected_full_coverage"]
    mapped_count = int(first_projection["eligible_musicbrainz_mapped_artists"])
    sample_count = summary["artists_sampled"]
    projection_factor = mapped_count / sample_count if sample_count else 0.0
    projected_additional = round(
        summary["additional_historical_relationships"] * projection_factor
    )
    projected_pre_dense = round(
        summary["additional_pre_july_2026_relationships"] * projection_factor
    )
    dense_6 = sum(row["dense_6_month_coverage"] for row in market_rows)
    dense_12 = sum(row["dense_12_month_coverage"] for row in market_rows)
    represented_markets = [row for row in market_rows if row["additional_relationships"]]
    mean_candidates = (
        sum(row["candidate_venues"] for row in represented_markets) / len(represented_markets)
        if represented_markets
        else 0.0
    )
    observed_requests_per_artist = (
        request_metrics["requests"] / summary["artists_queried"]
        if summary["artists_queried"]
        else 0.0
    )
    estimated_mapped_calls = round(observed_requests_per_artist * mapped_count)
    combined_usable = 8_671 + 372 + projected_additional
    held_out = 8_531 if projected_pre_dense else 0
    projection = {
        "eligible_musicbrainz_mapped_artists": mapped_count,
        "projected_additional_usable_relationships": projected_additional,
        "projected_pre_july_2026_training_relationships": projected_pre_dense,
        "combined_usable_historical_relationships": combined_usable,
        "projected_held_out_relationships": held_out,
        "projected_markets_with_dense_6_month_coverage": dense_6,
        "projected_markets_with_dense_12_month_coverage": dense_12,
        "average_historical_events_per_represented_market": round(
            sum(row["additional_relationships"] for row in represented_markets)
            / len(represented_markets), 2
        ) if represented_markets else 0.0,
        "average_candidate_venues_per_represented_market": round(mean_candidates, 2),
        "candidate_set_viable": mean_candidates >= 5,
        "estimated_requests_for_all_current_mbid_artists": estimated_mapped_calls,
        "theoretical_requests_if_all_artists_had_mbids": round(
            observed_requests_per_artist * 5_520
        ),
        "estimated_runtime_minutes_current_mbid_artists": round(
            estimated_mapped_calls / 60, 1
        ),
        "current_allowance_appears_sufficient": (
            summary["artists_queried"] == sample_count
            and summary["artist_query_failures"] == 0
            and request_metrics["request_cap_respected"]
        ),
        "allowance_note": (
            f"Probe used {request_metrics['requests']} of the 500-request safety cap; "
            f"{request_metrics['throttles']} HTTP 429 responses were handled conservatively."
        ),
    }
    checks = {
        "usable_historical_examples": combined_usable >= 5_000,
        "held_out_examples": held_out >= 1_000,
        "markets_with_6_months": dense_6 >= 4,
        "markets_with_12_months_preferred": dense_12 >= 4,
        "candidate_venues": mean_candidates >= 5,
    }
    coverage_sufficient = all(
        checks[key]
        for key in (
            "usable_historical_examples",
            "held_out_examples",
            "markets_with_6_months",
            "candidate_venues",
        )
    )
    decision = (
        "SETLIST_PERMISSION_REQUIRED_FOR_TRAINING"
        if coverage_sufficient
        else "SETLIST_PARTIAL_ENRICHMENT_ONLY"
        if projected_additional >= 500 or dense_6 > 0
        else "SETLIST_HISTORY_INSUFFICIENT"
    )
    history_bands = Counter()
    provider_bias = Counter()
    established = Counter()
    for batch in batches:
        profile = batch["sample_profile"]
        history_bands.update(profile["history_bands"])
        provider_bias.update(profile["provider_bias"])
        established.update(profile["established_or_sparse"])

    return {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "as_of": as_of.isoformat(),
            "read_only": True,
            "transient_event_data_deleted_after_aggregation": True,
            "server_batches": len(batches),
            "max_pages_per_artist": max(
                int(batch["metadata"]["max_pages_per_artist"]) for batch in batches
            ),
            "dense_market_definition": (
                f">={DENSE_MARKET_RELATIONSHIPS} additional relationships, >=5 artists, "
                ">=3 resolved venues using a conservative aggregate-only lower bound, "
                "and >=5 candidate venues"
            ),
        },
        "summary": summary,
        "sample_profile": {
            "history_bands": dict(sorted(history_bands.items())),
            "provider_bias": dict(sorted(provider_bias.items())),
            "established_or_sparse": dict(sorted(established.items())),
            "represented_markets_lower_bound": max(
                int(batch["sample_profile"]["represented_markets"]) for batch in batches
            ),
            "represented_primary_genres_lower_bound": max(
                int(batch["sample_profile"]["represented_primary_genres"])
                for batch in batches
            ),
        },
        "request_metrics": request_metrics,
        "historical_window_summary": window_rows,
        "market_coverage_summary": market_rows,
        "provider_overlap_summary": provider_rows,
        "projected_full_coverage": projection,
        "decision_checks": checks,
        "decision": decision,
        "permission_required_before_storage_or_training": True,
    }


def render_setlist_probe_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    projection = result["projected_full_coverage"]
    return f"""# VenueMatch Setlist.fm Historical Coverage Probe

Generated: {result['metadata']['generated_at_utc']}<br>
As-of date: {result['metadata']['as_of']}<br>
Mode: transient read-only probe; no Setlist.fm event records persisted

## Decision

**{result['decision']}**

Explicit Setlist.fm permission required before permanent storage or ML training: **True**

## Coverage Summary

- Artists sampled / queried: **{summary['artists_sampled']} / {summary['artists_queried']}**
- Artists with history: **{summary['artists_with_history']}**
- Unique historical performances: **{summary['unique_historical_performances']:,}**
- Performances in / outside / unresolved for current markets: **{summary['performances_in_current_markets']:,} / {summary['performances_outside_current_markets']:,} / {summary['performances_with_unresolved_market']:,}**
- Additional historical relationships: **{summary['additional_historical_relationships']:,}**
- Venue-resolution rate in current markets: **{summary['current_market_venue_resolution_rate']:.1%}**
- Oldest / newest: **{summary['oldest_event_date']} / {summary['newest_event_date']}**
- September 2025 through June 2026 additions: **{summary['september_2025_through_june_2026_relationships']:,}**

## Request Metrics

```json
{json.dumps(result['request_metrics'], indent=2)}
```

## Historical Windows

{_markdown_table(result['historical_window_summary'])}

## Market Coverage

{_markdown_table(result['market_coverage_summary'])}

## Provider Overlap

{_markdown_table(result['provider_overlap_summary'])}

## Projected Full Coverage

```json
{json.dumps(projection, indent=2)}
```

## Decision Checks

```json
{json.dumps(result['decision_checks'], indent=2)}
```

## Data Handling

No API key, raw response, setlist, song, per-artist response, event-level performance row, or Setlist.fm venue list is retained in these artifacts. Event-level objects existed only in process memory and were cleared after aggregate calculation. Setlist.fm permission is required before any durable storage or training use.
"""


def _markdown_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_No rows available._"
    columns = list(rows[0])
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        lines.append(
            "| " + " | ".join(str(row.get(column, "")).replace("|", "\\|") for column in columns) + " |"
        )
    return "\n".join(lines)


def write_setlist_probe_artifacts(result: dict[str, Any], output_dir: str | Path) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    allowed_keys = {
        "metadata",
        "summary",
        "sample_profile",
        "request_metrics",
        "historical_window_summary",
        "market_coverage_summary",
        "provider_overlap_summary",
        "projected_full_coverage",
        "decision_checks",
        "decision",
        "permission_required_before_storage_or_training",
    }
    aggregate = {key: result[key] for key in allowed_keys}
    (output / "setlist_history_probe.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output / "setlist_history_probe.md").write_text(
        render_setlist_probe_report(result), encoding="utf-8"
    )
    pd.DataFrame(result["market_coverage_summary"]).to_csv(
        output / "market_coverage_summary.csv", index=False
    )
    pd.DataFrame(result["historical_window_summary"]).to_csv(
        output / "historical_window_summary.csv", index=False
    )
    pd.DataFrame(result["provider_overlap_summary"]).to_csv(
        output / "provider_overlap_summary.csv", index=False
    )
    (output / "projected_full_coverage.json").write_text(
        json.dumps(result["projected_full_coverage"], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output
