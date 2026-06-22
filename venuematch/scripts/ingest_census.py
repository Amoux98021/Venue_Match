from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.clients.census_client import CensusClient
from src.utils.config import PROJECT_ROOT
from src.utils.io import write_json


def main() -> None:
    output_path = PROJECT_ROOT / "data" / "raw" / "census_city_profile.json"
    client = CensusClient()
    payload = client.get_city_profile(state_fips="11", place_fips="50000")
    write_json(output_path, {"source": "api", "payload": payload})
    print(f"Wrote Census payload to {output_path}")


if __name__ == "__main__":
    main()
