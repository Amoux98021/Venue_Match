from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
IS_VERCEL = os.getenv("VERCEL") == "1"
RUNTIME_DATA_ROOT = Path("/tmp/venuematch") if IS_VERCEL else PROJECT_ROOT / "data"
DEFAULT_DB_PATH = RUNTIME_DATA_ROOT / "processed" / "venuematch.db"
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample" / "mock_data.json"

load_dotenv(ENV_PATH, override=False)


def get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def get_database_url() -> str:
    raw_value = get_env("DATABASE_URL")
    if not raw_value:
        return f"sqlite:///{DEFAULT_DB_PATH}"
    if raw_value.startswith("sqlite:///"):
        sqlite_path = Path(raw_value.replace("sqlite:///", "", 1))
        if not sqlite_path.is_absolute():
            sqlite_path = PROJECT_ROOT / sqlite_path
        return f"sqlite:///{sqlite_path.resolve()}"
    return raw_value


def ensure_data_directories() -> None:
    (RUNTIME_DATA_ROOT / "raw").mkdir(parents=True, exist_ok=True)
    (RUNTIME_DATA_ROOT / "processed").mkdir(parents=True, exist_ok=True)


def credentials_available() -> dict[str, bool]:
    return {
        "ticketmaster": bool(get_env("TICKETMASTER_API_KEY")),
        "spotify": bool(get_env("SPOTIFY_CLIENT_ID") and get_env("SPOTIFY_CLIENT_SECRET")),
        "lastfm": bool(get_env("LASTFM_API_KEY")),
        "musicbrainz": bool(get_env("MUSICBRAINZ_USER_AGENT")),
        "census": bool(get_env("CENSUS_API_KEY")),
        "jambase": bool(get_env("JAMBASE_API_KEY")),
    }
