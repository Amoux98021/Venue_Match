from __future__ import annotations

import argparse
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation import run_historical_data_audit, write_audit_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a read-only VenueMatch historical-data audit."
    )
    parser.add_argument(
        "--database-url",
        help="Optional SQLAlchemy database URL or SQLite path. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--api-url",
        help="Optional deployed VenueMatch API URL. Fetches its read-only audit endpoint.",
    )
    parser.add_argument(
        "--as-of",
        help="UTC audit date in YYYY-MM-DD format. Defaults to the current UTC date.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "reports" / "historical_audit"),
        help="Artifact output directory.",
    )
    return parser.parse_args()


def fetch_audit(api_url: str, as_of: str | None) -> dict:
    params = {"as_of": as_of} if as_of else None
    response = requests.get(
        f"{api_url.rstrip('/')}/evaluation/historical-audit",
        params=params,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    args = parse_args()
    if args.api_url and args.database_url:
        raise SystemExit("Choose either --api-url or --database-url, not both.")
    audit = (
        fetch_audit(args.api_url, args.as_of)
        if args.api_url
        else run_historical_data_audit(db_target=args.database_url, as_of=args.as_of)
    )
    output = write_audit_artifacts(audit, args.output_dir)
    summary = audit["benchmark_eligibility"]
    print(f"Wrote historical audit artifacts to {output}")
    print(f"Historical relationships: {audit['temporal_coverage']['historical_event_relationships']}")
    print(f"Benchmark eligible: {summary['eligible_historical_bookings']}")
    print(f"Setlist decision: {audit['setlist_recommendation']['decision']}")


if __name__ == "__main__":
    main()
