from __future__ import annotations

from src.clients.base import BaseAPIClient
from src.utils.config import get_env


class CensusClient(BaseAPIClient):
    base_url = "https://api.census.gov/data/2023/acs/acs5"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_env("CENSUS_API_KEY")

    def get_city_profile(self, state_fips: str, place_fips: str) -> dict:
        params = {
            "get": "NAME,B01003_001E,B19013_001E,B01002_001E",
            "for": f"place:{place_fips}",
            "in": f"state:{state_fips}",
        }
        if self.api_key:
            params["key"] = self.api_key
        return self.get("", params=params)
