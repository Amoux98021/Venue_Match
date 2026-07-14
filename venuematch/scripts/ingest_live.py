from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingestion import run_live_ingestion


def main() -> None:
    print(json.dumps(asdict(run_live_ingestion()), indent=2))


if __name__ == "__main__":
    main()
