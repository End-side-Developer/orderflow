from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from orderflow_api.api.extraction_persistence import record_audit_event
from orderflow_api.core.db import get_engine
from orderflow_api.schemas.cases import (
    ExtractionJobError,
    ExtractionJobStage,
    ExtractionJobStatusData,
)


EXTRACTION_JOBS_TABLE = sa.Table(
    "extraction_jobs",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("stage", sa.String(length=40), nullable=False),
    sa.Column("pages_total", sa.Integer(), nullable=False),
    sa.Column("pages_completed", sa.Integer(), nullable=False),
    sa.Column("current_page", sa.Integer(), nullable=True),
    sa.Column("current_page_excerpt", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("last_error_code", sa.String(length=80), nullable=True),
    sa.Column("last_error_message", sa.Text(), nullable=True),
    sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
    sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
    sa.Column("current_concurrency", sa.Integer(), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
)


def create_extraction_job(
    document_id: UUID,
    *,
    pages_total: int = 0,
    current_concurrency: int = 1,
    stage: ExtractionJobStage = "pending",
    started_at: datetime | None = None,
) -> ExtractionJobStatusData:
    existing = get_extraction_job(document_id)
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "document_id": document_id,
        "stage": stage,
        "pages_total": max(0, pages_total),
        "pages_completed": 0,
        "current_page": None,
        "current_page_excerpt": None,
        "last_error_code": None,
        "last_error_message": None,
        "retry_after_seconds": None,
        "paused_until": None,
        "current_concurrency": max(1, current_concurrency),
        "started_at": started_at,
        "created_at": now,
        "updated_at": now,
        "finalized_at": None,
    }

    with get_engine().begin() as connection:
        connection.execute(sa.insert(EXTRACTION_JOBS_TABLE).values(**values))

    status = _to_extraction_job_status(values)
    _record_stage_transition_audit(
        document_id=document_id,
        job_id=status.id,
        previous_stage=None,
        next_stage=status.stage,
        source="extraction_job_created",
    )
    return status


def get_extraction_job(document_id: UUID) -> ExtractionJobStatusData | None:
    statement = sa.select(EXTRACTION_JOBS_TABLE).where(
        EXTRACTION_JOBS_TABLE.c.document_id == document_id
    )
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()

    if row is None:
        return None
    return _to_extraction_job_status(row)


def update_extraction_job_stage(
    document_id: UUID,
    stage: ExtractionJobStage,
    *,
    started_at: datetime | None = None,
) -> ExtractionJobStatusData | None:
    previous = get_extraction_job(document_id)
    values: dict[str, object] = {
        "stage": stage,
        "updated_at": datetime.now(UTC),
        "last_error_code": None,
        "last_error_message": None,
    }
    if started_at is not None:
        values["started_at"] = started_at
    if stage == "finalized":
        values["finalized_at"] = datetime.now(UTC)

    updated = _update_job(document_id, values)
    if updated is not None:
        _record_stage_transition_audit(
            document_id=document_id,
            job_id=updated.id,
            previous_stage=previous.stage if previous is not None else None,
            next_stage=updated.stage,
            source="extraction_job_stage_update",
        )
    return updated


def update_extraction_job_progress(
    document_id: UUID,
    *,
    pages_total: int | None = None,
    pages_completed: int | None = None,
    current_page: int | None = None,
    current_page_excerpt: dict[str, Any] | None = None,
    current_concurrency: int | None = None,
) -> ExtractionJobStatusData | None:
    values: dict[str, object | None] = {"updated_at": datetime.now(UTC)}
    if pages_total is not None:
        values["pages_total"] = max(0, pages_total)
    if pages_completed is not None:
        values["pages_completed"] = max(0, pages_completed)
    if current_page is not None:
        values["current_page"] = max(1, current_page)
    if current_page_excerpt is not None:
        values["current_page_excerpt"] = current_page_excerpt
    if current_concurrency is not None:
        values["current_concurrency"] = max(1, current_concurrency)

    return _update_job(document_id, values)


def pause_extraction_job(
    document_id: UUID,
    *,
    retry_after_seconds: int,
    paused_until: datetime,
    error_code: str,
    error_message: str,
    current_concurrency: int | None = None,
) -> ExtractionJobStatusData | None:
    values: dict[str, object | None] = {
        "last_error_code": error_code,
        "last_error_message": error_message,
        "retry_after_seconds": max(0, retry_after_seconds),
        "paused_until": paused_until,
        "updated_at": datetime.now(UTC),
    }
    if current_concurrency is not None:
        values["current_concurrency"] = max(1, current_concurrency)
    return _update_job(document_id, values)


def resume_extraction_job(
    document_id: UUID,
    *,
    current_concurrency: int | None = None,
) -> ExtractionJobStatusData | None:
    values: dict[str, object | None] = {
        "last_error_code": None,
        "last_error_message": None,
        "retry_after_seconds": None,
        "paused_until": None,
        "updated_at": datetime.now(UTC),
    }
    if current_concurrency is not None:
        values["current_concurrency"] = max(1, current_concurrency)
    return _update_job(document_id, values)


def fail_extraction_job(
    document_id: UUID,
    *,
    error_code: str,
    error_message: str,
) -> ExtractionJobStatusData | None:
    return _update_job(
        document_id,
        {
            "last_error_code": error_code,
            "last_error_message": error_message,
            "updated_at": datetime.now(UTC),
        },
    )


def finalize_extraction_job(document_id: UUID) -> ExtractionJobStatusData | None:
    now = datetime.now(UTC)
    previous = get_extraction_job(document_id)
    updated = _update_job(
        document_id,
        {
            "stage": "finalized",
            "finalized_at": now,
            "updated_at": now,
            "last_error_code": None,
            "last_error_message": None,
            "retry_after_seconds": None,
            "paused_until": None,
        },
    )
    if updated is not None:
        _record_stage_transition_audit(
            document_id=document_id,
            job_id=updated.id,
            previous_stage=previous.stage if previous is not None else None,
            next_stage=updated.stage,
            source="extraction_job_finalized",
        )
    return updated


def _update_job(
    document_id: UUID,
    values: dict[str, object | None],
) -> ExtractionJobStatusData | None:
    statement = (
        sa.update(EXTRACTION_JOBS_TABLE)
        .where(EXTRACTION_JOBS_TABLE.c.document_id == document_id)
        .values(**values)
    )
    with get_engine().begin() as connection:
        result = connection.execute(statement)

    if result.rowcount == 0:
        return None
    return get_extraction_job(document_id)


def _to_extraction_job_status(row) -> ExtractionJobStatusData:
    error = None
    if row["last_error_code"] is not None or row["last_error_message"] is not None:
        error = ExtractionJobError(
            code=row["last_error_code"],
            message=row["last_error_message"],
        )

    pages_total = int(row["pages_total"] or 0)
    pages_completed = int(row["pages_completed"] or 0)
    current_page_excerpt = row["current_page_excerpt"]
    cache_status = _current_cache_status(current_page_excerpt)
    retry_after_seconds = row["retry_after_seconds"]
    paused_until = row["paused_until"]

    return ExtractionJobStatusData(
        id=row["id"],
        document_id=row["document_id"],
        stage=row["stage"],
        pages_total=pages_total,
        pages_completed=pages_completed,
        current_page=row["current_page"],
        current_page_excerpt=current_page_excerpt,
        percent=_calculate_percent(pages_completed, pages_total),
        status_message=_status_message(
            stage=row["stage"],
            pages_completed=pages_completed,
            pages_total=pages_total,
            current_page=row["current_page"],
            cache_status=cache_status,
            retry_after_seconds=retry_after_seconds,
            error=error,
        ),
        current_page_cache_status=cache_status,
        is_paused=paused_until is not None or retry_after_seconds is not None,
        next_action=_next_action(row["stage"], error),
        error=error,
        retry_after_seconds=retry_after_seconds,
        paused_until=paused_until,
        current_concurrency=int(row["current_concurrency"] or 1),
        started_at=row["started_at"],
        finalized_at=row["finalized_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _calculate_percent(pages_completed: int, pages_total: int) -> float:
    if pages_total <= 0:
        return 0.0
    bounded_completed = min(max(0, pages_completed), pages_total)
    return round((bounded_completed / pages_total) * 100, 2)


def _current_cache_status(current_page_excerpt: object) -> str | None:
    if not isinstance(current_page_excerpt, dict):
        return None
    value = current_page_excerpt.get("cache_status")
    return value if isinstance(value, str) and value.strip() else None


def _status_message(
    *,
    stage: str,
    pages_completed: int,
    pages_total: int,
    current_page: int | None,
    cache_status: str | None,
    retry_after_seconds: int | None,
    error: ExtractionJobError | None,
) -> str:
    if error is not None and error.message:
        if _is_known_user_facing_error(error.code):
            return error.message
        return "Extraction needs attention."
    if retry_after_seconds is not None:
        return f"Rate limit pause. Retrying in {retry_after_seconds}s."
    if stage == "pending":
        return "Ready to begin intake."
    if stage == "pages_extracting":
        page = f" page {current_page}" if current_page is not None else ""
        cache = f" ({cache_status})" if cache_status else ""
        total = f" of {pages_total}" if pages_total else ""
        return f"Extracting{page}{total}. Completed {pages_completed}{total}{cache}."
    if stage == "pages_done":
        return "Pages are ready for summary."
    if stage == "summary_pending":
        return "Summary generation requested."
    if stage == "summary_done":
        return "Summary is ready for action-plan generation."
    if stage == "action_plan_pending":
        return "Action-plan generation requested."
    if stage == "action_plan_done":
        return "Action plan is ready for human review."
    if stage == "review_in_progress":
        return "Human review is in progress."
    if stage == "finalized":
        return "Case is finalized and ready for trusted dashboard."
    return "Intake status updated."


def _next_action(stage: str, error: ExtractionJobError | None) -> str | None:
    if error is not None:
        if error.code == "ocr_required":
            return "Run OCR or upload a text-readable PDF, then restart intake."
        if error.code in {"ai_rate_limit_rpm", "ai_rate_limit_tpm"}:
            return "Wait for the scheduled retry or reduce intake concurrency."
        if error.code in {
            "ai_timeout",
            "ai_network_error",
            "ai_invalid_json",
            "partial_page_failure",
            "page_extraction_failed",
        }:
            return "Retry intake; completed pages will be reused."
        return "Review extraction error and retry intake."
    if stage == "pending":
        return "Start intake."
    if stage == "pages_done":
        return "Continue to summary."
    if stage == "summary_done":
        return "Generate action plan."
    if stage == "action_plan_done":
        return "Begin human review."
    if stage == "review_in_progress":
        return "Review, edit, approve, reject, or regenerate action items."
    if stage == "finalized":
        return "Open trusted dashboard."
    return None


def _is_known_user_facing_error(code: str | None) -> bool:
    return code in {
        "ai_rate_limit_rpm",
        "ai_rate_limit_tpm",
        "ai_timeout",
        "ai_network_error",
        "ocr_required",
        "ai_invalid_json",
        "partial_page_failure",
        "page_extraction_failed",
    }


def _record_stage_transition_audit(
    *,
    document_id: UUID,
    job_id: UUID | None,
    previous_stage: ExtractionJobStage | None,
    next_stage: ExtractionJobStage,
    source: str,
) -> None:
    if previous_stage == next_stage:
        return

    try:
        record_audit_event(
            entity_type="document",
            entity_id=document_id,
            action="case.stage.transitioned",
            actor_type="system",
            actor_id="orderflow_system",
            request_id=None,
            payload={
                "document_id": str(document_id),
                "extraction_job_id": str(job_id) if job_id is not None else None,
                "previous_stage": previous_stage,
                "next_stage": next_stage,
                "source": source,
            },
        )
    except Exception:
        pass
