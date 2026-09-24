from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
import requests

from src.clients.musicbrainz_client import MusicBrainzClient


@dataclass
class FakeClock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeResponse:
    def __init__(
        self,
        payload: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(response=response)


def test_musicbrainz_event_pagination() -> None:
    offsets: list[int] = []

    def request_get(*_: Any, **kwargs: Any) -> FakeResponse:
        offset = kwargs["params"]["offset"]
        offsets.append(offset)
        row_count = 2 if offset == 0 else 1
        rows = [{"id": f"event-{offset + index}"} for index in range(row_count)]
        return FakeResponse({"event-count": 3, "events": rows})

    clock = FakeClock()
    client = MusicBrainzClient(
        request_get=request_get,
        clock=clock,
        sleeper=clock.sleep,
    )

    pages = list(client.iter_artist_event_pages("artist-mbid", limit=2))

    assert len(pages) == 2
    assert offsets == [0, 2]
    assert client.request_count == 2


def test_musicbrainz_throttles_to_one_request_per_second() -> None:
    clock = FakeClock()
    client = MusicBrainzClient(
        request_get=lambda *_args, **_kwargs: FakeResponse({"artists": []}),
        clock=clock,
        sleeper=clock.sleep,
    )

    client.search_artist("First")
    client.search_artist("Second")

    assert clock.sleeps == [pytest.approx(1.05)]


def test_musicbrainz_retries_503_with_backoff() -> None:
    responses = [
        FakeResponse({}, status_code=503, headers={"Retry-After": "2"}),
        FakeResponse({"artists": []}),
    ]
    clock = FakeClock()
    client = MusicBrainzClient(
        request_get=lambda *_args, **_kwargs: responses.pop(0),
        clock=clock,
        sleeper=clock.sleep,
    )

    assert client.search_artist("Retry") == {"artists": []}
    assert client.request_count == 2
    assert sum(clock.sleeps) >= 2


def test_musicbrainz_rejects_malformed_event_response() -> None:
    client = MusicBrainzClient(
        request_get=lambda *_args, **_kwargs: FakeResponse({"events": "not-a-list"}),
        minimum_interval=1.0,
    )

    with pytest.raises(ValueError, match="events list"):
        client.get_artist_events("artist-mbid")
