from __future__ import annotations

from src.clients.base import BaseAPIClient
from src.utils.config import get_env


class LastFMClient(BaseAPIClient):
    base_url = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_env("LASTFM_API_KEY")
        self.headers = {
            "User-Agent": get_env(
                "MUSICBRAINZ_USER_AGENT",
                "VenueMatch/1.0 (https://github.com/Amoux98021/Venue_Match)",
            )
        }

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
            headers=self.headers,
        )

    def get_artist_info(self, artist_name: str) -> dict:
        if not self.api_key:
            return {"source": "mock", "artist": {}}
        return self.get(
            "",
            params={
                "method": "artist.getInfo",
                "artist": artist_name,
                "autocorrect": 1,
                "api_key": self.api_key,
                "format": "json",
            },
            headers=self.headers,
        )

    def get_metro_top_tracks(self, country: str, location: str, limit: int = 50) -> dict:
        if not self.api_key:
            return {"source": "mock", "tracks": {"track": []}}
        return self.get(
            "",
            params={
                "method": "geo.getTopTracks",
                "country": country,
                "location": location,
                "limit": limit,
                "api_key": self.api_key,
                "format": "json",
            },
            headers=self.headers,
        )
