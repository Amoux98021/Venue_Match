from datetime import datetime, timezone
from pathlib import Path

import requests

from src.db import repository
from src.db.seed import seed_sample_data
from src.ingestion.service import (
    IngestionClients,
    TARGET_CITIES,
    _apply_capacity_overrides,
    get_ingestion_status,
    run_jambase_history_backfill,
    run_live_ingestion,
)
from src.scoring.recommender import recommend_venues_for_artist


class FakeTicketmaster:
    def search_events(self, **params):
        city = params["city"]
        state = params["state_code"]
        slug = city.lower().replace(" ", "-")
        return {
            "_embedded": {
                "events": [
                    {
                        "id": f"event-{slug}",
                        "dates": {"start": {"localDate": "2026-09-01"}},
                        "classifications": [
                            {"genre": {"name": "Rock"}, "subGenre": {"name": "Alternative Rock"}}
                        ],
                        "_embedded": {
                            "venues": [
                                {
                                    "id": f"venue-{slug}",
                                    "name": f"{city} Live Hall",
                                    "city": {"name": city},
                                    "state": {"stateCode": state},
                                    "location": {"latitude": "39.0", "longitude": "-77.0"},
                                }
                            ],
                            "attractions": [
                                {
                                    "id": f"artist-{slug}",
                                    "name": f"{city} Live Artist",
                                    "classifications": [
                                        {
                                            "genre": {"name": "Rock"},
                                            "subGenre": {"name": "Alternative Rock"},
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                ]
            }
        }


class EmptyTicketmaster:
    def search_events(self, **params):
        return {"_embedded": {"events": []}}


class FakeLastFM:
    def get_artist_info(self, artist_name):
        return {"artist": {"url": "https://last.fm/fake", "stats": {"listeners": "125000"}}}

    def get_artist_tags(self, artist_name):
        return {"toptags": {"tag": [{"name": "indie rock"}, {"name": "alternative"}]}}


class FakeMusicBrainz:
    def search_artist(self, artist_name):
        return {"artists": [{"id": f"mbid-{artist_name.lower().replace(' ', '-')}"}]}


class FakeCensus:
    def get_city_profile(self, state_fips, place_fips):
        return [
            ["NAME", "B01003_001E", "B19013_001E", "B01002_001E"],
            ["Test city", "500000", "85000", "35.5"],
        ]


class FakeJamBase:
    def get_venue_by_external_id(self, source, external_id):
        return {
            "venue": {
                "identifier": f"jambase:{external_id}",
                "url": f"https://www.jambase.com/venue/{external_id}",
                "maximumAttendeeCapacity": 1750,
            }
        }

    def search_events(self, venue_id, **params):
        slug = venue_id.split(":", 1)[-1]
        return {
            "events": [
                {
                    "identifier": f"jambase:event-{slug}",
                    "url": f"https://www.jambase.com/show/{slug}",
                    "startDate": "2026-06-15T20:00:00",
                    "genre": [{"name": "Indie Rock"}],
                    "performer": [
                        {
                            "name": f"JamBase Artist {slug}",
                            "identifier": f"jambase:artist-{slug}",
                        }
                    ],
                }
            ],
            "pagination": {"page": 1, "totalPages": 1},
        }


class OneBadVenueJamBase(FakeJamBase):
    def __init__(self):
        self.calls = 0

    def search_events(self, venue_id, **params):
        self.calls += 1
        if self.calls == 1:
            response = requests.Response()
            response.status_code = 400
            raise requests.HTTPError(response=response)
        return super().search_events(venue_id, **params)


class NoCapacityJamBase(FakeJamBase):
    def get_venue_by_external_id(self, source, external_id):
        return {
            "venue": {
                "identifier": f"jambase:{external_id}",
                "url": f"https://www.jambase.com/venue/{external_id}",
            }
        }


class OneBadCapacityJamBase(FakeJamBase):
    def __init__(self):
        self.calls = 0

    def get_venue_by_external_id(self, source, external_id):
        self.calls += 1
        if self.calls == 1:
            response = requests.Response()
            response.status_code = 400
            raise requests.HTTPError(response=response)
        return super().get_venue_by_external_id(source, external_id)


def _clients(ticketmaster=None):
    return IngestionClients(
        ticketmaster=ticketmaster or FakeTicketmaster(),
        lastfm=FakeLastFM(),
        musicbrainz=FakeMusicBrainz(),
        census=FakeCensus(),
        jambase=FakeJamBase(),
    )


def test_live_ingestion_replaces_sample_data_and_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "live.db"
    seed_sample_data(database_path, overwrite=True)

    first = run_live_ingestion(database_path, clients=_clients())
    second = run_live_ingestion(database_path, clients=_clients())
    third = run_live_ingestion(database_path, clients=_clients())

    assert first.sample_data_removed is True
    assert second.sample_data_removed is False
    assert first.capacities_updated == 5
    assert second.capacities_updated == 5
    assert third.jambase_venues_checked == 0
    assert set(repository.get_artists(database_path)["data_source"]) != {"sample"}
    assert len(repository.get_events(database_path)) == len(TARGET_CITIES)
    assert len(repository.get_venues(database_path)) == len(TARGET_CITIES)
    assert set(repository.get_venues(database_path)["capacity"]) == {1750}
    assert len(repository.get_venue_capacity_sources(database_path)) == len(TARGET_CITIES)
    assert len(repository.get_city_demographics(database_path)) == len(TARGET_CITIES)
    assert not repository.get_city_genre_signals(database_path).empty
    assert not repository.get_venue_genre_history(database_path).empty
    recommendation = recommend_venues_for_artist(
        "Washington Live Artist", "Washington", db_path=database_path, top_n=1
    ).ranked.iloc[0]
    assert recommendation["capacity"] == 1750
    assert recommendation["capacity_source"] == "jambase"
    assert get_ingestion_status(database_path)["counts"]["ingestion_runs"] == 3


def test_empty_ticketmaster_refresh_preserves_existing_data(tmp_path: Path) -> None:
    database_path = tmp_path / "preserve.db"
    seed_sample_data(database_path, overwrite=True)

    try:
        run_live_ingestion(database_path, clients=_clients(EmptyTicketmaster()))
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected empty Ticketmaster refresh to fail")

    assert "The District Echoes" in repository.get_artists(database_path)["name"].tolist()


def test_manual_capacity_override_is_persistent() -> None:
    venue_rows = {
        "venue_nikki": {
            "id": "venue_nikki",
            "name": "Nikki Lopez Philly",
            "city": "Philadelphia",
            "state": "PA",
            "data_source": "ticketmaster",
        }
    }
    source_rows = []

    updated = _apply_capacity_overrides(venue_rows, source_rows, now=datetime.now(timezone.utc))

    assert updated == 1
    assert venue_rows["venue_nikki"]["capacity"] == 150
    assert venue_rows["venue_nikki"]["capacity_source"] == "manual"
    assert source_rows[0]["capacity"] == 150


def test_jambase_history_backfill_is_resumable(tmp_path: Path) -> None:
    database_path = tmp_path / "history.db"
    run_live_ingestion(database_path, clients=_clients())

    first = run_jambase_history_backfill(
        database_path,
        client=FakeJamBase(),
        batch_size=2,
    )
    second = run_jambase_history_backfill(
        database_path,
        client=FakeJamBase(),
        batch_size=2,
    )

    assert first.venues_checked == 2
    assert second.venues_checked == 2
    assert first.mode == "historical"
    assert first.remaining_venues == 3
    assert second.remaining_venues == 1
    assert len(repository.get_events(database_path)) == len(TARGET_CITIES) + 4
    assert "indie rock" in repository.get_artist_genres(database_path)["genre"].tolist()

    future = run_jambase_history_backfill(
        database_path,
        client=FakeJamBase(),
        batch_size=1,
        include_history=False,
    )
    assert future.mode == "future"
    assert future.venues_checked == 1
    assert repository.get_venues(database_path)["jambase_future_checked_at"].notna().sum() == 1


def test_jambase_backfill_skips_one_invalid_venue(tmp_path: Path) -> None:
    database_path = tmp_path / "invalid-venue.db"
    run_live_ingestion(database_path, clients=_clients())

    result = run_jambase_history_backfill(
        database_path,
        client=OneBadVenueJamBase(),
        batch_size=2,
        include_history=False,
    )

    assert result.status == "partial"
    assert result.venues_checked == 1
    assert result.remaining_venues == 3
    assert result.provider_errors == ["jambase:HTTP 400"]


def test_jambase_identity_is_kept_without_capacity(tmp_path: Path) -> None:
    database_path = tmp_path / "identity.db"
    clients = _clients()
    clients.jambase = NoCapacityJamBase()

    result = run_live_ingestion(database_path, clients=clients)
    stored_venues = repository.get_venues(database_path)

    assert result.jambase_venues_checked == 5
    assert result.capacities_updated == 0
    assert stored_venues["jambase_id"].notna().sum() == 5


def test_capacity_enrichment_skips_one_invalid_venue(tmp_path: Path) -> None:
    database_path = tmp_path / "invalid-capacity.db"
    clients = _clients()
    clients.jambase = OneBadCapacityJamBase()

    result = run_live_ingestion(database_path, clients=clients)

    assert result.jambase_venues_checked == 4
    assert result.capacities_updated == 4
    assert result.provider_errors == ["jambase:HTTP 400"]
