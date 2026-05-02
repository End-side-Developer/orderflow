"""Tests for the PII redaction service (P1-4)."""

from __future__ import annotations

from orderflow_api.core.redaction_service import redact_text


def test_masks_personal_name_after_honorific() -> None:
    text = "Shri Anil Verma is directed to file a compliance report."
    redacted, stats = redact_text(text)
    assert "Anil Verma" not in redacted
    assert stats.names == 1
    assert "[PERSON-" in redacted


def test_preserves_generic_phrases_after_honorific() -> None:
    text = "The Hon'ble Court directed all parties to comply."
    redacted, stats = redact_text(text)
    assert "Hon'ble Court" in redacted
    assert stats.names == 0


def test_masks_email_and_phone() -> None:
    text = "Contact officer@example.gov.in or call +91 9876543210."
    redacted, stats = redact_text(text)
    assert "officer@example.gov.in" not in redacted
    assert "9876543210" not in redacted
    assert stats.emails == 1
    assert stats.phones >= 1


def test_masks_aadhaar_and_pan() -> None:
    text = "PAN: ABCDE1234F, Aadhaar: 1234 5678 9012."
    redacted, stats = redact_text(text)
    assert "ABCDE1234F" not in redacted
    assert "1234 5678 9012" not in redacted
    assert stats.pan == 1
    assert stats.aadhaar == 1


def test_masks_case_number() -> None:
    text = "Pursuant to W.P. No. 456/2024, the petitioner shall comply."
    redacted, stats = redact_text(text)
    assert "456/2024" not in redacted
    assert stats.case_numbers == 1


def test_year_alone_not_treated_as_phone() -> None:
    text = "The order was issued in 2024 and shall be complied with."
    redacted, stats = redact_text(text)
    assert "2024" in redacted
    assert stats.phones == 0


def test_dates_and_statutes_preserved() -> None:
    text = (
        "Under Section 482 of the CrPC, the petitioner shall file a "
        "compliance report by 30 June 2025."
    )
    redacted, _ = redact_text(text)
    assert "Section 482" in redacted
    assert "30 June 2025" in redacted


def test_empty_input_returns_empty() -> None:
    redacted, stats = redact_text("")
    assert redacted == ""
    assert stats.to_dict()["total"] == 0
