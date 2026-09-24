from __future__ import annotations

from datetime import date
import json

import pytest
from sqlalchemy import func, select, text

from src.db.database import get_connection
from src.db.schema import artists, events, venues
from src.db.seed import seed_sample_data
from src.evaluation.setlist_history_probe import (
    build_setlist_probe_input,
    classify_overlap,
    consolidate_setlist_probe_batches,
    historical_bucket,
    ProbeRequestCapReached,
    resolve_artist,
    resolve_venue,
    run_setlist_history_probe,
    write_setlist_probe_artifacts,
)


ARTIST_MBID = "11111111-1111-4111-8111-111111111111"


def test_exact_mbid_artist_resolution() -> None:
    result = resolve_artist(
        {"artist_mbid": ARTIST_MBID, "artist_name": "Different Name"},
        {ARTIST_MBID: {"id": "artist-1", "name": "Known Artist"}},
        {},
    )
    assert result == {"artist_id": "artist-1", "match_quality": "exact"}


def test_venue_resolution_by_name_city_and_fuzzy_market() -> None:
    venues = [
        {
            "id": "venue-1",
            "name": "9:30 Club",
            "city": "Washington",
            "state": "DC",
            "market": "Washington, DC",
            "latitude": 38.917,
            "longitude": -77.023,
        }
    ]
    exact = resolve_venue(
        {"venue_name": "9:30 Club", "city": "Washington"},
        "Washington, DC",
        venues,
    )
    assert exact == {"venue_id": "venue-1", "match_quality": "high"}

    fuzzy = resolve_venue(
        {"venue_name": "930 Club", "city": "Washington"},
        "Washington, DC",
        venues,
    )
    assert fuzzy == {"venue_id": "venue-1", "match_quality": "medium"}


def test_venue_resolution_handles_equal_fuzzy_scores() -> None:
    venues = [
        {
            "id": "venue-a",
            "name": "Main Hall East",
            "city": "Washington",
            "state": "DC",
            "market": "Washington, DC",
        },
        {
            "id": "venue-b",
            "name": "Main Hall West",
            "city": "Washington",
            "state": "DC",
            "market": "Washington, DC",
        },
    ]

    result = resolve_venue(
        {"venue_name": "Main Hall", "city": "Washington"},
        "Washington, DC",
        venues,
    )

    assert result == {"venue_id": None, "match_quality": "unresolved"}


def test_overlap_detection() -> None:
    row = {
        "event_date": "2026-01-10",
        "artist_id": "artist-1",
        "artist_mbid": ARTIST_MBID,
        "artist_match_quality": "exact",
        "venue_id": "venue-1",
        "venue_name": "Known Venue",
        "venue_match_quality": "high",
        "market_status": "current",
    }
    category, sources = classify_overlap(
        row,
        {("2026-01-10", "artist-1", "venue-1"): {"ticketmaster"}},
        {("2026-01-10", "artist-1")},
        set(),
        set(),
        {"venue-1": "Known Venue"},
    )
    assert category == "already_known"
    assert sources == ["ticketmaster"]


def test_historical_bucket_calculations() -> None:
    as_of = date(2026, 9, 24)
    assert historical_bucket("2026-09-24", as_of) == "0-3 months"
    assert historical_bucket("2026-06-25", as_of) == "3-6 months"
    assert historical_bucket("2025-09-24", as_of) == "6-12 months"
    assert historical_bucket("2024-09-24", as_of) == "12-24 months"
    assert historical_bucket("2024-09-23", as_of) == "24+ months"


def test_probe_input_does_not_mutate_database(tmp_path) -> None:
    database_url = seed_sample_data(tmp_path / "setlist-probe.sqlite3")
    with get_connection(database_url) as connection:
        artist_id = connection.scalar(select(artists.c.id).limit(1))
        connection.execute(
            text("UPDATE artists SET musicbrainz_id = :mbid WHERE id = :artist_id"),
            {"mbid": ARTIST_MBID, "artist_id": artist_id},
        )

    def counts() -> tuple[int, int, int]:
        with get_connection(database_url) as connection:
            return (
                int(connection.scalar(select(func.count()).select_from(artists)) or 0),
                int(connection.scalar(select(func.count()).select_from(venues)) or 0),
                int(connection.scalar(select(func.count()).select_from(events)) or 0),
            )

    before = counts()
    snapshot = build_setlist_probe_input(database_url, as_of=date(2026, 9, 24))
    assert counts() == before
    assert snapshot["metadata"]["read_only"] is True


class FakeProbeClient:
    minimum_interval = 1.0
    throttle_count = 0
    rate_limit_observations = {}

    def __init__(self) -> None:
        self.request_count = 0

    def get_artist_setlists(self, _mbid: str, page: int = 1) -> dict:
        self.request_count += 1
        return {
            "setlist": [
                {
                    "id": "private-event-id",
                    "eventDate": "15-06-2026",
                    "artist": {"mbid": ARTIST_MBID, "name": "Known Artist"},
                    "venue": {
                        "id": "private-venue-id",
                        "name": "Known Venue",
                        "city": {
                            "name": "Washington",
                            "stateCode": "DC",
                            "country": {"code": "US", "name": "United States"},
                            "coords": {"lat": 38.9, "long": -77.0},
                        },
                    },
                    "sets": {"set": [{"song": [{"name": "Private Song"}]}]},
                }
            ],
            "total": 1,
            "page": page,
            "itemsPerPage": 20,
        }

    def health_summary(self) -> dict:
        return {
            "requests": self.request_count,
            "retries": 0,
            "throttles": 0,
            "not_found": 0,
            "status_counts": {200: self.request_count},
            "rate_limit_headers": {},
        }


def test_no_event_persistence_and_aggregate_only_artifacts(tmp_path) -> None:
    snapshot = {
        "metadata": {"as_of": "2026-09-24"},
        "sample_artists": [
            {
                "id": "artist-1",
                "name": "Known Artist",
                "musicbrainz_id": ARTIST_MBID,
                "history_band": "medium",
                "provider_bias": "ticketmaster-heavy",
                "established_or_sparse": "established",
                "market": "Washington, DC",
                "primary_genre": "rock",
            }
        ],
        "artist_index": [
            {"id": "artist-1", "name": "Known Artist", "musicbrainz_id": ARTIST_MBID}
        ],
        "venue_index": [
            {
                "id": "venue-1",
                "name": "Known Venue",
                "city": "Washington",
                "state": "DC",
                "latitude": 38.9,
                "longitude": -77.0,
            }
        ],
        "existing_relationships": [],
        "target_markets": [
            {"city": "Washington", "state": "DC", "market": "Washington, DC"}
        ],
        "counts": {
            "artists": 1,
            "musicbrainz_mapped_artists": 1,
            "venues": 1,
            "relationships": 0,
        },
    }
    result = run_setlist_history_probe(snapshot, FakeProbeClient(), max_pages_per_artist=1)
    write_setlist_probe_artifacts(result, tmp_path)

    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "historical_window_summary.csv",
        "market_coverage_summary.csv",
        "projected_full_coverage.json",
        "provider_overlap_summary.csv",
        "setlist_history_probe.json",
        "setlist_history_probe.md",
    ]
    serialized = json.dumps(result)
    assert "private-event-id" not in serialized
    assert "Private Song" not in serialized
    assert result["metadata"]["transient_event_data_deleted_after_aggregation"] is True
    public_json = (tmp_path / "setlist_history_probe.json").read_text(encoding="utf-8")
    assert "private-event-id" not in public_json
    assert "Private Song" not in public_json


def test_request_cap_stops_probe() -> None:
    class CappedClient(FakeProbeClient):
        def get_artist_setlists(self, _mbid: str, page: int = 1) -> dict:
            raise ProbeRequestCapReached("cap reached")

    snapshot = {
        "metadata": {"as_of": "2026-09-24"},
        "sample_artists": [{"musicbrainz_id": ARTIST_MBID}],
        "artist_index": [],
        "venue_index": [],
        "existing_relationships": [],
        "target_markets": [],
        "counts": {"artists": 1, "musicbrainz_mapped_artists": 1},
    }

    with pytest.raises(ProbeRequestCapReached, match="cap reached"):
        run_setlist_history_probe(snapshot, CappedClient())


def test_aggregate_batches_consolidate_without_event_rows(tmp_path) -> None:
    snapshot = {
        "metadata": {"as_of": "2026-09-24"},
        "sample_artists": [
            {
                "id": "artist-1",
                "name": "Known Artist",
                "musicbrainz_id": ARTIST_MBID,
                "history_band": "medium",
                "provider_bias": "ticketmaster-heavy",
                "established_or_sparse": "established",
                "market": "Washington, DC",
                "primary_genre": "rock",
            }
        ],
        "artist_index": [
            {"id": "artist-1", "name": "Known Artist", "musicbrainz_id": ARTIST_MBID}
        ],
        "venue_index": [
            {
                "id": "venue-1",
                "name": "Known Venue",
                "city": "Washington",
                "state": "DC",
                "latitude": 38.9,
                "longitude": -77.0,
            }
        ],
        "existing_relationships": [],
        "target_markets": [
            {"city": "Washington", "state": "DC", "market": "Washington, DC"}
        ],
        "counts": {
            "artists": 2,
            "musicbrainz_mapped_artists": 2,
            "venues": 1,
            "relationships": 0,
        },
    }
    first = run_setlist_history_probe(snapshot, FakeProbeClient(), max_pages_per_artist=1)
    second = json.loads(json.dumps(first))
    first["metadata"].update({"batch_offset": 0, "total_sample_size": 2})
    second["metadata"].update({"batch_offset": 1, "total_sample_size": 2})

    result = consolidate_setlist_probe_batches(
        [first, second],
        unaggregated_successful_requests=5,
    )
    write_setlist_probe_artifacts(result, tmp_path)

    assert result["summary"]["artists_sampled"] == 2
    assert result["summary"]["unique_historical_performances"] == 2
    assert result["request_metrics"]["requests"] == 7
    assert result["request_metrics"]["status_counts"][200] == 7
    assert result["request_metrics"]["unaggregated_successful_requests"] == 5
    assert result["request_metrics"]["request_cap_respected"] is True
    assert "setlist_id" not in json.dumps(result)
