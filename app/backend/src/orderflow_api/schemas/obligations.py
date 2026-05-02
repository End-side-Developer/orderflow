from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


ObligationStatus = Literal["draft", "active", "completed", "cancelled"]
ObligationPriority = Literal["low", "medium", "high", "critical"]
ObligationReviewState = Literal["pending_review", "approved", "rejected"]
EscalationLevel = Literal["none", "watch", "escalated", "critical"]


class ObligationCitation(BaseModel):
    page_number: int | None = Field(default=None, ge=1)
    clause_span: str | None = None
    clause_index: int | None = Field(default=None, ge=1)
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=0)


class ObligationConfidenceAnnotations(BaseModel):
    extractor_version: str | None = None
    components: dict[str, float] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)
    signals: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ObligationEscalationSignal(BaseModel):
    level: EscalationLevel = "none"
    open: bool = False
    reasons: list[str] = Field(default_factory=list)
    days_until_due: int | None = None
    generated_at: datetime | None = None


class ObligationRiskFactor(BaseModel):
    name: str
    weight: float
    contribution: float
    detail: str


class ObligationRecord(BaseModel):
    id: UUID
    document_id: UUID
    obligation_code: str | None = None
    title: str
    description: str | None = None
    owner_hint: str | None = None
    due_date: date | None = None
    status: ObligationStatus
    priority: ObligationPriority
    review_state: ObligationReviewState
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_annotations: ObligationConfidenceAnnotations | None = None
    escalation: ObligationEscalationSignal | None = None
    citation: ObligationCitation | None = None
    risk_score: int | None = Field(default=None, ge=0, le=100)
    risk_band: Literal["low", "moderate", "high", "critical"] | None = None
    risk_factors: list[ObligationRiskFactor] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ObligationProofSubmission(BaseModel):
    """Evidence submitted alongside a status transition to `completed`.

    The verifier consumes these fields. `proof_text` is required when
    closing the obligation; the rest sharpen the verdict.
    """

    proof_text: str = Field(..., min_length=1, max_length=50_000)
    proof_timestamp: datetime | None = None
    proof_bytes_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    expected_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    proof_pdf_metadata: dict[str, Any] | None = None
    original_pdf_metadata: dict[str, Any] | None = None


class ObligationUpdateRequest(BaseModel):
    review_state: ObligationReviewState | None = None
    owner_hint: str | None = Field(default=None, max_length=200)
    status: ObligationStatus | None = None
    proof: ObligationProofSubmission | None = None

    @model_validator(mode="after")
    def _ensure_at_least_one_change(self):
        if self.review_state is None and self.owner_hint is None and self.status is None:
            raise ValueError("At least one update field must be provided")
        return self


class ObligationsListData(BaseModel):
    document_id: UUID | None = None
    total: int = 0
    items: list[ObligationRecord]


class ObligationsEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: ObligationsListData


class ObligationEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: ObligationRecord


class EscalationSummaryItem(BaseModel):
    obligation_id: UUID
    title: str
    level: EscalationLevel
    days_until_due: int | None = None
    due_date: date | None = None
    review_state: ObligationReviewState
    priority: ObligationPriority
    reasons: list[str] = Field(default_factory=list)
    risk_score: int | None = Field(default=None, ge=0, le=100)
    risk_band: Literal["low", "moderate", "high", "critical"] | None = None
    risk_factors: list[ObligationRiskFactor] = Field(default_factory=list)


class EscalationsSummaryData(BaseModel):
    document_id: UUID
    total: int
    open_total: int
    critical_total: int
    items: list[EscalationSummaryItem]


class EscalationsEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: EscalationsSummaryData


class ObligationAuditEvent(BaseModel):
    id: int
    obligation_id: UUID
    action: str
    actor_type: str
    actor_id: str | None = None
    request_id: str | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime


class ObligationAuditTrailData(BaseModel):
    obligation_id: UUID
    total: int
    items: list[ObligationAuditEvent]


class ObligationAuditTrailEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: ObligationAuditTrailData
