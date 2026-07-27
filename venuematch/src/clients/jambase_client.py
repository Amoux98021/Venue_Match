from __future__ import annotations

from urllib.parse import quote

import requests

from src.clients.base import BaseAPIClient
from src.db.database import DatabaseTarget
from src.utils.api_quota import reserve_jambase_call
from src.utils.config import get_env


class JamBaseClient(BaseAPIClient):
    base_url = "https://api.data.jambase.com/v3"

    def __init__(self, db_target: DatabaseTarget = None) -> None:
        super().__init__()
        self.db_target = db_target
        self.api_key = get_env("JAMBASE_API_KEY")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "VenueMatch/1.0 (https://github.com/Amoux98021/Venue_Match)",
        }

    def get_venue_by_external_id(self, source: str, external_id: str) -> dict:
        if not self.api_key:
            return {"source": "mock", "venue": {}}
        reserve_jambase_call(self.db_target)
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
        reserve_jambase_call(self.db_target)
        return self.get(
            "/venues",
            params={"venueName": venue_name, "perPage": min(max(per_page, 1), 100)},
            headers=self.headers,
        )

    def search_events(
        self,
        venue_id: str,
        event_date_from: str,
        event_date_to: str,
        page: int = 1,
        per_page: int = 100,
        expand_past_events: bool = True,
    ) -> dict:
        if not self.api_key:
            return {"source": "mock", "events": [], "pagination": {}}
        reserve_jambase_call(self.db_target)
        return self.get(
            "/events",
            params={
                "venueId": venue_id,
                "eventDateFrom": event_date_from,
                "eventDateTo": event_date_to,
                "expandPastEvents": str(expand_past_events).lower(),
                "sort": "-eventDate",
                "page": max(page, 1),
                "perPage": min(max(per_page, 1), 100),
            },
            headers=self.headers,
        )
