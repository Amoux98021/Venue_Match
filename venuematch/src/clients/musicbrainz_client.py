from __future__ import annotations

import requests

from src.utils.config import get_env


class MusicBrainzClient:
    base_url = "https://musicbrainz.org/ws/2"

    def __init__(self) -> None:
        self.user_agent = get_env("MUSICBRAINZ_USER_AGENT")

    def search_artist(self, artist_name: str) -> dict:
        if not self.user_agent:
            return {"source": "mock", "artists": []}
        response = requests.get(
            f"{self.base_url}/artist",
            params={"query": artist_name, "fmt": "json"},
            headers={"User-Agent": self.user_agent},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
