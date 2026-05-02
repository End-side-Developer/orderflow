"""Schemas for the Proof-Authenticity Verifier."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProofVerifyRequest(BaseModel):
    obligation_text: str = Field(..., min_length=1, max_length=20_000)
    proof_text: str = Field(..., min_length=1, max_length=50_000)
    obligation_due_date: date | None = None
    obligation_issued_date: date | None = None
    proof_timestamp: datetime | None = None
    proof_bytes_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    expected_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    proof_pdf_metadata: dict[str, Any] | None = None
    original_pdf_metadata: dict[str, Any] | None = None


class ProofCheckResult(BaseModel):
    name: Literal["date_validity", "semantic_relevance", "tamper_signal"]
    outcome: Literal["passed", "failed", "skipped"]
    score: float | None = None
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ProofVerifyData(BaseModel):
    passed: bool
    summary: str
    checks: list[ProofCheckResult]


class ProofVerifyEnvelope(BaseModel):
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: ProofVerifyData
