from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from orderflow_api.schemas.advocates import AdvocateCaseLinkRecord, AdvocateDirectoryItem

DocumentStatus = Literal["uploaded", "processing", "ready", "failed"]
SupportedLanguage = Literal["en", "hi", "ta", "te", "kn", "ml", "mr"]


class DocumentCreateRequest(BaseModel):
    source_file_name: str = Field(min_length=1, max_length=255)
    source_file_type: str | None = Field(default=None, max_length=100)
    source_file_size: int | None = Field(default=None, ge=0)
    object_key: str | None = Field(default=None, max_length=512)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    source_language: SupportedLanguage = "en"
    auto_detected_language: SupportedLanguage | None = None
    language_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    translated_text_stored: bool = False
    metadata: dict[str, Any] | None = None


class DocumentRecord(BaseModel):
    id: UUID
    source_file_name: str
    source_file_type: str | None = None
    source_file_size: int | None = None
    object_key: str | None = None
    checksum_sha256: str | None = None
    workflow_run_id: str | None = None
    status: DocumentStatus
    metadata: dict[str, Any] | None = None
    case_flow_graph: dict[str, Any] | None = None
    source_language: SupportedLanguage = "en"
    auto_detected_language: SupportedLanguage | None = None
    language_confidence: float = 1.0
    translated_text_stored: bool = False
    created_at: datetime
    updated_at: datetime


class DocumentEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: DocumentRecord


class DocumentsListData(BaseModel):
    total: int
    items: list[DocumentRecord]


class DocumentsListEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: DocumentsListData


class AdvocateRecommendationFilters(BaseModel):
    specialization: str | None = None
    jurisdiction_state: str | None = None
    jurisdiction_level: str | None = None
    language: str | None = None


class AdvocateRecommendationsData(BaseModel):
    document_id: UUID
    total: int
    filters: AdvocateRecommendationFilters
    items: list[AdvocateDirectoryItem]


class AdvocateRecommendationsEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: AdvocateRecommendationsData


class DocumentAdvocatesData(BaseModel):
    document_id: UUID
    total: int
    items: list[AdvocateCaseLinkRecord]


class DocumentAdvocatesEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: DocumentAdvocatesData


class CaseFlowNode(BaseModel):
    id: str
    node_type: Literal["party", "event", "order", "obligation"]
    label: str
    detail: str | None = None
    page_ref: int | None = None


class CaseFlowEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str


class CaseFlowData(BaseModel):
    document_id: UUID
    nodes: list[CaseFlowNode]
    edges: list[CaseFlowEdge]


class CaseFlowEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: CaseFlowData


class IndianECourtsCCMSEnvelope(BaseModel):
    reference_id: str | None = Field(default=None, max_length=128)
    delivery_timestamp: datetime | None = None
    document_type: str | None = Field(default=None, max_length=100)
    source_url: str | None = Field(default=None, max_length=1024)
    source_gateway: str | None = Field(default=None, max_length=255)
    receipt_id: str | None = Field(default=None, max_length=128)


class IndianECourtsCISEnvelope(BaseModel):
    case_id: str | None = Field(default=None, max_length=128)
    court_name: str | None = Field(default=None, max_length=255)
    court_code: str | None = Field(default=None, max_length=64)
    order_date: date | None = None
    bench: str | None = Field(default=None, max_length=255)
    parties: list[str] | None = None
    petitioners: list[str] | None = None
    respondents: list[str] | None = None
    case_type: str | None = Field(default=None, max_length=100)
    filing_number: str | None = Field(default=None, max_length=128)
    diary_number: str | None = Field(default=None, max_length=128)
    judge_names: list[str] | None = None
    hearing_stage: str | None = Field(default=None, max_length=255)
    state: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    department_tags: list[str] | None = None


class IndianECourtsIntakeRequest(BaseModel):
    ccms: IndianECourtsCCMSEnvelope
    cis: IndianECourtsCISEnvelope | None = None
    source_file_name: str | None = Field(default=None, max_length=255)
    source_file_type: str | None = Field(default="application/pdf", max_length=100)
    additional_metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def ensure_identifier_present(self) -> "IndianECourtsIntakeRequest":
        ccms_reference = self.ccms.reference_id if self.ccms is not None else None
        cis_case_id = self.cis.case_id if self.cis is not None else None
        if ccms_reference or cis_case_id:
            return self
        raise ValueError("Provide ccms.reference_id or cis.case_id for traceable intake")


class IndianECourtsLookupRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=1024)


class IndianECourtsLookupRecord(BaseModel):
    identifier: str
    resolved_source_url: str
    source_file_name: str
    source_file_type: str
    file_content_base64: str
    envelope: IndianECourtsIntakeRequest
    note: str | None = None


class IndianECourtsLookupEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: IndianECourtsLookupRecord
