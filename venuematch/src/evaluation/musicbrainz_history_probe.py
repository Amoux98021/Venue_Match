from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

import pandas as pd

from src.clients.musicbrainz_client import MusicBrainzClient
from src.db import repository
from src.db.database import DatabaseTarget


MBID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
PROBE_SAMPLE_SIZE = 100
PLACE_SAMPLE_SIZE = 20
PLACE_CANDIDATE_SIZE = 50
MAX_EVENT_PAGES = 5
SUPPORTED_EVENT_TYPES = {"concert", "festival", "stage performance", ""}


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


def _iso_date(value: Any) -> str | None:
    if isinstance(value, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _stable_order(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def lookback_bucket(event_date: str | date, as_of: date) -> str | None:
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
    cleaned = [value for value in values if value]
    if not cleaned:
        return None
    counts = Counter(cleaned)
    return sorted(counts, key=lambda value: (-counts[value], value))[0]


def _provider_bias(ticketmaster_count: int, jambase_count: int, source: str | None) -> str:
    if ticketmaster_count > jambase_count:
        return "ticketmaster-heavy"
    if jambase_count > ticketmaster_count:
        return "jambase-heavy"
    source_value = (source or "").casefold()
    if "ticketmaster" in source_value and "jambase" not in source_value:
        return "ticketmaster-heavy"
    if "jambase" in source_value and "ticketmaster" not in source_value:
        return "jambase-heavy"
    return "balanced"


def _greedy_artist_sample(candidates: list[dict[str, Any]], sample_size: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    remaining = {row["id"]: row for row in candidates}
    counts: dict[str, Counter[str]] = {
        "market": Counter(),
        "history_band": Counter(),
        "provider_bias": Counter(),
        "primary_genre": Counter(),
    }
    while remaining and len(selected) < sample_size:
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for row in remaining.values():
            score = 0.0
            for field, weight in (
                ("market", 5.0),
                ("history_band", 3.0),
                ("provider_bias", 2.0),
                ("primary_genre", 1.0),
            ):
                value = row.get(field) or "unresolved"
                score += weight / (1 + counts[field][value])
            scored.append((score, _stable_order(row["id"]), row))
        _, _, chosen = max(scored, key=lambda item: (item[0], item[1]))
        selected.append(chosen)
        remaining.pop(chosen["id"])
        for field in counts:
            counts[field][chosen.get(field) or "unresolved"] += 1
    return selected


def build_musicbrainz_probe_input(
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

    event_rows = events.copy()
    event_rows["event_dt"] = pd.to_datetime(event_rows["event_date"], errors="coerce", utc=True)
    event_rows["event_dt"] = event_rows["event_dt"].dt.tz_convert(None)
    venue_markets = venues[["id", "city", "state"]].rename(
        columns={"id": "venue_lookup_id", "city": "venue_city", "state": "venue_state"}
    )
    event_rows = event_rows.merge(
        venue_markets,
        left_on="venue_id",
        right_on="venue_lookup_id",
        how="left",
    )
    event_rows["resolved_city"] = event_rows["city"].where(
        event_rows["city"].notna(), event_rows["venue_city"]
    )
    event_rows["resolved_state"] = event_rows["state"].where(
        event_rows["state"].notna(), event_rows["venue_state"]
    )
    event_rows["market"] = [
        _market(city, state)
        for city, state in zip(event_rows["resolved_city"], event_rows["resolved_state"])
    ]
    historical = event_rows.loc[
        event_rows["event_dt"].notna()
        & (event_rows["event_dt"].dt.date < reference_date)
    ].copy()

    genre_map = (
        genres.groupby("artist_id")["genre"].apply(lambda values: sorted(set(values))).to_dict()
        if not genres.empty
        else {}
    )
    artist_stats: dict[str, dict[str, Any]] = {}
    for artist_id, group in historical.groupby("artist_id"):
        sources = group["source"].fillna("").astype(str).str.casefold()
        markets = [str(value) for value in group["market"].dropna()]
        artist_stats[str(artist_id)] = {
            "history_count": int(len(group)),
            "ticketmaster_count": int(sources.str.contains("ticketmaster").sum()),
            "jambase_count": int(sources.str.contains("jambase").sum()),
            "market": _mode(markets),
            "markets": sorted(set(markets)),
        }

    mapped_artists = artists.loc[artists["musicbrainz_id"].map(valid_mbid)].copy()
    positive_history_counts = [
        artist_stats.get(str(row_id), {}).get("history_count", 0)
        for row_id in mapped_artists["id"]
        if artist_stats.get(str(row_id), {}).get("history_count", 0) > 0
    ]
    low_cut = (
        float(pd.Series(positive_history_counts).quantile(0.50))
        if positive_history_counts
        else 1.0
    )
    high_cut = (
        float(pd.Series(positive_history_counts).quantile(0.80))
        if positive_history_counts
        else 2.0
    )
    candidates: list[dict[str, Any]] = []
    for row in mapped_artists.to_dict("records"):
        stats = artist_stats.get(str(row["id"]), {})
        history_count = int(stats.get("history_count", 0))
        history_band = (
            "low"
            if history_count == 0
            else "high"
            if history_count >= high_cut
            else "medium"
        )
        artist_genres = genre_map.get(row["id"], [])
        candidates.append(
            {
                "id": row["id"],
                "name": row["name"],
                "musicbrainz_id": row["musicbrainz_id"],
                "data_source": _clean(row.get("data_source")),
                "history_count": history_count,
                "history_band": history_band,
                "ticketmaster_count": int(stats.get("ticketmaster_count", 0)),
                "jambase_count": int(stats.get("jambase_count", 0)),
                "provider_bias": _provider_bias(
                    int(stats.get("ticketmaster_count", 0)),
                    int(stats.get("jambase_count", 0)),
                    row.get("data_source"),
                ),
                "market": stats.get("market") or _market(row.get("home_city"), row.get("home_state")),
                "markets": stats.get("markets", []),
                "genres": artist_genres,
                "primary_genre": artist_genres[0] if artist_genres else "unknown",
            }
        )
    sample_artists = _greedy_artist_sample(candidates, min(sample_size, len(candidates)))

    venue_counts = historical.groupby("venue_id").size().to_dict()
    venue_candidates = []
    for row in venues.to_dict("records"):
        market = _market(row.get("city"), row.get("state"))
        if market:
            venue_candidates.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "city": row["city"],
                    "state": row["state"],
                    "market": market,
                    "history_count": int(venue_counts.get(row["id"], 0)),
                }
            )
    venue_candidates.sort(
        key=lambda row: (row["market"], -row["history_count"], _stable_order(row["id"]))
    )
    selected_venues: list[dict[str, Any]] = []
    seen_venue_ids: set[str] = set()
    for market in sorted({row["market"] for row in venue_candidates}):
        first = next(row for row in venue_candidates if row["market"] == market)
        selected_venues.append(first)
        seen_venue_ids.add(first["id"])
    for row in sorted(
        venue_candidates,
        key=lambda value: (-value["history_count"], _stable_order(value["id"])),
    ):
        if len(selected_venues) >= PLACE_CANDIDATE_SIZE:
            break
        if row["id"] not in seen_venue_ids:
            selected_venues.append(row)
            seen_venue_ids.add(row["id"])

    result = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "as_of": reference_date.isoformat(),
            "read_only": True,
            "sample_method": "deterministic greedy stratification",
        },
        "sample_artists": sample_artists,
        "venue_candidates": selected_venues,
        "artist_index": [
            {
                "id": row["id"],
                "name": row["name"],
                "musicbrainz_id": _clean(row.get("musicbrainz_id")),
            }
            for row in artists.to_dict("records")
        ],
        "venue_index": [
            {
                "id": row["id"],
                "name": row["name"],
                "city": row["city"],
                "state": row["state"],
            }
            for row in venues.to_dict("records")
        ],
        "existing_relationships": [
            {
                "artist_id": row["artist_id"],
                "venue_id": row["venue_id"],
                "event_date": _iso_date(row.get("event_date")),
                "source": _clean(row.get("source")),
                "external_id": _clean(row.get("external_id")),
            }
            for row in events.to_dict("records")
        ],
        "target_markets": [
            {"city": target.city, "state": target.state, "market": _market(target.city, target.state)}
            for target in TARGET_CITIES
        ],
        "counts": {
            "artists": int(len(artists)),
            "musicbrainz_mapped_artists": int(len(mapped_artists)),
            "venues": int(len(venues)),
            "relationships": int(len(events)),
        },
    }
    return result


def _area_names(area: Any) -> list[str]:
    names: list[str] = []
    current = area
    while isinstance(current, dict):
        name = _clean(current.get("name"))
        if name:
            names.append(name)
        current = current.get("area")
    return names


def resolve_place_search(
    venue: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    places = payload.get("places") or []
    if not isinstance(places, list):
        raise ValueError("MusicBrainz place search response is malformed")
    venue_name = normalize_entity(venue["name"])
    venue_city = normalize_entity(venue["city"])
    candidates: list[tuple[float, dict[str, Any]]] = []
    for place in places:
        if not isinstance(place, dict) or not valid_mbid(place.get("id")):
            continue
        place_name = normalize_entity(place.get("name"))
        area_names = [normalize_entity(value) for value in _area_names(place.get("area"))]
        same_area = any(
            venue_city == area or venue_city in area or area in venue_city
            for area in area_names
            if area
        )
        similarity = SequenceMatcher(None, venue_name, place_name).ratio()
        if same_area and (place_name == venue_name or similarity >= 0.90):
            candidates.append((1.0 if place_name == venue_name else similarity, place))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], str(item[1].get("id"))))
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None
    score, place = candidates[0]
    return {
        "venue_id": venue["id"],
        "venue_name": venue["name"],
        "city": venue["city"],
        "state": venue["state"],
        "market": venue["market"],
        "place_mbid": place["id"],
        "place_name": place.get("name"),
        "place_area": _area_names(place.get("area")),
        "match_quality": "exact" if score == 1.0 else "high",
    }


def _relation_attributes(relation: dict[str, Any]) -> set[str]:
    values = relation.get("attributes") or []
    return {normalize_entity(value) for value in values if value}


def normalize_musicbrainz_event(
    raw: dict[str, Any],
    queried_artist_mbids: set[str] | None = None,
) -> dict[str, Any] | None:
    event_mbid = raw.get("id")
    if not valid_mbid(event_mbid):
        return None
    life_span = raw.get("life-span") or {}
    begin = _iso_date(life_span.get("begin"))
    end = _iso_date(life_span.get("end"))
    performers: dict[str, dict[str, Any]] = {}
    place: dict[str, Any] | None = None
    for relation in raw.get("relations") or []:
        if not isinstance(relation, dict):
            continue
        artist = relation.get("artist")
        relation_type = normalize_entity(relation.get("type"))
        if isinstance(artist, dict) and valid_mbid(artist.get("id")) and "performer" in relation_type:
            performers[artist["id"]] = {
                "musicbrainz_id": artist["id"],
                "name": artist.get("name"),
                "relationship_type": relation.get("type"),
                "cancelled_appearance": "cancelled" in _relation_attributes(relation),
            }
        linked_place = relation.get("place")
        if isinstance(linked_place, dict) and valid_mbid(linked_place.get("id")):
            if relation_type == "held at" or place is None:
                place = {
                    "musicbrainz_id": linked_place["id"],
                    "name": linked_place.get("name"),
                    "areas": _area_names(linked_place.get("area")),
                }
    for artist_mbid in queried_artist_mbids or set():
        performers.setdefault(
            artist_mbid,
            {
                "musicbrainz_id": artist_mbid,
                "name": None,
                "relationship_type": "browse artist",
                "cancelled_appearance": False,
            },
        )
    return {
        "event_mbid": event_mbid,
        "name": raw.get("name"),
        "event_type": raw.get("type"),
        "begin_date": begin,
        "end_date": end,
        "cancelled": bool(raw.get("cancelled")),
        "performers": sorted(performers.values(), key=lambda row: row["musicbrainz_id"]),
        "place": place,
    }


def resolve_artist(
    performer: dict[str, Any],
    artist_by_mbid: dict[str, dict[str, Any]],
    artists_by_name: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    mbid = performer.get("musicbrainz_id")
    if mbid in artist_by_mbid:
        row = artist_by_mbid[mbid]
        return {"artist_id": row["id"], "artist_name": row["name"], "match_quality": "exact"}
    normalized_name = normalize_entity(performer.get("name"))
    matches = artists_by_name.get(normalized_name, [])
    if normalized_name and len(matches) == 1:
        return {
            "artist_id": matches[0]["id"],
            "artist_name": matches[0]["name"],
            "match_quality": "medium",
        }
    return {"artist_id": None, "artist_name": performer.get("name"), "match_quality": "unresolved"}


def resolve_venue(
    place: dict[str, Any] | None,
    place_mappings: dict[str, dict[str, Any]],
    venues: list[dict[str, Any]],
    target_markets: list[dict[str, Any]],
) -> dict[str, Any]:
    if not place:
        return {"venue_id": None, "market": None, "match_quality": "unresolved", "ambiguous": False}
    place_mbid = place.get("musicbrainz_id")
    if place_mbid in place_mappings:
        mapping = place_mappings[place_mbid]
        return {
            "venue_id": mapping["venue_id"],
            "venue_name": mapping["venue_name"],
            "market": mapping["market"],
            "match_quality": mapping["match_quality"],
            "ambiguous": False,
        }

    place_name = normalize_entity(place.get("name"))
    area_names = {normalize_entity(value) for value in place.get("areas", [])}
    market_candidates = [
        market
        for market in target_markets
        if normalize_entity(market["city"]) in area_names
        or any(normalize_entity(market["city"]) in area for area in area_names)
    ]
    candidate_venues = [
        venue
        for venue in venues
        if any(venue["market"] == market["market"] for market in market_candidates)
    ]
    exact = [venue for venue in candidate_venues if normalize_entity(venue["name"]) == place_name]
    if len(exact) == 1:
        return {
            "venue_id": exact[0]["id"],
            "venue_name": exact[0]["name"],
            "market": exact[0]["market"],
            "match_quality": "high",
            "ambiguous": False,
        }
    fuzzy = [
        (SequenceMatcher(None, place_name, normalize_entity(venue["name"])).ratio(), venue)
        for venue in candidate_venues
    ]
    fuzzy = sorted((item for item in fuzzy if item[0] >= 0.90), key=lambda item: -item[0])
    if fuzzy and (len(fuzzy) == 1 or fuzzy[0][0] > fuzzy[1][0]):
        return {
            "venue_id": fuzzy[0][1]["id"],
            "venue_name": fuzzy[0][1]["name"],
            "market": fuzzy[0][1]["market"],
            "match_quality": "medium",
            "ambiguous": False,
        }
    market = market_candidates[0]["market"] if len(market_candidates) == 1 else None
    return {
        "venue_id": None,
        "venue_name": place.get("name"),
        "market": market,
        "match_quality": "unresolved",
        "ambiguous": len(exact) > 1 or len(fuzzy) > 1,
    }


def classify_provider_overlap(
    relationship: dict[str, Any],
    existing_keys: dict[tuple[str, str, str], set[str]],
    existing_date_artist: dict[tuple[str, str], set[str]],
) -> tuple[str, list[str]]:
    event_date = relationship.get("event_date")
    artist_id = relationship.get("artist_id")
    venue_id = relationship.get("venue_id")
    if not event_date or not artist_id:
        return "ambiguous", []
    sources = sorted(existing_keys.get((event_date, artist_id, venue_id), set())) if venue_id else []
    if sources:
        return "already_known", sources
    if existing_date_artist.get((event_date, artist_id)):
        return "likely_duplicate", []
    if relationship.get("artist_match_quality") == "unresolved" or relationship.get(
        "venue_match_quality"
    ) in {"unresolved", "medium"}:
        return "ambiguous", []
    return "musicbrainz_only", []


def _collect_pages(
    pages: Any,
    raw_events: dict[str, dict[str, Any]],
    discovery: dict[str, set[str]],
    discovery_key: str,
) -> tuple[int, bool]:
    page_count = 0
    truncated = False
    for payload in pages:
        page_count += 1
        rows = payload.get("events", [])
        for row in rows:
            event_id = row.get("id")
            if valid_mbid(event_id):
                current = raw_events.get(event_id)
                if current is None or len(row.get("relations") or []) > len(current.get("relations") or []):
                    raw_events[event_id] = row
                discovery[event_id].add(discovery_key)
        total = int(payload.get("event-count") or 0)
        offset = int(payload.get("event-offset") or 0)
        if page_count >= MAX_EVENT_PAGES and offset + len(rows) < total:
            truncated = True
    return page_count, truncated


def run_musicbrainz_history_probe(
    snapshot: dict[str, Any],
    client: MusicBrainzClient | None = None,
) -> dict[str, Any]:
    probe_client = client or MusicBrainzClient()
    as_of = date.fromisoformat(snapshot["metadata"]["as_of"])
    sample_artists = snapshot["sample_artists"]
    venues = [
        {**row, "market": _market(row["city"], row["state"])} for row in snapshot["venue_index"]
    ]
    target_markets = snapshot["target_markets"]
    artist_by_mbid = {
        row["musicbrainz_id"]: row
        for row in snapshot["artist_index"]
        if valid_mbid(row.get("musicbrainz_id"))
    }
    artists_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in snapshot["artist_index"]:
        artists_by_name[normalize_entity(row["name"])].append(row)

    raw_events: dict[str, dict[str, Any]] = {}
    discovery: dict[str, set[str]] = defaultdict(set)
    artist_results: list[dict[str, Any]] = []
    artist_phase_start = probe_client.request_count
    for artist in sample_artists:
        before = probe_client.request_count
        error: str | None = None
        page_count = 0
        truncated = False
        try:
            page_count, truncated = _collect_pages(
                probe_client.iter_artist_event_pages(
                    artist["musicbrainz_id"], max_pages=MAX_EVENT_PAGES
                ),
                raw_events,
                discovery,
                f'artist:{artist["musicbrainz_id"]}',
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
        artist_results.append(
            {
                **artist,
                "queried": error is None,
                "api_requests": probe_client.request_count - before,
                "pages": page_count,
                "truncated": truncated,
                "error": error,
            }
        )
    artist_api_requests = probe_client.request_count - artist_phase_start

    place_mappings: list[dict[str, Any]] = []
    place_search_start = probe_client.request_count
    for venue in snapshot["venue_candidates"]:
        if len(place_mappings) >= PLACE_SAMPLE_SIZE:
            break
        try:
            payload = probe_client.search_place(venue["name"], venue["city"], limit=10)
            mapping = resolve_place_search(venue, payload)
            if mapping:
                place_mappings.append(mapping)
        except Exception:
            continue
    place_search_requests = probe_client.request_count - place_search_start
    mappings_by_place = {row["place_mbid"]: row for row in place_mappings}

    place_event_start = probe_client.request_count
    place_probe_rows: list[dict[str, Any]] = []
    for mapping in place_mappings:
        before = probe_client.request_count
        error = None
        page_count = 0
        truncated = False
        try:
            page_count, truncated = _collect_pages(
                probe_client.iter_place_event_pages(
                    mapping["place_mbid"], max_pages=MAX_EVENT_PAGES
                ),
                raw_events,
                discovery,
                f'place:{mapping["place_mbid"]}',
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
        place_probe_rows.append(
            {
                **mapping,
                "api_requests": probe_client.request_count - before,
                "pages": page_count,
                "truncated": truncated,
                "error": error,
            }
        )
    place_event_requests = probe_client.request_count - place_event_start

    normalized_events: list[dict[str, Any]] = []
    for event_mbid, raw in raw_events.items():
        queried_mbids = {
            value.split(":", 1)[1]
            for value in discovery[event_mbid]
            if value.startswith("artist:")
        }
        normalized = normalize_musicbrainz_event(raw, queried_mbids)
        if normalized:
            normalized["discovered_by"] = sorted(discovery[event_mbid])
            normalized_events.append(normalized)

    existing_keys: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    existing_date_artist: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in snapshot["existing_relationships"]:
        if row.get("event_date") and row.get("artist_id") and row.get("venue_id"):
            key = (row["event_date"], row["artist_id"], row["venue_id"])
            existing_keys[key].add(row.get("source") or "unknown")
            existing_date_artist[(row["event_date"], row["artist_id"])].add(row["venue_id"])

    relationships: list[dict[str, Any]] = []
    for event in normalized_events:
        event_date = event.get("begin_date")
        bucket = lookback_bucket(event_date, as_of) if event_date else None
        venue_match = resolve_venue(event.get("place"), mappings_by_place, venues, target_markets)
        for performer in event["performers"]:
            artist_match = resolve_artist(performer, artist_by_mbid, artists_by_name)
            relationship = {
                "event_mbid": event["event_mbid"],
                "event_name": event.get("name"),
                "event_type": event.get("event_type"),
                "event_date": event_date,
                "lookback_bucket": bucket,
                "cancelled": event["cancelled"] or performer["cancelled_appearance"],
                "performer_mbid": performer["musicbrainz_id"],
                "performer_name": performer.get("name") or artist_match.get("artist_name"),
                "artist_id": artist_match["artist_id"],
                "artist_match_quality": artist_match["match_quality"],
                "place_mbid": (event.get("place") or {}).get("musicbrainz_id"),
                "place_name": (event.get("place") or {}).get("name"),
                "venue_id": venue_match.get("venue_id"),
                "venue_name": venue_match.get("venue_name"),
                "venue_match_quality": venue_match["match_quality"],
                "venue_ambiguous": venue_match.get("ambiguous", False),
                "market": venue_match.get("market"),
                "discovered_by": event["discovered_by"],
            }
            event_type = normalize_entity(event.get("event_type"))
            relationship["usable_historical"] = bool(
                event_date
                and date.fromisoformat(event_date) < as_of
                and not relationship["cancelled"]
                and event_type in SUPPORTED_EVENT_TYPES
            )
            overlap, sources = classify_provider_overlap(
                relationship, existing_keys, existing_date_artist
            )
            relationship["provider_overlap"] = overlap
            relationship["existing_sources"] = sources
            relationships.append(relationship)

    relationship_keys: set[tuple[Any, ...]] = set()
    deduped_relationships: list[dict[str, Any]] = []
    for row in relationships:
        key = (
            row["event_mbid"],
            row.get("artist_id") or row["performer_mbid"],
            row.get("venue_id") or row.get("place_mbid"),
            row.get("event_date"),
        )
        if key not in relationship_keys:
            relationship_keys.add(key)
            deduped_relationships.append(row)
    relationships = deduped_relationships

    historical_events = [
        row
        for row in normalized_events
        if row.get("begin_date") and date.fromisoformat(row["begin_date"]) < as_of
    ]
    usable = [row for row in relationships if row["usable_historical"]]
    additional = [row for row in usable if row["provider_overlap"] == "musicbrainz_only"]
    current_markets = {row["market"] for row in target_markets}
    events_in_markets = {
        row["event_mbid"] for row in usable if row.get("market") in current_markets
    }
    bucket_counts = Counter(
        row["lookback_bucket"] for row in usable if row.get("lookback_bucket")
    )

    queried_artist_events: dict[str, set[str]] = defaultdict(set)
    queried_artist_market_events: dict[str, set[str]] = defaultdict(set)
    for row in usable:
        for source in row["discovered_by"]:
            if source.startswith("artist:"):
                mbid = source.split(":", 1)[1]
                queried_artist_events[mbid].add(row["event_mbid"])
                if row.get("market") in current_markets:
                    queried_artist_market_events[mbid].add(row["event_mbid"])
    for row in artist_results:
        mbid = row["musicbrainz_id"]
        row["historical_events_found"] = len(queried_artist_events[mbid])
        row["events_in_current_markets"] = len(queried_artist_market_events[mbid])

    market_rows: list[dict[str, Any]] = []
    for market in sorted(current_markets):
        rows = [row for row in additional if row.get("market") == market]
        if not rows:
            continue
        dates = sorted(row["event_date"] for row in rows if row.get("event_date"))
        resolved = [row for row in rows if row["venue_match_quality"] in {"exact", "high"}]
        market_rows.append(
            {
                "market": market,
                "additional_relationships": len(rows),
                "additional_events": len({row["event_mbid"] for row in rows}),
                "unique_artists": len({row["artist_id"] for row in rows if row.get("artist_id")}),
                "unique_resolved_venues": len(
                    {row["venue_id"] for row in rows if row.get("venue_id")}
                ),
                "oldest_event_date": dates[0] if dates else None,
                "newest_event_date": dates[-1] if dates else None,
                "months_of_temporal_depth": (
                    round((as_of - date.fromisoformat(dates[0])).days / 30.44, 1)
                    if dates
                    else 0.0
                ),
                "exact_high_venue_resolution_rate": (
                    round(len(resolved) / len(rows), 4) if rows else 0.0
                ),
            }
        )

    overlap_counts = Counter(row["provider_overlap"] for row in usable)
    overlap_rows = [
        {"category": category, "relationship_count": overlap_counts.get(category, 0)}
        for category in ("already_known", "musicbrainz_only", "likely_duplicate", "ambiguous")
    ]
    source_overlap = Counter(
        source
        for row in usable
        for source in row.get("existing_sources", [])
    )
    overlap_rows.extend(
        {"category": f"already_known_{source}", "relationship_count": count}
        for source, count in sorted(source_overlap.items())
    )

    successful_artists = sum(bool(row["queried"]) for row in artist_results)
    mapped_artist_count = int(snapshot["counts"]["musicbrainz_mapped_artists"])
    avg_artist_calls = artist_api_requests / successful_artists if successful_artists else 1.0
    projected_artist_calls = round(mapped_artist_count * avg_artist_calls)
    projected_additional = round(
        len(additional) * mapped_artist_count / successful_artists
    ) if successful_artists else 0
    projected_recent = round(
        sum(row["lookback_bucket"] == "0-3 months" for row in additional)
        * mapped_artist_count
        / successful_artists
    ) if successful_artists else 0
    markets_6 = sum(row["months_of_temporal_depth"] >= 6 for row in market_rows)
    markets_12 = sum(row["months_of_temporal_depth"] >= 12 for row in market_rows)
    venue_resolution_rate = (
        sum(row["venue_match_quality"] in {"exact", "high"} for row in usable) / len(usable)
        if usable
        else 0.0
    )
    oldest = min((row["begin_date"] for row in historical_events if row.get("begin_date")), default=None)
    projection = {
        "eligible_musicbrainz_mapped_artists": mapped_artist_count,
        "sample_successful_artists": successful_artists,
        "average_artist_api_requests": round(avg_artist_calls, 3),
        "artist_backfill_api_call_estimate": projected_artist_calls,
        "optional_place_search_and_event_calls": round(
            snapshot["counts"]["venues"]
            + snapshot["counts"]["venues"]
            * (place_event_requests / len(place_mappings) if place_mappings else 0)
        ),
        "runtime_seconds_at_rate_limit": round(projected_artist_calls * probe_client.minimum_interval),
        "runtime_hours_at_rate_limit": round(
            projected_artist_calls * probe_client.minimum_interval / 3600, 2
        ),
        "projected_additional_historical_relationships": projected_additional,
        "projected_0_3_month_relationships": projected_recent,
        "expected_oldest_event_date": oldest,
        "expected_markets_with_6_months": markets_6,
        "expected_markets_with_12_months": markets_12,
        "projection_note": "Market projections are conservative lower bounds from observed sample markets.",
    }
    total_after = len(
        [
            row
            for row in snapshot["existing_relationships"]
            if row.get("event_date") and date.fromisoformat(row["event_date"]) < as_of
        ]
    ) + projected_additional
    checks = {
        "usable_relationships_after_enrichment": total_after >= 5_000,
        "future_held_out_examples": projected_recent >= 1_000,
        "markets_with_6_months": markets_6 >= 4,
        "markets_with_12_months_preferred": markets_12 >= 4,
        "venue_resolution_quality": venue_resolution_rate >= 0.60,
    }
    if all(
        checks[key]
        for key in (
            "usable_relationships_after_enrichment",
            "future_held_out_examples",
            "markets_with_6_months",
            "venue_resolution_quality",
        )
    ):
        decision = "MUSICBRAINZ_BACKFILL_RECOMMENDED"
    elif len(additional) >= 25 or projected_additional >= 500 or markets_6 > 0:
        decision = "MUSICBRAINZ_PARTIAL_ENRICHMENT_ONLY"
    else:
        decision = "MUSICBRAINZ_HISTORY_INSUFFICIENT"

    summary = {
        "artists_sampled": len(sample_artists),
        "artists_successfully_queried": successful_artists,
        "artists_with_historical_events": sum(
            row["historical_events_found"] > 0 for row in artist_results
        ),
        "artists_with_events_in_current_markets": sum(
            row["events_in_current_markets"] > 0 for row in artist_results
        ),
        "venues_places_mapped": len(place_mappings),
        "total_historical_events_returned": len(historical_events),
        "unique_historical_events": len({row["event_mbid"] for row in historical_events}),
        "events_in_current_markets": len(events_in_markets),
        "relationships_resolving_to_existing_artists": sum(
            bool(row.get("artist_id")) for row in usable
        ),
        "relationships_resolving_to_existing_venues": sum(
            bool(row.get("venue_id")) for row in usable
        ),
        "relationships_already_present": overlap_counts.get("already_known", 0),
        "additional_historical_relationships": len(additional),
        "likely_duplicate_relationships": overlap_counts.get("likely_duplicate", 0),
        "ambiguous_relationships": overlap_counts.get("ambiguous", 0),
        "cancelled_relationships_excluded": sum(row["cancelled"] for row in relationships),
        "oldest_historical_event": oldest,
        "newest_historical_event": max(
            (row["begin_date"] for row in historical_events if row.get("begin_date")),
            default=None,
        ),
        "lookback_counts": {
            label: bucket_counts.get(label, 0)
            for label in (
                "0-3 months",
                "3-6 months",
                "6-12 months",
                "12-24 months",
                "24+ months",
            )
        },
        "venue_resolution_success_rate": round(venue_resolution_rate, 4),
        "markets_with_6_months": markets_6,
        "markets_with_12_months": markets_12,
    }
    result = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "as_of": as_of.isoformat(),
            "read_only": True,
            "max_event_pages_per_entity": MAX_EVENT_PAGES,
            "minimum_request_interval_seconds": probe_client.minimum_interval,
        },
        "api_requests_used": probe_client.request_count,
        "request_breakdown": {
            "artist_events": artist_api_requests,
            "place_search": place_search_requests,
            "place_events": place_event_requests,
        },
        "summary": summary,
        "artist_probe_results": artist_results,
        "place_probe_results": place_probe_rows,
        "market_probe_results": market_rows,
        "provider_overlap_summary": overlap_rows,
        "projected_backfill": projection,
        "decision_checks": checks,
        "decision": decision,
        "setlist_fm_still_needed": decision != "MUSICBRAINZ_BACKFILL_RECOMMENDED",
        "normalized_events": normalized_events,
    }
    return refine_musicbrainz_probe_metrics(result, snapshot)


def refine_musicbrainz_probe_metrics(
    result: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Recompute reporting metrics from cached normalized events without API access."""
    as_of = date.fromisoformat(result["metadata"]["as_of"])
    venues = [
        {**row, "market": _market(row["city"], row["state"])}
        for row in snapshot["venue_index"]
    ]
    target_markets = snapshot["target_markets"]
    current_markets = {row["market"] for row in target_markets}
    artist_by_mbid = {
        row["musicbrainz_id"]: row
        for row in snapshot["artist_index"]
        if valid_mbid(row.get("musicbrainz_id"))
    }
    artists_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in snapshot["artist_index"]:
        artists_by_name[normalize_entity(row["name"])].append(row)
    place_mappings = {
        row["place_mbid"]: row
        for row in result.get("place_probe_results", [])
        if row.get("place_mbid") and not row.get("error")
    }

    existing_keys: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    existing_date_artist: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in snapshot["existing_relationships"]:
        if row.get("event_date") and row.get("artist_id") and row.get("venue_id"):
            existing_keys[(row["event_date"], row["artist_id"], row["venue_id"])].add(
                row.get("source") or "unknown"
            )
            existing_date_artist[(row["event_date"], row["artist_id"])].add(row["venue_id"])

    relationships: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for event in result["normalized_events"]:
        event_date = event.get("begin_date")
        bucket = lookback_bucket(event_date, as_of) if event_date else None
        venue_match = resolve_venue(event.get("place"), place_mappings, venues, target_markets)
        for performer in event["performers"]:
            artist_match = resolve_artist(performer, artist_by_mbid, artists_by_name)
            row = {
                "event_mbid": event["event_mbid"],
                "event_date": event_date,
                "lookback_bucket": bucket,
                "artist_id": artist_match["artist_id"],
                "artist_match_quality": artist_match["match_quality"],
                "performer_mbid": performer["musicbrainz_id"],
                "venue_id": venue_match.get("venue_id"),
                "venue_match_quality": venue_match["match_quality"],
                "place_mbid": (event.get("place") or {}).get("musicbrainz_id"),
                "market": venue_match.get("market"),
                "cancelled": event["cancelled"] or performer["cancelled_appearance"],
            }
            event_type = normalize_entity(event.get("event_type"))
            row["usable_historical"] = bool(
                event_date
                and date.fromisoformat(event_date) < as_of
                and not row["cancelled"]
                and event_type in SUPPORTED_EVENT_TYPES
            )
            overlap, sources = classify_provider_overlap(
                row, existing_keys, existing_date_artist
            )
            row["provider_overlap"] = overlap
            row["existing_sources"] = sources
            key = (
                row["event_mbid"],
                row.get("artist_id") or row["performer_mbid"],
                row.get("venue_id") or row.get("place_mbid"),
                row.get("event_date"),
            )
            if key not in seen:
                seen.add(key)
                relationships.append(row)

    usable = [row for row in relationships if row["usable_historical"]]
    additional = [row for row in usable if row["provider_overlap"] == "musicbrainz_only"]
    relationship_bucket_counts = Counter(
        row["lookback_bucket"] for row in usable if row.get("lookback_bucket")
    )
    event_buckets: dict[str, set[str]] = defaultdict(set)
    for row in usable:
        if row.get("lookback_bucket"):
            event_buckets[row["lookback_bucket"]].add(row["event_mbid"])
    bucket_labels = (
        "0-3 months",
        "3-6 months",
        "6-12 months",
        "12-24 months",
        "24+ months",
    )

    market_rows: list[dict[str, Any]] = []
    for market in sorted(current_markets):
        market_usable = [row for row in usable if row.get("market") == market]
        market_additional = [row for row in additional if row.get("market") == market]
        if not market_usable:
            continue
        dates = sorted(
            row["event_date"] for row in market_additional if row.get("event_date")
        )
        resolved = [
            row
            for row in market_usable
            if row["venue_match_quality"] in {"exact", "high"}
        ]
        market_rows.append(
            {
                "market": market,
                "additional_relationships": len(market_additional),
                "additional_events": len(
                    {row["event_mbid"] for row in market_additional}
                ),
                "unique_artists": len(
                    {row["artist_id"] for row in market_additional if row.get("artist_id")}
                ),
                "unique_resolved_venues": len(
                    {row["venue_id"] for row in market_additional if row.get("venue_id")}
                ),
                "oldest_event_date": dates[0] if dates else None,
                "newest_event_date": dates[-1] if dates else None,
                "months_of_temporal_depth": (
                    round((as_of - date.fromisoformat(dates[0])).days / 30.44, 1)
                    if dates
                    else 0.0
                ),
                "exact_high_venue_resolution_rate": round(
                    len(resolved) / len(market_usable), 4
                ),
            }
        )

    overlap_rows = []
    for category in ("already_known", "musicbrainz_only", "likely_duplicate", "ambiguous"):
        rows = [row for row in usable if row["provider_overlap"] == category]
        overlap_rows.append(
            {
                "category": category,
                "event_count": len({row["event_mbid"] for row in rows}),
                "relationship_count": len(rows),
            }
        )
    for source in sorted(
        {source for row in usable for source in row.get("existing_sources", [])}
    ):
        rows = [row for row in usable if source in row.get("existing_sources", [])]
        overlap_rows.append(
            {
                "category": f"already_known_{source}",
                "event_count": len({row["event_mbid"] for row in rows}),
                "relationship_count": len(rows),
            }
        )

    summary = result["summary"]
    summary["lookback_counts"] = {
        label: len(event_buckets[label]) for label in bucket_labels
    }
    summary["lookback_event_counts"] = dict(summary["lookback_counts"])
    summary["lookback_relationship_counts"] = {
        label: relationship_bucket_counts[label] for label in bucket_labels
    }
    summary["events_resolving_to_existing_artists"] = len(
        {row["event_mbid"] for row in usable if row.get("artist_id")}
    )
    summary["events_resolving_to_existing_venues"] = len(
        {row["event_mbid"] for row in usable if row.get("venue_id")}
    )
    summary["events_matching_existing_relationships"] = len(
        {
            row["event_mbid"]
            for row in usable
            if row["provider_overlap"] == "already_known"
        }
    )
    current_market_relationships = [
        row for row in usable if row.get("market") in current_markets
    ]
    summary["current_market_venue_resolution_success_rate"] = round(
        sum(
            row["venue_match_quality"] in {"exact", "high"}
            for row in current_market_relationships
        )
        / len(current_market_relationships),
        4,
    ) if current_market_relationships else 0.0
    summary["events_older_than_6_months"] = sum(
        len(event_buckets[label])
        for label in ("6-12 months", "12-24 months", "24+ months")
    )
    summary["events_older_than_12_months"] = sum(
        len(event_buckets[label]) for label in ("12-24 months", "24+ months")
    )
    summary["artist_resolution_quality"] = dict(
        sorted(Counter(row["artist_match_quality"] for row in usable).items())
    )
    summary["venue_resolution_quality"] = dict(
        sorted(Counter(row["venue_match_quality"] for row in usable).items())
    )
    summary["markets_with_6_months"] = sum(
        row["months_of_temporal_depth"] >= 6 for row in market_rows
    )
    summary["markets_with_12_months"] = sum(
        row["months_of_temporal_depth"] >= 12 for row in market_rows
    )
    result["market_probe_results"] = market_rows
    result["provider_overlap_summary"] = overlap_rows
    result["sample_profile"] = {
        "history_bands": dict(
            sorted(Counter(row["history_band"] for row in result["artist_probe_results"]).items())
        ),
        "provider_bias": dict(
            sorted(Counter(row["provider_bias"] for row in result["artist_probe_results"]).items())
        ),
        "represented_artist_markets": len(
            {row["market"] for row in result["artist_probe_results"] if row.get("market")}
        ),
        "represented_primary_genres": len(
            {row["primary_genre"] for row in result["artist_probe_results"]}
        ),
        "mapped_place_markets": len(
            {row["market"] for row in result.get("place_probe_results", []) if row.get("market")}
        ),
    }
    artist_calls = int(result["projected_backfill"]["artist_backfill_api_call_estimate"])
    venue_search_calls = int(snapshot["counts"]["venues"])
    place_probe_rows = result.get("place_probe_results", [])
    average_place_event_calls = (
        sum(row.get("api_requests", 0) for row in place_probe_rows) / len(place_probe_rows)
        if place_probe_rows
        else 1.0
    )
    optional_place_event_calls = round(venue_search_calls * average_place_event_calls)
    recommended_calls = artist_calls + venue_search_calls
    expanded_calls = recommended_calls + optional_place_event_calls
    result["projected_backfill"].update(
        {
            "venue_place_mapping_search_calls": venue_search_calls,
            "optional_venue_event_calls": optional_place_event_calls,
            "artist_plus_place_mapping_call_estimate": recommended_calls,
            "artist_plus_mapping_and_venue_event_call_estimate": expanded_calls,
            "artist_plus_place_mapping_runtime_minutes": round(
                recommended_calls * result["metadata"]["minimum_request_interval_seconds"] / 60,
                1,
            ),
            "expanded_runtime_minutes": round(
                expanded_calls * result["metadata"]["minimum_request_interval_seconds"] / 60,
                1,
            ),
        }
    )
    result["projected_backfill"].pop("optional_place_search_and_event_calls", None)
    result["decision_checks"]["venue_resolution_quality"] = (
        summary["current_market_venue_resolution_success_rate"] >= 0.60
    )
    result["projected_backfill"]["expected_markets_with_6_months"] = summary[
        "markets_with_6_months"
    ]
    result["projected_backfill"]["expected_markets_with_12_months"] = summary[
        "markets_with_12_months"
    ]
    return result


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows available._"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(row.get(column, "")).replace("|", "\\|") for column in columns)
            + " |"
        )
    return "\n".join(lines)


def render_musicbrainz_probe_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    projection = result["projected_backfill"]
    return f"""# VenueMatch MusicBrainz Historical Coverage Probe

Generated: {result['metadata']['generated_at_utc']}  
As-of date: {result['metadata']['as_of']}  
Mode: read-only; no production event writes

## Decision

**{result['decision']}**

Setlist.fm still needed before the final historical benchmark: **{result['setlist_fm_still_needed']}**

## Coverage Summary

- API requests used: **{result['api_requests_used']:,}**
- Request breakdown: **{result['request_breakdown']['artist_events']} artist-event / {result['request_breakdown']['place_search']} place-search / {result['request_breakdown']['place_events']} place-event**
- Artists sampled / successfully queried: **{summary['artists_sampled']} / {summary['artists_successfully_queried']}**
- Artists with historical events: **{summary['artists_with_historical_events']}**
- MusicBrainz places mapped: **{summary['venues_places_mapped']}**
- Unique historical events: **{summary['unique_historical_events']:,}**
- Events in current markets: **{summary['events_in_current_markets']:,}**
- Events resolving to existing artists / venues: **{summary['events_resolving_to_existing_artists']:,} / {summary['events_resolving_to_existing_venues']:,}**
- Already-known / MusicBrainz-only events: **{summary['events_matching_existing_relationships']:,} / {next(row['event_count'] for row in result['provider_overlap_summary'] if row['category'] == 'musicbrainz_only'):,}**
- Additional historical relationships: **{summary['additional_historical_relationships']:,}**
- Oldest / newest: **{summary['oldest_historical_event']} / {summary['newest_historical_event']}**
- Venue-resolution success rate: **{summary['venue_resolution_success_rate']:.1%}**
- Current-market venue-resolution success rate: **{summary['current_market_venue_resolution_success_rate']:.1%}**
- Markets with at least 6 months: **{summary['markets_with_6_months']}**
- Markets with at least 12 months: **{summary['markets_with_12_months']}**
- Events older than 6 months / 12 months: **{summary['events_older_than_6_months']:,} / {summary['events_older_than_12_months']:,}**

## Sample Profile

```json
{json.dumps(result['sample_profile'], indent=2)}
```

## Entity Resolution

```json
{json.dumps({'artist': summary['artist_resolution_quality'], 'venue': summary['venue_resolution_quality']}, indent=2)}
```

## Lookback Counts

```json
{json.dumps(summary['lookback_event_counts'], indent=2)}
```

## Market Results

{_markdown_table(result['market_probe_results'], ['market', 'additional_events', 'additional_relationships', 'unique_artists', 'unique_resolved_venues', 'oldest_event_date', 'months_of_temporal_depth', 'exact_high_venue_resolution_rate'])}

## Provider Overlap

{_markdown_table(result['provider_overlap_summary'], ['category', 'event_count', 'relationship_count'])}

## Projected Full Backfill

```json
{json.dumps(projection, indent=2)}
```

## Decision Checks

```json
{json.dumps(result['decision_checks'], indent=2)}
```

## Recommended Next Action

Use MusicBrainz as a partial historical enrichment source after expanding place mappings, but do not rely on it as the sole benchmark source. The all-artist projection adds approximately **{projection['projected_additional_historical_relationships']:,}** usable relationships and only **{projection['projected_0_3_month_relationships']:,}** recent held-out relationships, which is below the benchmark target. Proceed with Setlist.fm enrichment before the final historical recommendation benchmark.
"""


def public_musicbrainz_probe_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in (
            "metadata",
            "api_requests_used",
            "request_breakdown",
            "summary",
            "sample_profile",
            "market_probe_results",
            "provider_overlap_summary",
            "projected_backfill",
            "decision_checks",
            "decision",
            "setlist_fm_still_needed",
        )
    }


def write_musicbrainz_probe_artifacts(
    result: dict[str, Any],
    output_dir: str | Path,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    aggregate_result = public_musicbrainz_probe_result(result)
    (output / "musicbrainz_history_probe.json").write_text(
        json.dumps(aggregate_result, indent=2, sort_keys=True), encoding="utf-8"
    )
    (output / "musicbrainz_history_probe.md").write_text(
        render_musicbrainz_probe_report(result), encoding="utf-8"
    )
    pd.DataFrame(result["artist_probe_results"]).to_csv(
        output / "artist_probe_results.csv", index=False
    )
    pd.DataFrame(result["market_probe_results"]).to_csv(
        output / "market_probe_results.csv", index=False
    )
    pd.DataFrame(result["provider_overlap_summary"]).to_csv(
        output / "provider_overlap_summary.csv", index=False
    )
    (output / "projected_backfill.json").write_text(
        json.dumps(result["projected_backfill"], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output
