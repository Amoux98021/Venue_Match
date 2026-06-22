from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.seed import seed_sample_data


if __name__ == "__main__":
    path = seed_sample_data(overwrite=True)
    print(f"Seeded sample data into {path}")
