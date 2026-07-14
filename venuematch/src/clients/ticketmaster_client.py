from __future__ import annotations

from src.clients.base import BaseAPIClient
from src.utils.config import get_env


class TicketmasterClient(BaseAPIClient):
    base_url = "https://app.ticketmaster.com/discovery/v2"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_env("TICKETMASTER_API_KEY")

    def search_events(self, keyword: str, city: str | None = None, size: int = 20) -> dict:
        if not self.api_key:
            return {"source": "mock", "events": []}
        params = {"apikey": self.api_key, "keyword": keyword, "size": size}
        if city:
            params["city"] = city
        return self.get("/events.json", params=params)

    def search_venues(self, keyword: str, city: str | None = None, size: int = 20) -> dict:
        if not self.api_key:
            return {"source": "mock", "venues": []}
        params = {"apikey": self.api_key, "keyword": keyword, "size": size}
        if city:
            params["city"] = city
        return self.get("/venues.json", params=params)
