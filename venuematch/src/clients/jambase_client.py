from __future__ import annotations

from urllib.parse import quote

import requests

from src.clients.base import BaseAPIClient
from src.utils.config import get_env


class JamBaseClient(BaseAPIClient):
    base_url = "https://api.data.jambase.com/v3"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_env("JAMBASE_API_KEY")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "VenueMatch/1.0 (https://github.com/Amoux98021/Venue_Match)",
        }

    def get_venue_by_external_id(self, source: str, external_id: str) -> dict:
        if not self.api_key:
            return {"source": "mock", "venue": {}}
        identifier = quote(f"{source}:{external_id}", safe=":")
        try:
            return self.get(f"/venues/id/{identifier}", headers=self.headers)
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                return {"venue": {}}
            raise

    def search_venues(self, venue_name: str, per_page: int = 10) -> dict:
        if not self.api_key:
            return {"source": "mock", "venues": []}
        return self.get(
            "/venues",
            params={"venueName": venue_name, "perPage": min(max(per_page, 1), 100)},
            headers=self.headers,
        )
