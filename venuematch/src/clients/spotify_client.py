from __future__ import annotations

from typing import Any

import requests

from src.utils.config import get_env


class SpotifyClient:
    auth_url = "https://accounts.spotify.com/api/token"
    base_url = "https://api.spotify.com/v1"

    def __init__(self) -> None:
        self.client_id = get_env("SPOTIFY_CLIENT_ID")
        self.client_secret = get_env("SPOTIFY_CLIENT_SECRET")

    def _get_token(self) -> str | None:
        if not self.client_id or not self.client_secret:
            return None
        response = requests.post(
            self.auth_url,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("access_token")

    def search_artist(self, artist_name: str) -> dict[str, Any]:
        token = self._get_token()
        if not token:
            return {"source": "mock", "artists": {"items": []}}
        response = requests.get(
            f"{self.base_url}/search",
            params={"q": artist_name, "type": "artist", "limit": 5},
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
