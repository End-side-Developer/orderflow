from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.api.workbench_service import (
    build_document_workbench,
    build_workbench_overview,
)
from orderflow_api.schemas.workbench import (
    WorkbenchDocumentEnvelope,
    WorkbenchOverviewEnvelope,
)

router = APIRouter(tags=["workbench"])


@router.get("/workbench/overview", response_model=WorkbenchOverviewEnvelope)
async def get_workbench_overview_route(
    request: Request,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    data = build_workbench_overview()
    return success(data=data, request_id=request_id, message="workbench_overview")


@router.get("/workbench/documents/{document_id}", response_model=WorkbenchDocumentEnvelope)
async def get_document_workbench_route(
    request: Request,
    document_id: UUID,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)
    data = build_document_workbench(document_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return success(data=data, request_id=request_id, message="document_workbench")
