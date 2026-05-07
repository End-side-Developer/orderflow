"""Case-level gated intake flow routes.

This module is the API home for the per-document five-stage OrderFlow case
wizard. Endpoint leaves are added incrementally in the NF-07 checklist so
each stage gate can be verified without blurring route behavior.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from orderflow_api.api.dependencies.auth import audit_actor_from_request, require_permission
from orderflow_api.api.document_summary_persistence import get_document_summary
from orderflow_api.api.extraction_persistence import (
    get_persisted_obligation_by_id,
    list_persisted_obligations,
    record_persisted_obligation_audit_event,
    update_persisted_obligation,
)
from orderflow_api.api.intake_orchestrator import (
    ACTION_PLAN_ITEM_STAGES,
    APPROVED_ACTION_PLAN_ITEM_STAGES,
    IntakeActionItemNotFoundError,
    IntakeActionItemStageError,
    IntakeOrchestratorError,
    finalize_after_review,
    get_job_status,
    regenerate_action_item,
    request_action_plan_generation,
    request_summary_generation,
    start_intake,
    submit_review,
    to_http_exception,
)
from orderflow_api.api.page_summary_persistence import list_page_summaries
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.schemas.cases import (
    ActionPlanItemRegenerateData,
    ActionPlanItemRegenerateEnvelope,
    ActionPlanItemRegenerateRequest,
    ActionPlanItemReviewData,
    ActionPlanItemReviewEnvelope,
    ActionPlanItemReviewRequest,
    CaseDashboardData,
    CaseDashboardEnvelope,
    CaseDashboardGroup,
    CaseFinalizeData,
    CaseFinalizeEnvelope,
    CaseFinalizeRequest,
    DocumentSummaryEnvelope,
    ExtractionJobStatusEnvelope,
)
from orderflow_api.schemas.obligations import ObligationsEnvelope, ObligationsListData


router = APIRouter(tags=["cases"])

_ALLOWED_EDITED_STATUSES = {"draft", "active", "completed", "cancelled"}
_ALLOWED_EDITED_NATURES = {
    "compliance",
    "directive",
    "investigation",
    "report_filing",
    "payment",
    "notice",
    "appointment",
    "submission",
    "document_submission",
    "compliance_report",
    "policy",
    "policy_decision",
    "reconsideration",
    "hearing",
    "hearing_review",
    "appeal_review",
    "record_update",
    "other",
}


class CaseIntakeStartRequest(BaseModel):
    bypass_cache: bool = False
    pages_total: int = Field(default=0, ge=0)
    current_concurrency: int = Field(default=1, ge=1)
    ai_provider: str | None = None
    ai_model: str | None = None


@router.post(
    "/cases/{document_id}/intake/start",
    response_model=ExtractionJobStatusEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def start_case_intake_route(
    document_id: UUID,
    payload: CaseIntakeStartRequest | None = None,
    request: Request = None,
    _user=Depends(require_permission(Permission.EXTRACTION_RUN)),
) -> dict[str, object]:
    request_payload = payload or CaseIntakeStartRequest()
    request_id = getattr(request.state, "request_id", None) if request else None

    try:
        result = await start_intake(
            document_id,
            bypass_cache=request_payload.bypass_cache,
            pages_total=request_payload.pages_total,
            current_concurrency=request_payload.current_concurrency,
            ai_provider=request_payload.ai_provider,
            ai_model=request_payload.ai_model,
        )
    except IntakeOrchestratorError as exc:
        raise to_http_exception(exc) from exc

    message = "case_intake_started" if result.workflow_started else "case_intake_already_started"
    return success(data=result.job, request_id=request_id, message=message)


@router.get(
    "/cases/{document_id}/intake/status",
    response_model=ExtractionJobStatusEnvelope,
    status_code=status.HTTP_200_OK,
)
async def get_case_intake_status_route(
    document_id: UUID,
    request: Request = None,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None) if request else None

    try:
        job = get_job_status(document_id)
    except IntakeOrchestratorError as exc:
        raise to_http_exception(exc) from exc

    return success(data=job, request_id=request_id, message="case_intake_status")


@router.get(
    "/cases/{document_id}/intake/events",
    status_code=status.HTTP_200_OK,
)
async def stream_case_intake_events_route(
    document_id: UUID,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> StreamingResponse:
    try:
        get_job_status(document_id)
    except IntakeOrchestratorError as exc:
        raise to_http_exception(exc) from exc

    async def event_stream():
        terminal_stages = {"finalized", "failed"}
        last_snapshot: dict[str, object] | None = None
        max_iterations = 300  # ~10 minutes at 2s intervals
        poll_interval = 2.0

        for _ in range(max_iterations):
            try:
                current_job = get_job_status(document_id)
            except IntakeOrchestratorError:
                current_job = None

            if current_job is not None:
                snapshot = current_job.model_dump(mode="json")
                if snapshot == last_snapshot:
                    await asyncio.sleep(poll_interval)
                    continue

                last_snapshot = snapshot
                payload = {
                    "ok": True,
                    "message": "case_intake_status",
                    "data": snapshot,
                    "polling_fallback": f"/api/v1/cases/{document_id}/intake/status",
                }
                yield f"event: intake_status\ndata: {json.dumps(payload)}\n\n"

                if current_job.stage in terminal_stages:
                    return

            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


class CaseSummaryGenerateRequest(BaseModel):
    bypass_cache: bool = False


@router.post(
    "/cases/{document_id}/summary/generate",
    response_model=ExtractionJobStatusEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_case_summary_route(
    document_id: UUID,
    payload: CaseSummaryGenerateRequest | None = None,
    request: Request = None,
    _user=Depends(require_permission(Permission.EXTRACTION_RUN)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None) if request else None
    request_payload = payload or CaseSummaryGenerateRequest()

    if request_payload.bypass_cache:
        from orderflow_api.api.document_summary_persistence import delete_document_summary
        delete_document_summary(document_id)

    try:
        result = await request_summary_generation(document_id)
    except IntakeOrchestratorError as exc:
        raise to_http_exception(exc) from exc

    return success(
        data=result.job,
        request_id=request_id,
        message="case_summary_requested",
    )


@router.get(
    "/cases/{document_id}/summary",
    response_model=DocumentSummaryEnvelope,
    status_code=status.HTTP_200_OK,
)
async def get_case_summary_route(
    document_id: UUID,
    request: Request = None,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None) if request else None
    summary = get_document_summary(document_id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "document_summary_not_found",
                "message": f"Document summary not found: {document_id}",
            },
        )

    return success(data=summary, request_id=request_id, message="case_summary")


@router.post(
    "/cases/{document_id}/action-plan/generate",
    response_model=ExtractionJobStatusEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_case_action_plan_route(
    document_id: UUID,
    request: Request = None,
    _user=Depends(require_permission(Permission.EXTRACTION_RUN)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None) if request else None

    try:
        result = await request_action_plan_generation(document_id)
    except IntakeOrchestratorError as exc:
        raise to_http_exception(exc) from exc

    return success(
        data=result.job,
        request_id=request_id,
        message="case_action_plan_requested",
    )


@router.get(
    "/cases/{document_id}/action-plan",
    response_model=ObligationsEnvelope,
    status_code=status.HTTP_200_OK,
)
async def get_case_action_plan_route(
    document_id: UUID,
    request: Request = None,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None) if request else None
    items = [
        obligation
        for obligation in list_persisted_obligations(document_id)
        if obligation.action_plan_stage in ACTION_PLAN_ITEM_STAGES
    ]
    return success(
        data=ObligationsListData(document_id=document_id, total=len(items), items=items),
        request_id=request_id,
        message="case_action_plan",
    )


@router.post(
    "/cases/{document_id}/action-plan/items/{obligation_id}/review",
    response_model=ActionPlanItemReviewEnvelope,
    status_code=status.HTTP_200_OK,
)
async def review_case_action_plan_item_route(
    document_id: UUID,
    obligation_id: UUID,
    payload: ActionPlanItemReviewRequest,
    request: Request = None,
    _user=Depends(require_permission(Permission.OBLIGATION_WRITE)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None) if request else None
    actor_type, actor_id = (
        audit_actor_from_request(request) if request is not None else ("system", None)
    )

    try:
        submit_review(document_id)
        existing_obligation = _load_action_plan_item(document_id, obligation_id)
    except IntakeOrchestratorError as exc:
        raise to_http_exception(exc) from exc

    try:
        updated = update_persisted_obligation(
            obligation_id=obligation_id,
            **_review_update_values(payload),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "action_plan_review_update_failed",
                "message": f"Could not review action-plan item: {obligation_id}",
            },
        ) from exc

    if updated is None:
        raise to_http_exception(
            IntakeActionItemNotFoundError(
                f"Action-plan item not found for document {document_id}: {obligation_id}"
            )
        )

    _record_action_plan_review_audit(
        obligation_id=obligation_id,
        payload=payload,
        actor_type=actor_type,
        actor_id=actor_id,
        request_id=request_id,
        next_stage=updated.action_plan_stage,
        original_obligation=existing_obligation,
        updated_obligation=updated,
    )

    data = ActionPlanItemReviewData(
        document_id=document_id,
        obligation_id=obligation_id,
        decision=payload.decision,
        action_plan_stage=updated.action_plan_stage,
        obligation=updated,
        reviewer_name=payload.reviewer_name,
        rejection_reason=payload.rejection_reason,
        reviewed_at=updated.updated_at,
        comments=payload.comments,
    )
    return success(
        data=data,
        request_id=request_id,
        message="case_action_plan_item_reviewed",
    )


@router.post(
    "/cases/{document_id}/action-plan/items/{obligation_id}/regenerate",
    response_model=ActionPlanItemRegenerateEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_case_action_plan_item_route(
    document_id: UUID,
    obligation_id: UUID,
    payload: ActionPlanItemRegenerateRequest,
    request: Request = None,
    _user=Depends(require_permission(Permission.OBLIGATION_WRITE)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None) if request else None
    actor_type, actor_id = (
        audit_actor_from_request(request) if request is not None else ("system", None)
    )

    try:
        gate = regenerate_action_item(
            document_id=document_id,
            obligation_id=obligation_id,
            feedback=payload.feedback,
        )
    except IntakeOrchestratorError as exc:
        raise to_http_exception(exc) from exc

    regenerated_at = datetime.now(UTC)
    try:
        updated, updated_fields = _regenerate_action_item_from_cached_pages(
            gate=gate,
            feedback=gate.feedback,
            reviewer_name=payload.reviewer_name,
            actor_id=actor_id,
            regenerated_at=regenerated_at,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "action_plan_regeneration_failed",
                "message": f"Could not regenerate action-plan item: {obligation_id}",
            },
        ) from exc

    _record_action_plan_regeneration_request_audit(
        obligation_id=obligation_id,
        feedback=gate.feedback,
        reviewer_name=payload.reviewer_name,
        actor_type=actor_type,
        actor_id=actor_id,
        request_id=request_id,
        original_obligation=gate.obligation,
        updated_obligation=updated,
        updated_fields=updated_fields,
        regenerated_at=regenerated_at,
    )

    data = ActionPlanItemRegenerateData(
        document_id=document_id,
        obligation_id=obligation_id,
        action_plan_stage=updated.action_plan_stage,
        regen_count=updated.regen_count,
        obligation=updated,
        updated_fields=updated_fields,
        regenerated_at=regenerated_at,
    )
    return success(
        data=data,
        request_id=request_id,
        message="case_action_plan_item_regenerated",
    )


@router.post(
    "/cases/{document_id}/finalize",
    response_model=CaseFinalizeEnvelope,
    status_code=status.HTTP_200_OK,
)
async def finalize_case_route(
    document_id: UUID,
    payload: CaseFinalizeRequest | None = None,
    request: Request = None,
    _user=Depends(require_permission(Permission.OBLIGATION_WRITE)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None) if request else None

    try:
        result = await finalize_after_review(document_id)
    except IntakeOrchestratorError as exc:
        raise to_http_exception(exc) from exc

    data = CaseFinalizeData(
        document_id=document_id,
        approved_count=result.approved_count,
        edited_count=result.edited_count,
        rejected_count=result.rejected_count,
        finalized_at=result.job.finalized_at,
    )
    return success(data=data, request_id=request_id, message="case_finalized")


@router.get(
    "/cases/{document_id}/dashboard",
    response_model=CaseDashboardEnvelope,
    status_code=status.HTTP_200_OK,
)
async def get_case_dashboard_route(
    document_id: UUID,
    department: str | None = None,
    priority: str | None = None,
    deadline: str | None = None,
    item_status: str | None = Query(default=None, alias="status"),
    case_type: str | None = None,
    court: str | None = None,
    responsible_authority: str | None = None,
    request: Request = None,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None) if request else None

    try:
        job = get_job_status(document_id)
    except IntakeOrchestratorError as exc:
        raise to_http_exception(exc) from exc

    if job.stage != "finalized":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "case_not_finalized",
                "message": "Only finalized cases can be shown in the trusted dashboard.",
                "document_id": str(document_id),
                "current_stage": job.stage,
                "expected_stage": "finalized",
            },
        )

    items = [
        obligation
        for obligation in list_persisted_obligations(document_id)
        if obligation.action_plan_stage in APPROVED_ACTION_PLAN_ITEM_STAGES
    ]
    items = _filter_dashboard_items(
        items,
        department=department,
        priority=priority,
        deadline=deadline,
        status=item_status,
        case_type=case_type,
        court=court,
        responsible_authority=responsible_authority,
    )
    data = CaseDashboardData(
        document_id=document_id,
        total=len(items),
        approved_total=sum(1 for item in items if item.action_plan_stage == "approved"),
        edited_total=sum(1 for item in items if item.action_plan_stage == "edited"),
        groups=_group_dashboard_items_by_department(items),
    )
    return success(data=data, request_id=request_id, message="case_dashboard")


def _load_action_plan_item(document_id: UUID, obligation_id: UUID):
    obligation = get_persisted_obligation_by_id(obligation_id)
    if obligation is None or obligation.document_id != document_id:
        raise IntakeActionItemNotFoundError(
            f"Action-plan item not found for document {document_id}: {obligation_id}"
        )

    if obligation.action_plan_stage not in ACTION_PLAN_ITEM_STAGES:
        raise IntakeActionItemStageError(
            document_id=document_id,
            obligation_id=obligation_id,
            current_stage=obligation.action_plan_stage,
            allowed_stages=ACTION_PLAN_ITEM_STAGES,
        )

    return obligation


def _regenerate_action_item_from_cached_pages(
    *,
    gate,
    feedback: str,
    reviewer_name: str | None,
    actor_id: str | None,
    regenerated_at: datetime,
):
    page_summaries = _load_cited_page_summaries(gate.obligation)
    if not page_summaries:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "cited_page_summary_not_found",
                "message": (
                    "Per-item regeneration requires cached summaries for the "
                    "obligation's cited page."
                ),
                "obligation_id": str(gate.obligation.id),
            },
        )

    source_page_numbers = [summary.page_number for summary in page_summaries]
    source_summary_ids = [str(summary.id) for summary in page_summaries]
    previous_fields = _review_audit_fields(gate.obligation)
    description = _regenerated_description(
        gate.obligation,
        feedback=feedback,
        page_summaries=page_summaries,
    )
    updated_fields = {
        "description": description,
        "review_state": "pending_review",
        "action_plan_stage": "review_pending",
    }
    regen_count = gate.obligation.regen_count + 1
    regen_history = list(gate.obligation.regen_history or [])
    regen_history.append(
        {
            "at": regenerated_at.isoformat(),
            "feedback": feedback,
            "prev_fields": previous_fields,
            "updated_fields": updated_fields,
            "actor_id": actor_id,
            "reviewer_name": reviewer_name,
            "source": "cached_page_summaries_only",
            "source_page_numbers": source_page_numbers,
            "source_summary_ids": source_summary_ids,
        }
    )

    updated = update_persisted_obligation(
        gate.obligation.id,
        description=description,
        review_state="pending_review",
        action_plan_stage="review_pending",
        regen_count=regen_count,
        regen_history=regen_history,
        metadata={
            "last_regeneration": {
                "source": "cached_page_summaries_only",
                "source_page_numbers": source_page_numbers,
                "source_summary_ids": source_summary_ids,
                "feedback": feedback,
                "reviewer_name": reviewer_name,
                "regenerated_at": regenerated_at.isoformat(),
            }
        },
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "action_item_not_found",
                "message": f"Action-plan item not found: {gate.obligation.id}",
            },
        )
    return updated, updated_fields


def _load_cited_page_summaries(obligation) -> list[object]:
    page_numbers = _cited_page_numbers(obligation)
    if not page_numbers:
        return []
    return [
        summary
        for summary in list_page_summaries(obligation.document_id)
        if summary.page_number in page_numbers
    ]


def _cited_page_numbers(obligation) -> set[int]:
    page_numbers: set[int] = set()
    citation = getattr(obligation, "citation", None)
    page_number = getattr(citation, "page_number", None)
    if isinstance(page_number, int) and page_number >= 1:
        page_numbers.add(page_number)

    metadata = obligation.metadata if isinstance(obligation.metadata, dict) else {}
    for key in ("action_plan_source_evidence", "source_evidence"):
        payload = metadata.get(key)
        if isinstance(payload, dict):
            metadata_page_number = payload.get("page_number")
            if isinstance(metadata_page_number, int) and metadata_page_number >= 1:
                page_numbers.add(metadata_page_number)
    return page_numbers


def _regenerated_description(
    obligation,
    *,
    feedback: str,
    page_summaries: list[object],
) -> str:
    source_digest = " ".join(
        _short_cached_page_summary(summary) for summary in page_summaries
    ).strip()
    base = (
        "Regenerated from cached cited page summaries only. "
        f"Reviewer feedback: {feedback.strip()} "
    )
    if source_digest:
        base = f"{base}Cached source: {source_digest}"
    else:
        base = f"{base}Previous item: {obligation.description or obligation.title}"
    return _truncate_route_text(base, 1800)


def _short_cached_page_summary(summary) -> str:
    parts = [
        f"p{summary.page_number}:",
        getattr(summary, "summary", None),
        " ".join(getattr(summary, "key_points", []) or []),
        getattr(summary, "source_excerpt", None),
    ]
    return _truncate_route_text(" ".join(str(part) for part in parts if part), 600)


def _truncate_route_text(value: str, max_chars: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def _group_dashboard_items_by_department(items) -> list[CaseDashboardGroup]:
    grouped: dict[str, list[object]] = {}
    for obligation in items:
        department = (obligation.owner_hint or "Unassigned").strip() or "Unassigned"
        grouped.setdefault(department, []).append(obligation)

    return [
        CaseDashboardGroup(
            responsible_department=department,
            total=len(group_items),
            items=group_items,
        )
        for department, group_items in sorted(grouped.items())
    ]


def _filter_dashboard_items(
    items: list[object],
    *,
    department: str | None,
    priority: str | None,
    deadline: str | None,
    status: str | None,
    case_type: str | None,
    court: str | None,
    responsible_authority: str | None,
) -> list[object]:
    return [
        item
        for item in items
        if _matches_text_filter(getattr(item, "owner_hint", None), department)
        and _matches_text_filter(getattr(item, "owner_hint", None), responsible_authority)
        and _matches_exact_filter(getattr(item, "priority", None), priority)
        and _matches_exact_filter(getattr(item, "status", None), status)
        and _matches_deadline_filter(getattr(item, "due_date", None), deadline)
        and _matches_metadata_filter(item, "case_type", case_type)
        and _matches_metadata_filter(item, "court", court)
    ]


def _matches_text_filter(value: object, expected: str | None) -> bool:
    if not expected:
        return True
    if not isinstance(value, str):
        return False
    return expected.strip().lower() in value.lower()


def _matches_exact_filter(value: object, expected: str | None) -> bool:
    if not expected:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() == expected.strip().lower()


def _matches_deadline_filter(value: object, expected: str | None) -> bool:
    if not expected:
        return True
    if value is None:
        return False
    return getattr(value, "isoformat", lambda: str(value))() == expected.strip()


def _matches_metadata_filter(item: object, key: str, expected: str | None) -> bool:
    if not expected:
        return True
    metadata = getattr(item, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    candidates = [
        metadata.get(key),
        (
            (metadata.get("case_basics") or {}).get(key)
            if isinstance(metadata.get("case_basics"), dict)
            else None
        ),
    ]
    return any(_matches_text_filter(candidate, expected) for candidate in candidates)


def _review_update_values(payload: ActionPlanItemReviewRequest) -> dict[str, object | None]:
    if payload.decision == "reject":
        return {
            "review_state": "rejected",
            "action_plan_stage": "rejected",
        }

    values: dict[str, object | None] = {
        "review_state": "approved",
        "action_plan_stage": "approved" if payload.decision == "approve" else "edited",
    }

    if payload.decision == "edit" and payload.edited_fields:
        title = _edited_text(payload.edited_fields, "title")
        description = _edited_text(payload.edited_fields, "description")
        owner_hint = _edited_text(payload.edited_fields, "owner_hint")
        status_value = _edited_text(
            payload.edited_fields,
            "status",
            allowed_values=_ALLOWED_EDITED_STATUSES,
        )
        nature = _edited_text(
            payload.edited_fields,
            "nature_of_action",
            allowed_values=_ALLOWED_EDITED_NATURES,
        )
        if title is not None:
            values["title"] = title
        if description is not None:
            values["description"] = description
        if owner_hint is not None:
            values["owner_hint"] = owner_hint
        if status_value is not None:
            values["status"] = status_value
        if nature is not None:
            values["nature_of_action"] = nature

    return values


def _edited_text(
    edited_fields: dict[str, object],
    key: str,
    *,
    allowed_values: set[str] | None = None,
) -> str | None:
    value = edited_fields.get(key)
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    if not cleaned:
        return None
    if allowed_values is not None and cleaned not in allowed_values:
        return None
    return cleaned


def _record_action_plan_review_audit(
    *,
    obligation_id: UUID,
    payload: ActionPlanItemReviewRequest,
    actor_type: str,
    actor_id: str | None,
    request_id: str | None,
    next_stage: str,
    original_obligation,
    updated_obligation,
) -> None:
    try:
        record_persisted_obligation_audit_event(
            obligation_id=obligation_id,
            action=f"action_plan.item.{payload.decision}",
            actor_type=actor_type,
            actor_id=actor_id,
            request_id=request_id,
            payload={
                "decision": payload.decision,
                "action_plan_stage": next_stage,
                "reviewer_name": payload.reviewer_name,
                "reviewed_at": updated_obligation.updated_at.isoformat(),
                "edited_field_keys": sorted((payload.edited_fields or {}).keys()),
                "rejection_reason": payload.rejection_reason,
                "comments": payload.comments,
                "original_fields": _review_audit_fields(original_obligation),
                "updated_fields": _review_audit_fields(updated_obligation),
            },
        )
    except Exception:
        pass


def _review_audit_fields(obligation) -> dict[str, object | None]:
    return {
        "title": obligation.title,
        "description": obligation.description,
        "owner_hint": obligation.owner_hint,
        "status": obligation.status,
        "nature_of_action": obligation.nature_of_action,
        "review_state": obligation.review_state,
        "action_plan_stage": obligation.action_plan_stage,
    }


def _record_action_plan_regeneration_request_audit(
    *,
    obligation_id: UUID,
    feedback: str,
    reviewer_name: str | None,
    actor_type: str,
    actor_id: str | None,
    request_id: str | None,
    original_obligation,
    updated_obligation,
    updated_fields: dict[str, object],
    regenerated_at: datetime,
) -> None:
    try:
        record_persisted_obligation_audit_event(
            obligation_id=obligation_id,
            action="action_plan.item.regenerated",
            actor_type=actor_type,
            actor_id=actor_id,
            request_id=request_id,
            payload={
                "reviewer_name": reviewer_name,
                "feedback": feedback,
                "feedback_length": len(feedback),
                "regenerated_at": regenerated_at.isoformat(),
                "original_fields": _review_audit_fields(original_obligation),
                "updated_fields": updated_fields,
                "regen_count": updated_obligation.regen_count,
                "source": "cached_page_summaries_only",
            },
        )
    except Exception:
        pass
