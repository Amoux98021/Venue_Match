from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.seed import seed_sample_data


if __name__ == "__main__":
    database_url = seed_sample_data(overwrite=False)
    print(f"VenueMatch database is ready at {database_url}")
