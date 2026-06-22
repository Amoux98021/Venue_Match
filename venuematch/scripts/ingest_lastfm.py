from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.clients.lastfm_client import LastFMClient
from src.utils.config import PROJECT_ROOT, credentials_available
from src.utils.io import write_json


def main() -> None:
    output_path = PROJECT_ROOT / "data" / "raw" / "lastfm_tags.json"
    client = LastFMClient()
    if not credentials_available()["lastfm"]:
        write_json(output_path, {"source": "mock", "toptags": {"tag": []}, "note": "Missing LASTFM_API_KEY"})
        print(f"Wrote mock Last.fm payload to {output_path}")
        return

    payload = client.get_artist_tags("The District Echoes")
    write_json(output_path, payload)
    print(f"Wrote Last.fm payload to {output_path}")


if __name__ == "__main__":
    main()
