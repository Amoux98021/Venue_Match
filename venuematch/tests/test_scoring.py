from pathlib import Path

from src.db.seed import seed_sample_data
from src.scoring.recommender import WEIGHTS, recommend_venues_for_artist


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
