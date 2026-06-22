from __future__ import annotations

from src.clients.base import BaseAPIClient
from src.utils.config import get_env


class LastFMClient(BaseAPIClient):
    base_url = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_env("LASTFM_API_KEY")

    def get_artist_tags(self, artist_name: str) -> dict:
        if not self.api_key:
            return {"source": "mock", "toptags": {"tag": []}}
        return self.get(
            "",
            params={
                "method": "artist.getTopTags",
                "artist": artist_name,
                "api_key": self.api_key,
                "format": "json",
            },
        )
