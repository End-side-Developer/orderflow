from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from orderflow_api.schemas.obligations import ObligationActionPlanStage, ObligationRecord
from orderflow_api.schemas.page_summaries import ExtractedPlace


ExtractionJobStage = Literal[
    "pending",
    "pages_extracting",
    "pages_done",
    "summary_pending",
    "summary_done",
    "action_plan_pending",
    "action_plan_done",
    "review_in_progress",
    "finalized",
]


class ExtractionJobError(BaseModel):
    code: str | None = None
    message: str | None = None


class ExtractionJobStatusData(BaseModel):
    id: UUID | None = None
    document_id: UUID
    stage: ExtractionJobStage
    pages_total: int = Field(default=0, ge=0)
    pages_completed: int = Field(default=0, ge=0)
    current_page: int | None = Field(default=None, ge=1)
    current_page_excerpt: dict[str, Any] | None = None
    percent: float = Field(default=0.0, ge=0.0, le=100.0)
    status_message: str = ""
    current_page_cache_status: str | None = None
    is_paused: bool = False
    next_action: str | None = None
    error: ExtractionJobError | None = None
    retry_after_seconds: int | None = Field(default=None, ge=0)
    paused_until: datetime | None = None
    current_concurrency: int = Field(default=1, ge=1)
    started_at: datetime | None = None
    finalized_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ExtractionJobStatusEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: ExtractionJobStatusData


DirectiveKind = Literal["mandatory", "advisory", "needs_review"]
ComplianceFlag = Literal["yes", "no", "needs_review"]
FlowNodeType = Literal["party", "event", "order", "obligation"]


class DocumentSummarySourceEvidence(BaseModel):
    page_number: int | None = Field(default=None, ge=1)
    paragraph_reference: str | None = None
    source_excerpt: str | None = None
    highlight_reference: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class DocumentSummaryCaseBasics(BaseModel):
    case_number: str | None = None
    court_name: str | None = None
    case_type: str | None = None
    order_date: str | None = None
    petitioner: str | None = None
    respondent: str | None = None
    judge_name: str | None = None
    department_involved: str | None = None
    disposal_status: str | None = None
    main_subject: str | None = None
    directive_summary: str | None = None


class DocumentSummaryDirective(BaseModel):
    direction_text: str
    source_page_number: int | None = Field(default=None, ge=1)
    source_paragraph_reference: str | None = None
    source_excerpt: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    directive_kind: DirectiveKind = "needs_review"
    compliance_required: ComplianceFlag = "needs_review"
    source_evidence: list[DocumentSummarySourceEvidence] = Field(default_factory=list)


class DocumentSummaryImportantDate(BaseModel):
    label: str
    date_text: str | None = None
    source: str | None = None
    is_inferred: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_evidence: list[DocumentSummarySourceEvidence] = Field(default_factory=list)


class DocumentSummaryEntity(BaseModel):
    name: str
    entity_type: str | None = None
    role: str | None = None
    source_page_number: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentSummaryResponsibleDepartment(BaseModel):
    primary_department: str | None = None
    supporting_departments: list[str] = Field(default_factory=list)
    legal_department_role: str | None = None
    petitioner: str | None = None
    respondent: str | None = None
    reason: str | None = None
    source_evidence: list[DocumentSummarySourceEvidence] = Field(default_factory=list)


class DocumentSummaryFlowNode(BaseModel):
    id: str
    node_type: FlowNodeType
    label: str
    detail: str | None = None
    page_ref: int | None = Field(default=None, ge=1)


class DocumentSummaryFlowEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str


class DocumentSummaryFlowGraph(BaseModel):
    document_id: UUID
    nodes: list[DocumentSummaryFlowNode] = Field(default_factory=list)
    edges: list[DocumentSummaryFlowEdge] = Field(default_factory=list)
    narrative_steps: list[str] = Field(default_factory=list)


class DocumentSummaryMapData(BaseModel):
    available: bool = False
    reason: str | None = None
    places: list[ExtractedPlace] = Field(default_factory=list)
    flow: list[dict[str, Any]] = Field(default_factory=list)


class DocumentSummaryData(BaseModel):
    id: UUID | None = None
    document_id: UUID
    case_basics: DocumentSummaryCaseBasics = Field(default_factory=DocumentSummaryCaseBasics)
    overview: str = ""
    key_directives: list[DocumentSummaryDirective] = Field(default_factory=list)
    important_dates: list[DocumentSummaryImportantDate] = Field(default_factory=list)
    entities_involved: list[DocumentSummaryEntity] = Field(default_factory=list)
    responsible_departments: list[DocumentSummaryResponsibleDepartment] = Field(
        default_factory=list
    )
    flow_graph: DocumentSummaryFlowGraph | None = None
    map_data: DocumentSummaryMapData | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    prompt_version: str | None = None
    ai_model: str | None = None
    ai_provider: str | None = None
    generated_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentSummaryEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: DocumentSummaryData


ActionPlanReviewDecision = Literal["approve", "edit", "reject"]


class ActionPlanItemReviewRequest(BaseModel):
    decision: ActionPlanReviewDecision
    reviewer_name: str | None = Field(default=None, max_length=200)
    edited_fields: dict[str, Any] | None = None
    rejection_reason: str | None = Field(default=None, max_length=1000)
    comments: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _validate_decision_payload(self):
        if self.decision == "edit" and not self.edited_fields:
            raise ValueError("edited_fields is required when decision is edit")
        if self.decision == "reject" and not self.rejection_reason:
            raise ValueError("rejection_reason is required when decision is reject")
        return self


class ActionPlanItemReviewData(BaseModel):
    document_id: UUID
    obligation_id: UUID
    decision: ActionPlanReviewDecision
    action_plan_stage: ObligationActionPlanStage
    obligation: ObligationRecord | None = None
    reviewer_name: str | None = None
    rejection_reason: str | None = None
    reviewed_at: datetime | None = None
    comments: str | None = None


class ActionPlanItemReviewEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: ActionPlanItemReviewData


class ActionPlanItemRegenerateRequest(BaseModel):
    feedback: str = Field(..., min_length=1, max_length=4000)
    reviewer_name: str | None = Field(default=None, max_length=200)


class ActionPlanItemRegenerateData(BaseModel):
    document_id: UUID
    obligation_id: UUID
    action_plan_stage: ObligationActionPlanStage
    regen_count: int = Field(default=0, ge=0)
    obligation: ObligationRecord | None = None
    updated_fields: dict[str, Any] = Field(default_factory=dict)
    regenerated_at: datetime | None = None


class ActionPlanItemRegenerateEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: ActionPlanItemRegenerateData


class CaseFinalizeRequest(BaseModel):
    reviewer_name: str | None = Field(default=None, max_length=200)
    comments: str | None = Field(default=None, max_length=2000)


class CaseFinalizeData(BaseModel):
    document_id: UUID
    stage: Literal["finalized"] = "finalized"
    approved_count: int = Field(default=0, ge=0)
    edited_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    finalized_at: datetime | None = None


class CaseFinalizeEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: CaseFinalizeData


class CaseDashboardGroup(BaseModel):
    responsible_department: str
    total: int = Field(default=0, ge=0)
    items: list[ObligationRecord] = Field(default_factory=list)


class CaseDashboardData(BaseModel):
    document_id: UUID
    total: int = Field(default=0, ge=0)
    approved_total: int = Field(default=0, ge=0)
    edited_total: int = Field(default=0, ge=0)
    groups: list[CaseDashboardGroup] = Field(default_factory=list)


class CaseDashboardEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: CaseDashboardData
