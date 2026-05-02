"""Schemas for the Department Health Scoring dashboard (P1-2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DepartmentHealthItem(BaseModel):
    code: str
    name: str
    total_obligations: int = 0
    completed: int = 0
    overdue: int = 0
    pending_review: int = 0
    open_escalations: int = 0
    critical_escalations: int = 0
    avg_risk_score: float = 0.0
    compliance_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    breach_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    health_score: int = Field(default=0, ge=0, le=100)
    band: Literal["excellent", "healthy", "watch", "at_risk"]
    rationale: list[str] = Field(default_factory=list)


class DepartmentHealthData(BaseModel):
    total_departments: int = 0
    avg_health_score: float = 0.0
    items: list[DepartmentHealthItem] = Field(default_factory=list)


class DepartmentHealthEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: DepartmentHealthData
