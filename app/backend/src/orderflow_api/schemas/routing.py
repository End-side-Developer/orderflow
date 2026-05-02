"""Schemas for the Department-Aware Routing service (P1-1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DepartmentMatchSchema(BaseModel):
    code: str
    name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_aliases: list[str] = Field(default_factory=list)


class OfficerSuggestionSchema(BaseModel):
    id: str
    name: str
    designation: str
    department_code: str
    jurisdiction: str
    contact: str


class RouteDirectiveRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)
    top_n_candidates: int = Field(default=3, ge=1, le=10)
    top_officers_per_department: int = Field(default=2, ge=1, le=10)
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class RouteDirectiveData(BaseModel):
    primary: DepartmentMatchSchema | None = None
    candidates: list[DepartmentMatchSchema] = Field(default_factory=list)
    suggested_officers: list[OfficerSuggestionSchema] = Field(default_factory=list)
    multi_department: bool = False
    rationale: str = ""


class RouteDirectiveEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: RouteDirectiveData


class DepartmentDirectoryItem(BaseModel):
    code: str
    name: str
    aliases: list[str] = Field(default_factory=list)


class DepartmentDirectoryData(BaseModel):
    total: int = 0
    items: list[DepartmentDirectoryItem]


class DepartmentDirectoryEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: DepartmentDirectoryData
