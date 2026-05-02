"""Print every case id the eCourts intake can resolve right now.

Two sources:
1. Bundled local samples (always work)
2. Live DHC latest-judgments scrape (changes daily)

Usage:
    python -m scripts.list_resolvable_case_ids
    python -m scripts.list_resolvable_case_ids --type "W.P.(C)"
    python -m scripts.list_resolvable_case_ids --limit 50

Anything printed here can be pasted into the Intake page > "case identifier"
field. Beyond this list, you can always paste a full DHC URL or a bare
showFileJudgment token.
"""

from __future__ import annotations

import argparse
import re
import socket
import sys
from collections import defaultdict

from orderflow_api.api.indian_ecourts_lookup import (
    _fetch_latest_judgment_links,
    _load_local_case_sample_map,
)

CASE_TOKEN_PATTERN = re.compile(
    r"/showFileJudgment/(\d+)([A-Z]+?)(\d+)((?:19|20)\d{2})_"
)

CODE_TO_LABEL = {
    "CW": "W.P.(C)",
    "CRLW": "W.P.(CRL)",
    "CRLA": "CRL.A.",
    "CRLMA": "CRL.M.A.",
    "CRLMM": "CRL.M.M.",
    "BA": "BAIL APPLN.",
    "LPA": "LPA",
    "FAO": "FAO",
    "AA": "AA",
    "OMPCOMM": "O.M.P.(COMM)",
    "OMPICOMM": "O.M.P.(I)(COMM)",
    "OMPENFCOMM": "O.M.P.(ENF)(COMM)",
    "CS": "CS",
    "RFA": "RFA",
    "CCP": "CCP",
    "CMA": "CMA",
    "ARBACOMM": "ARB.A.(COMM.)",
    "CRLR": "CRL.REV.P.",
    "OMPMISCCOMM": "O.M.P.(MISC)(COMM)",
    "OMPTCOMM": "O.M.P.(T)(COMM)",
    "RFAC": "RFA(COMM)",
    "EP": "EP",
    "SC": "SC",
    "EX": "EX",
    "FAOC": "FAO(COMM)",
    "ESA": "ESA",
    "FAC": "FA(COMM)",
    "CMM": "CMM",
    "RCR": "RCR",
    "S": "S",
    "OMP": "OMP",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--type",
        default=None,
        help='Filter by case-type label, e.g. "W.P.(C)"',
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows to print per case type",
    )
    parser.add_argument(
        "--with-urls",
        action="store_true",
        help="Print the resolved DHC URL alongside each case id",
    )
    args = parser.parse_args()

    socket.setdefaulttimeout(30)

    # 1. Bundled samples
    samples = _load_local_case_sample_map()
    print("=" * 72)
    print(f"BUNDLED SAMPLES ({len(samples)} cases — always resolve via case id):")
    print("=" * 72)
    for normalized in sorted(samples.keys()):
        print(f"  {normalized}    [URL: {samples[normalized]}]")
    print()

    # 2. Live scrape
    print("=" * 72)
    print("LIVE DHC LATEST-JUDGMENTS (rotates daily):")
    print("=" * 72)
    try:
        links = _fetch_latest_judgment_links()
    except Exception as exc:
        print(f"  Could not fetch live list: {exc}")
        return 1

    buckets: dict[str, list[tuple[str, str]]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for link in links:
        match = CASE_TOKEN_PATTERN.search(link)
        if not match:
            continue
        _, code, num, year = match.groups()
        key = (code, num, year)
        if key in seen:
            continue
        seen.add(key)
        label = CODE_TO_LABEL.get(code, code)
        buckets[label].append((f"{label} {num}/{year}", link))

    total = sum(len(v) for v in buckets.values())
    print(f"  Total unique cases live: {total}")
    print()

    case_types = (
        [args.type] if args.type else sorted(buckets.keys(), key=lambda k: -len(buckets[k]))
    )
    for label in case_types:
        cases = buckets.get(label, [])
        if not cases:
            if args.type:
                print(f"  No cases on the live list for type '{args.type}'.")
            continue
        rows = cases if args.limit is None else cases[: args.limit]
        print(f"-- {label}  ({len(cases)} cases on live list) --")
        for case_id, url in rows:
            if args.with_urls:
                print(f"   {case_id}")
                print(f"      {url}")
            else:
                print(f"   {case_id}")
        if args.limit is not None and len(cases) > args.limit:
            print(f"   ... and {len(cases) - args.limit} more (raise --limit to see)")
        print()

    print("=" * 72)
    print(
        "Anything beyond this list: paste a full DHC URL or its bare token."
    )
    print("Examples:")
    print(
        "  https://delhihighcourt.nic.in/app/showFileJudgment/<token>.pdf"
    )
    print("  75005022026CW85242025_154137  (just the token)")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
