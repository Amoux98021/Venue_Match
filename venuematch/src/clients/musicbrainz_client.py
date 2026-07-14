from __future__ import annotations

import requests
from time import monotonic, sleep

from src.utils.config import get_env


class MusicBrainzClient:
    base_url = "https://musicbrainz.org/ws/2"

    def __init__(self) -> None:
        self.user_agent = get_env("MUSICBRAINZ_USER_AGENT")
        self._last_request_at = 0.0

    def search_artist(self, artist_name: str) -> dict:
        if not self.user_agent:
            return {"source": "mock", "artists": []}
        elapsed = monotonic() - self._last_request_at
        if elapsed < 1.05:
            sleep(1.05 - elapsed)
        response = requests.get(
            f"{self.base_url}/artist",
            params={"query": artist_name, "fmt": "json"},
            headers={"User-Agent": self.user_agent},
            timeout=20,
        )
        self._last_request_at = monotonic()
        response.raise_for_status()
        return response.json()
