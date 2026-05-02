from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


WorkflowRunStatus = Literal["started", "completed", "failed"]


class StartIntakeWorkflowRequest(BaseModel):
    document_id: UUID


class WorkflowRunRecord(BaseModel):
    id: UUID
    document_id: UUID
    workflow_type: str
    workflow_id: str
    run_id: str
    task_queue: str
    status: WorkflowRunStatus
    metadata: dict[str, Any] | None = None
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowRunEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: WorkflowRunRecord
