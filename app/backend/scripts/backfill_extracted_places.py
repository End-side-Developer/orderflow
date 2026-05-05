"""Backfill map-ready extracted places for legacy page summaries.

Usage (from app/backend):
    python -m scripts.backfill_extracted_places --dry-run --limit 50
    python -m scripts.backfill_extracted_places --limit 200 --batch-size 20

Safe to re-run. It only selects rows where `page_summaries.extracted_places IS NULL`.
Failed rows remain NULL so a later run can retry them.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import logging
from time import perf_counter
import sys
from uuid import UUID

from orderflow_api.api.document_persistence import get_persisted_document
from orderflow_api.api.page_summary_engine import PageSummaryExtractor
from orderflow_api.api.page_summary_persistence import (
    list_page_summaries_missing_extracted_places,
    update_page_summary_places,
)
from orderflow_api.core.config import settings
from orderflow_api.schemas.page_summaries import PageSummaryRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CisHints:
    state: str | None
    district: str | None
    court_fallback_query: str | None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill extracted_places for page summaries that have not been processed."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum page summaries to inspect in this run (default: 200).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Rows to process per database batch in write mode (default: 20).",
    )
    parser.add_argument(
        "--ai-provider",
        default=None,
        help="Override AI provider. Defaults to ORDERFLOW_AI_DEFAULT_PROVIDER.",
    )
    parser.add_argument(
        "--ai-model",
        default=None,
        help="Override AI model. Defaults to ORDERFLOW_AI_DEFAULT_MODEL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report candidate pages without extracting, geocoding, or writing.",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Return a non-zero exit code if any page fails.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> int:
    limit = max(1, args.limit)
    batch_size = max(1, args.batch_size)
    provider = args.ai_provider or settings.orderflow_ai_default_provider
    model = args.ai_model or settings.orderflow_ai_default_model
    extractor = PageSummaryExtractor(
        ai_provider=provider,
        model=model,
        api_key=_api_key_for_provider(provider),
        temperature=0.1,
    )

    started_at = perf_counter()
    inspected = 0
    updated = 0
    skipped_empty = 0
    failed = 0
    attempted_ids: set[UUID] = set()
    hints_by_document: dict[UUID, CisHints] = {}

    while inspected < limit:
        remaining = limit - inspected
        fetch_limit = remaining if args.dry_run else min(batch_size, remaining)
        batch = list_page_summaries_missing_extracted_places(
            limit=fetch_limit,
            exclude_ids=attempted_ids,
        )
        if not batch:
            break

        for summary in batch:
            inspected += 1
            attempted_ids.add(summary.id)

            if args.dry_run:
                _print_dry_run_candidate(summary)
                continue

            try:
                page_text = summary.page_text or ""
                if not page_text.strip():
                    update_page_summary_places(summary.id, [])
                    skipped_empty += 1
                    print(
                        "Skipped empty page "
                        f"document={summary.document_id} page={summary.page_number}.",
                        flush=True,
                    )
                    continue

                hints = _hints_for_document(summary.document_id, hints_by_document)
                places = await extractor.extract_places_for_page(
                    page_num=summary.page_number,
                    page_text=page_text,
                    state_hint=hints.state,
                    district_hint=hints.district,
                    court_fallback_query=hints.court_fallback_query,
                )
                update_page_summary_places(summary.id, places)
                updated += 1
                pinned = sum(
                    1
                    for place in places
                    if place.lat is not None and place.lng is not None
                )
                print(
                    "Backfilled places "
                    f"document={summary.document_id} page={summary.page_number} "
                    f"places={len(places)} pinned={pinned}.",
                    flush=True,
                )
            except Exception:
                failed += 1
                logger.exception(
                    "Failed to backfill places for document=%s page=%s summary=%s",
                    summary.document_id,
                    summary.page_number,
                    summary.id,
                )

        if args.dry_run:
            break

    elapsed = perf_counter() - started_at
    print(
        "Done. "
        f"inspected={inspected} updated={updated} skipped_empty={skipped_empty} "
        f"failed={failed} elapsed_seconds={elapsed:.1f}.",
        flush=True,
    )
    if failed and args.fail_on_error:
        return 1
    return 0


def _print_dry_run_candidate(summary: PageSummaryRecord) -> None:
    page_text = summary.page_text or ""
    print(
        "Would refresh "
        f"document={summary.document_id} page={summary.page_number} "
        f"summary={summary.id} page_text_chars={len(page_text)}.",
        flush=True,
    )


def _hints_for_document(
    document_id: UUID,
    cache: dict[UUID, CisHints],
) -> CisHints:
    if document_id not in cache:
        document = get_persisted_document(document_id)
        metadata = document.metadata if document is not None and document.metadata else {}
        cache[document_id] = _extract_cis_hints(metadata)
    return cache[document_id]


def _extract_cis_hints(metadata: dict[str, object]) -> CisHints:
    cis = metadata.get("cis")
    if not isinstance(cis, dict):
        return CisHints(state=None, district=None, court_fallback_query=None)

    state = _string_or_none(cis.get("state"))
    district = _string_or_none(cis.get("district"))
    court_name = _string_or_none(cis.get("court_name"))
    fallback_parts = [court_name, district, state, "India"]
    court_fallback_query = ", ".join(part for part in fallback_parts if part)
    return CisHints(
        state=state,
        district=district,
        court_fallback_query=court_fallback_query or None,
    )


def _api_key_for_provider(provider: str) -> str | None:
    if provider == "gemini":
        return settings.orderflow_ai_gemini_api_key
    if provider == "openai":
        return settings.orderflow_ai_openai_api_key
    if provider == "anthropic":
        return settings.orderflow_ai_anthropic_api_key
    return None


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


if __name__ == "__main__":
    sys.exit(main())
