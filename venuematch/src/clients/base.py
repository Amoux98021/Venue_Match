from __future__ import annotations

from typing import Any

import requests


class BaseAPIClient:
    base_url = ""

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout

    def get(self, path: str = "", params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict:
        response = requests.get(
            f"{self.base_url}{path}",
            params=params or {},
            headers=headers or {},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
