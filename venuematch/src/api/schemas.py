from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ArtistVenueRequest(BaseModel):
    artist_name: str = Field(min_length=1, max_length=200)
    target_city: str = Field(min_length=1, max_length=120)
    top_n: int = Field(default=10, ge=1, le=25)


class VenueArtistRequest(BaseModel):
    venue_name_or_city: str = Field(min_length=1, max_length=200)
    top_n: int = Field(default=10, ge=1, le=25)


class RecommendationResponse(BaseModel):
    explanation: str
    results: list[dict[str, Any]]
    weights: dict[str, float]
