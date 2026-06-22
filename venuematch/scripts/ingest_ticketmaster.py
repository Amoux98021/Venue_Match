from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.clients.ticketmaster_client import TicketmasterClient
from src.utils.config import PROJECT_ROOT, credentials_available
from src.utils.io import write_json


def main() -> None:
    output_path = PROJECT_ROOT / "data" / "raw" / "ticketmaster_events.json"
    client = TicketmasterClient()
    if not credentials_available()["ticketmaster"]:
        write_json(output_path, {"source": "mock", "events": [], "note": "Missing TICKETMASTER_API_KEY"})
        print(f"Wrote mock Ticketmaster payload to {output_path}")
        return

    payload = client.search_events(keyword="concert", size=50)
    write_json(output_path, payload)
    print(f"Wrote Ticketmaster payload to {output_path}")


if __name__ == "__main__":
    main()
