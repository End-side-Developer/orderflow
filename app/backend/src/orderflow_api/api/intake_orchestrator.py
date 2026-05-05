from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from orderflow_api.api.document_persistence import (
    get_persisted_document,
    set_document_workflow_run_id,
)
from orderflow_api.api.extraction_job_persistence import (
    create_extraction_job,
    fail_extraction_job,
    finalize_extraction_job,
    get_extraction_job,
    update_extraction_job_stage,
)
from orderflow_api.api.extraction_persistence import (
    get_persisted_obligation_by_id,
    list_persisted_obligations,
)
from orderflow_api.api.workflow_persistence import (
    get_workflow_run_by_run_id,
    record_workflow_run,
)
from orderflow_api.core.config import settings
from orderflow_api.core.temporal import get_temporal_client
from orderflow_api.schemas.cases import ExtractionJobStage, ExtractionJobStatusData
from orderflow_api.schemas.documents import DocumentRecord
from orderflow_api.schemas.obligations import ObligationActionPlanStage, ObligationRecord
from orderflow_api.schemas.workflows import WorkflowRunRecord

logger = logging.getLogger(__name__)

ACTION_PLAN_ITEM_STAGES: tuple[ObligationActionPlanStage, ...] = (
    "in_action_plan",
    "review_pending",
    "approved",
    "rejected",
    "edited",
)
FINAL_REVIEWED_ACTION_PLAN_ITEM_STAGES: tuple[ObligationActionPlanStage, ...] = (
    "approved",
    "rejected",
    "edited",
)
APPROVED_ACTION_PLAN_ITEM_STAGES: tuple[ObligationActionPlanStage, ...] = (
    "approved",
    "edited",
)


class IntakeOrchestratorError(Exception):
    """Base class for intake orchestration failures."""


class IntakeDocumentNotFoundError(IntakeOrchestratorError):
    """Raised when an intake flow is requested for an unknown document."""


class IntakeJobNotFoundError(IntakeOrchestratorError):
    """Raised when status is requested before an intake job exists."""


class IntakeActionItemNotFoundError(IntakeOrchestratorError):
    """Raised when a requested action-plan item cannot be found for a document."""


class IntakeActionItemStageError(IntakeOrchestratorError):
    """Raised when an obligation is not yet part of the action plan."""

    def __init__(
        self,
        *,
        document_id: UUID,
        obligation_id: UUID,
        current_stage: ObligationActionPlanStage,
        allowed_stages: tuple[ObligationActionPlanStage, ...],
    ) -> None:
        self.document_id = document_id
        self.obligation_id = obligation_id
        self.current_stage = current_stage
        self.allowed_stages = allowed_stages
        super().__init__(
            f"Cannot regenerate obligation {obligation_id} for document {document_id}; "
            f"action_plan_stage is {current_stage}, expected one of "
            f"{', '.join(allowed_stages)}."
        )


class IntakeRegenerationFeedbackError(IntakeOrchestratorError):
    """Raised when a regeneration request has no reviewer feedback."""


class IntakeFinalizeReadinessError(IntakeOrchestratorError):
    """Raised when a case cannot be finalized because review is incomplete."""

    def __init__(
        self,
        *,
        document_id: UUID,
        total_action_items: int,
        unreviewed_count: int,
        approved_count: int,
        edited_count: int,
        rejected_count: int,
    ) -> None:
        self.document_id = document_id
        self.total_action_items = total_action_items
        self.unreviewed_count = unreviewed_count
        self.approved_count = approved_count
        self.edited_count = edited_count
        self.rejected_count = rejected_count
        super().__init__(
            f"Cannot finalize document {document_id}; total_action_items="
            f"{total_action_items}, unreviewed_count={unreviewed_count}, "
            f"approved_count={approved_count}, edited_count={edited_count}, "
            f"rejected_count={rejected_count}."
        )


class IntakeStageTransitionError(IntakeOrchestratorError):
    """Raised when a requested stage transition violates the intake flow."""

    def __init__(
        self,
        *,
        document_id: UUID,
        current_stage: ExtractionJobStage,
        expected_stage: ExtractionJobStage | tuple[ExtractionJobStage, ...],
        next_stage: ExtractionJobStage,
    ) -> None:
        self.document_id = document_id
        self.current_stage = current_stage
        self.expected_stage = expected_stage
        self.next_stage = next_stage
        expected_label = (
            " or ".join(expected_stage) if isinstance(expected_stage, tuple) else expected_stage
        )
        super().__init__(
            f"Cannot advance document {document_id} from {current_stage} to "
            f"{next_stage}; expected {expected_label}."
        )


class IntakeWorkflowStartError(IntakeOrchestratorError):
    """Raised when the Temporal intake workflow cannot be started."""


def to_http_exception(error: IntakeOrchestratorError) -> HTTPException:
    """Translate intake gate failures into route-safe HTTP responses."""
    if isinstance(error, IntakeStageTransitionError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_stage_transition",
                "message": str(error),
                "document_id": str(error.document_id),
                "current_stage": error.current_stage,
                "expected_stage": _expected_stage_detail(error.expected_stage),
                "next_stage": error.next_stage,
            },
        )

    if isinstance(error, IntakeActionItemStageError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_action_item_stage",
                "message": str(error),
                "document_id": str(error.document_id),
                "obligation_id": str(error.obligation_id),
                "current_stage": error.current_stage,
                "allowed_stages": list(error.allowed_stages),
            },
        )

    if isinstance(error, IntakeFinalizeReadinessError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "case_not_ready_to_finalize",
                "message": str(error),
                "document_id": str(error.document_id),
                "total_action_items": error.total_action_items,
                "unreviewed_count": error.unreviewed_count,
                "approved_count": error.approved_count,
                "edited_count": error.edited_count,
                "rejected_count": error.rejected_count,
            },
        )

    if isinstance(error, (IntakeDocumentNotFoundError, IntakeJobNotFoundError)):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "intake_not_found", "message": str(error)},
        )

    if isinstance(error, IntakeActionItemNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "action_item_not_found", "message": str(error)},
        )

    if isinstance(error, IntakeRegenerationFeedbackError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "regeneration_feedback_required", "message": str(error)},
        )

    if isinstance(error, IntakeWorkflowStartError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "intake_workflow_start_failed", "message": str(error)},
        )

    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "intake_orchestrator_error", "message": str(error)},
    )


@dataclass(frozen=True)
class StartIntakeResult:
    job: ExtractionJobStatusData
    workflow_run: WorkflowRunRecord
    workflow_started: bool


@dataclass(frozen=True)
class RegenerateActionItemGateResult:
    job: ExtractionJobStatusData
    obligation: ObligationRecord
    feedback: str


@dataclass(frozen=True)
class StageGateSignalResult:
    job: ExtractionJobStatusData
    workflow_signal_sent: bool = False


@dataclass(frozen=True)
class FinalizeGateResult:
    job: ExtractionJobStatusData
    approved_count: int
    edited_count: int
    rejected_count: int
    workflow_finalize_signal_sent: bool = False


async def start_intake(
    document_id: UUID,
    *,
    bypass_cache: bool = False,
    pages_total: int = 0,
    current_concurrency: int = 1,
) -> StartIntakeResult:
    """Create or reuse an intake job and ensure its Temporal workflow is running."""
    document = get_persisted_document(document_id)
    if document is None:
        raise IntakeDocumentNotFoundError(f"Document not found: {document_id}")

    job = _ensure_started_job(
        document_id,
        pages_total=pages_total,
        current_concurrency=current_concurrency,
    )
    workflow_run, workflow_started = await _ensure_intake_workflow(
        document,
        bypass_cache=bypass_cache,
        current_concurrency=current_concurrency,
    )
    return StartIntakeResult(
        job=job,
        workflow_run=workflow_run,
        workflow_started=workflow_started,
    )


def get_job_status(document_id: UUID) -> ExtractionJobStatusData:
    """Return the persisted intake job status for a document."""
    document = get_persisted_document(document_id)
    if document is None:
        raise IntakeDocumentNotFoundError(f"Document not found: {document_id}")

    job = get_extraction_job(document_id)
    if job is None:
        return _pending_job_status(document_id)
    return job


def _pending_job_status(document_id: UUID) -> ExtractionJobStatusData:
    """Return the pre-intake status for a valid uploaded document."""
    return ExtractionJobStatusData(
        id=None,
        document_id=document_id,
        stage="pending",
        pages_total=0,
        pages_completed=0,
        current_page=None,
        current_page_excerpt=None,
        percent=0.0,
        status_message="Ready to begin intake.",
        current_page_cache_status=None,
        is_paused=False,
        next_action="Start intake.",
        error=None,
        retry_after_seconds=None,
        paused_until=None,
        current_concurrency=1,
        started_at=None,
        finalized_at=None,
        created_at=None,
        updated_at=None,
    )


def request_summary(document_id: UUID) -> ExtractionJobStatusData:
    """Advance from completed page extraction to summary generation."""
    job = get_job_status(document_id)
    if job.stage != "pages_done":
        raise IntakeStageTransitionError(
            document_id=document_id,
            current_stage=job.stage,
            expected_stage="pages_done",
            next_stage="summary_pending",
        )

    updated = update_extraction_job_stage(document_id, "summary_pending")
    if updated is None:
        raise IntakeJobNotFoundError(f"Intake job not found: {document_id}")
    return updated


def request_action_plan(document_id: UUID) -> ExtractionJobStatusData:
    """Advance from completed summary generation to action-plan generation."""
    job = get_job_status(document_id)
    if job.stage != "summary_done":
        raise IntakeStageTransitionError(
            document_id=document_id,
            current_stage=job.stage,
            expected_stage="summary_done",
            next_stage="action_plan_pending",
        )

    updated = update_extraction_job_stage(document_id, "action_plan_pending")
    if updated is None:
        raise IntakeJobNotFoundError(f"Intake job not found: {document_id}")
    return updated


async def request_summary_generation(document_id: UUID) -> StageGateSignalResult:
    """Advance the summary gate and release the waiting intake workflow."""
    job = request_summary(document_id)
    signal_sent = await signal_advance_to_summary(document_id)
    return StageGateSignalResult(job=job, workflow_signal_sent=signal_sent)


async def request_action_plan_generation(document_id: UUID) -> StageGateSignalResult:
    """Advance the action-plan gate and release the waiting intake workflow."""
    job = request_action_plan(document_id)
    signal_sent = await signal_advance_to_action_plan(document_id)
    return StageGateSignalResult(job=job, workflow_signal_sent=signal_sent)


def submit_review(document_id: UUID) -> ExtractionJobStatusData:
    """Enter human review after the action plan is generated."""
    job = get_job_status(document_id)
    if job.stage == "review_in_progress":
        return job

    if job.stage != "action_plan_done":
        raise IntakeStageTransitionError(
            document_id=document_id,
            current_stage=job.stage,
            expected_stage=("action_plan_done", "review_in_progress"),
            next_stage="review_in_progress",
        )

    updated = update_extraction_job_stage(document_id, "review_in_progress")
    if updated is None:
        raise IntakeJobNotFoundError(f"Intake job not found: {document_id}")
    return updated


def regenerate_action_item(
    document_id: UUID,
    obligation_id: UUID,
    feedback: str,
) -> RegenerateActionItemGateResult:
    """Validate a per-item regeneration request before AI or persistence updates."""
    normalized_feedback = feedback.strip()
    if not normalized_feedback:
        raise IntakeRegenerationFeedbackError("Regeneration feedback is required.")

    job = get_job_status(document_id)
    if job.stage != "review_in_progress":
        raise IntakeStageTransitionError(
            document_id=document_id,
            current_stage=job.stage,
            expected_stage="review_in_progress",
            next_stage="review_in_progress",
        )

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

    return RegenerateActionItemGateResult(
        job=job,
        obligation=obligation,
        feedback=normalized_feedback,
    )


def finalize(document_id: UUID) -> FinalizeGateResult:
    """Finalize a reviewed case only when every action-plan item has a decision."""
    job = get_job_status(document_id)
    if job.stage != "review_in_progress":
        raise IntakeStageTransitionError(
            document_id=document_id,
            current_stage=job.stage,
            expected_stage="review_in_progress",
            next_stage="finalized",
        )

    action_items = [
        obligation
        for obligation in list_persisted_obligations(document_id)
        if obligation.action_plan_stage in ACTION_PLAN_ITEM_STAGES
    ]
    approved_count = _count_action_items(action_items, "approved")
    edited_count = _count_action_items(action_items, "edited")
    rejected_count = _count_action_items(action_items, "rejected")
    unreviewed_count = sum(
        1
        for obligation in action_items
        if obligation.action_plan_stage not in FINAL_REVIEWED_ACTION_PLAN_ITEM_STAGES
    )

    if not action_items or unreviewed_count or (approved_count + edited_count) == 0:
        raise IntakeFinalizeReadinessError(
            document_id=document_id,
            total_action_items=len(action_items),
            unreviewed_count=unreviewed_count,
            approved_count=approved_count,
            edited_count=edited_count,
            rejected_count=rejected_count,
        )

    finalized_job = finalize_extraction_job(document_id)
    if finalized_job is None:
        raise IntakeJobNotFoundError(f"Intake job not found: {document_id}")

    return FinalizeGateResult(
        job=finalized_job,
        approved_count=approved_count,
        edited_count=edited_count,
        rejected_count=rejected_count,
    )


async def finalize_after_review(document_id: UUID) -> FinalizeGateResult:
    """Finalize a reviewed case and release the waiting intake workflow."""
    result = finalize(document_id)
    signal_sent = await signal_finalize(document_id)
    return FinalizeGateResult(
        job=result.job,
        approved_count=result.approved_count,
        edited_count=result.edited_count,
        rejected_count=result.rejected_count,
        workflow_finalize_signal_sent=signal_sent,
    )


async def signal_finalize(document_id: UUID) -> bool:
    """Best-effort signal for a workflow waiting after human review."""
    return await _signal_intake_workflow(document_id, "finalize")


async def signal_advance_to_summary(document_id: UUID) -> bool:
    """Best-effort signal for a workflow waiting after page extraction."""
    return await _signal_intake_workflow(document_id, "advance_to_summary")


async def signal_advance_to_action_plan(document_id: UUID) -> bool:
    """Best-effort signal for a workflow waiting after summary generation."""
    return await _signal_intake_workflow(document_id, "advance_to_action_plan")


async def _signal_intake_workflow(document_id: UUID, signal_name: str) -> bool:
    workflow_run = _find_intake_workflow_run(document_id)
    if workflow_run is None:
        return False

    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(
            workflow_run.workflow_id,
            run_id=workflow_run.run_id,
        )
        await handle.signal(signal_name)
    except Exception as exc:
        logger.error(
            "Failed to signal intake workflow %s/%s with signal %s: %s: %s",
            workflow_run.workflow_id,
            workflow_run.run_id,
            signal_name,
            type(exc).__name__,
            exc,
        )
        return False

    return True


def _ensure_started_job(
    document_id: UUID,
    *,
    pages_total: int,
    current_concurrency: int,
) -> ExtractionJobStatusData:
    existing = get_extraction_job(document_id)
    if existing is None:
        return create_extraction_job(
            document_id,
            pages_total=pages_total,
            current_concurrency=current_concurrency,
            stage="pages_extracting",
            started_at=datetime.now(UTC),
        )

    if existing.stage == "pending":
        updated = update_extraction_job_stage(
            document_id,
            "pages_extracting",
            started_at=existing.started_at or datetime.now(UTC),
        )
        if updated is not None:
            return updated

    return existing


def _count_action_items(
    obligations: list[ObligationRecord],
    stage: ObligationActionPlanStage,
) -> int:
    return sum(1 for obligation in obligations if obligation.action_plan_stage == stage)


def _find_intake_workflow_run(document_id: UUID) -> WorkflowRunRecord | None:
    document = get_persisted_document(document_id)
    if document is None or not document.workflow_run_id:
        return None
    return get_workflow_run_by_run_id(document.workflow_run_id)


def _expected_stage_detail(
    expected_stage: ExtractionJobStage | tuple[ExtractionJobStage, ...],
) -> str | list[str]:
    if isinstance(expected_stage, tuple):
        return list(expected_stage)
    return expected_stage


async def _ensure_intake_workflow(
    document: DocumentRecord,
    *,
    bypass_cache: bool,
    current_concurrency: int,
) -> tuple[WorkflowRunRecord, bool]:
    if document.workflow_run_id:
        existing_run = get_workflow_run_by_run_id(document.workflow_run_id)
        if existing_run is not None:
            return existing_run, False

    workflow_id = "-".join(
        (
            settings.orderflow_api_temporal_workflow_id_prefix,
            str(document.id),
            uuid4().hex[:8],
        )
    )
    workflow_input = {
        "document_id": str(document.id),
        "source_language": document.source_language,
        "translated_text_stored": "true" if document.translated_text_stored else "false",
        "bypass_cache": "true" if bypass_cache else "false",
        "current_concurrency": str(max(1, current_concurrency)),
    }
    # Pass pages_total from document metadata if available
    pages_total = document.metadata.get("pages_total") if document.metadata else None
    if pages_total is not None:
        workflow_input["pages_total"] = str(pages_total)
        workflow_input["total_pages"] = str(pages_total)

    try:
        client = await get_temporal_client()
        handle = await client.start_workflow(
            "orderflow-intake-workflow",
            workflow_input,
            id=workflow_id,
            task_queue=settings.orderflow_api_temporal_task_queue,
        )
    except Exception as exc:
        fail_extraction_job(
            document.id,
            error_code="temporal_start_failed",
            error_message=f"{type(exc).__name__}: {exc}",
        )
        raise IntakeWorkflowStartError(f"Temporal start failed: {exc}") from exc

    run_id = _extract_run_id(handle)
    workflow_run = record_workflow_run(
        document_id=document.id,
        workflow_type="intake",
        workflow_id=workflow_id,
        run_id=run_id,
        task_queue=settings.orderflow_api_temporal_task_queue,
        status="started",
        metadata={
            "source": "case_orchestrator_started",
            "bypass_cache": bypass_cache,
        },
    )
    set_document_workflow_run_id(document.id, run_id)
    return workflow_run, True


def _extract_run_id(handle: object) -> str:
    for attribute in ("result_run_id", "run_id", "first_execution_run_id"):
        value = getattr(handle, attribute, None)
        if isinstance(value, str) and value:
            return value
    raise IntakeWorkflowStartError(
        "Temporal workflow handle has no run_id attribute. "
        "The workflow may not have started correctly."
    )
