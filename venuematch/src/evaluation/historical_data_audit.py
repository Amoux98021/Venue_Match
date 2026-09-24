from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

import pandas as pd

from src.db import repository
from src.db.database import DatabaseTarget


AUDIT_VERSION = "1.0"
SETLIST_THRESHOLDS = {
    "eligible_historical_bookings": 5_000,
    "held_out_test_bookings": 1_000,
    "useful_markets": 4,
    "mean_candidate_count": 5.0,
    "historical_depth_days": 365,
}


def _as_utc_day(value: date | datetime | str | pd.Timestamp | None) -> pd.Timestamp:
    if value is None:
        value = datetime.now(timezone.utc)
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is not None:
        parsed = parsed.tz_convert("UTC").tz_localize(None)
    return parsed.normalize()


def _clean_string(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _normalized_entity(value: Any) -> str:
    cleaned = _clean_string(value) or ""
    ascii_value = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def _present(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("")


def _number(value: Any, digits: int = 2) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return round(float(value), digits)


def _iso_date(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _market_key(city: Any, state: Any) -> tuple[str, str] | None:
    clean_city = _clean_string(city)
    clean_state = _clean_string(state)
    if not clean_city or not clean_state:
        return None
    return clean_city.casefold(), clean_state.casefold()


def _market_label(city: Any, state: Any) -> str | None:
    key = _market_key(city, state)
    if key is None:
        return None
    return f"{_clean_string(city)}, {_clean_string(state)}"


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    records: list[dict[str, Any]] = []
    for record in clean.to_dict("records"):
        converted: dict[str, Any] = {}
        for key, value in record.items():
            if isinstance(value, (pd.Timestamp, datetime, date)):
                converted[key] = _iso_date(value)
            elif hasattr(value, "item"):
                converted[key] = value.item()
            else:
                converted[key] = value
        records.append(converted)
    return records


def classify_events(
    events: pd.DataFrame,
    as_of: date | datetime | str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Classify relationship rows without treating malformed dates as historical."""
    result = events.copy()
    if "event_date" not in result:
        result["event_date"] = None
    result["event_dt"] = pd.to_datetime(result["event_date"], errors="coerce", utc=True)
    result["event_dt"] = result["event_dt"].dt.tz_convert(None).dt.normalize()
    as_of_day = _as_utc_day(as_of)
    result["temporal_class"] = "missing_date"
    result.loc[result["event_dt"].notna() & (result["event_dt"] < as_of_day), "temporal_class"] = (
        "historical"
    )
    result.loc[result["event_dt"].notna() & (result["event_dt"] >= as_of_day), "temporal_class"] = (
        "current_or_future"
    )
    return result


def _enrich_event_entities(
    events: pd.DataFrame,
    artists: pd.DataFrame,
    venues: pd.DataFrame,
    as_of: date | datetime | str | pd.Timestamp | None,
) -> pd.DataFrame:
    classified = classify_events(events, as_of)
    artist_ids = set(artists.get("id", pd.Series(dtype=object)).dropna().astype(str))
    venue_ids = set(venues.get("id", pd.Series(dtype=object)).dropna().astype(str))

    venue_lookup = venues.copy()
    for column in ("id", "city", "state", "capacity"):
        if column not in venue_lookup:
            venue_lookup[column] = None
    venue_lookup = venue_lookup[["id", "city", "state", "capacity"]].rename(
        columns={
            "id": "resolved_venue_id",
            "city": "venue_city",
            "state": "venue_state",
            "capacity": "venue_capacity",
        }
    )
    result = classified.merge(
        venue_lookup,
        left_on="venue_id",
        right_on="resolved_venue_id",
        how="left",
    )
    result["artist_resolved"] = result.get("artist_id", pd.Series(dtype=object)).astype(str).isin(
        artist_ids
    )
    result["venue_resolved"] = result.get("venue_id", pd.Series(dtype=object)).astype(str).isin(
        venue_ids
    )
    event_city = result.get("city", pd.Series(index=result.index, dtype=object)).map(_clean_string)
    event_state = result.get("state", pd.Series(index=result.index, dtype=object)).map(_clean_string)
    result["resolved_city"] = event_city.where(event_city.notna(), result["venue_city"].map(_clean_string))
    result["resolved_state"] = event_state.where(
        event_state.notna(), result["venue_state"].map(_clean_string)
    )
    result["market"] = [
        _market_label(city, state)
        for city, state in zip(result["resolved_city"], result["resolved_state"])
    ]
    result["market_resolved"] = result["market"].notna()
    return result


def build_venue_activity(historical_events: pd.DataFrame) -> dict[str, dict[str, pd.Timestamp]]:
    """Return first observed historical activity by market and venue."""
    valid = historical_events.loc[
        historical_events["event_dt"].notna()
        & historical_events["market"].notna()
        & historical_events["venue_resolved"]
    ].copy()
    if valid.empty:
        return {}
    first_seen = valid.groupby(["market", "venue_id"], dropna=False)["event_dt"].min()
    activity: dict[str, dict[str, pd.Timestamp]] = {}
    for (market, venue_id), first_date in first_seen.items():
        activity.setdefault(str(market), {})[str(venue_id)] = pd.Timestamp(first_date)
    return activity


def candidate_venues_for_event(
    event: pd.Series | dict[str, Any],
    venue_activity: dict[str, dict[str, pd.Timestamp]],
) -> set[str]:
    """Generate candidates from same-market venues active no later than the event."""
    market = event.get("market")
    event_dt = event.get("event_dt")
    if not market or event_dt is None or pd.isna(event_dt):
        return set()
    event_day = pd.Timestamp(event_dt)
    return {
        venue_id
        for venue_id, first_active in venue_activity.get(str(market), {}).items()
        if first_active <= event_day
    }


def evaluate_benchmark_eligibility(
    events: pd.DataFrame,
    artists: pd.DataFrame,
    venues: pd.DataFrame,
    as_of: date | datetime | str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    enriched = _enrich_event_entities(events, artists, venues, as_of)
    historical = enriched.loc[enriched["temporal_class"] == "historical"].copy()
    activity = build_venue_activity(historical)

    rows: list[dict[str, Any]] = []
    for _, event in historical.iterrows():
        candidates = candidate_venues_for_event(event, activity)
        actual_venue = _clean_string(event.get("venue_id"))
        actual_active = bool(actual_venue and actual_venue in candidates)
        base_resolved = bool(
            event.get("event_dt") is not None
            and not pd.isna(event.get("event_dt"))
            and event.get("artist_resolved")
            and event.get("venue_resolved")
            and event.get("market_resolved")
            and actual_active
        )
        candidate_count = len(candidates) if base_resolved else 0
        alternative_count = max(candidate_count - 1, 0) if actual_active else candidate_count
        eligible = base_resolved and alternative_count >= 1
        eligible_5 = base_resolved and candidate_count >= 5

        reasons: list[str] = []
        if not event.get("artist_resolved"):
            reasons.append("unresolved_artist")
        if not event.get("venue_resolved"):
            reasons.append("unresolved_venue")
        if not event.get("market_resolved"):
            reasons.append("unresolved_market")
        if base_resolved and not actual_active:
            reasons.append("venue_not_active")
        if base_resolved and alternative_count < 1:
            reasons.append("no_alternative_venue")

        rows.append(
            {
                "event_id": event.get("id"),
                "artist_id": event.get("artist_id"),
                "venue_id": event.get("venue_id"),
                "event_date": _iso_date(event.get("event_dt")),
                "event_dt": event.get("event_dt"),
                "market": event.get("market"),
                "candidate_count": candidate_count,
                "alternative_candidate_count": alternative_count,
                "eligible": eligible,
                "eligible_5_candidates": eligible_5,
                "ineligible_reasons": ",".join(reasons),
            }
        )
    return pd.DataFrame(rows)


def _distribution(values: list[int] | pd.Series) -> dict[str, float | int | None]:
    series = pd.Series(values, dtype="float64").dropna()
    if series.empty:
        return {
            "minimum": None,
            "p25": None,
            "median": None,
            "mean": None,
            "p75": None,
            "p90": None,
            "maximum": None,
        }
    return {
        "minimum": int(series.min()),
        "p25": _number(series.quantile(0.25)),
        "median": _number(series.median()),
        "mean": _number(series.mean()),
        "p75": _number(series.quantile(0.75)),
        "p90": _number(series.quantile(0.90)),
        "maximum": int(series.max()),
    }


def recommend_temporal_folds(
    eligible_events: pd.DataFrame,
    fold_count: int = 3,
    initial_train_fraction: float = 0.40,
) -> list[dict[str, Any]]:
    """Build expanding-window folds from event-count quantiles without fixed dates."""
    if eligible_events.empty or fold_count < 1:
        return []
    eligible = eligible_events.loc[eligible_events["eligible"]].copy()
    eligible["event_dt"] = pd.to_datetime(eligible["event_dt"], errors="coerce")
    eligible = eligible.dropna(subset=["event_dt"]).sort_values("event_dt")
    if len(eligible) < fold_count + 2 or eligible["event_dt"].nunique() < fold_count + 1:
        return []

    test_fraction = (1.0 - initial_train_fraction) / fold_count
    quantiles = [initial_train_fraction + (index * test_fraction) for index in range(fold_count)]
    starts = [
        pd.Timestamp(eligible["event_dt"].quantile(value, interpolation="higher"))
        for value in quantiles
    ]
    unique_dates = sorted(pd.Timestamp(value) for value in eligible["event_dt"].unique())
    normalized_starts: list[pd.Timestamp] = []
    for start in starts:
        if normalized_starts and start <= normalized_starts[-1]:
            later = [value for value in unique_dates if value > normalized_starts[-1]]
            if not later:
                return []
            start = later[0]
        normalized_starts.append(start)

    folds: list[dict[str, Any]] = []
    for index, test_start in enumerate(normalized_starts):
        test_end_exclusive = (
            normalized_starts[index + 1] if index + 1 < len(normalized_starts) else None
        )
        train = eligible.loc[eligible["event_dt"] < test_start]
        if test_end_exclusive is None:
            test = eligible.loc[eligible["event_dt"] >= test_start]
        else:
            test = eligible.loc[
                (eligible["event_dt"] >= test_start)
                & (eligible["event_dt"] < test_end_exclusive)
            ]
        if train.empty or test.empty:
            return []
        folds.append(
            {
                "fold": index + 1,
                "train_start": _iso_date(train["event_dt"].min()),
                "train_end": _iso_date(train["event_dt"].max()),
                "test_start": _iso_date(test["event_dt"].min()),
                "test_end": _iso_date(test["event_dt"].max()),
                "train_event_count": int(len(train)),
                "test_event_count": int(len(test)),
                "markets_represented": int(test["market"].nunique()),
                "market_names": sorted(test["market"].dropna().unique().tolist()),
                "artists_represented": int(test["artist_id"].nunique()),
                "venues_represented": int(test["venue_id"].nunique()),
            }
        )
    return folds


def _provider_coverage(enriched: pd.DataFrame) -> list[dict[str, Any]]:
    frame = enriched.copy()
    source = frame.get("source", pd.Series(index=frame.index, dtype=object)).map(_clean_string)
    frame["provider"] = source.fillna("missing")
    rows: list[dict[str, Any]] = []
    for provider, group in frame.groupby("provider", dropna=False):
        dated = group.dropna(subset=["event_dt"])
        historical = group.loc[group["temporal_class"] == "historical"]
        rows.append(
            {
                "provider": str(provider),
                "relationship_count": int(len(group)),
                "historical_relationship_count": int(len(historical)),
                "earliest_date": _iso_date(dated["event_dt"].min()) if not dated.empty else None,
                "latest_date": _iso_date(dated["event_dt"].max()) if not dated.empty else None,
                "unique_artists": int(group["artist_id"].nunique()),
                "unique_venues": int(group["venue_id"].nunique()),
                "unique_markets": int(group["market"].nunique()),
            }
        )
    return sorted(rows, key=lambda row: row["relationship_count"], reverse=True)


def _market_coverage(
    enriched: pd.DataFrame,
    venues: pd.DataFrame,
    eligibility: pd.DataFrame,
    target_markets: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    venue_markets = {
        _market_label(row.get("city"), row.get("state"))
        for row in venues.to_dict("records")
    }
    event_markets = set(enriched["market"].dropna().unique().tolist())
    configured_markets = {
        _market_label(row.get("city"), row.get("state"))
        for row in (target_markets.to_dict("records") if target_markets is not None else [])
    }
    configured_markets.discard(None)
    markets = sorted((venue_markets | event_markets | configured_markets) - {None})
    rows: list[dict[str, Any]] = []
    for market in markets:
        group = enriched.loc[enriched["market"] == market]
        historical = group.loc[group["temporal_class"] == "historical"]
        future = group.loc[group["temporal_class"] == "current_or_future"]
        historical_by_venue = historical.groupby("venue_id").size()
        eligible_market = eligibility.loc[
            (eligibility.get("market") == market) & eligibility.get("eligible", False)
        ] if not eligibility.empty else pd.DataFrame()
        candidate_mean = (
            _number(eligible_market["candidate_count"].mean()) if not eligible_market.empty else 0.0
        )
        historical_months = int(historical["event_dt"].dt.to_period("M").nunique()) if not historical.empty else 0
        span_days = (
            int((historical["event_dt"].max() - historical["event_dt"].min()).days)
            if len(historical) > 1
            else 0
        )
        useful = len(eligible_market) >= 50 and historical_months >= 6 and candidate_mean >= 5
        rows.append(
            {
                "market": market,
                "is_target_market": market in configured_markets,
                "historical_event_count": int(len(historical)),
                "future_event_count": int(len(future)),
                "missing_date_count": int((group["temporal_class"] == "missing_date").sum()),
                "unique_artists": int(historical["artist_id"].nunique()),
                "unique_venues": int(historical["venue_id"].nunique()),
                "earliest_event_date": _iso_date(group["event_dt"].min()),
                "latest_event_date": _iso_date(group["event_dt"].max()),
                "median_historical_events_per_venue": (
                    _number(historical_by_venue.median()) if not historical_by_venue.empty else 0.0
                ),
                "artists_with_2_plus_historical_appearances": int(
                    (historical.groupby("artist_id").size() >= 2).sum()
                ),
                "venues_with_10_plus_historical_events": int((historical_by_venue >= 10).sum()),
                "historical_months": historical_months,
                "historical_span_days": span_days,
                "benchmark_eligible_count": int(len(eligible_market)),
                "mean_candidate_count": candidate_mean,
                "useful_for_temporal_benchmark": useful,
            }
        )
    return sorted(rows, key=lambda row: row["historical_event_count"], reverse=True)


def _artist_coverage(
    artists: pd.DataFrame,
    artist_genres: pd.DataFrame,
    historical: pd.DataFrame,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    history_counts = historical.groupby("artist_id").size().rename("historical_booking_count")
    genre_counts = artist_genres.groupby("artist_id").size().rename("genre_count")
    coverage = artists.copy()
    coverage = coverage.merge(history_counts, left_on="id", right_index=True, how="left")
    coverage = coverage.merge(genre_counts, left_on="id", right_index=True, how="left")
    coverage["historical_booking_count"] = coverage["historical_booking_count"].fillna(0).astype(int)
    coverage["genre_count"] = coverage["genre_count"].fillna(0).astype(int)
    for column in ("musicbrainz_id", "lastfm_listeners", "popularity"):
        if column not in coverage:
            coverage[column] = None
    coverage["has_musicbrainz_id"] = _present(coverage["musicbrainz_id"])
    coverage["has_genre_data"] = coverage["genre_count"] > 0
    coverage["has_lastfm_audience_data"] = coverage["lastfm_listeners"].notna()
    coverage["has_artist_popularity"] = coverage["popularity"].notna()
    history_positive = coverage.loc[coverage["historical_booking_count"] > 0]
    total = max(len(coverage), 1)
    summary = {
        "total_artists": int(len(coverage)),
        "artists_with_1_plus": int((coverage["historical_booking_count"] >= 1).sum()),
        "artists_with_2_plus": int((coverage["historical_booking_count"] >= 2).sum()),
        "artists_with_3_plus": int((coverage["historical_booking_count"] >= 3).sum()),
        "artists_with_5_plus": int((coverage["historical_booking_count"] >= 5).sum()),
        "artists_with_10_plus": int((coverage["historical_booking_count"] >= 10).sum()),
        "median_historical_bookings_per_artist_with_history": (
            _number(history_positive["historical_booking_count"].median())
            if not history_positive.empty
            else 0.0
        ),
        "mean_historical_bookings_per_artist_with_history": (
            _number(history_positive["historical_booking_count"].mean())
            if not history_positive.empty
            else 0.0
        ),
        "percent_with_musicbrainz_id": _number(100 * coverage["has_musicbrainz_id"].sum() / total),
        "percent_with_genre_data": _number(100 * coverage["has_genre_data"].sum() / total),
        "percent_with_lastfm_audience_data": _number(
            100 * coverage["has_lastfm_audience_data"].sum() / total
        ),
        "percent_with_artist_popularity": _number(
            100 * coverage["has_artist_popularity"].sum() / total
        ),
        "top_25_artists": _records(
            coverage.sort_values(["historical_booking_count", "name"], ascending=[False, True])[
                ["id", "name", "historical_booking_count"]
            ].head(25)
        ),
        "lastfm_limitation": (
            "The schema stores Last.fm listener counts but does not currently store Last.fm playcount."
        ),
    }
    output_columns = [
        "id",
        "name",
        "historical_booking_count",
        "genre_count",
        "has_musicbrainz_id",
        "has_genre_data",
        "has_lastfm_audience_data",
        "has_artist_popularity",
    ]
    return summary, _records(
        coverage[output_columns].sort_values(
            ["historical_booking_count", "name"], ascending=[False, True]
        )
    )


def _venue_coverage(
    venues: pd.DataFrame,
    venue_history: pd.DataFrame,
    historical: pd.DataFrame,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    history_counts = historical.groupby("venue_id").size().rename("historical_booking_count")
    genre_counts = venue_history.groupby("venue_id").size().rename("genre_history_count")
    coverage = venues.copy()
    coverage = coverage.merge(history_counts, left_on="id", right_index=True, how="left")
    coverage = coverage.merge(genre_counts, left_on="id", right_index=True, how="left")
    coverage["historical_booking_count"] = coverage["historical_booking_count"].fillna(0).astype(int)
    coverage["genre_history_count"] = coverage["genre_history_count"].fillna(0).astype(int)
    for column in ("capacity", "latitude", "longitude", "city", "state"):
        if column not in coverage:
            coverage[column] = None
    coverage["has_capacity"] = coverage["capacity"].notna()
    coverage["has_genre_history"] = coverage["genre_history_count"] > 0
    coverage["has_coordinates"] = coverage["latitude"].notna() & coverage["longitude"].notna()
    coverage["has_resolved_market"] = [
        _market_key(city, state) is not None
        for city, state in zip(coverage["city"], coverage["state"])
    ]
    history_positive = coverage.loc[coverage["historical_booking_count"] > 0]
    total = max(len(coverage), 1)
    summary = {
        "total_venues": int(len(coverage)),
        "venues_with_1_plus": int((coverage["historical_booking_count"] >= 1).sum()),
        "venues_with_5_plus": int((coverage["historical_booking_count"] >= 5).sum()),
        "venues_with_10_plus": int((coverage["historical_booking_count"] >= 10).sum()),
        "venues_with_25_plus": int((coverage["historical_booking_count"] >= 25).sum()),
        "venues_with_50_plus": int((coverage["historical_booking_count"] >= 50).sum()),
        "median_historical_bookings_per_venue_with_history": (
            _number(history_positive["historical_booking_count"].median())
            if not history_positive.empty
            else 0.0
        ),
        "mean_historical_bookings_per_venue_with_history": (
            _number(history_positive["historical_booking_count"].mean())
            if not history_positive.empty
            else 0.0
        ),
        "percent_with_capacity": _number(100 * coverage["has_capacity"].sum() / total),
        "percent_with_genre_history": _number(100 * coverage["has_genre_history"].sum() / total),
        "percent_with_coordinates": _number(100 * coverage["has_coordinates"].sum() / total),
        "percent_with_resolved_market": _number(
            100 * coverage["has_resolved_market"].sum() / total
        ),
        "top_25_venues": _records(
            coverage.sort_values(["historical_booking_count", "name"], ascending=[False, True])[
                ["id", "name", "city", "state", "historical_booking_count"]
            ].head(25)
        ),
    }
    output_columns = [
        "id",
        "name",
        "city",
        "state",
        "historical_booking_count",
        "genre_history_count",
        "has_capacity",
        "has_genre_history",
        "has_coordinates",
        "has_resolved_market",
    ]
    return summary, _records(
        coverage[output_columns].sort_values(
            ["historical_booking_count", "name"], ascending=[False, True]
        )
    )


def _duplicate_groups(frame: pd.DataFrame, columns: list[str], name_column: str) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    normalized = frame.copy()
    normalized["duplicate_key"] = normalized[columns].apply(
        lambda row: "|".join(_normalized_entity(value) for value in row), axis=1
    )
    normalized = normalized.loc[normalized["duplicate_key"].str.replace("|", "", regex=False).ne("")]
    duplicated = normalized.loc[normalized.duplicated("duplicate_key", keep=False)]
    groups: list[dict[str, Any]] = []
    for key, group in duplicated.groupby("duplicate_key"):
        groups.append(
            {
                "normalized_key": key,
                "record_count": int(len(group)),
                "ids": sorted(group["id"].astype(str).tolist()),
                "names": sorted(group[name_column].astype(str).unique().tolist()),
            }
        )
    return sorted(groups, key=lambda row: (-row["record_count"], row["normalized_key"]))


def _entity_quality(
    enriched: pd.DataFrame,
    artists: pd.DataFrame,
    venues: pd.DataFrame,
    artist_genres: pd.DataFrame,
) -> dict[str, Any]:
    artist_duplicates = _duplicate_groups(artists, ["name"], "name")
    venue_duplicates = _duplicate_groups(venues, ["name", "city", "state"], "name")
    artist_ids_with_genres = set(artist_genres.get("artist_id", pd.Series(dtype=object)).astype(str))
    missing_artist_id = ~_present(enriched.get("artist_id", pd.Series(index=enriched.index, dtype=object)))
    missing_venue_id = ~_present(enriched.get("venue_id", pd.Series(index=enriched.index, dtype=object)))
    source_present = _present(enriched.get("source", pd.Series(index=enriched.index, dtype=object)))
    missing_event_genre = ~_present(enriched.get("genre", pd.Series(index=enriched.index, dtype=object)))
    missing_artist_genre = ~enriched.get("artist_id", pd.Series(index=enriched.index, dtype=object)).astype(
        str
    ).isin(artist_ids_with_genres)
    return {
        "duplicate_artist_candidate_groups": len(artist_duplicates),
        "duplicate_artist_candidates": artist_duplicates,
        "duplicate_venue_candidate_groups": len(venue_duplicates),
        "duplicate_venue_candidates": venue_duplicates,
        "relationships_missing_artist_id": int(missing_artist_id.sum()),
        "relationships_missing_venue_id": int(missing_venue_id.sum()),
        "unresolved_artist_relationships": int((~enriched["artist_resolved"]).sum()),
        "unresolved_venue_relationships": int((~enriched["venue_resolved"]).sum()),
        "relationships_missing_market": int((~enriched["market_resolved"]).sum()),
        "relationships_missing_event_genre": int(missing_event_genre.sum()),
        "relationships_whose_artist_has_no_genre": int(missing_artist_genre.sum()),
        "venues_missing_capacity": int(venues.get("capacity", pd.Series(dtype=object)).isna().sum()),
        "relationships_with_missing_venue_capacity": int(
            enriched.get("venue_capacity", pd.Series(index=enriched.index, dtype=object)).isna().sum()
        ),
        "relationships_missing_provider_provenance": int((~source_present).sum()),
        "provider_provenance_limitation": (
            "Event-level source is stored. MusicBrainz is used for artist identity enrichment, not as an "
            "event relationship source, so MusicBrainz-derived bookings cannot be reported."
        ),
    }


def _events_by_period(historical: pd.DataFrame, period: str) -> list[dict[str, Any]]:
    if historical.empty:
        return []
    column = "month" if period == "M" else "year"
    counts = historical["event_dt"].dt.to_period(period).astype(str).value_counts().sort_index()
    return [{column: key, "historical_event_count": int(value)} for key, value in counts.items()]


def _setlist_decision(
    temporal: dict[str, Any],
    benchmark: dict[str, Any],
    candidate_distribution: dict[str, Any],
    folds: list[dict[str, Any]],
    useful_markets: int,
) -> dict[str, Any]:
    historical_depth_days = int(temporal.get("historical_depth_days") or 0)
    held_out = sum(int(fold["test_event_count"]) for fold in folds)
    checks = {
        "eligible_historical_bookings": {
            "actual": benchmark["eligible_historical_bookings"],
            "threshold": SETLIST_THRESHOLDS["eligible_historical_bookings"],
        },
        "held_out_test_bookings": {
            "actual": held_out,
            "threshold": SETLIST_THRESHOLDS["held_out_test_bookings"],
        },
        "useful_markets": {
            "actual": useful_markets,
            "threshold": SETLIST_THRESHOLDS["useful_markets"],
        },
        "mean_candidate_count": {
            "actual": candidate_distribution.get("mean") or 0,
            "threshold": SETLIST_THRESHOLDS["mean_candidate_count"],
        },
        "historical_depth_days": {
            "actual": historical_depth_days,
            "threshold": SETLIST_THRESHOLDS["historical_depth_days"],
        },
    }
    failed: list[str] = []
    for name, check in checks.items():
        check["passed"] = check["actual"] >= check["threshold"]
        if not check["passed"]:
            failed.append(name)
    decision = "SETLIST_NOT_NEEDED_YET" if not failed else "SETLIST_ENRICHMENT_RECOMMENDED"
    return {
        "decision": decision,
        "checks": checks,
        "failed_thresholds": failed,
        "explanation": (
            "Current history meets every suggested benchmark-readiness threshold."
            if not failed
            else "Historical enrichment is recommended because these thresholds failed: "
            + ", ".join(failed)
            + "."
        ),
    }


def build_historical_data_audit(
    frames: dict[str, pd.DataFrame],
    as_of: date | datetime | str | pd.Timestamp | None = None,
) -> dict[str, Any]:
    as_of_day = _as_utc_day(as_of)
    events = frames.get("events", pd.DataFrame()).copy()
    artists = frames.get("artists", pd.DataFrame()).copy()
    venues = frames.get("venues", pd.DataFrame()).copy()
    artist_genres = frames.get("artist_genres", pd.DataFrame()).copy()
    venue_history = frames.get("venue_genre_history", pd.DataFrame()).copy()
    enriched = _enrich_event_entities(events, artists, venues, as_of_day)
    historical = enriched.loc[enriched["temporal_class"] == "historical"].copy()
    future = enriched.loc[enriched["temporal_class"] == "current_or_future"].copy()
    missing = enriched.loc[enriched["temporal_class"] == "missing_date"].copy()

    eligibility = evaluate_benchmark_eligibility(events, artists, venues, as_of_day)
    eligible = eligibility.loc[eligibility.get("eligible", False)].copy() if not eligibility.empty else pd.DataFrame()
    eligible_5 = (
        eligibility.loc[eligibility.get("eligible_5_candidates", False)].copy()
        if not eligibility.empty
        else pd.DataFrame()
    )
    folds = recommend_temporal_folds(eligibility)
    target_markets = frames.get("target_markets")
    market_coverage = _market_coverage(enriched, venues, eligibility, target_markets)
    useful_markets = sum(bool(row["useful_for_temporal_benchmark"]) for row in market_coverage)
    artist_summary, artist_rows = _artist_coverage(artists, artist_genres, historical)
    venue_summary, venue_rows = _venue_coverage(venues, venue_history, historical)

    oldest = historical["event_dt"].min() if not historical.empty else None
    newest = historical["event_dt"].max() if not historical.empty else None
    depth_days = int((newest - oldest).days) if oldest is not None and newest is not None else 0
    temporal = {
        "total_event_relationships": int(len(enriched)),
        "historical_event_relationships": int(len(historical)),
        "current_or_future_event_relationships": int(len(future)),
        "missing_date_relationships": int(len(missing)),
        "oldest_historical_date": _iso_date(oldest),
        "newest_historical_date": _iso_date(newest),
        "historical_depth_days": depth_days,
        "distinct_historical_months": int(historical["event_dt"].dt.to_period("M").nunique()),
        "distinct_historical_years": int(historical["event_dt"].dt.year.nunique()),
        "events_by_month": _events_by_period(historical, "M"),
        "events_by_year": _events_by_period(historical, "Y"),
    }
    candidate_distribution = _distribution(
        eligible.get("candidate_count", pd.Series(dtype=float))
    )
    benchmark = {
        "total_historical_bookings": int(len(historical)),
        "eligible_historical_bookings": int(len(eligible)),
        "eligible_with_5_plus_candidates": int(len(eligible_5)),
        "eligible_unique_artists": int(eligible["artist_id"].nunique()) if not eligible.empty else 0,
        "eligible_unique_venues": int(eligible["venue_id"].nunique()) if not eligible.empty else 0,
        "eligible_markets": int(eligible["market"].nunique()) if not eligible.empty else 0,
        "useful_markets": useful_markets,
        "basic_eligibility_definition": (
            "Resolved historical relationship with a known market and at least one alternative venue "
            "in the same market that had been observed by the event date."
        ),
        "strict_eligibility_definition": (
            "Basic entity/date requirements with at least five total candidate venues, including the "
            "booked venue."
        ),
    }
    audit = {
        "metadata": {
            "audit_version": AUDIT_VERSION,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "as_of_utc_date": as_of_day.date().isoformat(),
            "relationship_unit": "artist-event-venue relationship",
            "read_only": True,
            "configured_target_markets": (
                int(len(target_markets)) if target_markets is not None else None
            ),
        },
        "temporal_coverage": temporal,
        "provider_coverage": _provider_coverage(enriched),
        "market_coverage": market_coverage,
        "artist_summary": artist_summary,
        "artist_history_coverage": artist_rows,
        "venue_summary": venue_summary,
        "venue_history_coverage": venue_rows,
        "entity_quality": _entity_quality(enriched, artists, venues, artist_genres),
        "benchmark_eligibility": benchmark,
        "candidate_set_distribution": candidate_distribution,
        "recommended_temporal_folds": folds,
    }
    audit["setlist_recommendation"] = _setlist_decision(
        temporal,
        benchmark,
        candidate_distribution,
        folds,
        useful_markets,
    )
    return audit


def run_historical_data_audit(
    db_target: DatabaseTarget = None,
    as_of: date | datetime | str | pd.Timestamp | None = None,
) -> dict[str, Any]:
    from src.ingestion.service import TARGET_CITIES

    frames = {
        "artists": repository.get_artists(db_target),
        "venues": repository.get_venues(db_target),
        "events": repository.get_events(db_target),
        "artist_genres": repository.get_artist_genres(db_target),
        "venue_genre_history": repository.get_venue_genre_history(db_target),
        "target_markets": pd.DataFrame(
            [{"city": target.city, "state": target.state} for target in TARGET_CITIES]
        ),
    }
    return build_historical_data_audit(frames, as_of)


def _markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_No rows available._"
    header = "| " + " | ".join(label for _, label in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, divider]
    for row in rows:
        values = [str(row.get(key, "")).replace("|", "\\|") for key, _ in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_markdown_report(audit: dict[str, Any]) -> str:
    temporal = audit["temporal_coverage"]
    benchmark = audit["benchmark_eligibility"]
    distribution = audit["candidate_set_distribution"]
    decision = audit["setlist_recommendation"]
    market_columns = [
        ("market", "Market"),
        ("is_target_market", "Target"),
        ("historical_event_count", "Historical"),
        ("future_event_count", "Future"),
        ("unique_artists", "Artists"),
        ("unique_venues", "Venues"),
        ("benchmark_eligible_count", "Eligible"),
        ("mean_candidate_count", "Mean candidates"),
        ("useful_for_temporal_benchmark", "Useful"),
    ]
    provider_columns = [
        ("provider", "Provider"),
        ("relationship_count", "Relationships"),
        ("historical_relationship_count", "Historical"),
        ("earliest_date", "Earliest"),
        ("latest_date", "Latest"),
        ("unique_artists", "Artists"),
        ("unique_venues", "Venues"),
        ("unique_markets", "Markets"),
    ]
    fold_columns = [
        ("fold", "Fold"),
        ("train_start", "Train start"),
        ("train_end", "Train end"),
        ("test_start", "Test start"),
        ("test_end", "Test end"),
        ("train_event_count", "Train events"),
        ("test_event_count", "Test events"),
        ("markets_represented", "Markets"),
    ]
    failed = ", ".join(decision["failed_thresholds"]) or "None"
    return f"""# VenueMatch Historical Data Audit

Generated: {audit['metadata']['generated_at_utc']}  
As-of date: {audit['metadata']['as_of_utc_date']}  
Unit: artist-event-venue relationship  
Mode: read-only

## Executive Summary

- Total relationships: **{temporal['total_event_relationships']:,}**
- Historical relationships: **{temporal['historical_event_relationships']:,}**
- Current/future relationships: **{temporal['current_or_future_event_relationships']:,}**
- Missing-date relationships: **{temporal['missing_date_relationships']:,}**
- Historical range: **{temporal['oldest_historical_date']}** through **{temporal['newest_historical_date']}**
- Benchmark-eligible historical bookings: **{benchmark['eligible_historical_bookings']:,}**
- Eligible with at least five candidates: **{benchmark['eligible_with_5_plus_candidates']:,}**
- Useful markets: **{benchmark['useful_markets']}**
- Median candidate count: **{distribution['median']}**
- Setlist.fm decision: **{decision['decision']}**
- Failed readiness thresholds: **{failed}**

## Temporal Coverage

- Historical depth: {temporal['historical_depth_days']:,} days
- Distinct months: {temporal['distinct_historical_months']}
- Distinct years: {temporal['distinct_historical_years']}

## Provider Coverage

{_markdown_table(audit['provider_coverage'], provider_columns)}

MusicBrainz enriches artist identity but is not stored as an event relationship source. The audit does not infer provider provenance that is absent from `events.source`.

## Market Coverage

{_markdown_table(audit['market_coverage'], market_columns)}

A useful market has at least 50 eligible relationships, six historical months, and a mean candidate set of at least five venues.

## Artist Coverage

```json
{json.dumps(audit['artist_summary'], indent=2)}
```

## Venue Coverage

```json
{json.dumps(audit['venue_summary'], indent=2)}
```

## Entity Quality

```json
{json.dumps(audit['entity_quality'], indent=2)}
```

## Benchmark Eligibility

```json
{json.dumps(benchmark, indent=2)}
```

Candidate counts include the booked venue. Basic eligibility requires at least one additional same-market venue with observed activity on or before the booking date. Genre, capacity, and artist history are deliberately excluded from candidate generation.

## Candidate-Set Distribution

```json
{json.dumps(distribution, indent=2)}
```

## Recommended Temporal Folds

{_markdown_table(audit['recommended_temporal_folds'], fold_columns)}

## Setlist.fm Recommendation

**{decision['decision']}**

{decision['explanation']}

```json
{json.dumps(decision['checks'], indent=2)}
```
"""


def write_audit_artifacts(audit: dict[str, Any], output_dir: str | Path) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    (output / "historical_data_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output / "historical_data_audit.md").write_text(
        render_markdown_report(audit), encoding="utf-8"
    )
    pd.DataFrame(audit["temporal_coverage"]["events_by_month"]).to_csv(
        output / "historical_events_by_month.csv", index=False
    )
    pd.DataFrame(audit["market_coverage"]).to_csv(
        output / "historical_events_by_market.csv", index=False
    )
    pd.DataFrame(audit["artist_history_coverage"]).to_csv(
        output / "artist_history_coverage.csv", index=False
    )
    pd.DataFrame(audit["venue_history_coverage"]).to_csv(
        output / "venue_history_coverage.csv", index=False
    )
    benchmark_rows = [
        {"metric": key, "value": value}
        for key, value in audit["benchmark_eligibility"].items()
        if not isinstance(value, (dict, list))
    ]
    benchmark_rows.extend(
        {"metric": f"candidate_{key}", "value": value}
        for key, value in audit["candidate_set_distribution"].items()
    )
    pd.DataFrame(benchmark_rows).to_csv(
        output / "benchmark_eligibility_summary.csv", index=False
    )
    (output / "recommended_temporal_folds.json").write_text(
        json.dumps(audit["recommended_temporal_folds"], indent=2), encoding="utf-8"
    )
    return output
