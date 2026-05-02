"""Backfill embeddings for obligations rows that are missing one.

Usage (from app/backend):
    python -m scripts.backfill_embeddings [--limit N]

Iterates in batches until no rows remain or the optional limit is hit.
Safe to re-run; only touches rows where `embedding IS NULL`.
"""

from __future__ import annotations

import argparse
import logging
import sys

from orderflow_api.core.clustering_service import backfill_missing_embeddings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=2000,
        help="Maximum rows to process in a single run (default: 2000).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Per-iteration batch size (default: 500).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    total = 0
    while total < args.limit:
        remaining = args.limit - total
        chunk = min(args.batch_size, remaining)
        updated = backfill_missing_embeddings(limit=chunk)
        if updated == 0:
            break
        total += updated
        print(f"Backfilled {updated} embeddings ({total} total).", flush=True)

    print(f"Done. Total embeddings written: {total}.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
