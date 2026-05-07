from __future__ import annotations

from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.document_persistence import (
    get_persisted_document,
    set_document_workflow_run_id,
)
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.api.workflow_persistence import (
    get_latest_workflow_run_for_document,
    get_workflow_run_by_run_id,
    record_workflow_run,
    update_workflow_run_status,
)
from orderflow_api.core.config import settings
from orderflow_api.core.temporal import get_temporal_client
from orderflow_api.schemas.workflows import StartIntakeWorkflowRequest, WorkflowRunEnvelope

router = APIRouter(tags=["workflows"])


@router.get(
    "/workflows/runs/{run_id}",
    response_model=WorkflowRunEnvelope,
    status_code=status.HTTP_200_OK,
)
async def get_workflow_run_route(
    request: Request,
    run_id: str,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    run_record = get_workflow_run_by_run_id(run_id)
    if run_record is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    run_record = await _reconcile_run_with_temporal(run_record)

    request_id = getattr(request.state, "request_id", None)
    return success(data=run_record, request_id=request_id, message="workflow_status")


@router.get(
    "/workflows/intake/status",
    response_model=WorkflowRunEnvelope,
    status_code=status.HTTP_200_OK,
)
async def get_intake_workflow_status_route(
    request: Request,
    document_id: UUID = Query(...),
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    document = get_persisted_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    run_record = None
    if document.workflow_run_id:
        run_record = get_workflow_run_by_run_id(document.workflow_run_id)

    if run_record is None:
        run_record = get_latest_workflow_run_for_document(document_id)

    if run_record is None:
        raise HTTPException(status_code=404, detail="Workflow run not found for document")

    run_record = await _reconcile_run_with_temporal(run_record)

    request_id = getattr(request.state, "request_id", None)
    return success(data=run_record, request_id=request_id, message="workflow_status")


@router.post(
    "/workflows/intake/start",
    response_model=WorkflowRunEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def start_intake_workflow_route(
    request: Request,
    payload: StartIntakeWorkflowRequest,
    _user=Depends(require_permission(Permission.EXTRACTION_RUN)),
) -> dict[str, object]:
    document = get_persisted_document(payload.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.workflow_run_id:
        existing_run = get_workflow_run_by_run_id(document.workflow_run_id)
        if existing_run is not None:
            request_id = getattr(request.state, "request_id", None)
            return success(
                data=existing_run,
                request_id=request_id,
                message="workflow_already_started",
            )

    workflow_id = "-".join(
        (
            settings.orderflow_api_temporal_workflow_id_prefix,
            str(payload.document_id),
            uuid4().hex[:8],
        )
    )

    try:
        client = await get_temporal_client()
        workflow_input = {
            "document_id": str(payload.document_id),
            "source_language": document.source_language,
            "translated_text_stored": "true" if document.translated_text_stored else "false",
            "bypass_cache": "true" if payload.bypass_cache else "false",
        }
        # Pass pages_total from document metadata if available
        pages_total = document.metadata.get("pages_total") if document.metadata else None
        if pages_total is not None:
            workflow_input["pages_total"] = str(pages_total)
            workflow_input["total_pages"] = str(pages_total)

        handle = await client.start_workflow(
            "orderflow-intake-workflow",
            workflow_input,
            id=workflow_id,
            task_queue=settings.orderflow_api_temporal_task_queue,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Temporal start failed: {exc}") from exc

    run_id = _extract_run_id(handle)
    run_record = record_workflow_run(
        document_id=payload.document_id,
        workflow_type="intake",
        workflow_id=workflow_id,
        run_id=run_id,
        task_queue=settings.orderflow_api_temporal_task_queue,
        status="started",
        metadata={"source": "api", "bypass_cache": payload.bypass_cache},
    )
    set_document_workflow_run_id(payload.document_id, run_id)

    request_id = getattr(request.state, "request_id", None)
    return success(
        data=run_record,
        request_id=request_id,
        message="workflow_started",
    )


def _extract_run_id(handle: object) -> str:
    for attribute in ("result_run_id", "run_id", "first_execution_run_id"):
        value = getattr(handle, attribute, None)
        if isinstance(value, str) and value:
            return value

    raise HTTPException(
        status_code=502,
        detail="Temporal workflow handle has no run_id attribute. The workflow may not have started correctly.",
    )


async def _reconcile_run_with_temporal(run_record):
    if run_record.status != "started":
        return run_record

    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(run_record.workflow_id, run_id=run_record.run_id)
        description = await handle.describe()
    except Exception:
        # Keep last known DB status when Temporal is temporarily unreachable.
        return run_record

    next_status = _map_temporal_status_to_run_status(description.status)
    close_time = getattr(description, "close_time", None)

    if next_status == run_record.status and (
        close_time is None or run_record.completed_at is not None
    ):
        return run_record

    metadata_patch: dict[str, object] | None = None
    if next_status == "failed":
        failure_reason = await _resolve_workflow_failure_reason(handle)
        metadata_patch = {
            "temporal_status": getattr(description.status, "name", str(description.status)).lower(),
        }
        if close_time is not None:
            metadata_patch["close_time"] = close_time.isoformat()
        if failure_reason:
            metadata_patch["failure_reason"] = failure_reason

    updated = update_workflow_run_status(
        run_record.run_id,
        status=next_status,
        completed_at=close_time,
        metadata_patch=metadata_patch,
    )
    return updated or run_record


async def _resolve_workflow_failure_reason(handle) -> str | None:
    try:
        await handle.result()
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"

    return None


def _map_temporal_status_to_run_status(temporal_status: object) -> str:
    status_name = getattr(temporal_status, "name", str(temporal_status)).upper()
    if "COMPLETED" in status_name:
        return "completed"
    if any(
        token in status_name for token in ("FAILED", "CANCEL", "TERMINATED", "TIMED_OUT", "TIMEOUT")
    ):
        return "failed"

    return "started"
