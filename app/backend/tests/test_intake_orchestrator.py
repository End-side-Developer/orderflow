from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from orderflow_api.api import intake_orchestrator
from orderflow_api.api.intake_orchestrator import (
    IntakeActionItemNotFoundError,
    IntakeActionItemStageError,
    IntakeDocumentNotFoundError,
    IntakeFinalizeReadinessError,
    IntakeJobNotFoundError,
    IntakeRegenerationFeedbackError,
    IntakeStageTransitionError,
    IntakeWorkflowStartError,
    finalize,
    finalize_after_review,
    get_job_status,
    regenerate_action_item,
    request_action_plan,
    request_action_plan_generation,
    request_summary,
    request_summary_generation,
    start_intake,
    submit_review,
    to_http_exception,
)
from orderflow_api.schemas.cases import ExtractionJobStatusData
from orderflow_api.schemas.documents import DocumentRecord
from orderflow_api.schemas.obligations import ObligationRecord
from orderflow_api.schemas.workflows import WorkflowRunRecord


def test_start_intake_creates_job_and_starts_temporal_workflow(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    captured: dict[str, object] = {}
    document = _document(document_id)
    job = _job(document_id, stage="pages_extracting")
    workflow_run = _workflow_run(document_id, run_id="temporal-run-1")

    async def fake_get_temporal_client():
        return _FakeTemporalClient(captured, run_id="temporal-run-1")

    def fake_create_extraction_job(document_id_arg, **kwargs):  # noqa: ANN001, ANN003
        captured["created_job"] = {"document_id": document_id_arg, **kwargs}
        return job

    def fake_record_workflow_run(**kwargs):  # noqa: ANN003
        captured["workflow_run"] = kwargs
        return workflow_run

    def fake_set_document_workflow_run_id(document_id_arg, run_id):  # noqa: ANN001
        captured["document_workflow_run_id"] = (document_id_arg, run_id)

    monkeypatch.setattr(intake_orchestrator, "get_persisted_document", lambda _: document)
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: None)
    monkeypatch.setattr(
        intake_orchestrator,
        "create_extraction_job",
        fake_create_extraction_job,
    )
    monkeypatch.setattr(intake_orchestrator, "get_temporal_client", fake_get_temporal_client)
    monkeypatch.setattr(intake_orchestrator, "record_workflow_run", fake_record_workflow_run)
    monkeypatch.setattr(
        intake_orchestrator,
        "set_document_workflow_run_id",
        fake_set_document_workflow_run_id,
    )

    result = asyncio.run(
        start_intake(
            document_id,
            bypass_cache=True,
            pages_total=12,
            current_concurrency=3,
        )
    )

    assert result.job == job
    assert result.workflow_run == workflow_run
    assert result.workflow_started is True
    assert captured["created_job"]["stage"] == "pages_extracting"
    assert captured["created_job"]["pages_total"] == 12
    assert captured["created_job"]["current_concurrency"] == 3
    assert captured["workflow_input"]["document_id"] == str(document_id)
    assert captured["workflow_input"]["bypass_cache"] == "true"
    assert captured["workflow_input"]["current_concurrency"] == "3"
    assert captured["workflow_run"]["metadata"] == {
        "source": "case_orchestrator_started",
        "bypass_cache": True,
    }
    assert captured["document_workflow_run_id"] == (document_id, "temporal-run-1")


def test_start_intake_advances_pending_job_and_reuses_existing_workflow(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    captured: dict[str, object] = {}
    document = _document(document_id, workflow_run_id="existing-run")
    pending_job = _job(document_id, stage="pending")
    extracting_job = _job(document_id, stage="pages_extracting")
    existing_run = _workflow_run(document_id, run_id="existing-run")

    async def fail_get_temporal_client():
        raise AssertionError("Temporal should not be started for an existing workflow")

    def fake_update_extraction_job_stage(document_id_arg, stage, **kwargs):  # noqa: ANN001, ANN003
        captured["stage_update"] = (document_id_arg, stage, kwargs)
        return extracting_job

    monkeypatch.setattr(intake_orchestrator, "get_persisted_document", lambda _: document)
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: pending_job)
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        fake_update_extraction_job_stage,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_workflow_run_by_run_id",
        lambda run_id: existing_run if run_id == "existing-run" else None,
    )
    monkeypatch.setattr(intake_orchestrator, "get_temporal_client", fail_get_temporal_client)

    result = asyncio.run(start_intake(document_id))

    assert result.job == extracting_job
    assert result.workflow_run == existing_run
    assert result.workflow_started is False
    assert captured["stage_update"][0] == document_id
    assert captured["stage_update"][1] == "pages_extracting"


def test_start_intake_raises_for_missing_document(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(intake_orchestrator, "get_persisted_document", lambda _: None)

    with pytest.raises(IntakeDocumentNotFoundError):
        asyncio.run(start_intake(uuid4()))


def test_start_intake_marks_job_failed_when_temporal_start_fails(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    captured: dict[str, object] = {}
    document = _document(document_id)
    job = _job(document_id, stage="pages_extracting")

    async def fail_get_temporal_client():
        raise RuntimeError("temporal unavailable")

    def fake_fail_extraction_job(document_id_arg, **kwargs):  # noqa: ANN001, ANN003
        captured["failed_job"] = (document_id_arg, kwargs)
        return job

    monkeypatch.setattr(intake_orchestrator, "get_persisted_document", lambda _: document)
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: job)
    monkeypatch.setattr(intake_orchestrator, "get_temporal_client", fail_get_temporal_client)
    monkeypatch.setattr(
        intake_orchestrator,
        "fail_extraction_job",
        fake_fail_extraction_job,
    )

    with pytest.raises(IntakeWorkflowStartError):
        asyncio.run(start_intake(document_id))

    assert captured["failed_job"][0] == document_id
    assert captured["failed_job"][1]["error_code"] == "temporal_start_failed"
    assert "RuntimeError: temporal unavailable" in captured["failed_job"][1]["error_message"]


def test_get_job_status_returns_progress_pause_retry_and_excerpt(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    status = _job(
        document_id,
        stage="pages_extracting",
        pages_total=10,
        pages_completed=4,
        current_page=5,
        current_page_excerpt={"page_number": 5, "text": "short source excerpt"},
        retry_after_seconds=30,
        paused_until=datetime(2026, 5, 4, 13, 30, tzinfo=UTC),
        current_concurrency=2,
    )

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: status)

    result = get_job_status(document_id)

    assert result == status
    assert result.percent == 40.0
    assert result.pages_total == 10
    assert result.pages_completed == 4
    assert result.current_page == 5
    assert result.current_page_excerpt == {
        "page_number": 5,
        "text": "short source excerpt",
    }
    assert result.retry_after_seconds == 30
    assert result.paused_until == datetime(2026, 5, 4, 13, 30, tzinfo=UTC)
    assert result.current_concurrency == 2


def test_get_job_status_raises_for_missing_document(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(intake_orchestrator, "get_persisted_document", lambda _: None)

    with pytest.raises(IntakeDocumentNotFoundError):
        get_job_status(uuid4())


def test_get_job_status_returns_pending_when_job_is_missing(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: None)

    result = get_job_status(document_id)

    assert result.id is None
    assert result.document_id == document_id
    assert result.stage == "pending"
    assert result.status_message == "Ready to begin intake."
    assert result.next_action == "Start intake."
    assert result.pages_total == 0
    assert result.pages_completed == 0


def test_request_summary_requires_pages_done_and_advances_stage(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    captured: dict[str, object] = {}
    pages_done = _job(document_id, stage="pages_done", pages_total=5, pages_completed=5)
    summary_pending = _job(
        document_id,
        stage="summary_pending",
        pages_total=5,
        pages_completed=5,
    )

    def fake_update_extraction_job_stage(document_id_arg, stage):  # noqa: ANN001
        captured["stage_update"] = (document_id_arg, stage)
        return summary_pending

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: pages_done)
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        fake_update_extraction_job_stage,
    )

    result = request_summary(document_id)

    assert result == summary_pending
    assert result.stage == "summary_pending"
    assert captured["stage_update"] == (document_id, "summary_pending")


def test_request_summary_rejects_before_pages_done(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    extracting = _job(
        document_id,
        stage="pages_extracting",
        pages_total=5,
        pages_completed=3,
    )

    def fail_update_extraction_job_stage(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("request_summary should not advance an invalid stage")

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: extracting)
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        fail_update_extraction_job_stage,
    )

    with pytest.raises(IntakeStageTransitionError) as exc_info:
        request_summary(document_id)

    error = exc_info.value
    assert error.document_id == document_id
    assert error.current_stage == "pages_extracting"
    assert error.expected_stage == "pages_done"
    assert error.next_stage == "summary_pending"


def test_request_summary_generation_signals_temporal_gate(monkeypatch) -> None:
    document_id = uuid4()
    captured: dict[str, object] = {}
    document = _document(document_id, workflow_run_id="temporal-run-1")
    pages_done = _job(document_id, stage="pages_done", pages_total=5, pages_completed=5)
    summary_pending = _job(
        document_id,
        stage="summary_pending",
        pages_total=5,
        pages_completed=5,
    )
    workflow_run = _workflow_run(document_id, run_id="temporal-run-1")

    async def fake_get_temporal_client():
        return _FakeTemporalClient(captured, run_id="temporal-run-1")

    monkeypatch.setattr(intake_orchestrator, "get_persisted_document", lambda _: document)
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: pages_done)
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        lambda *_args, **_kwargs: summary_pending,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_workflow_run_by_run_id",
        lambda run_id: workflow_run if run_id == "temporal-run-1" else None,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_temporal_client",
        fake_get_temporal_client,
    )

    result = asyncio.run(request_summary_generation(document_id))

    assert result.job == summary_pending
    assert result.workflow_signal_sent is True
    assert captured["workflow_handle"] == (
        workflow_run.workflow_id,
        workflow_run.run_id,
    )
    assert captured["workflow_signal"] == "advance_to_summary"


def test_request_action_plan_requires_summary_done_and_advances_stage(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    captured: dict[str, object] = {}
    summary_done = _job(
        document_id,
        stage="summary_done",
        pages_total=5,
        pages_completed=5,
    )
    action_plan_pending = _job(
        document_id,
        stage="action_plan_pending",
        pages_total=5,
        pages_completed=5,
    )

    def fake_update_extraction_job_stage(document_id_arg, stage):  # noqa: ANN001
        captured["stage_update"] = (document_id_arg, stage)
        return action_plan_pending

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: summary_done)
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        fake_update_extraction_job_stage,
    )

    result = request_action_plan(document_id)

    assert result == action_plan_pending
    assert result.stage == "action_plan_pending"
    assert captured["stage_update"] == (document_id, "action_plan_pending")


def test_request_action_plan_rejects_before_summary_done(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    summary_pending = _job(
        document_id,
        stage="summary_pending",
        pages_total=5,
        pages_completed=5,
    )

    def fail_update_extraction_job_stage(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("request_action_plan should not advance an invalid stage")

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: summary_pending)
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        fail_update_extraction_job_stage,
    )

    with pytest.raises(IntakeStageTransitionError) as exc_info:
        request_action_plan(document_id)

    error = exc_info.value
    assert error.document_id == document_id
    assert error.current_stage == "summary_pending"
    assert error.expected_stage == "summary_done"
    assert error.next_stage == "action_plan_pending"


def test_request_action_plan_generation_signals_temporal_gate(monkeypatch) -> None:
    document_id = uuid4()
    captured: dict[str, object] = {}
    document = _document(document_id, workflow_run_id="temporal-run-1")
    summary_done = _job(document_id, stage="summary_done", pages_total=5, pages_completed=5)
    action_plan_pending = _job(
        document_id,
        stage="action_plan_pending",
        pages_total=5,
        pages_completed=5,
    )
    workflow_run = _workflow_run(document_id, run_id="temporal-run-1")

    async def fake_get_temporal_client():
        return _FakeTemporalClient(captured, run_id="temporal-run-1")

    monkeypatch.setattr(intake_orchestrator, "get_persisted_document", lambda _: document)
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: summary_done)
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        lambda *_args, **_kwargs: action_plan_pending,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_workflow_run_by_run_id",
        lambda run_id: workflow_run if run_id == "temporal-run-1" else None,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_temporal_client",
        fake_get_temporal_client,
    )

    result = asyncio.run(request_action_plan_generation(document_id))

    assert result.job == action_plan_pending
    assert result.workflow_signal_sent is True
    assert captured["workflow_handle"] == (
        workflow_run.workflow_id,
        workflow_run.run_id,
    )
    assert captured["workflow_signal"] == "advance_to_action_plan"


def test_submit_review_requires_action_plan_done_and_advances_stage(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    captured: dict[str, object] = {}
    action_plan_done = _job(
        document_id,
        stage="action_plan_done",
        pages_total=5,
        pages_completed=5,
    )
    review_in_progress = _job(
        document_id,
        stage="review_in_progress",
        pages_total=5,
        pages_completed=5,
    )

    def fake_update_extraction_job_stage(document_id_arg, stage):  # noqa: ANN001
        captured["stage_update"] = (document_id_arg, stage)
        return review_in_progress

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_extraction_job",
        lambda _: action_plan_done,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        fake_update_extraction_job_stage,
    )

    result = submit_review(document_id)

    assert result == review_in_progress
    assert result.stage == "review_in_progress"
    assert captured["stage_update"] == (document_id, "review_in_progress")


def test_submit_review_reuses_existing_review_stage(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    review_in_progress = _job(
        document_id,
        stage="review_in_progress",
        pages_total=5,
        pages_completed=5,
    )

    def fail_update_extraction_job_stage(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("submit_review should not rewrite an active review")

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_extraction_job",
        lambda _: review_in_progress,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        fail_update_extraction_job_stage,
    )

    result = submit_review(document_id)

    assert result == review_in_progress
    assert result.stage == "review_in_progress"


def test_submit_review_rejects_before_action_plan_done(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    action_plan_pending = _job(
        document_id,
        stage="action_plan_pending",
        pages_total=5,
        pages_completed=5,
    )

    def fail_update_extraction_job_stage(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("submit_review should not advance an invalid stage")

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_extraction_job",
        lambda _: action_plan_pending,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        fail_update_extraction_job_stage,
    )

    with pytest.raises(IntakeStageTransitionError) as exc_info:
        submit_review(document_id)

    error = exc_info.value
    assert error.document_id == document_id
    assert error.current_stage == "action_plan_pending"
    assert error.expected_stage == ("action_plan_done", "review_in_progress")
    assert error.next_stage == "review_in_progress"


@pytest.mark.parametrize(
    ("gate", "current_stage"),
    (
        (request_summary, "pages_done"),
        (request_action_plan, "summary_done"),
        (submit_review, "action_plan_done"),
    ),
)
def test_stage_transition_gates_raise_job_not_found_when_update_returns_none(
    monkeypatch,
    gate,
    current_stage,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    job = _job(document_id, stage=current_stage, pages_total=5, pages_completed=5)

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: job)
    monkeypatch.setattr(
        intake_orchestrator,
        "update_extraction_job_stage",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(IntakeJobNotFoundError):
        gate(document_id)


def test_regenerate_action_item_requires_action_plan_item_and_feedback(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    obligation_id = uuid4()
    job = _job(document_id, stage="review_in_progress", pages_total=5, pages_completed=5)
    obligation = _obligation(
        document_id,
        obligation_id=obligation_id,
        action_plan_stage="review_pending",
    )

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: job)
    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_obligation_by_id",
        lambda _: obligation,
    )

    result = regenerate_action_item(
        document_id,
        obligation_id,
        "  clarify owner and deadline  ",
    )

    assert result.job == job
    assert result.obligation == obligation
    assert result.feedback == "clarify owner and deadline"


def test_regenerate_action_item_rejects_blank_feedback() -> None:
    with pytest.raises(IntakeRegenerationFeedbackError):
        regenerate_action_item(uuid4(), uuid4(), "   ")


def test_regenerate_action_item_rejects_missing_or_wrong_document_item(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    other_document_id = uuid4()
    obligation_id = uuid4()
    job = _job(document_id, stage="review_in_progress", pages_total=5, pages_completed=5)
    obligation = _obligation(
        other_document_id,
        obligation_id=obligation_id,
        action_plan_stage="review_pending",
    )

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: job)
    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_obligation_by_id",
        lambda _: obligation,
    )

    with pytest.raises(IntakeActionItemNotFoundError):
        regenerate_action_item(document_id, obligation_id, "regenerate this item")


def test_regenerate_action_item_rejects_absent_item(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    obligation_id = uuid4()
    job = _job(document_id, stage="review_in_progress", pages_total=5, pages_completed=5)

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: job)
    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_obligation_by_id",
        lambda _: None,
    )

    with pytest.raises(IntakeActionItemNotFoundError):
        regenerate_action_item(document_id, obligation_id, "regenerate this item")


def test_regenerate_action_item_rejects_extracted_non_action_plan_item(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    obligation_id = uuid4()
    job = _job(document_id, stage="review_in_progress", pages_total=5, pages_completed=5)
    obligation = _obligation(
        document_id,
        obligation_id=obligation_id,
        action_plan_stage="extracted",
    )

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: job)
    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_obligation_by_id",
        lambda _: obligation,
    )

    with pytest.raises(IntakeActionItemStageError) as exc_info:
        regenerate_action_item(document_id, obligation_id, "make it actionable")

    error = exc_info.value
    assert error.document_id == document_id
    assert error.obligation_id == obligation_id
    assert error.current_stage == "extracted"
    assert "review_pending" in error.allowed_stages


def test_regenerate_action_item_rejects_before_review_stage(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    obligation_id = uuid4()
    job = _job(document_id, stage="action_plan_done", pages_total=5, pages_completed=5)

    def fail_get_persisted_obligation_by_id(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("item lookup should wait for the correct case stage")

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: job)
    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_obligation_by_id",
        fail_get_persisted_obligation_by_id,
    )

    with pytest.raises(IntakeStageTransitionError) as exc_info:
        regenerate_action_item(document_id, obligation_id, "make it clearer")

    error = exc_info.value
    assert error.current_stage == "action_plan_done"
    assert error.expected_stage == "review_in_progress"
    assert error.next_stage == "review_in_progress"


def test_finalize_requires_all_items_reviewed_and_one_approved_or_edited(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    captured: dict[str, object] = {}
    review_job = _job(document_id, stage="review_in_progress", pages_total=5, pages_completed=5)
    finalized_job = _job(document_id, stage="finalized", pages_total=5, pages_completed=5)
    obligations = [
        _obligation(document_id, action_plan_stage="approved"),
        _obligation(document_id, action_plan_stage="edited"),
        _obligation(document_id, action_plan_stage="rejected"),
        _obligation(document_id, action_plan_stage="extracted"),
    ]

    def fake_list_persisted_obligations(document_id_arg):  # noqa: ANN001
        captured["listed_document_id"] = document_id_arg
        return obligations

    def fake_finalize_extraction_job(document_id_arg):  # noqa: ANN001
        captured["finalized_document_id"] = document_id_arg
        return finalized_job

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: review_job)
    monkeypatch.setattr(
        intake_orchestrator,
        "list_persisted_obligations",
        fake_list_persisted_obligations,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "finalize_extraction_job",
        fake_finalize_extraction_job,
    )

    result = finalize(document_id)

    assert result.job == finalized_job
    assert result.job.stage == "finalized"
    assert result.approved_count == 1
    assert result.edited_count == 1
    assert result.rejected_count == 1
    assert captured["listed_document_id"] == document_id
    assert captured["finalized_document_id"] == document_id


def test_finalize_after_review_signals_temporal_finalize_gate(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    captured: dict[str, object] = {}
    document = _document(document_id, workflow_run_id="temporal-run-1")
    review_job = _job(
        document_id,
        stage="review_in_progress",
        pages_total=5,
        pages_completed=5,
    )
    finalized_job = _job(
        document_id,
        stage="finalized",
        pages_total=5,
        pages_completed=5,
    )
    workflow_run = _workflow_run(document_id, run_id="temporal-run-1")
    obligations = [_obligation(document_id, action_plan_stage="approved")]

    async def fake_get_temporal_client():
        return _FakeTemporalClient(captured, run_id="temporal-run-1")

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: document,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_extraction_job",
        lambda _: review_job,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "list_persisted_obligations",
        lambda _: obligations,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "finalize_extraction_job",
        lambda _: finalized_job,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_workflow_run_by_run_id",
        lambda run_id: workflow_run if run_id == "temporal-run-1" else None,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "get_temporal_client",
        fake_get_temporal_client,
    )

    result = asyncio.run(finalize_after_review(document_id))

    assert result.job == finalized_job
    assert result.workflow_finalize_signal_sent is True
    assert captured["workflow_handle"] == (
        workflow_run.workflow_id,
        workflow_run.run_id,
    )
    assert captured["workflow_signal"] == "finalize"


def test_finalize_raises_job_not_found_when_finalizer_loses_job(
    monkeypatch,
) -> None:  # noqa: ANN001
    document_id = uuid4()
    review_job = _job(document_id, stage="review_in_progress", pages_total=5, pages_completed=5)
    obligations = [_obligation(document_id, action_plan_stage="approved")]

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: review_job)
    monkeypatch.setattr(
        intake_orchestrator,
        "list_persisted_obligations",
        lambda _: obligations,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "finalize_extraction_job",
        lambda _: None,
    )

    with pytest.raises(IntakeJobNotFoundError):
        finalize(document_id)


def test_finalize_rejects_unreviewed_action_plan_items(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    review_job = _job(document_id, stage="review_in_progress", pages_total=5, pages_completed=5)
    obligations = [
        _obligation(document_id, action_plan_stage="approved"),
        _obligation(document_id, action_plan_stage="review_pending"),
        _obligation(document_id, action_plan_stage="in_action_plan"),
    ]

    def fail_finalize_extraction_job(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("finalize should wait until every item is reviewed")

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: review_job)
    monkeypatch.setattr(
        intake_orchestrator,
        "list_persisted_obligations",
        lambda _: obligations,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "finalize_extraction_job",
        fail_finalize_extraction_job,
    )

    with pytest.raises(IntakeFinalizeReadinessError) as exc_info:
        finalize(document_id)

    error = exc_info.value
    assert error.document_id == document_id
    assert error.total_action_items == 3
    assert error.unreviewed_count == 2
    assert error.approved_count == 1
    assert error.edited_count == 0
    assert error.rejected_count == 0


def test_finalize_rejects_all_rejected_action_items(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    review_job = _job(document_id, stage="review_in_progress", pages_total=5, pages_completed=5)
    obligations = [
        _obligation(document_id, action_plan_stage="rejected"),
        _obligation(document_id, action_plan_stage="rejected"),
    ]

    def fail_finalize_extraction_job(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("finalize needs at least one approved or edited item")

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: review_job)
    monkeypatch.setattr(
        intake_orchestrator,
        "list_persisted_obligations",
        lambda _: obligations,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "finalize_extraction_job",
        fail_finalize_extraction_job,
    )

    with pytest.raises(IntakeFinalizeReadinessError) as exc_info:
        finalize(document_id)

    error = exc_info.value
    assert error.total_action_items == 2
    assert error.unreviewed_count == 0
    assert error.approved_count == 0
    assert error.edited_count == 0
    assert error.rejected_count == 2


def test_finalize_rejects_without_action_plan_items(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    review_job = _job(document_id, stage="review_in_progress", pages_total=5, pages_completed=5)
    obligations = [_obligation(document_id, action_plan_stage="extracted")]

    def fail_finalize_extraction_job(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("finalize needs at least one reviewed action-plan item")

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: review_job)
    monkeypatch.setattr(
        intake_orchestrator,
        "list_persisted_obligations",
        lambda _: obligations,
    )
    monkeypatch.setattr(
        intake_orchestrator,
        "finalize_extraction_job",
        fail_finalize_extraction_job,
    )

    with pytest.raises(IntakeFinalizeReadinessError) as exc_info:
        finalize(document_id)

    error = exc_info.value
    assert error.total_action_items == 0
    assert error.unreviewed_count == 0
    assert error.approved_count == 0
    assert error.edited_count == 0
    assert error.rejected_count == 0


def test_finalize_rejects_before_review_stage(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    job = _job(document_id, stage="action_plan_done", pages_total=5, pages_completed=5)

    def fail_list_persisted_obligations(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("finalize should not list items before the review stage")

    monkeypatch.setattr(
        intake_orchestrator,
        "get_persisted_document",
        lambda _: _document(document_id),
    )
    monkeypatch.setattr(intake_orchestrator, "get_extraction_job", lambda _: job)
    monkeypatch.setattr(
        intake_orchestrator,
        "list_persisted_obligations",
        fail_list_persisted_obligations,
    )

    with pytest.raises(IntakeStageTransitionError) as exc_info:
        finalize(document_id)

    error = exc_info.value
    assert error.current_stage == "action_plan_done"
    assert error.expected_stage == "review_in_progress"
    assert error.next_stage == "finalized"


def test_to_http_exception_maps_stage_transition_to_clear_409() -> None:
    document_id = uuid4()
    error = IntakeStageTransitionError(
        document_id=document_id,
        current_stage="pages_extracting",
        expected_stage="pages_done",
        next_stage="summary_pending",
    )

    http_error = to_http_exception(error)

    assert http_error.status_code == 409
    assert http_error.detail == {
        "code": "invalid_stage_transition",
        "message": str(error),
        "document_id": str(document_id),
        "current_stage": "pages_extracting",
        "expected_stage": "pages_done",
        "next_stage": "summary_pending",
    }


def test_to_http_exception_maps_multi_stage_transition_to_clear_409() -> None:
    document_id = uuid4()
    error = IntakeStageTransitionError(
        document_id=document_id,
        current_stage="action_plan_pending",
        expected_stage=("action_plan_done", "review_in_progress"),
        next_stage="review_in_progress",
    )

    http_error = to_http_exception(error)

    assert http_error.status_code == 409
    assert http_error.detail["code"] == "invalid_stage_transition"
    assert http_error.detail["document_id"] == str(document_id)
    assert http_error.detail["current_stage"] == "action_plan_pending"
    assert http_error.detail["expected_stage"] == [
        "action_plan_done",
        "review_in_progress",
    ]
    assert http_error.detail["next_stage"] == "review_in_progress"


def test_to_http_exception_maps_action_item_stage_to_clear_409() -> None:
    document_id = uuid4()
    obligation_id = uuid4()
    error = IntakeActionItemStageError(
        document_id=document_id,
        obligation_id=obligation_id,
        current_stage="extracted",
        allowed_stages=("in_action_plan", "review_pending", "approved"),
    )

    http_error = to_http_exception(error)

    assert http_error.status_code == 409
    assert http_error.detail == {
        "code": "invalid_action_item_stage",
        "message": str(error),
        "document_id": str(document_id),
        "obligation_id": str(obligation_id),
        "current_stage": "extracted",
        "allowed_stages": ["in_action_plan", "review_pending", "approved"],
    }


def test_to_http_exception_maps_finalize_readiness_to_clear_409() -> None:
    document_id = uuid4()
    error = IntakeFinalizeReadinessError(
        document_id=document_id,
        total_action_items=3,
        unreviewed_count=1,
        approved_count=1,
        edited_count=0,
        rejected_count=1,
    )

    http_error = to_http_exception(error)

    assert http_error.status_code == 409
    assert http_error.detail == {
        "code": "case_not_ready_to_finalize",
        "message": str(error),
        "document_id": str(document_id),
        "total_action_items": 3,
        "unreviewed_count": 1,
        "approved_count": 1,
        "edited_count": 0,
        "rejected_count": 1,
    }


class _FakeTemporalClient:
    def __init__(self, captured: dict[str, object], *, run_id: str) -> None:
        self._captured = captured
        self._run_id = run_id

    async def start_workflow(self, workflow_name, workflow_input, **kwargs):  # noqa: ANN001, ANN003
        self._captured["workflow_name"] = workflow_name
        self._captured["workflow_input"] = workflow_input
        self._captured["workflow_options"] = kwargs
        return _FakeTemporalHandle(self._run_id)

    def get_workflow_handle(self, workflow_id, *, run_id=None):  # noqa: ANN001
        self._captured["workflow_handle"] = (workflow_id, run_id)
        return _FakeTemporalSignalHandle(self._captured)


class _FakeTemporalHandle:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id


class _FakeTemporalSignalHandle:
    def __init__(self, captured: dict[str, object]) -> None:
        self._captured = captured

    async def signal(self, signal_name):  # noqa: ANN001
        self._captured["workflow_signal"] = signal_name


def _document(document_id: UUID, *, workflow_run_id: str | None = None) -> DocumentRecord:
    now = datetime.now(UTC)
    return DocumentRecord(
        id=document_id,
        source_file_name="judgment.pdf",
        source_file_type="application/pdf",
        source_file_size=1024,
        object_key=f"documents/{document_id}/judgment.pdf",
        checksum_sha256="a" * 64,
        workflow_run_id=workflow_run_id,
        status="uploaded",
        metadata=None,
        case_flow_graph=None,
        source_language="en",
        auto_detected_language=None,
        language_confidence=1.0,
        translated_text_stored=False,
        created_at=now,
        updated_at=now,
    )


def _job(
    document_id: UUID,
    *,
    stage: str,
    pages_total: int = 0,
    pages_completed: int = 0,
    current_page: int | None = None,
    current_page_excerpt: dict[str, object] | None = None,
    retry_after_seconds: int | None = None,
    paused_until: datetime | None = None,
    current_concurrency: int = 1,
) -> ExtractionJobStatusData:
    now = datetime.now(UTC)
    percent = round((pages_completed / pages_total) * 100, 2) if pages_total else 0.0
    return ExtractionJobStatusData(
        id=uuid4(),
        document_id=document_id,
        stage=stage,
        pages_total=pages_total,
        pages_completed=pages_completed,
        current_page=current_page,
        current_page_excerpt=current_page_excerpt,
        percent=percent,
        error=None,
        retry_after_seconds=retry_after_seconds,
        paused_until=paused_until,
        current_concurrency=current_concurrency,
        started_at=now if stage != "pending" else None,
        finalized_at=None,
        created_at=now,
        updated_at=now,
    )


def _obligation(
    document_id: UUID,
    *,
    obligation_id: UUID | None = None,
    action_plan_stage: str = "review_pending",
) -> ObligationRecord:
    now = datetime.now(UTC)
    return ObligationRecord(
        id=obligation_id or uuid4(),
        document_id=document_id,
        obligation_code="AP-001",
        title="Submit compliance report",
        description="Prepare and submit the compliance report.",
        owner_hint="Legal Department",
        due_date=None,
        status="active",
        priority="high",
        review_state="pending_review",
        confidence=0.9,
        nature_of_action="compliance_report",
        action_plan_stage=action_plan_stage,
        regen_count=0,
        regen_history=[],
        created_at=now,
        updated_at=now,
    )


def _workflow_run(document_id: UUID, *, run_id: str) -> WorkflowRunRecord:
    now = datetime.now(UTC)
    return WorkflowRunRecord(
        id=uuid4(),
        document_id=document_id,
        workflow_type="intake",
        workflow_id=f"orderflow-intake-{document_id}",
        run_id=run_id,
        task_queue="orderflow-task-queue",
        status="started",
        metadata={"source": "test"},
        started_at=now,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
