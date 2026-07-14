from __future__ import annotations

from src.clients.base import BaseAPIClient
from src.utils.config import get_env


class TicketmasterClient(BaseAPIClient):
    base_url = "https://app.ticketmaster.com/discovery/v2"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_env("TICKETMASTER_API_KEY")

    def search_events(
        self,
        keyword: str | None = None,
        city: str | None = None,
        state_code: str | None = None,
        classification_name: str | None = None,
        country_code: str | None = None,
        start_date_time: str | None = None,
        end_date_time: str | None = None,
        size: int = 20,
        page: int = 0,
        sort: str = "relevance,desc",
    ) -> dict:
        if not self.api_key:
            return {"source": "mock", "events": []}
        params = {
            "apikey": self.api_key,
            "size": min(max(size, 1), 200),
            "page": max(page, 0),
            "sort": sort,
        }
        optional_params = {
            "keyword": keyword,
            "city": city,
            "stateCode": state_code,
            "classificationName": classification_name,
            "countryCode": country_code,
            "startDateTime": start_date_time,
            "endDateTime": end_date_time,
        }
        params.update({key: value for key, value in optional_params.items() if value})
        return self.get("/events.json", params=params)

    def search_venues(self, keyword: str, city: str | None = None, size: int = 20) -> dict:
        if not self.api_key:
            return {"source": "mock", "venues": []}
        params = {"apikey": self.api_key, "keyword": keyword, "size": size}
        if city:
            params["city"] = city
        return self.get("/venues.json", params=params)
