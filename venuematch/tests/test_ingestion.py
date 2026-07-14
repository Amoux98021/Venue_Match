from pathlib import Path

from src.db import repository
from src.db.seed import seed_sample_data
from src.ingestion.service import IngestionClients, get_ingestion_status, run_live_ingestion


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


def _clients(ticketmaster=None):
    return IngestionClients(
        ticketmaster=ticketmaster or FakeTicketmaster(),
        lastfm=FakeLastFM(),
        musicbrainz=FakeMusicBrainz(),
        census=FakeCensus(),
    )


def test_live_ingestion_replaces_sample_data_and_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "live.db"
    seed_sample_data(database_path, overwrite=True)

    first = run_live_ingestion(database_path, clients=_clients())
    second = run_live_ingestion(database_path, clients=_clients())

    assert first.sample_data_removed is True
    assert second.sample_data_removed is False
    assert set(repository.get_artists(database_path)["data_source"]) != {"sample"}
    assert len(repository.get_events(database_path)) == 5
    assert len(repository.get_venues(database_path)) == 5
    assert len(repository.get_city_demographics(database_path)) == 5
    assert not repository.get_city_genre_signals(database_path).empty
    assert not repository.get_venue_genre_history(database_path).empty
    assert get_ingestion_status(database_path)["counts"]["ingestion_runs"] == 2


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
