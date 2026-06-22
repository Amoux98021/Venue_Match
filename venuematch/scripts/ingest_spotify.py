from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.clients.spotify_client import SpotifyClient
from src.utils.config import PROJECT_ROOT, credentials_available
from src.utils.io import write_json


def main() -> None:
    output_path = PROJECT_ROOT / "data" / "raw" / "spotify_artists.json"
    client = SpotifyClient()
    if not credentials_available()["spotify"]:
        write_json(output_path, {"source": "mock", "artists": {"items": []}, "note": "Missing Spotify credentials"})
        print(f"Wrote mock Spotify payload to {output_path}")
        return

    payload = client.search_artist("The District Echoes")
    write_json(output_path, payload)
    print(f"Wrote Spotify payload to {output_path}")


if __name__ == "__main__":
    main()
