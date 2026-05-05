from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from orderflow_api.api import extraction_job_persistence
from orderflow_api.schemas.cases import ExtractionJobStage, ExtractionJobStatusData


def test_update_extraction_job_stage_records_document_audit(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    job_id = uuid4()
    previous = _job(document_id=document_id, job_id=job_id, stage="pages_done")
    updated = _job(document_id=document_id, job_id=job_id, stage="summary_pending")
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(extraction_job_persistence, "get_extraction_job", lambda _: previous)
    monkeypatch.setattr(extraction_job_persistence, "_update_job", lambda *_args: updated)
    monkeypatch.setattr(
        extraction_job_persistence,
        "record_audit_event",
        lambda **kwargs: captured.append(kwargs),
    )

    result = extraction_job_persistence.update_extraction_job_stage(
        document_id,
        "summary_pending",
    )

    assert result == updated
    assert len(captured) == 1
    audit = captured[0]
    assert audit["entity_type"] == "document"
    assert audit["entity_id"] == document_id
    assert audit["action"] == "case.stage.transitioned"
    assert audit["actor_type"] == "system"
    assert audit["actor_id"] == "orderflow_system"
    assert audit["request_id"] is None
    assert audit["payload"] == {
        "document_id": str(document_id),
        "extraction_job_id": str(job_id),
        "previous_stage": "pages_done",
        "next_stage": "summary_pending",
        "source": "extraction_job_stage_update",
    }


def test_update_extraction_job_stage_skips_audit_when_stage_is_unchanged(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    job_id = uuid4()
    existing = _job(document_id=document_id, job_id=job_id, stage="summary_pending")
    captured: list[dict[str, object]] = []

    monkeypatch.setattr(extraction_job_persistence, "get_extraction_job", lambda _: existing)
    monkeypatch.setattr(extraction_job_persistence, "_update_job", lambda *_args: existing)
    monkeypatch.setattr(
        extraction_job_persistence,
        "record_audit_event",
        lambda **kwargs: captured.append(kwargs),
    )

    result = extraction_job_persistence.update_extraction_job_stage(
        document_id,
        "summary_pending",
    )

    assert result == existing
    assert captured == []


def test_to_extraction_job_status_adds_progress_message_fields() -> None:
    document_id = uuid4()
    job_id = uuid4()
    now = datetime.now(UTC)

    status = extraction_job_persistence._to_extraction_job_status(
        {
            "id": job_id,
            "document_id": document_id,
            "stage": "pages_extracting",
            "pages_total": 8,
            "pages_completed": 3,
            "current_page": 4,
            "current_page_excerpt": {
                "page_number": 4,
                "cache_status": "hit",
                "source_excerpt": "short excerpt",
            },
            "last_error_code": None,
            "last_error_message": None,
            "retry_after_seconds": None,
            "paused_until": None,
            "current_concurrency": 2,
            "started_at": now,
            "created_at": now,
            "updated_at": now,
            "finalized_at": None,
        }
    )

    assert status.status_message == "Extracting page 4 of 8. Completed 3 of 8 (hit)."
    assert status.current_page_cache_status == "hit"
    assert status.is_paused is False
    assert status.next_action is None


def test_to_extraction_job_status_uses_user_facing_error_message() -> None:
    document_id = uuid4()
    job_id = uuid4()
    now = datetime.now(UTC)
    error_message = (
        "This PDF page could not be read as text. Run OCR or upload a "
        "text-readable PDF, then restart intake."
    )

    status = extraction_job_persistence._to_extraction_job_status(
        {
            "id": job_id,
            "document_id": document_id,
            "stage": "pages_extracting",
            "pages_total": 5,
            "pages_completed": 2,
            "current_page": 3,
            "current_page_excerpt": {
                "page_number": 3,
                "cache_status": "failed",
                "error_code": "ocr_required",
                "error_message": error_message,
            },
            "last_error_code": "ocr_required",
            "last_error_message": error_message,
            "retry_after_seconds": None,
            "paused_until": None,
            "current_concurrency": 1,
            "started_at": now,
            "created_at": now,
            "updated_at": now,
            "finalized_at": None,
        }
    )

    assert status.status_message == error_message
    assert status.current_page_cache_status == "failed"
    assert status.next_action == "Run OCR or upload a text-readable PDF, then restart intake."


def _job(
    *,
    document_id: UUID,
    job_id: UUID,
    stage: ExtractionJobStage,
) -> ExtractionJobStatusData:
    now = datetime.now(UTC)
    return ExtractionJobStatusData(
        id=job_id,
        document_id=document_id,
        stage=stage,
        pages_total=5,
        pages_completed=5,
        current_page=None,
        current_page_excerpt=None,
        percent=100,
        error=None,
        retry_after_seconds=None,
        paused_until=None,
        current_concurrency=1,
        started_at=now,
        finalized_at=None,
        created_at=now,
        updated_at=now,
    )
