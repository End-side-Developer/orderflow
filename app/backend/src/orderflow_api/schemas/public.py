"""Schemas for the Public-Trust Mode endpoints (P1-4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PublicObligationItem(BaseModel):
    id: str
    document_id: str
    title: str
    description: str
    owner_role: str | None = None
    due_date: str | None = None
    status: str | None = None
    priority: str | None = None
    review_state: str | None = None
    risk_score: int | None = Field(default=None, ge=0, le=100)
    risk_band: Literal["low", "moderate", "high", "critical"] | None = None
    redaction: dict[str, int] = Field(default_factory=dict)


class PublicObligationsData(BaseModel):
    total: int = 0
    redacted_count_summary: dict[str, int] = Field(default_factory=dict)
    items: list[PublicObligationItem] = Field(default_factory=list)


class PublicObligationsEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: PublicObligationsData
