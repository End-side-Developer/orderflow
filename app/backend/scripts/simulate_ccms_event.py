"""Fire a sample CCMS webhook event at the running OrderFlow API.

Used for hackathon demo when an upstream CCMS sandbox is unavailable.
Posts a realistic event payload to /api/v1/webhooks/ccms; the backend
runs the same intake pipeline as a manual upload.

Usage:
    python -m scripts.simulate_ccms_event
    python -m scripts.simulate_ccms_event \\
        --identifier "https://delhihighcourt.nic.in/app/showFileJudgment/<token>.pdf"
    python -m scripts.simulate_ccms_event --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SAMPLE_IDENTIFIERS = [
    "W.P.(C) 8524/2025",
    "W.P.(C) 8523/2025",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the OrderFlow API (default: http://localhost:8000).",
    )
    parser.add_argument(
        "--identifier",
        action="append",
        default=None,
        help=(
            "eCourts identifier or PDF URL (repeatable). Defaults to a small "
            "set of public DHC sample case ids."
        ),
    )
    parser.add_argument(
        "--reference-id",
        default=None,
        help="Override the CCMS reference id for the first event (optional).",
    )
    args = parser.parse_args()

    identifiers = args.identifier or SAMPLE_IDENTIFIERS
    now = datetime.now(timezone.utc).isoformat()

    events = []
    for index, identifier in enumerate(identifiers):
        events.append(
            {
                "reference_id": (
                    args.reference_id
                    if index == 0 and args.reference_id
                    else f"CCMS-DEMO-{int(datetime.now().timestamp())}-{index}"
                ),
                "identifier": identifier,
                "document_type": "judgment",
                "delivery_timestamp": now,
                "source_gateway": "ccms-sim",
            }
        )

    url = f"{args.base_url.rstrip('/')}/api/v1/webhooks/ccms"
    body = json.dumps({"events": events}).encode("utf-8")
    print(f"POST {url}")
    print(json.dumps(events, indent=2))

    req = Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=120) as response:
            print(f"Status: {response.status}")
            print(response.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode('utf-8')}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"URL error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
