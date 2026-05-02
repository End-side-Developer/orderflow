"""CCMS webhook + poll routes (P1-5)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from orderflow_api.api.response import success
from orderflow_api.core.ccms_client import (
    CCMSEvent,
    ingest_event,
    poll_and_ingest,
)
from orderflow_api.schemas.webhooks import (
    CCMSIngestResultItem,
    CCMSPollData,
    CCMSPollEnvelope,
    CCMSWebhookData,
    CCMSWebhookEnvelope,
    CCMSWebhookRequest,
)

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/ccms", response_model=CCMSWebhookEnvelope)
async def ccms_webhook_route(
    request: Request,
    payload: CCMSWebhookRequest,
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)

    items: list[CCMSIngestResultItem] = []
    for event in payload.events:
        result = ingest_event(
            CCMSEvent(
                reference_id=event.reference_id,
                identifier=event.identifier,
                document_type=event.document_type,
                delivery_timestamp=(
                    event.delivery_timestamp or datetime.now(timezone.utc)
                ),
                source_gateway=event.source_gateway,
            )
        )
        items.append(
            CCMSIngestResultItem(
                reference_id=result.reference_id,
                document_id=result.document_id,
                status=result.status,
                detail=result.detail,
            )
        )

    data = CCMSWebhookData(
        received=len(items),
        ingested=sum(1 for i in items if i.status == "ingested"),
        duplicates=sum(1 for i in items if i.status == "duplicate"),
        failed=sum(1 for i in items if i.status == "failed"),
        results=items,
    )
    return success(data=data, request_id=request_id, message="ccms_events_processed")


@router.post("/webhooks/ccms/poll", response_model=CCMSPollEnvelope)
async def ccms_poll_route(
    request: Request,
    limit: int = Query(default=5, ge=1, le=50),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    results = poll_and_ingest(limit=limit)
    items = [
        CCMSIngestResultItem(
            reference_id=r.reference_id,
            document_id=r.document_id,
            status=r.status,
            detail=r.detail,
        )
        for r in results
    ]
    data = CCMSPollData(
        polled=len(items),
        ingested=sum(1 for i in items if i.status == "ingested"),
        duplicates=sum(1 for i in items if i.status == "duplicate"),
        failed=sum(1 for i in items if i.status == "failed"),
        results=items,
    )
    return success(data=data, request_id=request_id, message="ccms_polled")
