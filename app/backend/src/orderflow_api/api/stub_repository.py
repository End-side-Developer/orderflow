from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from orderflow_api.schemas.extractions import ClauseRecord
from orderflow_api.schemas.documents import DocumentCreateRequest, DocumentRecord
from orderflow_api.schemas.obligations import (
    ObligationAuditEvent,
    ObligationCitation,
    ObligationEscalationSignal,
    ObligationRecord,
)

_DOCUMENTS: dict[UUID, DocumentRecord] = {}
_OBLIGATIONS_BY_DOCUMENT: dict[UUID, list[ObligationRecord]] = {}
_CLAUSES_BY_DOCUMENT: dict[UUID, list[ClauseRecord]] = {}
_AUDIT_EVENTS_BY_OBLIGATION: dict[UUID, list[ObligationAuditEvent]] = {}
_AUDIT_SEQUENCE: int = 0


def create_document(payload: DocumentCreateRequest) -> DocumentRecord:
    now = datetime.now(UTC)
    document = DocumentRecord(
        id=uuid4(),
        source_file_name=payload.source_file_name,
        source_file_type=payload.source_file_type,
        source_file_size=payload.source_file_size,
        object_key=payload.object_key,
        checksum_sha256=payload.checksum_sha256,
        status="uploaded",
        source_language=payload.source_language,
        auto_detected_language=payload.auto_detected_language,
        language_confidence=payload.language_confidence,
        translated_text_stored=payload.translated_text_stored,
        metadata=payload.metadata,
        created_at=now,
        updated_at=now,
    )
    _DOCUMENTS[document.id] = document
    _CLAUSES_BY_DOCUMENT[document.id] = _build_default_clauses(document.id, now)
    obligations = _build_default_obligations(document.id)
    _OBLIGATIONS_BY_DOCUMENT[document.id] = obligations
    for obligation in obligations:
        _AUDIT_EVENTS_BY_OBLIGATION.setdefault(obligation.id, [])
    return document


def get_document(document_id: UUID) -> DocumentRecord | None:
    return _DOCUMENTS.get(document_id)


def list_obligations(document_id: UUID | None = None) -> list[ObligationRecord]:
    if document_id is not None:
        return list(_OBLIGATIONS_BY_DOCUMENT.get(document_id, []))

    items: list[ObligationRecord] = []
    for obligations in _OBLIGATIONS_BY_DOCUMENT.values():
        items.extend(obligations)
    return items


def list_clauses(document_id: UUID | None = None) -> list[ClauseRecord]:
    if document_id is not None:
        return list(_CLAUSES_BY_DOCUMENT.get(document_id, []))

    items: list[ClauseRecord] = []
    for clauses in _CLAUSES_BY_DOCUMENT.values():
        items.extend(clauses)
    return items


def update_obligation(
    obligation_id: UUID,
    review_state: str | None = None,
    owner_hint: str | None = None,
    status: str | None = None,
    actor_type: str = "reviewer",
    actor_id: str | None = None,
    request_id: str | None = None,
) -> ObligationRecord | None:
    now = datetime.now(UTC)

    for document_id, obligations in _OBLIGATIONS_BY_DOCUMENT.items():
        for index, obligation in enumerate(obligations):
            if obligation.id != obligation_id:
                continue

            update_values: dict[str, object] = {"updated_at": now}
            if review_state is not None:
                update_values["review_state"] = review_state
            if owner_hint is not None:
                update_values["owner_hint"] = owner_hint
            if status is not None:
                update_values["status"] = status

            next_status = str(update_values.get("status", obligation.status))
            next_review_state = str(update_values.get("review_state", obligation.review_state))
            update_values["escalation"] = _build_escalation_signal(
                due_date=obligation.due_date,
                status=next_status,
                priority=obligation.priority,
                review_state=next_review_state,
            )

            updated = obligation.model_copy(update=update_values)
            obligations[index] = updated
            _OBLIGATIONS_BY_DOCUMENT[document_id] = obligations

            _append_stub_obligation_audit_event(
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
                created_at=now,
            )
            return updated

    return None


def list_obligation_audit_events(obligation_id: UUID) -> list[ObligationAuditEvent]:
    return list(_AUDIT_EVENTS_BY_OBLIGATION.get(obligation_id, []))


def _build_default_clauses(document_id: UUID, now: datetime) -> list[ClauseRecord]:
    return [
        ClauseRecord(
            id=uuid4(),
            document_id=document_id,
            clause_index=1,
            page_number=2,
            span_start=120,
            span_end=260,
            text=(
                "District Administration shall constitute an implementation committee "
                "within seven days."
            ),
            normalized_text=(
                "District Administration shall constitute an implementation committee "
                "within seven days."
            ),
            citation_span="p2:c1:120-260",
            confidence=0.86,
            created_at=now,
            updated_at=now,
        ),
        ClauseRecord(
            id=uuid4(),
            document_id=document_id,
            clause_index=2,
            page_number=5,
            span_start=410,
            span_end=560,
            text=(
                "Government Counsel Office shall file a compliance progress affidavit "
                "before next listing date."
            ),
            normalized_text=(
                "Government Counsel Office shall file a compliance progress affidavit "
                "before next listing date."
            ),
            citation_span="p5:c2:410-560",
            confidence=0.79,
            created_at=now,
            updated_at=now,
        ),
    ]


def _build_default_obligations(document_id: UUID) -> list[ObligationRecord]:
    now = datetime.now(UTC)
    return [
        ObligationRecord(
            id=uuid4(),
            document_id=document_id,
            obligation_code="OBL-001",
            title="Constitute implementation committee",
            description="Set up cross-department implementation committee within seven days.",
            owner_hint="District Administration",
            due_date=date.today() + timedelta(days=7),
            status="draft",
            priority="high",
            review_state="pending_review",
            confidence=0.86,
            escalation=_build_escalation_signal(
                due_date=date.today() + timedelta(days=7),
                status="draft",
                priority="high",
                review_state="pending_review",
            ),
            citation=ObligationCitation(page_number=2, clause_span="para-4"),
            created_at=now,
            updated_at=now,
        ),
        ObligationRecord(
            id=uuid4(),
            document_id=document_id,
            obligation_code="OBL-002",
            title="Submit progress affidavit",
            description="File compliance progress affidavit before next listing date.",
            owner_hint="Government Counsel Office",
            due_date=date.today() + timedelta(days=14),
            status="draft",
            priority="critical",
            review_state="pending_review",
            confidence=0.79,
            escalation=_build_escalation_signal(
                due_date=date.today() + timedelta(days=14),
                status="draft",
                priority="critical",
                review_state="pending_review",
            ),
            citation=ObligationCitation(page_number=5, clause_span="para-12"),
            created_at=now,
            updated_at=now,
        ),
    ]


def _build_escalation_signal(
    due_date: date | None,
    status: str,
    priority: str,
    review_state: str,
) -> ObligationEscalationSignal:
    if status in {"completed", "cancelled"}:
        return ObligationEscalationSignal(
            level="none",
            open=False,
            reasons=[],
            days_until_due=None,
            generated_at=datetime.now(UTC),
        )

    days_until_due = (due_date - date.today()).days if due_date else None
    level = "none"
    reasons: list[str] = []

    if review_state == "pending_review" and priority in {"high", "critical"}:
        level = _pick_stronger_level(level, "watch")
        reasons.append("pending_review_high_priority")

    if days_until_due is not None:
        if days_until_due < 0:
            level = _pick_stronger_level(level, "critical")
            reasons.append("overdue")
        elif days_until_due <= 3:
            level = _pick_stronger_level(level, "escalated")
            reasons.append("due_within_3_days")
        elif days_until_due <= 7:
            level = _pick_stronger_level(level, "watch")
            reasons.append("due_within_7_days")

    if priority == "critical" and status == "active":
        level = _pick_stronger_level(level, "escalated")
        reasons.append("critical_priority_active")

    return ObligationEscalationSignal(
        level=level,
        open=level != "none",
        reasons=reasons,
        days_until_due=days_until_due,
        generated_at=datetime.now(UTC),
    )


def _pick_stronger_level(current: str, candidate: str) -> str:
    rank = {"none": 0, "watch": 1, "escalated": 2, "critical": 3}
    return candidate if rank.get(candidate, 0) > rank.get(current, 0) else current


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


def _append_stub_obligation_audit_event(
    obligation_id: UUID,
    action: str,
    actor_type: str,
    actor_id: str | None,
    request_id: str | None,
    payload: dict[str, object],
    created_at: datetime,
) -> None:
    global _AUDIT_SEQUENCE
    _AUDIT_SEQUENCE += 1

    event = ObligationAuditEvent(
        id=_AUDIT_SEQUENCE,
        obligation_id=obligation_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        request_id=request_id,
        payload={key: value for key, value in payload.items() if value is not None},
        created_at=created_at,
    )

    _AUDIT_EVENTS_BY_OBLIGATION.setdefault(obligation_id, []).append(event)
