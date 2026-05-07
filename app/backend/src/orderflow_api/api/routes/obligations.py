from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from orderflow_api.api.dependencies.auth import (
    audit_actor_from_request,
    require_permission,
)
from orderflow_api.api.document_persistence import get_persisted_document
from orderflow_api.api.extraction_persistence import (
    list_persisted_obligation_audit_events,
    update_persisted_obligation,
    list_persisted_clauses,
    list_persisted_obligations,
    record_persisted_obligation_audit_event,
)
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.api.stub_repository import (
    get_document,
    list_clauses,
    list_obligations,
    list_obligation_audit_events,
    update_obligation,
)
from orderflow_api.core.proof_verifier import ProofPayload, verify_proof
from orderflow_api.core.risk_service import (
    annotate_obligations_with_risk,
)
from orderflow_api.schemas.extractions import ClausesEnvelope, ClausesListData
from orderflow_api.schemas.obligations import (
    EscalationSummaryItem,
    EscalationsEnvelope,
    EscalationsSummaryData,
    ObligationEnvelope,
    ObligationAuditTrailData,
    ObligationAuditTrailEnvelope,
    ObligationUpdateRequest,
    ObligationsEnvelope,
    ObligationsListData,
)

router = APIRouter(tags=["obligations"])


@router.get("/obligations", response_model=ObligationsEnvelope)
async def list_obligations_route(
    request: Request,
    document_id: UUID | None = Query(default=None),
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    items = _resolve_obligations(document_id)
    data = ObligationsListData(document_id=document_id, total=len(items), items=items)
    request_id = getattr(request.state, "request_id", None)
    return success(data=data, request_id=request_id)


@router.get("/clauses", response_model=ClausesEnvelope)
async def list_clauses_route(
    request: Request,
    document_id: UUID = Query(...),
    page_number: int | None = Query(default=None, ge=1),
    clause_span: str | None = Query(default=None, min_length=1, max_length=80),
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    items = _resolve_clauses(
        document_id=document_id,
        page_number=page_number,
        clause_span=clause_span,
    )
    data = ClausesListData(
        document_id=document_id,
        page_number=page_number,
        clause_span=clause_span,
        total=len(items),
        items=items,
    )
    request_id = getattr(request.state, "request_id", None)
    return success(data=data, request_id=request_id)


@router.patch("/obligations/{obligation_id}", response_model=ObligationEnvelope)
async def update_obligation_route(
    request: Request,
    obligation_id: UUID,
    payload: ObligationUpdateRequest,
    _user=Depends(require_permission(Permission.OBLIGATION_WRITE)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    actor_type, actor_id = audit_actor_from_request(request)

    # Proof-Gated Completion (P0-2): closure requires a verified proof.
    # We check this BEFORE mutating any state so failed verification is
    # safe and idempotent.
    if payload.status == "completed":
        existing = _find_obligation(obligation_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Obligation not found")

        if payload.proof is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "proof_required",
                    "message": (
                        "Cannot close obligation without a proof submission. "
                        "Attach evidence text and a timestamp before closing."
                    ),
                },
            )

        verification = verify_proof(
            ProofPayload(
                obligation_text=_obligation_text(existing),
                proof_text=payload.proof.proof_text,
                obligation_due_date=existing.due_date,
                obligation_issued_date=_obligation_issued_date(existing),
                proof_timestamp=payload.proof.proof_timestamp,
                proof_bytes_sha256=payload.proof.proof_bytes_sha256,
                expected_sha256=payload.proof.expected_sha256,
                proof_pdf_metadata=payload.proof.proof_pdf_metadata,
                original_pdf_metadata=payload.proof.original_pdf_metadata,
            )
        )

        if not verification.passed:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "proof_verification_failed",
                    "message": verification.summary,
                    "details": {"verification": verification.to_dict()},
                },
            )

    updated = update_obligation(
        obligation_id=obligation_id,
        review_state=payload.review_state,
        owner_hint=payload.owner_hint,
        status=payload.status,
        actor_type=actor_type,
        actor_id=actor_id,
        request_id=request_id,
    )

    if updated is None:
        updated = _safe_update_persisted_obligation(
            obligation_id=obligation_id,
            review_state=payload.review_state,
            owner_hint=payload.owner_hint,
            status=payload.status,
            request_id=request_id,
            actor_type=actor_type,
            actor_id=actor_id,
        )

    if updated is None:
        raise HTTPException(status_code=404, detail="Obligation not found")

    return success(data=updated, request_id=request_id, message="obligation_updated")


def _obligation_text(obligation) -> str:
    parts = [obligation.title or ""]
    if obligation.description:
        parts.append(obligation.description)
    return "\n".join(p for p in parts if p)


def _obligation_issued_date(obligation):
    """Best-effort issued/judgment date for the obligation."""
    created = getattr(obligation, "created_at", None)
    if created is None:
        return None
    return created.date() if hasattr(created, "date") else None


@router.get("/escalations", response_model=EscalationsEnvelope)
async def list_escalations_route(
    request: Request,
    document_id: UUID = Query(...),
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    obligations = _resolve_obligations(document_id)

    items: list[EscalationSummaryItem] = []
    for obligation in obligations:
        escalation = obligation.escalation
        if escalation is None:
            continue
        if not escalation.open:
            continue

        items.append(
            EscalationSummaryItem(
                obligation_id=obligation.id,
                title=obligation.title,
                level=escalation.level,
                days_until_due=escalation.days_until_due,
                due_date=obligation.due_date,
                review_state=obligation.review_state,
                priority=obligation.priority,
                reasons=escalation.reasons,
                risk_score=getattr(obligation, "risk_score", None),
                risk_band=getattr(obligation, "risk_band", None),
                risk_factors=getattr(obligation, "risk_factors", []) or [],
            )
        )

    items.sort(
        key=lambda item: (
            -(item.risk_score or 0),
            -_escalation_rank(item.level),
            item.days_until_due if item.days_until_due is not None else 10_000,
        )
    )

    data = EscalationsSummaryData(
        document_id=document_id,
        total=len(items),
        open_total=len(items),
        critical_total=sum(1 for item in items if item.level == "critical"),
        items=items,
    )
    request_id = getattr(request.state, "request_id", None)
    return success(data=data, request_id=request_id)


@router.get(
    "/obligations/{obligation_id}/audit",
    response_model=ObligationAuditTrailEnvelope,
)
async def get_obligation_audit_trail_route(
    request: Request,
    obligation_id: UUID,
    _user=Depends(require_permission(Permission.AUDIT_READ)),
) -> dict[str, object]:
    obligation = _find_obligation(obligation_id)
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found")

    events = list_obligation_audit_events(obligation_id)
    if not events:
        events = _safe_list_persisted_obligation_audit_events(obligation_id)

    data = ObligationAuditTrailData(
        obligation_id=obligation_id,
        total=len(events),
        items=events,
    )
    request_id = getattr(request.state, "request_id", None)
    return success(data=data, request_id=request_id)


def _resolve_obligations(document_id: UUID | None):
    if document_id is not None:
        stub_document = get_document(document_id)
        if stub_document is not None:
            items = list_obligations(document_id=document_id)
            annotate_obligations_with_risk(items)
            return items

        persisted_document = _safe_get_persisted_document(document_id)
        if persisted_document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        items = _safe_list_persisted_obligations(document_id=document_id)
        annotate_obligations_with_risk(items)
        return items

    persisted_items = _safe_list_persisted_obligations(document_id=None)
    stub_items = list_obligations(document_id=None)
    combined = [*persisted_items, *stub_items]
    annotate_obligations_with_risk(combined)
    return combined


def _resolve_clauses(
    document_id: UUID,
    page_number: int | None,
    clause_span: str | None,
):
    stub_document = get_document(document_id)
    if stub_document is not None:
        stub_items = list_clauses(document_id=document_id)
        return [
            item
            for item in stub_items
            if (page_number is None or item.page_number == page_number)
            and (
                clause_span is None
                or item.citation_span == clause_span
                or clause_span == f"clause-{item.clause_index}"
            )
        ]

    persisted_document = _safe_get_persisted_document(document_id)
    if persisted_document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return _safe_list_persisted_clauses(
        document_id=document_id,
        page_number=page_number,
        clause_span=clause_span,
    )


def _safe_get_persisted_document(document_id: UUID):
    try:
        return get_persisted_document(document_id)
    except Exception:
        return None


def _safe_list_persisted_obligations(document_id: UUID | None):
    try:
        return list_persisted_obligations(document_id=document_id)
    except Exception:
        return []


def _safe_list_persisted_clauses(
    document_id: UUID,
    page_number: int | None,
    clause_span: str | None,
):
    try:
        return list_persisted_clauses(
            document_id=document_id,
            page_number=page_number,
            clause_span=clause_span,
        )
    except Exception:
        return []


def _safe_update_persisted_obligation(
    obligation_id: UUID,
    review_state: str | None,
    owner_hint: str | None,
    status: str | None,
    request_id: str | None,
    actor_type: str = "system",
    actor_id: str | None = None,
):
    try:
        updated = update_persisted_obligation(
            obligation_id=obligation_id,
            review_state=review_state,
            owner_hint=owner_hint,
            status=status,
        )
    except Exception:
        return None

    if updated is not None:
        try:
            record_persisted_obligation_audit_event(
                obligation_id=obligation_id,
                action=_build_update_action(review_state, owner_hint, status),
                actor_type=actor_type,
                actor_id=actor_id,
                request_id=request_id,
                payload={
                    "review_state": review_state,
                    "owner_hint": owner_hint,
                    "status": status,
                },
            )
        except Exception:
            pass

    return updated


def _safe_list_persisted_obligation_audit_events(obligation_id: UUID):
    try:
        return list_persisted_obligation_audit_events(obligation_id)
    except Exception:
        return []


def _find_obligation(obligation_id: UUID):
    obligations = _safe_list_persisted_obligations(document_id=None)
    obligations.extend(list_obligations(document_id=None))
    for obligation in obligations:
        if obligation.id == obligation_id:
            return obligation
    return None


def _build_update_action(
    review_state: str | None,
    owner_hint: str | None,
    status: str | None,
) -> str:
    if review_state is not None and owner_hint is None and status is None:
        return "obligation.review_state.updated"
    if owner_hint is not None and review_state is None and status is None:
        return "obligation.owner_hint.updated"
    if status is not None and review_state is None and owner_hint is None:
        return "obligation.status.updated"
    return "obligation.updated"


def _escalation_rank(level: str) -> int:
    rank = {
        "none": 0,
        "watch": 1,
        "escalated": 2,
        "critical": 3,
    }
    return rank.get(level, 0)
