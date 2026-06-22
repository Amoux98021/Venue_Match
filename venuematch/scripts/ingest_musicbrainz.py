from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.clients.musicbrainz_client import MusicBrainzClient
from src.utils.config import PROJECT_ROOT
from src.utils.io import write_json


def main() -> None:
    output_path = PROJECT_ROOT / "data" / "raw" / "musicbrainz_artists.json"
    client = MusicBrainzClient()
    payload = client.search_artist("The District Echoes")
    write_json(output_path, payload)
    print(f"Wrote MusicBrainz payload to {output_path}")


if __name__ == "__main__":
    main()
