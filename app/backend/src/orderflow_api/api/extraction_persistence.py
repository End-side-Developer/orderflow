from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
import re
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import RowMapping

from orderflow_api.api.extraction_engine import (
    ParsedClause,
    ParsedObligation,
    build_clause_span_token,
)
from orderflow_api.core.db import get_engine
from orderflow_api.schemas.extractions import ClauseRecord
from orderflow_api.schemas.obligations import (
    ObligationAuditEvent,
    ObligationCitation,
    ObligationConfidenceAnnotations,
    ObligationEscalationSignal,
    ObligationRecord,
)

_RICH_CLAUSE_SPAN_PATTERN = re.compile(
    r"^p(?P<page>\d+):c(?P<index>\d+):(?P<start>\d+)-(?P<end>\d+)$"
)
_COMPACT_CLAUSE_SPAN_PATTERN = re.compile(r"^c(?P<index>\d+):(?P<start>\d+)-(?P<end>\d+)$")
_LEGACY_CLAUSE_SPAN_PATTERN = re.compile(r"^clause-(?P<index>\d+)$")
_ESCALATION_LEVEL_RANK = {
    "none": 0,
    "watch": 1,
    "escalated": 2,
    "critical": 3,
}

CLAUSES_TABLE = sa.Table(
    "clauses",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("clause_index", sa.Integer(), nullable=False),
    sa.Column("page_number", sa.Integer(), nullable=True),
    sa.Column("span_start", sa.Integer(), nullable=True),
    sa.Column("span_end", sa.Integer(), nullable=True),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("normalized_text", sa.Text(), nullable=True),
    sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

OBLIGATIONS_TABLE = sa.Table(
    "obligations",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("clause_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("obligation_code", sa.String(length=64), nullable=True),
    sa.Column("title", sa.String(length=300), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("owner_hint", sa.String(length=200), nullable=True),
    sa.Column("nature_of_action", sa.String(length=64), nullable=True),
    sa.Column("due_date", sa.Date(), nullable=True),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("priority", sa.String(length=16), nullable=False),
    sa.Column("review_state", sa.String(length=32), nullable=False),
    sa.Column(
        "action_plan_stage", sa.String(length=32), nullable=False, server_default="extracted"
    ),
    sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
    sa.Column("regen_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("regen_history", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

DOCUMENTS_TABLE = sa.Table(
    "documents",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("status", sa.String(length=32), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

AUDIT_LOG_TABLE = sa.Table(
    "audit_log",
    sa.MetaData(),
    sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
    sa.Column("entity_type", sa.String(length=64), nullable=False),
    sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("action", sa.String(length=128), nullable=False),
    sa.Column("actor_type", sa.String(length=64), nullable=False),
    sa.Column("actor_id", sa.String(length=128), nullable=True),
    sa.Column("request_id", sa.String(length=128), nullable=True),
    sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)


def replace_document_extraction(
    document_id: UUID,
    clauses: list[ParsedClause],
    obligations: list[ParsedObligation],
) -> tuple[list[ClauseRecord], list[ObligationRecord]]:
    now = datetime.now(UTC)

    clause_rows = [
        {
            "id": clause.id,
            "document_id": clause.document_id,
            "clause_index": clause.clause_index,
            "page_number": clause.page_number,
            "span_start": clause.span_start,
            "span_end": clause.span_end,
            "text": _sanitize_database_text(clause.text) or "[unreadable clause]",
            "normalized_text": _sanitize_database_text(clause.normalized_text),
            "confidence": clause.confidence,
            "created_at": now,
            "updated_at": now,
        }
        for clause in clauses
    ]

    obligation_rows = [
        {
            "id": obligation.id,
            "document_id": obligation.document_id,
            "clause_id": obligation.clause_id,
            "obligation_code": _sanitize_database_text(obligation.obligation_code),
            "title": _sanitize_database_text(obligation.title) or "Untitled obligation",
            "description": _sanitize_database_text(obligation.description),
            "owner_hint": _sanitize_database_text(obligation.owner_hint),
            "nature_of_action": getattr(obligation, "nature_of_action", None),
            "due_date": obligation.due_date,
            "status": _sanitize_database_text(obligation.status) or "active",
            "priority": _sanitize_database_text(obligation.priority) or "medium",
            "review_state": _sanitize_database_text(obligation.review_state) or "pending_review",
            "action_plan_stage": getattr(obligation, "action_plan_stage", "extracted"),
            "confidence": obligation.confidence,
            "regen_count": getattr(obligation, "regen_count", 0),
            "regen_history": _sanitize_database_json(getattr(obligation, "regen_history", None)),
            "metadata": _sanitize_database_json(
                {
                    **(obligation.metadata if isinstance(obligation.metadata, dict) else {}),
                    "citation": {
                        "page_number": obligation.citation_page_number,
                        "clause_span": obligation.citation_clause_span,
                    },
                    "escalation": _build_escalation_signal_payload(
                        due_date=obligation.due_date,
                        status=obligation.status,
                        priority=obligation.priority,
                        review_state=obligation.review_state,
                    ),
                }
            ),
            "created_at": now,
            "updated_at": now,
        }
        for obligation in obligations
    ]

    with get_engine().begin() as connection:
        connection.execute(
            sa.delete(OBLIGATIONS_TABLE).where(OBLIGATIONS_TABLE.c.document_id == document_id)
        )
        connection.execute(
            sa.delete(CLAUSES_TABLE).where(CLAUSES_TABLE.c.document_id == document_id)
        )

        for clause_chunk in _chunk_rows(clause_rows, size=500):
            connection.execute(sa.insert(CLAUSES_TABLE).values(clause_chunk))

        for obligation_chunk in _chunk_rows(obligation_rows, size=500):
            connection.execute(sa.insert(OBLIGATIONS_TABLE).values(obligation_chunk))

        next_status = "ready" if obligation_rows else "processing"
        connection.execute(
            sa.update(DOCUMENTS_TABLE)
            .where(DOCUMENTS_TABLE.c.id == document_id)
            .values(status=next_status, updated_at=now)
        )

    persisted_clauses = list_persisted_clauses(document_id)
    persisted_obligations = list_persisted_obligations(document_id)

    # P1-3: best-effort embedding write so case clustering / similarity
    # search work without a separate backfill. Failure is non-fatal.
    try:
        from orderflow_api.core.clustering_service import (
            write_embeddings_for_new_obligations,
        )

        write_embeddings_for_new_obligations(persisted_obligations)
    except Exception:
        pass

    return persisted_clauses, persisted_obligations


def list_persisted_clauses(
    document_id: UUID,
    page_number: int | None = None,
    clause_span: str | None = None,
) -> list[ClauseRecord]:
    if clause_span is not None:
        clause = find_persisted_clause_by_span(document_id=document_id, clause_span=clause_span)
        return [clause] if clause is not None else []

    statement = (
        sa.select(CLAUSES_TABLE)
        .where(CLAUSES_TABLE.c.document_id == document_id)
        .order_by(CLAUSES_TABLE.c.page_number.asc(), CLAUSES_TABLE.c.clause_index.asc())
    )

    if page_number is not None:
        statement = statement.where(CLAUSES_TABLE.c.page_number == page_number)

    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [_to_clause_record(row) for row in rows]


def find_persisted_clause_by_span(document_id: UUID, clause_span: str) -> ClauseRecord | None:
    filters = _parse_clause_span_filters(clause_span)
    if filters is None:
        return None

    statement = sa.select(CLAUSES_TABLE).where(CLAUSES_TABLE.c.document_id == document_id)

    if "page_number" in filters:
        statement = statement.where(CLAUSES_TABLE.c.page_number == filters["page_number"])
    if "clause_index" in filters:
        statement = statement.where(CLAUSES_TABLE.c.clause_index == filters["clause_index"])
    if "span_start" in filters:
        statement = statement.where(CLAUSES_TABLE.c.span_start == filters["span_start"])
    if "span_end" in filters:
        statement = statement.where(CLAUSES_TABLE.c.span_end == filters["span_end"])

    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()

    if row is None:
        return None

    return _to_clause_record(row)


def list_persisted_obligations(document_id: UUID | None = None) -> list[ObligationRecord]:
    statement = (
        sa.select(
            OBLIGATIONS_TABLE,
            CLAUSES_TABLE.c.clause_index,
            CLAUSES_TABLE.c.page_number,
            CLAUSES_TABLE.c.span_start,
            CLAUSES_TABLE.c.span_end,
        )
        .select_from(
            OBLIGATIONS_TABLE.outerjoin(
                CLAUSES_TABLE,
                OBLIGATIONS_TABLE.c.clause_id == CLAUSES_TABLE.c.id,
            )
        )
        .order_by(OBLIGATIONS_TABLE.c.created_at.asc(), OBLIGATIONS_TABLE.c.id.asc())
    )

    if document_id is not None:
        statement = statement.where(OBLIGATIONS_TABLE.c.document_id == document_id)

    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [_to_obligation_record(row) for row in rows]


def get_persisted_obligation_by_id(obligation_id: UUID) -> ObligationRecord | None:
    statement = (
        sa.select(
            OBLIGATIONS_TABLE,
            CLAUSES_TABLE.c.clause_index,
            CLAUSES_TABLE.c.page_number,
            CLAUSES_TABLE.c.span_start,
            CLAUSES_TABLE.c.span_end,
        )
        .select_from(
            OBLIGATIONS_TABLE.outerjoin(
                CLAUSES_TABLE,
                OBLIGATIONS_TABLE.c.clause_id == CLAUSES_TABLE.c.id,
            )
        )
        .where(OBLIGATIONS_TABLE.c.id == obligation_id)
    )

    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()

    if row is None:
        return None

    return _to_obligation_record(row)


def update_persisted_obligation(
    obligation_id: UUID,
    review_state: str | None = None,
    title: str | None = None,
    description: str | None = None,
    owner_hint: str | None = None,
    status: str | None = None,
    action_plan_stage: str | None = None,
    nature_of_action: str | None = None,
    regen_count: int | None = None,
    regen_history: list[dict[str, object]] | None = None,
    metadata: dict[str, object] | None = None,
) -> ObligationRecord | None:
    with get_engine().connect() as connection:
        existing_row = (
            connection.execute(
                sa.select(OBLIGATIONS_TABLE).where(OBLIGATIONS_TABLE.c.id == obligation_id)
            )
            .mappings()
            .first()
        )

    if existing_row is None:
        return None

    update_values: dict[str, object] = {}

    if review_state is not None:
        update_values["review_state"] = (
            _sanitize_database_text(review_state) or existing_row["review_state"]
        )
    if title is not None:
        update_values["title"] = _sanitize_database_text(title) or existing_row["title"]
    if description is not None:
        update_values["description"] = _sanitize_database_text(description)
    if owner_hint is not None:
        update_values["owner_hint"] = _sanitize_database_text(owner_hint)
    if status is not None:
        update_values["status"] = _sanitize_database_text(status) or existing_row["status"]
    if action_plan_stage is not None:
        update_values["action_plan_stage"] = (
            _sanitize_database_text(action_plan_stage) or existing_row["action_plan_stage"]
        )
    if nature_of_action is not None:
        update_values["nature_of_action"] = _sanitize_database_text(nature_of_action)
    if regen_count is not None:
        update_values["regen_count"] = regen_count
    if regen_history is not None:
        update_values["regen_history"] = _sanitize_database_json(regen_history)

    if not update_values and metadata is None:
        return get_persisted_obligation_by_id(obligation_id)

    next_status = str(update_values.get("status", existing_row["status"]))
    next_review_state = str(update_values.get("review_state", existing_row["review_state"]))
    next_priority = str(existing_row["priority"])
    next_due_date = existing_row["due_date"]

    existing_metadata = (
        existing_row["metadata"] if isinstance(existing_row["metadata"], dict) else {}
    )
    if metadata is not None:
        existing_metadata = {
            **existing_metadata,
            **metadata,
        }
    next_metadata = {
        **existing_metadata,
        "escalation": _build_escalation_signal_payload(
            due_date=next_due_date,
            status=next_status,
            priority=next_priority,
            review_state=next_review_state,
        ),
    }

    update_values["metadata"] = _sanitize_database_json(next_metadata)
    update_values["updated_at"] = datetime.now(UTC)

    with get_engine().begin() as connection:
        result = connection.execute(
            sa.update(OBLIGATIONS_TABLE)
            .where(OBLIGATIONS_TABLE.c.id == obligation_id)
            .values(**update_values)
        )

    if result.rowcount == 0:
        return None

    return get_persisted_obligation_by_id(obligation_id)


def record_audit_event(
    *,
    entity_type: str,
    entity_id: UUID | None,
    action: str,
    actor_type: str,
    actor_id: str | None,
    request_id: str | None,
    payload: dict[str, object] | None,
) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            sa.insert(AUDIT_LOG_TABLE).values(
                entity_type=_sanitize_database_text(entity_type) or "unknown_entity",
                entity_id=entity_id,
                action=_sanitize_database_text(action) or "unknown_action",
                actor_type=_sanitize_database_text(actor_type) or "unknown_actor",
                actor_id=_sanitize_database_text(actor_id),
                request_id=_sanitize_database_text(request_id),
                payload=_sanitize_database_json(payload) if payload is not None else None,
                created_at=datetime.now(UTC),
            )
        )


def record_persisted_obligation_audit_event(
    obligation_id: UUID,
    action: str,
    actor_type: str,
    actor_id: str | None,
    request_id: str | None,
    payload: dict[str, object] | None,
) -> None:
    record_audit_event(
        entity_type="obligation",
        entity_id=obligation_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        request_id=request_id,
        payload=payload,
    )


def list_persisted_obligation_audit_events(obligation_id: UUID) -> list[ObligationAuditEvent]:
    statement = (
        sa.select(AUDIT_LOG_TABLE)
        .where(
            AUDIT_LOG_TABLE.c.entity_type == "obligation",
            AUDIT_LOG_TABLE.c.entity_id == obligation_id,
        )
        .order_by(AUDIT_LOG_TABLE.c.created_at.asc(), AUDIT_LOG_TABLE.c.id.asc())
    )

    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [
        ObligationAuditEvent(
            id=int(row["id"]),
            obligation_id=obligation_id,
            action=row["action"],
            actor_type=row["actor_type"],
            actor_id=row["actor_id"],
            request_id=row["request_id"],
            payload=row["payload"] if isinstance(row["payload"], dict) else None,
            created_at=row["created_at"],
        )
        for row in rows
    ]


def list_recent_persisted_obligation_audit_events(
    *,
    limit: int = 20,
    document_id: UUID | None = None,
) -> list[ObligationAuditEvent]:
    statement = (
        sa.select(
            AUDIT_LOG_TABLE,
            OBLIGATIONS_TABLE.c.document_id.label("document_id"),
        )
        .select_from(
            AUDIT_LOG_TABLE.join(
                OBLIGATIONS_TABLE,
                sa.and_(
                    AUDIT_LOG_TABLE.c.entity_type == "obligation",
                    AUDIT_LOG_TABLE.c.entity_id == OBLIGATIONS_TABLE.c.id,
                ),
            )
        )
        .order_by(AUDIT_LOG_TABLE.c.created_at.desc(), AUDIT_LOG_TABLE.c.id.desc())
        .limit(max(limit, 1))
    )

    if document_id is not None:
        statement = statement.where(OBLIGATIONS_TABLE.c.document_id == document_id)

    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [
        ObligationAuditEvent(
            id=int(row["id"]),
            obligation_id=row["entity_id"],
            action=row["action"],
            actor_type=row["actor_type"],
            actor_id=row["actor_id"],
            request_id=row["request_id"],
            payload=row["payload"] if isinstance(row["payload"], dict) else None,
            created_at=row["created_at"],
        )
        for row in rows
    ]


def _to_clause_record(row: RowMapping) -> ClauseRecord:
    return ClauseRecord(
        id=row["id"],
        document_id=row["document_id"],
        clause_index=row["clause_index"],
        page_number=row["page_number"],
        span_start=row["span_start"],
        span_end=row["span_end"],
        text=row["text"],
        normalized_text=row["normalized_text"],
        citation_span=build_clause_span_token(
            clause_index=row["clause_index"],
            page_number=row["page_number"],
            span_start=row["span_start"],
            span_end=row["span_end"],
        ),
        confidence=_to_float(row["confidence"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_obligation_record(row: RowMapping) -> ObligationRecord:
    metadata = row["metadata"] if isinstance(row["metadata"], dict) else {}
    citation_payload = metadata.get("citation") if isinstance(metadata, dict) else None
    confidence_payload = (
        metadata.get("confidence_annotations") if isinstance(metadata, dict) else None
    )
    escalation_payload = metadata.get("escalation") if isinstance(metadata, dict) else None

    clause_index = row.get("clause_index")
    row_page_number = _to_int(row.get("page_number"))
    row_span_start = _to_int(row.get("span_start"))
    row_span_end = _to_int(row.get("span_end"))

    if isinstance(clause_index, int):
        default_span = build_clause_span_token(
            clause_index=clause_index,
            page_number=row_page_number,
            span_start=row_span_start,
            span_end=row_span_end,
        )
    else:
        default_span = None

    payload_page_number = _citation_int(citation_payload, "page_number")
    payload_clause_index = _citation_int(citation_payload, "clause_index")
    payload_span_start = _citation_int(citation_payload, "span_start")
    payload_span_end = _citation_int(citation_payload, "span_end")

    citation_page_number = (
        payload_page_number if payload_page_number is not None else row_page_number
    )
    citation_clause_index = (
        payload_clause_index if payload_clause_index is not None else _to_int(clause_index)
    )
    citation_span_start = payload_span_start if payload_span_start is not None else row_span_start
    citation_span_end = payload_span_end if payload_span_end is not None else row_span_end
    citation_clause_span = _citation_text(citation_payload, "clause_span") or default_span

    citation = ObligationCitation(
        page_number=citation_page_number,
        clause_span=citation_clause_span,
        clause_index=citation_clause_index,
        span_start=citation_span_start,
        span_end=citation_span_end,
    )
    confidence_annotations = _to_confidence_annotations(confidence_payload)
    escalation = _to_escalation_signal(escalation_payload)
    if escalation is None:
        escalation = ObligationEscalationSignal.model_validate(
            _build_escalation_signal_payload(
                due_date=row["due_date"],
                status=row["status"],
                priority=row["priority"],
                review_state=row["review_state"],
            )
        )

    regen_history = row.get("regen_history")
    if not isinstance(regen_history, list):
        regen_history = []

    return ObligationRecord(
        id=row["id"],
        document_id=row["document_id"],
        obligation_code=row["obligation_code"],
        title=row["title"],
        description=row["description"],
        owner_hint=row["owner_hint"],
        nature_of_action=row.get("nature_of_action"),
        due_date=row["due_date"],
        status=row["status"],
        priority=row["priority"],
        review_state=row["review_state"],
        action_plan_stage=row.get("action_plan_stage") or "extracted",
        confidence=_to_float(row["confidence"]),
        regen_count=row.get("regen_count") or 0,
        regen_history=regen_history,
        confidence_annotations=confidence_annotations,
        escalation=escalation,
        citation=citation,
        metadata=metadata,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (float, int)):
        return float(value)
    return None


def _to_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _citation_int(payload: object, key: str) -> int | None:
    if not isinstance(payload, dict):
        return None
    return _to_int(payload.get(key))


def _citation_text(payload: object, key: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _to_confidence_annotations(payload: object) -> ObligationConfidenceAnnotations | None:
    if not isinstance(payload, dict):
        return None

    try:
        return ObligationConfidenceAnnotations.model_validate(payload)
    except Exception:
        return None


def _to_escalation_signal(payload: object) -> ObligationEscalationSignal | None:
    if not isinstance(payload, dict):
        return None

    try:
        return ObligationEscalationSignal.model_validate(payload)
    except Exception:
        return None


def _build_escalation_signal_payload(
    due_date: date | None,
    status: str,
    priority: str,
    review_state: str,
) -> dict[str, object]:
    if status in {"completed", "cancelled"}:
        return {
            "level": "none",
            "open": False,
            "reasons": [],
            "days_until_due": None,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    days_until_due: int | None = None
    if isinstance(due_date, date):
        days_until_due = (due_date - date.today()).days

    level = "none"
    reasons: list[str] = []

    if review_state == "pending_review" and priority in {"high", "critical"}:
        level = _pick_stronger_escalation_level(level, "watch")
        reasons.append("pending_review_high_priority")

    if isinstance(days_until_due, int):
        if days_until_due < 0:
            level = _pick_stronger_escalation_level(level, "critical")
            reasons.append("overdue")
        elif days_until_due <= 3:
            level = _pick_stronger_escalation_level(level, "escalated")
            reasons.append("due_within_3_days")
        elif days_until_due <= 7:
            level = _pick_stronger_escalation_level(level, "watch")
            reasons.append("due_within_7_days")

    if priority == "critical" and status == "active":
        level = _pick_stronger_escalation_level(level, "escalated")
        reasons.append("critical_priority_active")

    return {
        "level": level,
        "open": level != "none",
        "reasons": reasons,
        "days_until_due": days_until_due,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _pick_stronger_escalation_level(current: str, candidate: str) -> str:
    current_rank = _ESCALATION_LEVEL_RANK.get(current, 0)
    candidate_rank = _ESCALATION_LEVEL_RANK.get(candidate, 0)
    return candidate if candidate_rank > current_rank else current


def _sanitize_database_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None

    sanitized = "".join(
        ch for ch in value if ch != "\x00" and (ch in "\n\r\t" or ord(ch) >= 0x20)
    ).strip()
    return sanitized or None


def _sanitize_database_json(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _sanitize_database_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_database_json(item) for item in value]
    if isinstance(value, str):
        return _sanitize_database_text(value) or ""
    return value


def _chunk_rows(rows: list[dict[str, object]], size: int) -> list[list[dict[str, object]]]:
    if size <= 0:
        return [rows]

    return [rows[index : index + size] for index in range(0, len(rows), size)]


def _parse_clause_span_filters(clause_span: str) -> dict[str, int] | None:
    rich_match = _RICH_CLAUSE_SPAN_PATTERN.match(clause_span)
    if rich_match:
        return {
            "page_number": int(rich_match.group("page")),
            "clause_index": int(rich_match.group("index")),
            "span_start": int(rich_match.group("start")),
            "span_end": int(rich_match.group("end")),
        }

    compact_match = _COMPACT_CLAUSE_SPAN_PATTERN.match(clause_span)
    if compact_match:
        return {
            "clause_index": int(compact_match.group("index")),
            "span_start": int(compact_match.group("start")),
            "span_end": int(compact_match.group("end")),
        }

    legacy_match = _LEGACY_CLAUSE_SPAN_PATTERN.match(clause_span)
    if legacy_match:
        return {
            "clause_index": int(legacy_match.group("index")),
        }

    return None
