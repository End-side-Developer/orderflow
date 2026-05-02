from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from orderflow_api.schemas.obligations import ObligationRecord


class ClauseRecord(BaseModel):
    id: UUID
    document_id: UUID
    clause_index: int = Field(ge=1)
    page_number: int | None = Field(default=None, ge=1)
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=0)
    text: str
    normalized_text: str | None = None
    citation_span: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime


class IntakeAiOptions(BaseModel):
    enabled: bool | None = None
    provider: Literal["openai", "anthropic", "gemini", "groq"] | None = None
    model: str | None = Field(default=None, min_length=1, max_length=120)
    api_key: str | None = Field(default=None, min_length=8, max_length=512)
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    max_obligations: int | None = Field(default=None, ge=1, le=300)


class IntakeExtractionRequest(BaseModel):
    document_id: UUID
    ai: IntakeAiOptions | None = None


class IntakeExtractionResult(BaseModel):
    document_id: UUID
    clause_count: int
    obligation_count: int
    extraction_mode: Literal["deterministic", "ai", "ai_fallback"] = "deterministic"
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_reason: str | None = None
    clauses: list[ClauseRecord]
    obligations: list[ObligationRecord]


class IntakeExtractionEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: IntakeExtractionResult


class ClausesListData(BaseModel):
    document_id: UUID | None = None
    page_number: int | None = Field(default=None, ge=1)
    clause_span: str | None = None
    total: int = 0
    items: list[ClauseRecord]


class ClausesEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: ClausesListData
