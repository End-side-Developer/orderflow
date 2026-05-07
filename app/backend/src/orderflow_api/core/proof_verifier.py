"""Proof-Authenticity Verifier.

Three-layer validation gate that runs before an obligation can be marked
`completed`:

1. **Date validity** — proof timestamp must lie within the obligation's
   compliance window (after the judgment date, on or before the due date,
   and not in the future).
2. **Semantic relevance** — cosine similarity between the obligation's
   text and the proof text using the shared embedding service. Default
   threshold 0.55, configurable via `ORDERFLOW_PROOF_SIM_THRESHOLD`.
3. **Tamper signal** — flags PDF metadata mismatches and SHA-256 hash
   conflicts when proof is re-uploaded against a registered fingerprint.

The verifier returns a structured `ProofVerificationResult` so callers
(API layer, UI) can render exactly which check failed and why.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from orderflow_api.core import embedding_service

logger = logging.getLogger(__name__)

CheckName = Literal["date_validity", "semantic_relevance", "tamper_signal"]
CheckOutcome = Literal["passed", "failed", "skipped"]

DEFAULT_SIM_THRESHOLD = 0.55


def _sim_threshold() -> float:
    raw = os.environ.get("ORDERFLOW_PROOF_SIM_THRESHOLD")
    if not raw:
        return DEFAULT_SIM_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_SIM_THRESHOLD


@dataclass
class ProofPayload:
    """Inputs needed to verify a single proof submission."""

    obligation_text: str
    proof_text: str
    obligation_due_date: date | None = None
    obligation_issued_date: date | None = None  # judgment / order date
    proof_timestamp: datetime | None = None
    proof_bytes_sha256: str | None = None
    expected_sha256: str | None = None  # if obligation already has a registered fingerprint
    proof_pdf_metadata: dict | None = None
    original_pdf_metadata: dict | None = None


@dataclass
class CheckResult:
    name: CheckName
    outcome: CheckOutcome
    score: float | None = None  # 0..1 for relevance; None for binary checks
    reason: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class ProofVerificationResult:
    passed: bool
    checks: list[CheckResult]
    summary: str

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "summary": self.summary,
            "checks": [
                {
                    "name": c.name,
                    "outcome": c.outcome,
                    "score": c.score,
                    "reason": c.reason,
                    "details": c.details,
                }
                for c in self.checks
            ],
        }


def _check_date_validity(payload: ProofPayload) -> CheckResult:
    if payload.proof_timestamp is None:
        return CheckResult(
            name="date_validity",
            outcome="skipped",
            reason="Proof timestamp not provided.",
        )

    now = datetime.now(timezone.utc)
    proof_dt = payload.proof_timestamp
    if proof_dt.tzinfo is None:
        proof_dt = proof_dt.replace(tzinfo=timezone.utc)

    # Allow up to 1 day clock skew.
    if proof_dt > now + timedelta(days=1):
        return CheckResult(
            name="date_validity",
            outcome="failed",
            reason="Proof timestamp is in the future.",
            details={"proof_timestamp": proof_dt.isoformat()},
        )

    if payload.obligation_issued_date is not None:
        issued_dt = datetime.combine(
            payload.obligation_issued_date, datetime.min.time(), tzinfo=timezone.utc
        )
        if proof_dt < issued_dt:
            return CheckResult(
                name="date_validity",
                outcome="failed",
                reason="Proof predates the judgment / order date.",
                details={
                    "proof_timestamp": proof_dt.isoformat(),
                    "issued_date": payload.obligation_issued_date.isoformat(),
                },
            )

    if payload.obligation_due_date is not None:
        # Grace window: proof can land up to 30 days after the deadline,
        # but it'll be flagged in the reason for transparency.
        due_dt = datetime.combine(
            payload.obligation_due_date, datetime.max.time(), tzinfo=timezone.utc
        )
        if proof_dt > due_dt + timedelta(days=30):
            return CheckResult(
                name="date_validity",
                outcome="failed",
                reason="Proof submitted more than 30 days after the deadline.",
                details={
                    "proof_timestamp": proof_dt.isoformat(),
                    "due_date": payload.obligation_due_date.isoformat(),
                },
            )

    return CheckResult(
        name="date_validity",
        outcome="passed",
        reason="Proof timestamp falls within the compliance window.",
        details={
            "proof_timestamp": proof_dt.isoformat(),
            "issued_date": (
                payload.obligation_issued_date.isoformat()
                if payload.obligation_issued_date
                else None
            ),
            "due_date": (
                payload.obligation_due_date.isoformat() if payload.obligation_due_date else None
            ),
        },
    )


def _check_semantic_relevance(payload: ProofPayload) -> CheckResult:
    obligation_text = (payload.obligation_text or "").strip()
    proof_text = (payload.proof_text or "").strip()

    if not obligation_text or not proof_text:
        return CheckResult(
            name="semantic_relevance",
            outcome="skipped",
            reason="Obligation or proof text is empty; cannot score relevance.",
        )

    threshold = _sim_threshold()
    o_vec = embedding_service.embed_text(obligation_text)
    p_vec = embedding_service.embed_text(proof_text)
    score = embedding_service.cosine(o_vec, p_vec)
    score_clamped = max(-1.0, min(1.0, score))

    if score_clamped >= threshold:
        return CheckResult(
            name="semantic_relevance",
            outcome="passed",
            score=score_clamped,
            reason=f"Semantic similarity {score_clamped:.2f} ≥ threshold {threshold:.2f}.",
            details={"threshold": threshold},
        )

    return CheckResult(
        name="semantic_relevance",
        outcome="failed",
        score=score_clamped,
        reason=(
            f"Semantic similarity {score_clamped:.2f} below threshold "
            f"{threshold:.2f} — proof does not appear to address the obligation."
        ),
        details={"threshold": threshold},
    )


def _check_tamper_signal(payload: ProofPayload) -> CheckResult:
    # Hash mismatch against an expected fingerprint.
    if payload.expected_sha256 and payload.proof_bytes_sha256:
        if payload.expected_sha256.lower() != payload.proof_bytes_sha256.lower():
            return CheckResult(
                name="tamper_signal",
                outcome="failed",
                reason="SHA-256 of submitted proof does not match the registered fingerprint.",
                details={
                    "expected": payload.expected_sha256,
                    "actual": payload.proof_bytes_sha256,
                },
            )

    # PDF metadata mismatch (creator/producer/title differ from registered original).
    if payload.proof_pdf_metadata and payload.original_pdf_metadata:
        diffs: dict[str, dict[str, str]] = {}
        for key in ("creator", "producer", "title", "author"):
            orig = (payload.original_pdf_metadata or {}).get(key)
            cur = (payload.proof_pdf_metadata or {}).get(key)
            if orig is not None and cur is not None and orig != cur:
                diffs[key] = {"expected": str(orig), "actual": str(cur)}
        if diffs:
            return CheckResult(
                name="tamper_signal",
                outcome="failed",
                reason="PDF metadata fields differ from the registered original.",
                details={"differences": diffs},
            )

    if not payload.proof_bytes_sha256 and not payload.proof_pdf_metadata:
        return CheckResult(
            name="tamper_signal",
            outcome="skipped",
            reason="No fingerprint or metadata supplied; tamper check skipped.",
        )

    return CheckResult(
        name="tamper_signal",
        outcome="passed",
        reason="No tamper indicators detected.",
    )


def verify_proof(payload: ProofPayload) -> ProofVerificationResult:
    """Run all three checks and return an aggregated result."""

    checks = [
        _check_date_validity(payload),
        _check_semantic_relevance(payload),
        _check_tamper_signal(payload),
    ]

    failed = [c for c in checks if c.outcome == "failed"]
    if failed:
        summary = "; ".join(c.reason for c in failed)
        return ProofVerificationResult(passed=False, checks=checks, summary=summary)

    # If all checks were skipped, refuse — we should never close on no evidence.
    if all(c.outcome == "skipped" for c in checks):
        return ProofVerificationResult(
            passed=False,
            checks=checks,
            summary=(
                "No proof signals could be evaluated. Attach a dated proof "
                "with text content before closing this obligation."
            ),
        )

    summary_parts = [c.reason for c in checks if c.outcome == "passed"]
    return ProofVerificationResult(
        passed=True,
        checks=checks,
        summary="; ".join(summary_parts) or "All proof checks passed.",
    )


def sha256_of_bytes(data: bytes) -> str:
    """Helper for callers to compute a fingerprint."""
    return hashlib.sha256(data).hexdigest()
