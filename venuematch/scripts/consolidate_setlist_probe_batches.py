from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.setlist_history_probe import (
    consolidate_setlist_probe_batches,
    write_setlist_probe_artifacts,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolidate sanitized Setlist.fm probe batches."
    )
    parser.add_argument("--batches", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/setlist_history_probe"),
    )
    args = parser.parse_args()
    batches = json.loads(args.batches.read_text(encoding="utf-8"))
    if not isinstance(batches, list):
        raise ValueError("Batch input must be a JSON list")
    result = consolidate_setlist_probe_batches(batches)
    write_setlist_probe_artifacts(result, args.output_dir)
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "summary": result["summary"],
                "request_metrics": result["request_metrics"],
                "decision": result["decision"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
