from fastapi.testclient import TestClient

from src.api.app import app


def test_api_seed_mode_end_to_end() -> None:
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        options = client.get("/meta/options")
        assert options.status_code == 200
        assert "The District Echoes" in options.json()["artists"]

        artist_match = client.post(
            "/recommendations/artist-to-venue",
            json={"artist_name": "The District Echoes", "target_city": "Washington"},
        )
        assert artist_match.status_code == 200
        assert artist_match.json()["results"][0]["venue_name"] == "9:30 Club"

        venue_match = client.post(
            "/recommendations/venue-to-artist",
            json={"venue_name_or_city": "9:30 Club"},
        )
        assert venue_match.status_code == 200
        assert venue_match.json()["results"][0]["artist_name"] == "The District Echoes"


def test_city_and_raw_data_endpoints() -> None:
    with TestClient(app) as client:
        city = client.get("/cities/Washington/dashboard", params={"state": "DC"})
        assert city.status_code == 200
        assert city.json()["demographics"]["population"] > 0
        assert city.json()["genre_signals"]

        raw = client.get("/raw/events", params={"limit": 3})
        assert raw.status_code == 200
        assert raw.json()["count"] == 3


def test_unknown_artist_returns_404() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/recommendations/artist-to-venue",
            json={"artist_name": "Not A Seed Artist", "target_city": "Washington"},
        )
        assert response.status_code == 404


def test_ingestion_sync_requires_cron_secret() -> None:
    with TestClient(app) as client:
        response = client.get("/ingestion/sync")
        assert response.status_code == 401
