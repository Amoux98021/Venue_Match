from __future__ import annotations

from collections.abc import Callable, Iterator
from time import monotonic, sleep
from typing import Any

import requests

from src.utils.config import get_env


DEFAULT_USER_AGENT = "VenueMatch/1.0 (https://github.com/Amoux98021/Venue_Match)"
EVENT_RELATIONSHIPS = "artist-rels+place-rels+event-rels+area-rels"


class MusicBrainzClient:
    base_url = "https://musicbrainz.org/ws/2"

    def __init__(
        self,
        user_agent: str | None = None,
        timeout: int = 30,
        minimum_interval: float = 1.05,
        max_retries: int = 3,
        request_get: Callable[..., Any] = requests.get,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.user_agent = user_agent or get_env("MUSICBRAINZ_USER_AGENT") or DEFAULT_USER_AGENT
        self.timeout = timeout
        self.minimum_interval = max(minimum_interval, 1.0)
        self.max_retries = max(max_retries, 0)
        self._request_get = request_get
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self.request_count = 0

    def _wait_for_request_slot(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self._clock() - self._last_request_at
        if elapsed < self.minimum_interval:
            self._sleeper(self.minimum_interval - elapsed)

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            self._wait_for_request_slot()
            response = self._request_get(
                f"{self.base_url}{path}",
                params={**params, "fmt": "json"},
                headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                timeout=self.timeout,
            )
            self.request_count += 1
            self._last_request_at = self._clock()
            if response.status_code != 503 or attempt >= self.max_retries:
                response.raise_for_status()
                try:
                    payload = response.json()
                except (TypeError, ValueError) as error:
                    raise ValueError("MusicBrainz returned malformed JSON") from error
                if not isinstance(payload, dict):
                    raise ValueError("MusicBrainz response must be a JSON object")
                return payload

            retry_after = response.headers.get("Retry-After")
            try:
                backoff = float(retry_after) if retry_after else float(2**attempt)
            except ValueError:
                backoff = float(2**attempt)
            self._sleeper(max(backoff, self.minimum_interval))

        raise RuntimeError("MusicBrainz request retry loop exited unexpectedly")

    @staticmethod
    def _validated_event_page(payload: dict[str, Any]) -> dict[str, Any]:
        event_rows = payload.get("events")
        if not isinstance(event_rows, list):
            raise ValueError("MusicBrainz event response is missing an events list")
        for row in event_rows:
            if not isinstance(row, dict):
                raise ValueError("MusicBrainz event response contains a malformed event")
        return payload

    def search_artist(self, artist_name: str) -> dict[str, Any]:
        return self._get("/artist", {"query": artist_name})

    def search_place(
        self,
        place_name: str,
        area_name: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        escaped_name = place_name.replace('"', r'\"')
        query = f'place:"{escaped_name}"'
        if area_name:
            escaped_area = area_name.replace('"', r'\"')
            query += f' AND area:"{escaped_area}"'
        return self._get(
            "/place",
            {
                "query": query,
                "limit": min(max(limit, 1), 100),
                "offset": max(offset, 0),
            },
        )

    def get_artist_events(
        self,
        artist_mbid: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        payload = self._get(
            "/event",
            {
                "artist": artist_mbid,
                "inc": EVENT_RELATIONSHIPS,
                "limit": min(max(limit, 1), 100),
                "offset": max(offset, 0),
            },
        )
        return self._validated_event_page(payload)

    def get_place_events(
        self,
        place_mbid: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        payload = self._get(
            "/event",
            {
                "place": place_mbid,
                "inc": EVENT_RELATIONSHIPS,
                "limit": min(max(limit, 1), 100),
                "offset": max(offset, 0),
            },
        )
        return self._validated_event_page(payload)

    def iter_artist_event_pages(
        self,
        artist_mbid: str,
        limit: int = 100,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._iter_event_pages(
            self.get_artist_events,
            artist_mbid,
            limit=limit,
            max_pages=max_pages,
        )

    def iter_place_event_pages(
        self,
        place_mbid: str,
        limit: int = 100,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        yield from self._iter_event_pages(
            self.get_place_events,
            place_mbid,
            limit=limit,
            max_pages=max_pages,
        )

    @staticmethod
    def _iter_event_pages(
        loader: Callable[..., dict[str, Any]],
        entity_mbid: str,
        limit: int,
        max_pages: int | None,
    ) -> Iterator[dict[str, Any]]:
        offset = 0
        page_count = 0
        while True:
            payload = loader(entity_mbid, limit=limit, offset=offset)
            yield payload
            page_count += 1
            rows = payload.get("events", [])
            total = int(payload.get("event-count") or 0)
            offset += len(rows)
            if not rows or offset >= total or (max_pages is not None and page_count >= max_pages):
                return
