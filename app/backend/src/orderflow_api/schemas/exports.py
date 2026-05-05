from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from orderflow_api.schemas.obligations import (
    ObligationPriority,
    ObligationReviewState,
    ObligationStatus,
)

ExportLanguage = Literal["en", "hi", "ta", "te", "kn", "ml", "mr"]


class ActionPlanExportItem(BaseModel):
    obligation_id: UUID
    title: str
    description: str | None = None
    owner_hint: str | None = None
    due_date: date | None = None
    status: ObligationStatus
    priority: ObligationPriority
    review_state: ObligationReviewState
    citation_span: str | None = None


class ActionPlanExportData(BaseModel):
    document_id: UUID
    language: ExportLanguage = "en"
    generated_at: datetime
    total: int = Field(ge=0)
    items: list[ActionPlanExportItem]


class ActionPlanExportEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: ActionPlanExportData


class CaseBundlePdfRequest(BaseModel):
    document_id: UUID
    include_per_page_maps: bool = True
    include_summary_map: bool = True
