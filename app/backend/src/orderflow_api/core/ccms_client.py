"""Event-Driven CCMS Integration (P1-5).

Two ingestion paths:

1. **Webhook** — `POST /webhooks/ccms` accepts push events from the court
   CMS / eCourts gateway. Each event references either a direct PDF URL
   or an eCourts identifier. We resolve the document, persist it, and
   trigger the existing intake pipeline.

2. **Polling client** — when an upstream gateway can't push, we poll a
   public endpoint for new judgments and process whatever's new.
   Configured via `ORDERFLOW_CCMS_POLL_URL`. The default points at the
   Delhi High Court public judgment feed for a working demo.

If both upstream connections are unavailable, the simulator script
(`scripts/simulate_ccms_event.py`) calls the same webhook with realistic
payloads. The system is real where it can be, and demoable everywhere
else.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from orderflow_api.api.indian_ecourts_lookup import lookup_indian_ecourts_prefill
from orderflow_api.api.document_persistence import (
    find_document_by_checksum,
    persist_uploaded_document,
)
from orderflow_api.api.intake_adapter import build_indian_ecourts_document_payload

logger = logging.getLogger(__name__)


# A public Delhi High Court endpoint that returns recent judgments.
# Override at runtime via ORDERFLOW_CCMS_POLL_URL when integrating with
# a real CCMS sandbox.
DEFAULT_POLL_URL = "https://delhihighcourt.nic.in/web/hi/judgement/fetch-data"
USER_AGENT = "OrderFlow-CCMS/1.0 (+contact: software@kshaminnovation.in)"
POLL_TIMEOUT_SECONDS = 20


@dataclass
class CCMSEvent:
    """A single judgment that needs to be ingested."""

    reference_id: str
    identifier: str  # eCourts identifier OR direct PDF URL
    document_type: str = "judgment"
    delivery_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_gateway: str = "ccms"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestResult:
    reference_id: str
    document_id: str | None
    status: str  # "ingested" | "duplicate" | "failed"
    detail: str = ""


def _resolve_poll_url() -> str:
    return os.environ.get("ORDERFLOW_CCMS_POLL_URL") or DEFAULT_POLL_URL


def fetch_latest_events(limit: int = 5) -> list[CCMSEvent]:
    """Fetch a small batch of recent judgments from the configured feed.

    Returns an empty list on any error; the caller decides whether that
    is a problem (e.g. surface to ops) or just silently retry later.
    """
    url = _resolve_poll_url()
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=POLL_TIMEOUT_SECONDS) as response:
            raw_bytes = response.read()
    except (URLError, TimeoutError) as exc:
        logger.warning("CCMS poll failed (%s): %s", url, exc)
        return []
    except Exception as exc:
        logger.warning("CCMS poll unexpected error (%s): %s", url, exc)
        return []

    body = raw_bytes.decode("utf-8", errors="replace")

    # Two shapes are common: JSON array of objects, or HTML-with-links.
    # Prefer JSON if we can parse it, otherwise return [] and let the
    # caller fall back to the webhook path.
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        logger.info(
            "CCMS feed at %s did not return JSON; skipping until webhook event arrives.",
            url,
        )
        return []

    events: list[CCMSEvent] = []
    candidates: list[dict] = []
    if isinstance(parsed, list):
        candidates = [c for c in parsed if isinstance(c, dict)]
    elif isinstance(parsed, dict):
        for key in ("data", "items", "results", "judgements", "judgments"):
            value = parsed.get(key)
            if isinstance(value, list):
                candidates = [c for c in value if isinstance(c, dict)]
                break

    for entry in candidates[:limit]:
        identifier = (
            entry.get("identifier")
            or entry.get("source_url")
            or entry.get("url")
            or entry.get("pdf_url")
        )
        if not isinstance(identifier, str) or not identifier.strip():
            continue
        reference_id = (
            str(entry.get("reference_id"))
            if entry.get("reference_id")
            else f"CCMS-AUTO-{abs(hash(identifier)) % 10**12}"
        )
        events.append(
            CCMSEvent(
                reference_id=reference_id,
                identifier=identifier.strip(),
                document_type=str(entry.get("document_type", "judgment")),
                source_gateway=str(entry.get("source_gateway", "ccms")),
                raw=entry,
            )
        )

    return events


def ingest_event(event: CCMSEvent) -> IngestResult:
    """Resolve, deduplicate, and persist a single CCMS event.

    Reuses the existing eCourts lookup pipeline so a document arrives
    with the same metadata shape as a manual upload.
    """
    try:
        lookup = lookup_indian_ecourts_prefill(event.identifier)
    except Exception as exc:
        return IngestResult(
            reference_id=event.reference_id,
            document_id=None,
            status="failed",
            detail=f"eCourts resolution failed: {exc}",
        )

    import base64

    try:
        payload = base64.b64decode(lookup.file_content_base64)
    except Exception as exc:
        return IngestResult(
            reference_id=event.reference_id,
            document_id=None,
            status="failed",
            detail=f"PDF decode failed: {exc}",
        )

    if not payload:
        return IngestResult(
            reference_id=event.reference_id,
            document_id=None,
            status="failed",
            detail="eCourts lookup returned no PDF payload.",
        )

    # Override the auto CCMS reference with the one we received over the wire
    # so audit trails point back at the upstream event.
    intake = lookup.envelope
    intake.ccms.reference_id = event.reference_id
    intake.ccms.delivery_timestamp = event.delivery_timestamp
    intake.ccms.source_gateway = event.source_gateway

    resolved_file_name, resolved_file_type, metadata = build_indian_ecourts_document_payload(
        envelope=intake,
        upload_file_name=lookup.source_file_name,
        upload_content_type=lookup.source_file_type,
    )

    # Dedup by checksum so re-delivered events don't create duplicates.
    import hashlib

    checksum = hashlib.sha256(payload).hexdigest()
    existing = _safe_find_document_by_checksum(checksum)
    if existing is not None:
        return IngestResult(
            reference_id=event.reference_id,
            document_id=str(existing.id),
            status="duplicate",
            detail="Document with matching checksum already ingested.",
        )

    try:
        document = persist_uploaded_document(
            source_file_name=resolved_file_name,
            source_file_type=resolved_file_type,
            payload=payload,
            metadata=metadata,
        )
    except Exception as exc:
        return IngestResult(
            reference_id=event.reference_id,
            document_id=None,
            status="failed",
            detail=f"Persistence failed: {exc}",
        )

    return IngestResult(
        reference_id=event.reference_id,
        document_id=str(document.id),
        status="ingested",
        detail="Event ingested and queued for extraction.",
    )


def _safe_find_document_by_checksum(checksum: str):
    try:
        return find_document_by_checksum(checksum)
    except Exception:
        return None


def poll_and_ingest(limit: int = 5) -> list[IngestResult]:
    """Convenience helper: pull the latest events and ingest each one."""
    events = fetch_latest_events(limit=limit)
    return [ingest_event(event) for event in events]
