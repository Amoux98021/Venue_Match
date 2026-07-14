from __future__ import annotations

from src.clients.base import BaseAPIClient
from src.utils.config import get_env


class CensusClient(BaseAPIClient):
    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_env("CENSUS_API_KEY")
        acs_year = get_env("CENSUS_ACS_YEAR", "2024")
        self.base_url = f"https://api.census.gov/data/{acs_year}/acs/acs5"

    def get_city_profile(self, state_fips: str, place_fips: str) -> dict:
        params = {
            "get": "NAME,B01003_001E,B19013_001E,B01002_001E",
            "for": f"place:{place_fips}",
            "in": f"state:{state_fips}",
        }
        if self.api_key:
            params["key"] = self.api_key
        return self.get("", params=params)
