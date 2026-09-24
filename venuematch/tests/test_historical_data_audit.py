from __future__ import annotations

import pandas as pd

from src.evaluation.historical_data_audit import (
    build_historical_data_audit,
    build_venue_activity,
    candidate_venues_for_event,
    classify_events,
    evaluate_benchmark_eligibility,
    recommend_temporal_folds,
)


AS_OF = "2025-01-01"


def _artists(*artist_ids: str) -> pd.DataFrame:
    return pd.DataFrame(
        [{"id": artist_id, "name": f"Artist {artist_id}"} for artist_id in artist_ids]
    )


def _venues() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"id": "v1", "name": "Venue 1", "city": "Alpha", "state": "AA", "capacity": 100},
            {"id": "v2", "name": "Venue 2", "city": "Alpha", "state": "AA", "capacity": 200},
            {"id": "v3", "name": "Venue 3", "city": "Alpha", "state": "AA", "capacity": 300},
            {"id": "v4", "name": "Venue 4", "city": "Beta", "state": "BB", "capacity": 400},
        ]
    )


def _event(
    event_id: str,
    artist_id: str,
    venue_id: str,
    event_date: str | None,
    city: str,
    state: str,
) -> dict:
    return {
        "id": event_id,
        "artist_id": artist_id,
        "venue_id": venue_id,
        "event_date": event_date,
        "city": city,
        "state": state,
        "genre": "rock",
        "source": "test",
    }


def test_historical_and_future_classification() -> None:
    events = pd.DataFrame(
        [
            _event("past", "a1", "v1", "2024-12-31", "Alpha", "AA"),
            _event("current", "a1", "v1", "2025-01-01", "Alpha", "AA"),
            _event("future", "a1", "v1", "2025-02-01", "Alpha", "AA"),
        ]
    )
    classified = classify_events(events, AS_OF).set_index("id")
    assert classified.loc["past", "temporal_class"] == "historical"
    assert classified.loc["current", "temporal_class"] == "current_or_future"
    assert classified.loc["future", "temporal_class"] == "current_or_future"


def test_missing_and_invalid_dates_are_not_historical() -> None:
    events = pd.DataFrame(
        [
            _event("missing", "a1", "v1", None, "Alpha", "AA"),
            _event("invalid", "a1", "v1", "not-a-date", "Alpha", "AA"),
        ]
    )
    classified = classify_events(events, AS_OF)
    assert set(classified["temporal_class"]) == {"missing_date"}
    assert classified["event_dt"].isna().all()


def test_benchmark_eligibility_requires_an_alternative_venue() -> None:
    events = pd.DataFrame(
        [
            _event("e1", "a1", "v1", "2024-01-01", "Alpha", "AA"),
            _event("e2", "a2", "v2", "2024-02-01", "Alpha", "AA"),
            _event("e3", "a1", "v1", "2024-03-01", "Alpha", "AA"),
        ]
    )
    eligibility = evaluate_benchmark_eligibility(events, _artists("a1", "a2"), _venues(), AS_OF)
    indexed = eligibility.set_index("event_id")
    assert not bool(indexed.loc["e1", "eligible"])
    assert bool(indexed.loc["e2", "eligible"])
    assert indexed.loc["e2", "candidate_count"] == 2
    assert bool(indexed.loc["e3", "eligible"])
    assert indexed.loc["e3", "candidate_count"] == 2


def test_candidate_generation_uses_only_same_market() -> None:
    historical = pd.DataFrame(
        [
            {"market": "Alpha, AA", "venue_id": "v1", "event_dt": pd.Timestamp("2024-01-01"), "venue_resolved": True},
            {"market": "Alpha, AA", "venue_id": "v2", "event_dt": pd.Timestamp("2024-02-01"), "venue_resolved": True},
            {"market": "Beta, BB", "venue_id": "v4", "event_dt": pd.Timestamp("2024-01-01"), "venue_resolved": True},
        ]
    )
    activity = build_venue_activity(historical)
    candidates = candidate_venues_for_event(
        {"market": "Alpha, AA", "event_dt": pd.Timestamp("2024-03-01")}, activity
    )
    assert candidates == {"v1", "v2"}


def test_candidate_generation_never_uses_future_venue_activity() -> None:
    historical = pd.DataFrame(
        [
            {"market": "Alpha, AA", "venue_id": "v1", "event_dt": pd.Timestamp("2024-01-01"), "venue_resolved": True},
            {"market": "Alpha, AA", "venue_id": "v2", "event_dt": pd.Timestamp("2024-04-01"), "venue_resolved": True},
        ]
    )
    activity = build_venue_activity(historical)
    candidates = candidate_venues_for_event(
        {"market": "Alpha, AA", "event_dt": pd.Timestamp("2024-03-01")}, activity
    )
    assert candidates == {"v1"}


def test_temporal_folds_are_ordered_and_expanding() -> None:
    rows = []
    for index, event_date in enumerate(pd.date_range("2020-01-01", periods=60, freq="MS")):
        rows.append(
            {
                "event_id": f"e{index}",
                "artist_id": f"a{index % 8}",
                "venue_id": f"v{index % 6}",
                "market": f"Market {index % 4}",
                "event_dt": event_date,
                "eligible": True,
            }
        )
    folds = recommend_temporal_folds(pd.DataFrame(rows))
    assert len(folds) == 3
    for fold in folds:
        assert fold["train_end"] < fold["test_start"]
        assert fold["train_event_count"] > 0
        assert fold["test_event_count"] > 0
    assert folds[0]["train_event_count"] < folds[1]["train_event_count"] < folds[2]["train_event_count"]
    assert folds[0]["test_end"] < folds[1]["test_start"]
    assert folds[1]["test_end"] < folds[2]["test_start"]


def test_sparse_market_is_not_benchmark_eligible() -> None:
    events = pd.DataFrame(
        [_event("e1", "a1", "v4", "2024-06-01", "Beta", "BB")]
    )
    eligibility = evaluate_benchmark_eligibility(events, _artists("a1"), _venues(), AS_OF)
    assert len(eligibility) == 1
    assert not bool(eligibility.iloc[0]["eligible"])
    assert eligibility.iloc[0]["candidate_count"] == 1
    assert eligibility.iloc[0]["ineligible_reasons"] == "no_alternative_venue"


def test_unresolved_relationship_is_not_benchmark_eligible() -> None:
    events = pd.DataFrame(
        [
            _event("e1", "missing", "v1", "2024-01-01", "Alpha", "AA"),
            _event("e2", "a1", "v2", "2024-02-01", "Alpha", "AA"),
        ]
    )
    eligibility = evaluate_benchmark_eligibility(events, _artists("a1"), _venues(), AS_OF)
    unresolved = eligibility.set_index("event_id").loc["e1"]
    assert not bool(unresolved["eligible"])
    assert "unresolved_artist" in unresolved["ineligible_reasons"]


def test_configured_sparse_market_appears_without_events() -> None:
    events = pd.DataFrame(
        [_event("e1", "a1", "v1", "2024-01-01", "Alpha", "AA")]
    )
    frames = {
        "artists": pd.DataFrame(
            [
                {
                    "id": "a1",
                    "name": "Artist 1",
                    "musicbrainz_id": None,
                    "lastfm_listeners": None,
                    "popularity": None,
                }
            ]
        ),
        "venues": _venues(),
        "events": events,
        "artist_genres": pd.DataFrame([{"artist_id": "a1", "genre": "rock"}]),
        "venue_genre_history": pd.DataFrame(
            [{"venue_id": "v1", "genre": "rock", "event_count": 1}]
        ),
        "target_markets": pd.DataFrame(
            [
                {"city": "Alpha", "state": "AA"},
                {"city": "Gamma", "state": "CC"},
            ]
        ),
    }
    audit = build_historical_data_audit(frames, AS_OF)
    markets = {row["market"]: row for row in audit["market_coverage"]}
    assert markets["Gamma, CC"]["is_target_market"] is True
    assert markets["Gamma, CC"]["historical_event_count"] == 0
    assert markets["Gamma, CC"]["future_event_count"] == 0
