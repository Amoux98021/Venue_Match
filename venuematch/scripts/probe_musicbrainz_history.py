from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from src.clients.musicbrainz_client import MusicBrainzClient
from src.evaluation.musicbrainz_history_probe import (
    run_musicbrainz_history_probe,
    write_musicbrainz_probe_artifacts,
)


def load_snapshot(input_file: Path | None, input_url: str | None) -> dict:
    if input_file:
        return json.loads(input_file.read_text(encoding="utf-8"))
    if not input_url:
        raise ValueError("Provide --input-file or --input-url")
    headers = {"User-Agent": "VenueMatch-MusicBrainz-Probe/1.0"}
    export_secret = os.getenv("PROBE_EXPORT_SECRET")
    if export_secret:
        headers["Authorization"] = f"Bearer {export_secret}"
    request = Request(input_url, headers=headers)
    with urlopen(request, timeout=120) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only MusicBrainz history probe.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-file", type=Path)
    source.add_argument("--input-url")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/musicbrainz_history_probe"),
    )
    args = parser.parse_args()

    snapshot = load_snapshot(args.input_file, args.input_url)
    result = run_musicbrainz_history_probe(snapshot, MusicBrainzClient())
    output_dir = write_musicbrainz_probe_artifacts(result, args.output_dir)
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "api_requests_used": result["api_requests_used"],
                "summary": result["summary"],
                "decision": result["decision"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
