from __future__ import annotations

import requests

from src.utils.config import get_env


class MusicBrainzClient:
    base_url = "https://musicbrainz.org/ws/2"

    def __init__(self) -> None:
        self.user_agent = get_env("MUSICBRAINZ_USER_AGENT", "VenueMatch/0.1 (contact@example.com)")

    def search_artist(self, artist_name: str) -> dict:
        response = requests.get(
            f"{self.base_url}/artist",
            params={"query": artist_name, "fmt": "json"},
            headers={"User-Agent": self.user_agent},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
