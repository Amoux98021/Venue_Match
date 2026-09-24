from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from src.clients.setlistfm_client import SetlistFmClient, normalize_setlist_performance


@dataclass
class FakeResponse:
    status_code: int
    payload: Any = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def page(number: int, total: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"setlist": rows, "total": total, "page": number, "itemsPerPage": 20}


def test_authentication_headers_and_normalization_excludes_songs() -> None:
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            200,
            page(
                1,
                1,
                [
                    {
                        "id": "abc123",
                        "eventDate": "15-06-2026",
                        "artist": {"mbid": "artist-mbid", "name": "Artist"},
                        "venue": {
                            "id": "venue-id",
                            "name": "Venue",
                            "city": {
                                "name": "Washington",
                                "stateCode": "DC",
                                "country": {"code": "US", "name": "United States"},
                                "coords": {"lat": 38.9, "long": -77.0},
                            },
                        },
                        "sets": {"set": [{"song": [{"name": "Do not retain"}]}]},
                    }
                ],
            ),
        )

    client = SetlistFmClient(
        api_key="test-secret",
        request_get=fake_get,
        minimum_interval=0.5,
    )
    payload = client.get_artist_setlists("artist-mbid")
    normalized = normalize_setlist_performance(payload["setlist"][0])

    assert calls[0][1]["headers"] == {
        "Accept": "application/json",
        "x-api-key": "test-secret",
    }
    assert normalized is not None
    assert normalized["event_date"] == "2026-06-15"
    assert "sets" not in normalized
    assert "song" not in normalized


def test_pagination() -> None:
    responses = [
        FakeResponse(200, page(1, 21, [{"id": "1"}] * 20)),
        FakeResponse(200, page(2, 21, [{"id": "2"}])),
    ]
    requested_pages = []

    def fake_get(_url, **kwargs):
        requested_pages.append(kwargs["params"]["p"])
        return responses.pop(0)

    client = SetlistFmClient(
        api_key="test-secret",
        request_get=fake_get,
        clock=lambda: 10.0,
        sleeper=lambda _seconds: None,
    )
    pages = list(client.iter_artist_setlist_pages("artist-mbid"))
    assert len(pages) == 2
    assert requested_pages == [1, 2]


def test_conservative_request_throttling() -> None:
    times = iter([0.0, 0.25, 1.0])
    sleeps = []
    responses = [
        FakeResponse(200, page(1, 21, [{"id": "1"}] * 20)),
        FakeResponse(200, page(2, 21, [{"id": "2"}])),
    ]
    client = SetlistFmClient(
        api_key="test-secret",
        request_get=lambda *_args, **_kwargs: responses.pop(0),
        minimum_interval=1.0,
        clock=lambda: next(times),
        sleeper=sleeps.append,
    )

    list(client.iter_artist_setlist_pages("artist-mbid"))

    assert sleeps == [0.75]


def test_404_returns_empty_page() -> None:
    client = SetlistFmClient(
        api_key="test-secret",
        request_get=lambda *_args, **_kwargs: FakeResponse(404),
    )
    assert client.get_artist_setlists("missing")["setlist"] == []
    assert client.not_found_count == 1


def test_429_retries_with_retry_after() -> None:
    responses = [
        FakeResponse(429, headers={"Retry-After": "3"}),
        FakeResponse(200, page(1, 0, [])),
    ]
    sleeps = []
    client = SetlistFmClient(
        api_key="test-secret",
        request_get=lambda *_args, **_kwargs: responses.pop(0),
        clock=lambda: 10.0,
        sleeper=sleeps.append,
    )
    client.get_artist_setlists("artist-mbid")
    assert client.throttle_count == 1
    assert 3.0 in sleeps


def test_5xx_retries_then_succeeds() -> None:
    responses = [FakeResponse(503), FakeResponse(200, page(1, 0, []))]
    client = SetlistFmClient(
        api_key="test-secret",
        request_get=lambda *_args, **_kwargs: responses.pop(0),
        clock=lambda: 10.0,
        sleeper=lambda _seconds: None,
    )
    assert client.get_artist_setlists("artist-mbid")["total"] == 0
    assert client.retry_count == 1


def test_malformed_payload() -> None:
    client = SetlistFmClient(
        api_key="test-secret",
        request_get=lambda *_args, **_kwargs: FakeResponse(200, {"setlist": {}}),
    )
    with pytest.raises(ValueError, match="setlist list"):
        client.get_artist_setlists("artist-mbid")
