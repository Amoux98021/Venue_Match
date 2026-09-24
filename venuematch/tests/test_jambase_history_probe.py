from datetime import date

from src.evaluation.jambase_history_probe import build_probe_plan, classify_probe


def _artists() -> list[dict]:
    return [
        {
            "id": f"artist-{index}",
            "name": f"Artist {index}",
            "jambase_id": f"jambase:artist-{index}",
            "historical_relationships": 20 - index,
        }
        for index in range(5)
    ]


def _venues() -> list[dict]:
    return [
        {
            "id": f"venue-{index}",
            "name": f"Venue {index}",
            "city": "Washington",
            "state": "DC",
            "jambase_id": f"jambase:venue-{index}",
            "historical_relationships": 30 - index,
        }
        for index in range(3)
    ]


def test_probe_plan_is_id_filtered_and_bounded() -> None:
    plan = build_probe_plan(_artists(), _venues(), date(2026, 9, 23))

    assert len(plan) == 12
    assert {request["query_type"] for request in plan} == {"artist_id", "venue_id"}
    assert {request["window"]["label"] for request in plan} >= {
        "3_months_ago",
        "6_months_ago",
        "9_months_ago",
        "12_months_ago",
    }


def test_recovery_probe_uses_only_three_representative_requests() -> None:
    plan = build_probe_plan(_artists(), _venues(), date(2026, 9, 23), recovery=True)

    assert len(plan) == 3
    assert [request["query_type"] for request in plan] == [
        "artist_id",
        "venue_id",
        "venue_id",
    ]
    assert [request["window"]["label"] for request in plan] == [
        "one_year_span",
        "one_year_span",
        "12_months_ago",
    ]


def test_probe_classifies_six_month_history_as_available() -> None:
    results = [
        {
            "oldest_event_date": "2026-02-01",
            "newest_event_date": "2026-02-20",
            "appears_plan_restricted": False,
        }
    ]

    classification, depth = classify_probe(results, date(2026, 9, 23))

    assert classification == "JAMBASE_HISTORY_AVAILABLE"
    assert depth is not None and depth >= 180


def test_probe_classifies_entitlement_denial_without_events_as_unavailable() -> None:
    results = [
        {
            "oldest_event_date": None,
            "newest_event_date": None,
            "appears_plan_restricted": True,
        }
    ]

    classification, depth = classify_probe(results, date(2026, 9, 23))

    assert classification == "JAMBASE_HISTORY_NOT_AVAILABLE"
    assert depth is None
