from pathlib import Path

from sqlalchemy import update

from src.db.database import get_connection
from src.db.schema import city_genre_signals
from src.db.seed import seed_sample_data
from src.scoring.recommender import (
    WEIGHTS,
    _confidence_score,
    _genre_similarity,
    recommend_venues_for_artist,
)


def test_final_score_uses_documented_weights(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    seed_sample_data(database_path, overwrite=True)
    result = recommend_venues_for_artist(
        "The District Echoes",
        "Washington",
        db_path=database_path,
        top_n=2,
    )

    top = result.ranked.iloc[0]
    expected = sum(float(top[score]) * weight for score, weight in WEIGHTS.items())
    assert abs(float(top["final_score"]) - expected) < 0.0002
    assert top["venue_name"] == "9:30 Club"


def test_city_filter_limits_artist_search(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    seed_sample_data(database_path, overwrite=True)
    result = recommend_venues_for_artist(
        "Campus Bloom",
        "College Park",
        db_path=database_path,
    )

    assert set(result.ranked["city"]) == {"College Park"}


def test_related_genres_receive_partial_credit() -> None:
    related = _genre_similarity({"indie rock"}, {"alternative rock"})
    unrelated = _genre_similarity({"indie rock"}, {"classical"})

    assert 0 < related < 1
    assert unrelated == 0


def test_confidence_reports_missing_supporting_data() -> None:
    complete, complete_note = _confidence_score(
        has_artist_genres=True,
        has_venue_history=True,
        has_city_signal=True,
        has_capacity=True,
        has_artist_popularity=True,
    )
    sparse, sparse_note = _confidence_score(
        has_artist_genres=True,
        has_venue_history=False,
        has_city_signal=False,
        has_capacity=False,
        has_artist_popularity=False,
    )

    assert complete == 1.0
    assert "high confidence" in complete_note
    assert sparse == 0.2
    assert "low confidence" in sparse_note


def test_city_demand_does_not_leak_into_genre_fit(tmp_path: Path) -> None:
    database_path = tmp_path / "independent-signals.db"
    seed_sample_data(database_path, overwrite=True)
    before = recommend_venues_for_artist(
        "The District Echoes",
        "Washington",
        db_path=database_path,
        top_n=10,
    ).ranked.set_index("venue_id")

    with get_connection(database_path) as connection:
        connection.execute(
            update(city_genre_signals)
            .where(city_genre_signals.c.city == "Washington")
            .values(signal_strength=0.01)
        )

    after = recommend_venues_for_artist(
        "The District Echoes",
        "Washington",
        db_path=database_path,
        top_n=10,
    ).ranked.set_index("venue_id")

    assert before.loc["venue_1", "genre_fit_score"] == after.loc["venue_1", "genre_fit_score"]
    assert before.loc["venue_1", "city_demand_score"] != after.loc["venue_1", "city_demand_score"]
