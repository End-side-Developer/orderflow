"""Public-Trust Mode read-only routes (P1-4).

Exposes a PII-redacted projection of obligations so citizens can see what
courts have directed and how compliance is tracking, without identifying
individual parties or officers.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Query, Request

from orderflow_api.api.extraction_persistence import list_persisted_obligations
from orderflow_api.api.response import success
from orderflow_api.api.stub_repository import list_obligations as list_stub_obligations
from orderflow_api.core.redaction_service import redact_obligations
from orderflow_api.core.risk_service import annotate_obligations_with_risk
from orderflow_api.schemas.public import (
    PublicObligationItem,
    PublicObligationsData,
    PublicObligationsEnvelope,
)

router = APIRouter(tags=["public"])


@router.get("/public/obligations", response_model=PublicObligationsEnvelope)
async def list_public_obligations_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)

    persisted = _safe_list_persisted()
    stub = list_stub_obligations(document_id=None) or []

    combined = [*persisted, *stub]
    annotate_obligations_with_risk(combined)
    combined = combined[:limit]

    redacted_dicts = redact_obligations(combined)

    items = [PublicObligationItem(**item) for item in redacted_dicts]

    summary = Counter()
    for item in items:
        for key, value in item.redaction.items():
            summary[key] += int(value)

    data = PublicObligationsData(
        total=len(items),
        redacted_count_summary=dict(summary),
        items=items,
    )
    return success(data=data, request_id=request_id, message="public_view")


def _safe_list_persisted() -> list:
    try:
        return list_persisted_obligations(document_id=None)
    except Exception:
        return []
