from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import func, select, text

from src.db.database import get_connection
from src.db.schema import artists, events, venues
from src.db.seed import seed_sample_data
from src.evaluation.musicbrainz_history_probe import (
    build_musicbrainz_probe_input,
    classify_provider_overlap,
    lookback_bucket,
    normalize_musicbrainz_event,
    public_musicbrainz_probe_result,
    refine_musicbrainz_probe_metrics,
    resolve_artist,
    resolve_place_search,
    resolve_venue,
    write_musicbrainz_probe_artifacts,
)


ARTIST_MBID = "11111111-1111-4111-8111-111111111111"
PLACE_MBID = "22222222-2222-4222-8222-222222222222"
EVENT_MBID = "33333333-3333-4333-8333-333333333333"


def test_exact_mbid_artist_resolution() -> None:
    resolved = resolve_artist(
        {"musicbrainz_id": ARTIST_MBID, "name": "Different spelling"},
        {ARTIST_MBID: {"id": "artist-1", "name": "Known Artist"}},
        {},
    )
    assert resolved == {
        "artist_id": "artist-1",
        "artist_name": "Known Artist",
        "match_quality": "exact",
    }


def test_place_search_and_exact_place_resolution() -> None:
    venue = {
        "id": "venue-1",
        "name": "9:30 Club",
        "city": "Washington",
        "state": "DC",
        "market": "Washington, DC",
    }
    payload = {
        "places": [
            {
                "id": PLACE_MBID,
                "name": "9:30 Club",
                "area": {"name": "Washington", "area": {"name": "United States"}},
            }
        ]
    }
    mapping = resolve_place_search(venue, payload)
    assert mapping is not None
    assert mapping["match_quality"] == "exact"

    resolved = resolve_venue(
        {"musicbrainz_id": PLACE_MBID, "name": "9:30 Club", "areas": ["Washington"]},
        {PLACE_MBID: mapping},
        [venue],
        [{"city": "Washington", "state": "DC", "market": "Washington, DC"}],
    )
    assert resolved["venue_id"] == "venue-1"
    assert resolved["match_quality"] == "exact"


def test_provider_duplicate_detection() -> None:
    exact_keys = defaultdict(set)
    exact_keys[("2026-01-10", "artist-1", "venue-1")].add("ticketmaster")
    date_artist = defaultdict(set)
    date_artist[("2026-01-10", "artist-1")].add("venue-1")

    exact, sources = classify_provider_overlap(
        {
            "event_date": "2026-01-10",
            "artist_id": "artist-1",
            "venue_id": "venue-1",
            "artist_match_quality": "exact",
            "venue_match_quality": "exact",
        },
        exact_keys,
        date_artist,
    )
    assert exact == "already_known"
    assert sources == ["ticketmaster"]

    likely, _ = classify_provider_overlap(
        {
            "event_date": "2026-01-10",
            "artist_id": "artist-1",
            "venue_id": None,
            "artist_match_quality": "exact",
            "venue_match_quality": "unresolved",
        },
        exact_keys,
        date_artist,
    )
    assert likely == "likely_duplicate"


def test_historical_lookback_bucketing() -> None:
    as_of = date(2026, 9, 23)
    assert lookback_bucket("2026-09-23", as_of) == "0-3 months"
    assert lookback_bucket("2026-06-25", as_of) == "0-3 months"
    assert lookback_bucket("2026-06-24", as_of) == "3-6 months"
    assert lookback_bucket("2025-09-23", as_of) == "6-12 months"
    assert lookback_bucket("2024-09-23", as_of) == "12-24 months"
    assert lookback_bucket("2024-09-22", as_of) == "24+ months"
    assert lookback_bucket("2026-09-24", as_of) is None


def test_cancelled_event_and_partial_date_handling() -> None:
    normalized = normalize_musicbrainz_event(
        {
            "id": EVENT_MBID,
            "name": "Cancelled Show",
            "type": "Concert",
            "cancelled": True,
            "life-span": {"begin": "2026", "end": "2026-02-01"},
            "relations": [
                {
                    "type": "main performer",
                    "attributes": ["cancelled"],
                    "artist": {"id": ARTIST_MBID, "name": "Known Artist"},
                }
            ],
        }
    )
    assert normalized is not None
    assert normalized["cancelled"] is True
    assert normalized["begin_date"] is None
    assert normalized["performers"][0]["cancelled_appearance"] is True


def test_probe_input_does_not_mutate_database(tmp_path) -> None:
    database_path = tmp_path / "probe.sqlite3"
    database_url = seed_sample_data(database_path)
    with get_connection(database_url) as connection:
        first_artist_id = connection.scalar(select(artists.c.id).limit(1))
        connection.execute(
            text("UPDATE artists SET musicbrainz_id = :mbid WHERE id = :artist_id"),
            {"mbid": ARTIST_MBID, "artist_id": first_artist_id},
        )

    def counts() -> tuple[int, int, int]:
        with get_connection(database_url) as connection:
            return (
                int(connection.scalar(select(func.count()).select_from(artists)) or 0),
                int(connection.scalar(select(func.count()).select_from(venues)) or 0),
                int(connection.scalar(select(func.count()).select_from(events)) or 0),
            )

    before = counts()
    snapshot = build_musicbrainz_probe_input(
        database_url,
        as_of=date(2026, 9, 23),
        sample_size=1,
    )
    after = counts()

    assert before == after
    assert snapshot["metadata"]["read_only"] is True
    assert len(snapshot["sample_artists"]) == 1


def test_refined_metrics_count_unique_events_and_relationships_separately() -> None:
    snapshot = {
        "artist_index": [
            {"id": "artist-1", "name": "Known Artist", "musicbrainz_id": ARTIST_MBID}
        ],
        "venue_index": [
            {"id": "venue-1", "name": "Known Venue", "city": "Washington", "state": "DC"}
        ],
        "existing_relationships": [],
        "target_markets": [
            {"city": "Washington", "state": "DC", "market": "Washington, DC"}
        ],
    }
    result = {
        "metadata": {"as_of": "2026-09-23", "minimum_request_interval_seconds": 1.05},
        "summary": {},
        "projected_backfill": {"artist_backfill_api_call_estimate": 1},
        "decision_checks": {},
        "artist_probe_results": [
            {
                "history_band": "medium",
                "provider_bias": "ticketmaster-heavy",
                "market": "Washington, DC",
                "primary_genre": "rock",
            }
        ],
        "place_probe_results": [
            {
                "place_mbid": PLACE_MBID,
                "venue_id": "venue-1",
                "venue_name": "Known Venue",
                "market": "Washington, DC",
                "match_quality": "exact",
                "error": None,
            }
        ],
        "normalized_events": [
            {
                "event_mbid": EVENT_MBID,
                "name": "Known Show",
                "event_type": "Concert",
                "begin_date": "2025-09-01",
                "end_date": "2025-09-01",
                "cancelled": False,
                "performers": [
                    {
                        "musicbrainz_id": ARTIST_MBID,
                        "name": "Known Artist",
                        "relationship_type": "main performer",
                        "cancelled_appearance": False,
                    },
                    {
                        "musicbrainz_id": "44444444-4444-4444-8444-444444444444",
                        "name": "Unknown Support",
                        "relationship_type": "supporting performer",
                        "cancelled_appearance": False,
                    },
                ],
                "place": {
                    "musicbrainz_id": PLACE_MBID,
                    "name": "Known Venue",
                    "areas": ["Washington"],
                },
                "discovered_by": [f"artist:{ARTIST_MBID}"],
            }
        ],
    }
    snapshot["counts"] = {"venues": 1}

    refined = refine_musicbrainz_probe_metrics(result, snapshot)
    assert refined["summary"]["lookback_event_counts"]["12-24 months"] == 1
    assert refined["summary"]["lookback_relationship_counts"]["12-24 months"] == 2
    assert refined["summary"]["current_market_venue_resolution_success_rate"] == 1.0


def test_public_json_excludes_entity_and_event_level_rows() -> None:
    result = {
        "metadata": {"as_of": "2026-09-23"},
        "api_requests_used": 1,
        "request_breakdown": {},
        "summary": {},
        "sample_profile": {},
        "market_probe_results": [],
        "provider_overlap_summary": [],
        "projected_backfill": {},
        "decision_checks": {},
        "decision": "MUSICBRAINZ_HISTORY_INSUFFICIENT",
        "setlist_fm_still_needed": True,
        "artist_probe_results": [{"name": "Private Artist Row"}],
        "place_probe_results": [{"venue_name": "Private Venue Row"}],
        "normalized_events": [{"name": "Private Event Row"}],
    }

    public_payload = public_musicbrainz_probe_result(result)

    assert "artist_probe_results" not in public_payload
    assert "place_probe_results" not in public_payload
    assert "normalized_events" not in public_payload
