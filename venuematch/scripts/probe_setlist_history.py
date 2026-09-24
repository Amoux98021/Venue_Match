from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from time import monotonic, sleep
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.setlist_history_probe import (
    ProbeRequestCapReached,
    run_setlist_history_probe,
    write_setlist_probe_artifacts,
)


class TransientSetlistProxyClient:
    def __init__(
        self,
        proxy_url: str,
        bearer_token: str,
        minimum_interval: float = 1.0,
        timeout: int = 60,
        hard_request_cap: int = 500,
        maximum_provider_attempts: int = 2,
    ) -> None:
        self.proxy_url = proxy_url.rstrip("/")
        self.bearer_token = bearer_token
        self.minimum_interval = max(minimum_interval, 1.0)
        self.timeout = timeout
        self.hard_request_cap = hard_request_cap
        self.maximum_provider_attempts = maximum_provider_attempts
        self._last_request_at: float | None = None
        self.request_count = 0
        self.retry_count = 0
        self.throttle_count = 0
        self.not_found_count = 0
        self.status_counts: Counter[int] = Counter()
        self.rate_limit_observations: dict[str, str] = {}

    def _wait(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = monotonic() - self._last_request_at
        if elapsed < self.minimum_interval:
            sleep(self.minimum_interval - elapsed)

    def get_artist_setlists(self, artist_mbid: str, page: int = 1) -> dict[str, Any]:
        if self.request_count > self.hard_request_cap - self.maximum_provider_attempts:
            raise ProbeRequestCapReached(
                f"Setlist.fm probe stopped before the {self.hard_request_cap}-request cap"
            )
        self._wait()
        response = requests.get(
            f"{self.proxy_url}/evaluation/setlist-probe-page/{artist_mbid}",
            params={"page": page},
            headers={"Authorization": f"Bearer {self.bearer_token}"},
            timeout=self.timeout,
        )
        self._last_request_at = monotonic()
        response.raise_for_status()
        envelope = response.json()
        payload = envelope["payload"]
        health = envelope["provider_health"]
        self.request_count += int(health.get("requests", 0))
        self.retry_count += int(health.get("retries", 0))
        self.throttle_count += int(health.get("throttles", 0))
        self.not_found_count += int(health.get("not_found", 0))
        self.status_counts.update(
            {int(key): int(value) for key, value in health.get("status_counts", {}).items()}
        )
        self.rate_limit_observations.update(health.get("rate_limit_headers", {}))
        return payload

    def health_summary(self) -> dict[str, Any]:
        return {
            "requests": self.request_count,
            "retries": self.retry_count,
            "throttles": self.throttle_count,
            "not_found": self.not_found_count,
            "status_counts": dict(sorted(self.status_counts.items())),
            "rate_limit_headers": dict(sorted(self.rate_limit_observations.items())),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the transient Setlist.fm history probe.")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--musicbrainz-prior", type=Path)
    parser.add_argument("--proxy-url", required=True)
    parser.add_argument("--bearer-token-file", type=Path, required=True)
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/setlist_history_probe"),
    )
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    prior = (
        json.loads(args.musicbrainz_prior.read_text(encoding="utf-8"))
        if args.musicbrainz_prior
        else None
    )
    token = args.bearer_token_file.read_text(encoding="utf-8").strip()
    client = TransientSetlistProxyClient(args.proxy_url, token)
    result = run_setlist_history_probe(
        snapshot,
        client,
        musicbrainz_prior=prior,
        max_pages_per_artist=max(args.max_pages, 1),
    )
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
