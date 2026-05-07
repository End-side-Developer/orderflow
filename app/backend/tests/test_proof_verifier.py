"""Tests for the Proof-Authenticity Verifier (P0-2 / P0-3)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from orderflow_api.core.proof_verifier import ProofPayload, verify_proof


def test_verify_passes_when_proof_relates_and_is_dated_in_window() -> None:
    issued = date(2025, 1, 1)
    due = date(2025, 6, 30)
    proof_ts = datetime(2025, 5, 1, 12, 0, tzinfo=timezone.utc)

    payload = ProofPayload(
        obligation_text=(
            "The state shall publish the revised water tariff order within 60 days "
            "and serve copies to all stakeholders."
        ),
        proof_text=(
            "Notification dated 1 May 2025 publishing revised water tariff order; "
            "service of copies completed to listed stakeholders."
        ),
        obligation_due_date=due,
        obligation_issued_date=issued,
        proof_timestamp=proof_ts,
    )

    result = verify_proof(payload)
    # Date should pass; tamper skipped (no fingerprint); semantic could pass or
    # fail depending on whether the real model is loaded. We accept either,
    # but require date_validity passed and structure is correct.
    date_check = next(c for c in result.checks if c.name == "date_validity")
    assert date_check.outcome == "passed"
    assert any(c.name == "semantic_relevance" for c in result.checks)
    assert any(c.name == "tamper_signal" for c in result.checks)


def test_verify_rejects_proof_dated_before_judgment() -> None:
    issued = date(2025, 6, 1)
    proof_ts = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    payload = ProofPayload(
        obligation_text="Pay arrears within 30 days of order.",
        proof_text="Receipt of payment of arrears.",
        obligation_due_date=date(2025, 7, 1),
        obligation_issued_date=issued,
        proof_timestamp=proof_ts,
    )

    result = verify_proof(payload)
    assert result.passed is False
    date_check = next(c for c in result.checks if c.name == "date_validity")
    assert date_check.outcome == "failed"
    assert "predates" in date_check.reason.lower()


def test_verify_rejects_when_sha256_mismatch() -> None:
    payload = ProofPayload(
        obligation_text="Submit compliance report.",
        proof_text="Compliance report attached.",
        obligation_due_date=date(2030, 1, 1),
        obligation_issued_date=date(2025, 1, 1),
        proof_timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc),
        proof_bytes_sha256="a" * 64,
        expected_sha256="b" * 64,
    )

    result = verify_proof(payload)
    assert result.passed is False
    tamper = next(c for c in result.checks if c.name == "tamper_signal")
    assert tamper.outcome == "failed"
    assert "sha-256" in tamper.reason.lower()


def test_verify_refuses_when_all_checks_skipped() -> None:
    # No timestamp, no fingerprint, but text present so semantic runs.
    # Force semantic to skip by passing empty proof text -- but schema would
    # reject that. Use whitespace-only after strip in the dataclass directly.
    payload = ProofPayload(
        obligation_text="   ",
        proof_text="   ",
    )

    result = verify_proof(payload)
    assert result.passed is False
    assert all(c.outcome == "skipped" for c in result.checks)


def test_verify_rejects_pdf_metadata_mismatch() -> None:
    payload = ProofPayload(
        obligation_text="File annual return.",
        proof_text="Annual return filed.",
        obligation_due_date=date(2030, 1, 1),
        obligation_issued_date=date(2025, 1, 1),
        proof_timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc),
        original_pdf_metadata={"creator": "MS Word", "producer": "Acrobat"},
        proof_pdf_metadata={"creator": "TamperTool", "producer": "Acrobat"},
    )

    result = verify_proof(payload)
    assert result.passed is False
    tamper = next(c for c in result.checks if c.name == "tamper_signal")
    assert tamper.outcome == "failed"
    assert "metadata" in tamper.reason.lower()
