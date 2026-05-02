from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from orderflow_api.schemas.documents import DocumentStatus, SupportedLanguage
from orderflow_api.schemas.workflows import WorkflowRunStatus


PressureLevel = Literal["stable", "watch", "urgent", "critical"]
WorkbenchStage = Literal[
    "intake_running",
    "ready_for_extraction",
    "review_gate",
    "execution",
    "execution_risk",
    "closure_ready",
]
NextActionPriority = Literal["critical", "high", "medium"]


class WorkbenchDocumentMetrics(BaseModel):
    total_obligations: int = 0
    pending_review: int = 0
    approved: int = 0
    rejected: int = 0
    completed: int = 0
    open_escalations: int = 0
    critical_escalations: int = 0


class WorkbenchDocumentCard(BaseModel):
    document_id: UUID
    source_file_name: str
    source_language: SupportedLanguage
    status: DocumentStatus
    workflow_status: WorkflowRunStatus | None = None
    pressure_level: PressureLevel
    stage: WorkbenchStage
    next_action: str
    department: str | None = None
    court_name: str | None = None
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime | None = None
    metrics: WorkbenchDocumentMetrics


class WorkbenchSummary(BaseModel):
    total_documents: int = 0
    ready_documents: int = 0
    in_flight_documents: int = 0
    pending_review: int = 0
    open_escalations: int = 0
    critical_escalations: int = 0
    total_obligations: int = 0


class WorkbenchActivityItem(BaseModel):
    title: str
    document_id: UUID
    obligation_id: UUID | None = None
    action: str
    actor_type: str
    created_at: datetime
    level: PressureLevel = "stable"
    detail: str | None = None


class WorkbenchRelatedCase(BaseModel):
    document_id: UUID
    source_file_name: str
    similarity_score: float = Field(ge=0.0)
    overlap_count: int = Field(ge=0)
    rationale_tags: list[str] = Field(default_factory=list)
    sample_titles: list[str] = Field(default_factory=list)
    open_escalations: int = 0
    pressure_level: PressureLevel = "stable"
    recommended_focus: str


class WorkbenchNextAction(BaseModel):
    priority: NextActionPriority
    title: str
    detail: str


class WorkbenchOverviewData(BaseModel):
    summary: WorkbenchSummary
    documents: list[WorkbenchDocumentCard]
    recent_activity: list[WorkbenchActivityItem]


class WorkbenchOverviewEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: WorkbenchOverviewData


class WorkbenchDocumentData(BaseModel):
    document: WorkbenchDocumentCard
    related_cases: list[WorkbenchRelatedCase]
    next_actions: list[WorkbenchNextAction]
    recent_activity: list[WorkbenchActivityItem]


class WorkbenchDocumentEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: WorkbenchDocumentData
