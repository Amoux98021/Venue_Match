from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
import logging
from time import monotonic, sleep
from typing import Any

import requests

from src.utils.config import get_env


logger = logging.getLogger(__name__)


class SetlistFmClient:
    base_url = "https://api.setlist.fm/rest/1.0"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 30,
        minimum_interval: float = 1.0,
        max_retries: int = 3,
        request_get: Callable[..., Any] = requests.get,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.api_key = api_key or get_env("SETLISTFM_API_KEY")
        self.timeout = timeout
        self.minimum_interval = max(minimum_interval, 0.5)
        self.max_retries = max(max_retries, 0)
        self._request_get = request_get
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None
        self.request_count = 0
        self.retry_count = 0
        self.throttle_count = 0
        self.not_found_count = 0
        self.status_counts: dict[int, int] = {}
        self.rate_limit_observations: dict[str, str] = {}

    def _wait_for_request_slot(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self._clock() - self._last_request_at
        if elapsed < self.minimum_interval:
            self._sleeper(self.minimum_interval - elapsed)

    @staticmethod
    def _retry_delay(response: Any, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        try:
            return float(retry_after) if retry_after else float(2**attempt)
        except (TypeError, ValueError):
            return float(2**attempt)

    def _observe_rate_limit(self, response: Any) -> None:
        for name in (
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "RateLimit-Limit",
            "RateLimit-Remaining",
            "RateLimit-Reset",
        ):
            value = response.headers.get(name)
            if value is not None:
                self.rate_limit_observations[name] = str(value)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not self.api_key:
            raise RuntimeError("SETLISTFM_API_KEY is required")

        for attempt in range(self.max_retries + 1):
            self._wait_for_request_slot()
            response = self._request_get(
                f"{self.base_url}{path}",
                params=params or {},
                headers={"Accept": "application/json", "x-api-key": self.api_key},
                timeout=self.timeout,
            )
            self.request_count += 1
            self._last_request_at = self._clock()
            status = int(response.status_code)
            self.status_counts[status] = self.status_counts.get(status, 0) + 1
            self._observe_rate_limit(response)

            if status == 404:
                self.not_found_count += 1
                logger.info("setlistfm_health status=404 path=%s", path)
                return None

            retryable = status == 429 or 500 <= status < 600
            if retryable and attempt < self.max_retries:
                self.retry_count += 1
                if status == 429:
                    self.throttle_count += 1
                delay = max(self._retry_delay(response, attempt), self.minimum_interval)
                logger.warning(
                    "setlistfm_health status=%s retry=%s path=%s",
                    status,
                    attempt + 1,
                    path,
                )
                self._sleeper(delay)
                continue

            if retryable:
                raise RuntimeError(f"Setlist.fm transient failure after retries: HTTP {status}")

            response.raise_for_status()
            try:
                payload = response.json()
            except (TypeError, ValueError) as error:
                raise ValueError("Setlist.fm returned malformed JSON") from error
            if not isinstance(payload, dict):
                raise ValueError("Setlist.fm response must be a JSON object")
            return payload

        raise RuntimeError("Setlist.fm request retry loop exited unexpectedly")

    @staticmethod
    def _validated_setlist_page(payload: dict[str, Any] | None, page: int) -> dict[str, Any]:
        if payload is None:
            return {"setlist": [], "total": 0, "page": page, "itemsPerPage": 20}
        rows = payload.get("setlist")
        if not isinstance(rows, list):
            raise ValueError("Setlist.fm response is missing a setlist list")
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError("Setlist.fm response contains a malformed setlist")
        for field in ("total", "page", "itemsPerPage"):
            if field not in payload:
                raise ValueError(f"Setlist.fm response is missing {field}")
        return payload

    def get_artist_setlists(self, artist_mbid: str, page: int = 1) -> dict[str, Any]:
        payload = self._get(f"/artist/{artist_mbid}/setlists", {"p": max(page, 1)})
        return self._validated_setlist_page(payload, max(page, 1))

    def search_setlists(
        self,
        *,
        city_name: str | None = None,
        state_code: str | None = None,
        venue_name: str | None = None,
        page: int = 1,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"p": max(page, 1)}
        if city_name:
            params["cityName"] = city_name
        if state_code:
            params["stateCode"] = state_code
        if venue_name:
            params["venueName"] = venue_name
        payload = self._get("/search/setlists", params)
        return self._validated_setlist_page(payload, max(page, 1))

    def iter_artist_setlist_pages(
        self,
        artist_mbid: str,
        max_pages: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            payload = self.get_artist_setlists(artist_mbid, page=page)
            yield payload
            rows = payload["setlist"]
            total = int(payload["total"])
            items_per_page = max(int(payload["itemsPerPage"]), 1)
            current_page = max(int(payload["page"]), page)
            if (
                not rows
                or current_page * items_per_page >= total
                or (max_pages is not None and page >= max_pages)
            ):
                return
            page += 1

    def health_summary(self) -> dict[str, Any]:
        return {
            "requests": self.request_count,
            "retries": self.retry_count,
            "throttles": self.throttle_count,
            "not_found": self.not_found_count,
            "status_counts": dict(sorted(self.status_counts.items())),
            "rate_limit_headers": dict(sorted(self.rate_limit_observations.items())),
        }


def _parse_event_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%d-%m-%Y").date().isoformat()
    except ValueError:
        return None


def normalize_setlist_performance(raw: dict[str, Any]) -> dict[str, Any] | None:
    setlist_id = raw.get("id")
    event_date = _parse_event_date(raw.get("eventDate"))
    artist = raw.get("artist") or {}
    venue = raw.get("venue") or {}
    city = venue.get("city") or {}
    country = city.get("country") or {}
    coordinates = city.get("coords") or {}
    if not setlist_id or not event_date or not artist.get("mbid"):
        return None
    return {
        "setlist_id": str(setlist_id),
        "event_date": event_date,
        "artist_mbid": artist.get("mbid"),
        "artist_name": artist.get("name"),
        "venue_external_id": venue.get("id"),
        "venue_name": venue.get("name"),
        "city": city.get("name"),
        "state": city.get("stateCode") or city.get("state"),
        "country_code": country.get("code"),
        "country_name": country.get("name"),
        "latitude": coordinates.get("lat"),
        "longitude": coordinates.get("long"),
        "tour_name": (raw.get("tour") or {}).get("name"),
        "source_url": raw.get("url"),
    }
