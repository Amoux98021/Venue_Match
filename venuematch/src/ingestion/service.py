from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import json
from math import log10
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection

from src.clients.census_client import CensusClient
from src.clients.lastfm_client import LastFMClient
from src.clients.musicbrainz_client import MusicBrainzClient
from src.clients.ticketmaster_client import TicketmasterClient
from src.db.database import DatabaseTarget, get_connection, initialize_database
from src.db.schema import (
    TABLES,
    artist_genres,
    artists,
    city_demographics,
    city_genre_signals,
    events,
    ingestion_runs,
    recommendations,
    venue_genre_history,
    venues,
)
from src.db.seed import DELETE_ORDER
from src.utils.config import credentials_available


@dataclass(frozen=True)
class CityTarget:
    city: str
    state: str
    state_fips: str
    place_fips: str


TARGET_CITIES = (
    CityTarget("Washington", "DC", "11", "50000"),
    CityTarget("Baltimore", "MD", "24", "04000"),
    CityTarget("Philadelphia", "PA", "42", "60000"),
    CityTarget("New York", "NY", "36", "51000"),
    CityTarget("College Park", "MD", "24", "18750"),
)

EVENT_LOOKAHEAD_DAYS = 180
EVENT_RETENTION_DAYS = 365
EVENTS_PER_CITY = 75
LASTFM_ARTISTS_PER_RUN = 8
MUSICBRAINZ_ARTISTS_PER_RUN = 3


@dataclass
class IngestionClients:
    ticketmaster: Any
    lastfm: Any
    musicbrainz: Any
    census: Any


@dataclass
class IngestionResult:
    status: str
    artists_upserted: int
    venues_upserted: int
    events_upserted: int
    cities_updated: int
    artist_genres_upserted: int
    provider_errors: list[str]
    sample_data_removed: bool
    started_at: str
    completed_at: str


def _default_clients() -> IngestionClients:
    return IngestionClients(
        ticketmaster=TicketmasterClient(),
        lastfm=LastFMClient(),
        musicbrainz=MusicBrainzClient(),
        census=CensusClient(),
    )


def _stable_id(prefix: str, *parts: str) -> str:
    normalized = "|".join(part.strip().casefold() for part in parts)
    return f"{prefix}_{uuid5(NAMESPACE_URL, normalized).hex}"


def _clean_genre(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.strip().lower().split())
    if not cleaned or cleaned in {"undefined", "music", "other"}:
        return None
    return cleaned


def _classification_genres(payload: dict[str, Any]) -> set[str]:
    genres: set[str] = set()
    for classification in payload.get("classifications", []) or []:
        for key in ("genre", "subGenre"):
            genre = _clean_genre((classification.get(key) or {}).get("name"))
            if genre:
                genres.add(genre)
    return genres


def _number(value: Any, caster: type[int] | type[float]) -> int | float | None:
    try:
        parsed = caster(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_provider_error(provider: str, error: Exception) -> str:
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    api_code = None
    if response is not None:
        try:
            api_code = response.json().get("error")
        except (AttributeError, TypeError, ValueError):
            pass
    suffix = f" HTTP {status_code}" if status_code else f" {type(error).__name__}"
    if api_code is not None:
        suffix += f"/API {api_code}"
    return f"{provider}:{suffix.strip()}"


def _source_list(existing: str | None, source: str) -> str:
    sources = {item for item in (existing or "").split(",") if item}
    sources.add(source)
    return ",".join(sorted(sources))


def _rotating_batch(values: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    if len(values) <= size:
        return values
    start = (date.today().toordinal() * size) % len(values)
    return (values + values)[start : start + size]


def _parse_ticketmaster_events(
    payload: dict[str, Any],
    city_target: CityTarget,
    now: datetime,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], set[tuple[str, str]]]:
    artist_rows: dict[str, dict[str, Any]] = {}
    venue_rows: dict[str, dict[str, Any]] = {}
    event_rows: dict[str, dict[str, Any]] = {}
    genre_rows: set[tuple[str, str]] = set()

    for event in (payload.get("_embedded") or {}).get("events", []) or []:
        event_id = event.get("id")
        embedded = event.get("_embedded") or {}
        event_venues = embedded.get("venues") or []
        attractions = embedded.get("attractions") or []
        if not event_id or not event_venues or not attractions:
            continue

        source_venue = event_venues[0]
        venue_name = source_venue.get("name")
        city = (source_venue.get("city") or {}).get("name") or city_target.city
        state = (source_venue.get("state") or {}).get("stateCode") or city_target.state
        if not venue_name:
            continue

        venue_id = _stable_id("venue", venue_name, city, state)
        location = source_venue.get("location") or {}
        venue_rows[venue_id] = {
            "id": venue_id,
            "name": venue_name,
            "city": city,
            "state": state,
            "capacity": None,
            "ticketmaster_id": source_venue.get("id"),
            "latitude": _number(location.get("latitude"), float),
            "longitude": _number(location.get("longitude"), float),
            "data_source": "ticketmaster",
            "updated_at": now,
        }

        event_genres = _classification_genres(event)
        primary_genre = sorted(event_genres)[0] if event_genres else None
        event_date = ((event.get("dates") or {}).get("start") or {}).get("localDate")

        for attraction in attractions:
            artist_name = attraction.get("name")
            if not artist_name:
                continue
            artist_id = _stable_id("artist", artist_name)
            artist_rows[artist_id] = {
                "id": artist_id,
                "name": artist_name,
                "popularity": None,
                "monthly_listeners": None,
                "lastfm_listeners": None,
                "home_city": None,
                "home_state": None,
                "musicbrainz_id": None,
                "ticketmaster_id": attraction.get("id"),
                "lastfm_url": None,
                "data_source": "ticketmaster",
                "updated_at": now,
            }
            attraction_genres = _classification_genres(attraction) or event_genres
            for genre in attraction_genres:
                genre_rows.add((artist_id, genre))

            row_id = _stable_id("event", "ticketmaster", str(event_id), artist_id)
            event_rows[row_id] = {
                "id": row_id,
                "artist_id": artist_id,
                "venue_id": venue_id,
                "event_date": event_date,
                "city": city,
                "state": state,
                "genre": primary_genre,
                "attendance_estimate": None,
                "outcome_label": None,
                "source": "ticketmaster",
                "external_id": event_id,
                "updated_at": now,
            }

    return artist_rows, venue_rows, event_rows, genre_rows


def _enrich_lastfm(
    artist_rows: dict[str, dict[str, Any]],
    genre_rows: set[tuple[str, str]],
    client: Any,
    errors: list[str],
) -> None:
    for artist in _rotating_batch(list(artist_rows.values()), LASTFM_ARTISTS_PER_RUN):
        try:
            info = client.get_artist_info(artist["name"]).get("artist") or {}
            tags = client.get_artist_tags(artist["name"])
            listeners = _number((info.get("stats") or {}).get("listeners"), float)
            if listeners is not None:
                artist["lastfm_listeners"] = listeners
                artist["popularity"] = min(100.0, 12.5 * log10(listeners + 1.0))
            artist["lastfm_url"] = info.get("url")
            artist["data_source"] = _source_list(artist.get("data_source"), "lastfm")

            tag_rows = (tags.get("toptags") or {}).get("tag", []) or []
            for tag in tag_rows[:5]:
                genre = _clean_genre(tag.get("name"))
                if genre:
                    genre_rows.add((artist["id"], genre))
        except Exception as error:  # Provider failures should not discard valid event data.
            errors.append(_safe_provider_error("lastfm", error))
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            if status_code in {401, 403}:
                break


def _enrich_musicbrainz(
    artist_rows: dict[str, dict[str, Any]],
    client: Any,
    errors: list[str],
) -> None:
    for artist in _rotating_batch(list(artist_rows.values()), MUSICBRAINZ_ARTISTS_PER_RUN):
        try:
            matches = client.search_artist(artist["name"]).get("artists", []) or []
            if matches:
                artist["musicbrainz_id"] = matches[0].get("id")
                artist["data_source"] = _source_list(artist.get("data_source"), "musicbrainz")
        except Exception as error:
            errors.append(_safe_provider_error("musicbrainz", error))


def _census_row(payload: Any, target: CityTarget, now: datetime) -> dict[str, Any] | None:
    if not isinstance(payload, list) or len(payload) < 2:
        return None
    values = dict(zip(payload[0], payload[1]))
    return {
        "city": target.city,
        "state": target.state,
        "population": _number(values.get("B01003_001E"), int),
        "median_age": _number(values.get("B01002_001E"), float),
        "median_income": _number(values.get("B19013_001E"), float),
        "data_source": "census_acs5",
        "updated_at": now,
    }


def _upsert(
    connection: Connection,
    table: Any,
    rows: list[dict[str, Any]],
    conflict_columns: list[str],
    update_columns: list[str] | None = None,
    preserve_existing_on_null: list[str] | None = None,
) -> None:
    if not rows:
        return
    dialect_insert = postgresql_insert if connection.dialect.name == "postgresql" else sqlite_insert
    statement = dialect_insert(table).values(rows)
    if update_columns == []:
        statement = statement.on_conflict_do_nothing(index_elements=conflict_columns)
    else:
        columns = update_columns or [
            column.name for column in table.columns if column.name not in conflict_columns
        ]
        preserve = set(preserve_existing_on_null or [])
        updates = {
            column: (
                func.coalesce(getattr(statement.excluded, column), getattr(table.c, column))
                if column in preserve
                else getattr(statement.excluded, column)
            )
            for column in columns
        }
        statement = statement.on_conflict_do_update(
            index_elements=conflict_columns,
            set_=updates,
        )
    connection.execute(statement)


def _is_sample_database(connection: Connection) -> bool:
    live_count = connection.scalar(
        select(func.count()).select_from(artists).where(artists.c.data_source != "sample")
    ) or 0
    sample_count = connection.scalar(
        select(func.count()).select_from(artists).where(artists.c.data_source == "sample")
    ) or 0
    return sample_count > 0 and live_count == 0


def _refresh_genre_aggregates(connection: Connection, now: datetime) -> None:
    rows = connection.execute(
        select(events.c.venue_id, events.c.city, events.c.state, events.c.genre).where(
            events.c.genre.is_not(None)
        )
    ).mappings()
    venue_counts: Counter[tuple[str, str]] = Counter()
    city_counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        genre = _clean_genre(row["genre"])
        if not genre:
            continue
        venue_counts[(row["venue_id"], genre)] += 1
        city_counts[(row["city"], row["state"], genre)] += 1

    connection.execute(delete(venue_genre_history))
    connection.execute(delete(city_genre_signals))
    _upsert(
        connection,
        venue_genre_history,
        [
            {
                "venue_id": venue_id,
                "genre": genre,
                "event_count": count,
                "data_source": "ticketmaster_bookings",
                "updated_at": now,
            }
            for (venue_id, genre), count in venue_counts.items()
        ],
        ["venue_id", "genre"],
    )

    city_max: dict[tuple[str, str], int] = {}
    for (city, state, _), count in city_counts.items():
        city_max[(city, state)] = max(city_max.get((city, state), 0), count)
    _upsert(
        connection,
        city_genre_signals,
        [
            {
                "city": city,
                "state": state,
                "genre": genre,
                "signal_strength": count / city_max[(city, state)],
                "data_source": "ticketmaster_event_frequency",
                "updated_at": now,
            }
            for (city, state, genre), count in city_counts.items()
        ],
        ["city", "state", "genre"],
    )


def run_live_ingestion(
    db_target: DatabaseTarget = None,
    clients: IngestionClients | None = None,
) -> IngestionResult:
    initialize_database(db_target)
    available = credentials_available()
    provided_clients = clients is not None
    if not provided_clients and not available["ticketmaster"]:
        raise RuntimeError("Ticketmaster credentials are required for live ingestion")

    started_at = datetime.now(timezone.utc)
    now = started_at
    clients = clients or _default_clients()
    provider_errors: list[str] = []
    artist_rows: dict[str, dict[str, Any]] = {}
    venue_rows: dict[str, dict[str, Any]] = {}
    event_rows: dict[str, dict[str, Any]] = {}
    genre_rows: set[tuple[str, str]] = set()
    census_rows: list[dict[str, Any]] = []

    start_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_date = (now + timedelta(days=EVENT_LOOKAHEAD_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for target in TARGET_CITIES:
        try:
            payload = clients.ticketmaster.search_events(
                city=target.city,
                state_code=target.state,
                classification_name="music",
                country_code="US",
                start_date_time=start_date,
                end_date_time=end_date,
                size=EVENTS_PER_CITY,
                sort="date,asc",
            )
            parsed_artists, parsed_venues, parsed_events, parsed_genres = _parse_ticketmaster_events(
                payload, target, now
            )
            artist_rows.update(parsed_artists)
            venue_rows.update(parsed_venues)
            event_rows.update(parsed_events)
            genre_rows.update(parsed_genres)
        except Exception as error:
            provider_errors.append(_safe_provider_error(f"ticketmaster:{target.city}", error))

        try:
            census_payload = clients.census.get_city_profile(target.state_fips, target.place_fips)
            row = _census_row(census_payload, target, now)
            if row:
                census_rows.append(row)
        except Exception as error:
            provider_errors.append(_safe_provider_error(f"census:{target.city}", error))

    if not event_rows:
        raise RuntimeError("Ticketmaster returned no usable music events for the target cities")

    if available["lastfm"] or provided_clients:
        _enrich_lastfm(artist_rows, genre_rows, clients.lastfm, provider_errors)
    if available["musicbrainz"] or provided_clients:
        _enrich_musicbrainz(artist_rows, clients.musicbrainz, provider_errors)

    sample_data_removed = False
    with get_connection(db_target) as connection:
        sample_data_removed = _is_sample_database(connection)
        if sample_data_removed:
            for table in DELETE_ORDER:
                connection.execute(delete(table))

        _upsert(
            connection,
            artists,
            list(artist_rows.values()),
            ["id"],
            update_columns=[
                "name",
                "popularity",
                "lastfm_listeners",
                "musicbrainz_id",
                "ticketmaster_id",
                "lastfm_url",
                "updated_at",
            ],
            preserve_existing_on_null=[
                "popularity",
                "lastfm_listeners",
                "musicbrainz_id",
                "lastfm_url",
            ],
        )
        _upsert(
            connection,
            venues,
            list(venue_rows.values()),
            ["id"],
            update_columns=[
                "name",
                "city",
                "state",
                "capacity",
                "ticketmaster_id",
                "latitude",
                "longitude",
                "data_source",
                "updated_at",
            ],
            preserve_existing_on_null=["capacity", "latitude", "longitude"],
        )
        _upsert(connection, artist_genres, [
            {"artist_id": artist_id, "genre": genre} for artist_id, genre in sorted(genre_rows)
        ], ["artist_id", "genre"], update_columns=[])
        _upsert(connection, events, list(event_rows.values()), ["id"])
        _upsert(connection, city_demographics, census_rows, ["city", "state"])

        retention_date = (date.today() - timedelta(days=EVENT_RETENTION_DAYS)).isoformat()
        connection.execute(
            delete(events).where(events.c.source == "ticketmaster", events.c.event_date < retention_date)
        )
        _refresh_genre_aggregates(connection, now)

        completed_at = datetime.now(timezone.utc)
        result = IngestionResult(
            status="ok",
            artists_upserted=len(artist_rows),
            venues_upserted=len(venue_rows),
            events_upserted=len(event_rows),
            cities_updated=len(census_rows),
            artist_genres_upserted=len(genre_rows),
            provider_errors=sorted(set(provider_errors)),
            sample_data_removed=sample_data_removed,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
        )
        connection.execute(
            insert(ingestion_runs).values(
                status=result.status,
                started_at=started_at,
                completed_at=completed_at,
                artists_upserted=result.artists_upserted,
                venues_upserted=result.venues_upserted,
                events_upserted=result.events_upserted,
                cities_updated=result.cities_updated,
                details=json.dumps({
                    "artist_genres_upserted": result.artist_genres_upserted,
                    "provider_errors": result.provider_errors,
                    "sample_data_removed": result.sample_data_removed,
                }),
            )
        )
    return result


def get_ingestion_status(db_target: DatabaseTarget = None) -> dict[str, Any]:
    initialize_database(db_target)
    with get_connection(db_target) as connection:
        counts = {
            name: int(connection.scalar(select(func.count()).select_from(table)) or 0)
            for name, table in TABLES.items()
        }
        latest = connection.execute(
            select(ingestion_runs).order_by(ingestion_runs.c.started_at.desc()).limit(1)
        ).mappings().first()
        storage_bytes = None
        if connection.dialect.name == "postgresql":
            storage_bytes = int(connection.scalar(text("SELECT pg_database_size(current_database())")) or 0)
    return {
        "counts": counts,
        "storage_bytes": storage_bytes,
        "latest_run": dict(latest) if latest else None,
    }
