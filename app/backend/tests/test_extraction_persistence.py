from datetime import UTC, datetime
from uuid import uuid4

from orderflow_api.api.extraction_persistence import (
    _sanitize_database_json,
    _sanitize_database_text,
    _to_obligation_record,
)


def test_sanitize_database_text_strips_nul_and_control_bytes() -> None:
    value = "A\x00B\x01C\nD\tE\rF"

    assert _sanitize_database_text(value) == "ABC\nD\tE\rF"


def test_sanitize_database_text_returns_none_when_empty_after_cleaning() -> None:
    value = "\x00\x01\x02"

    assert _sanitize_database_text(value) is None


def test_sanitize_database_json_recursively_cleans_strings() -> None:
    payload = {
        "title": "Tit\x00le",
        "items": ["A\x00", {"nested": "\x00"}],
        5: "Val\x00ue",
        "count": 3,
    }

    sanitized = _sanitize_database_json(payload)

    assert sanitized == {
        "title": "Title",
        "items": ["A", {"nested": ""}],
        "5": "Value",
        "count": 3,
    }


def test_to_obligation_record_defaults_nullable_lifecycle_fields() -> None:
    now = datetime.now(UTC)
    document_id = uuid4()

    record = _to_obligation_record(
        {
            "id": uuid4(),
            "document_id": document_id,
            "obligation_code": "OBL-001",
            "title": "Submit compliance report",
            "description": "Submit the compliance report within 30 days.",
            "owner_hint": "Education Department",
            "nature_of_action": None,
            "due_date": None,
            "status": "draft",
            "priority": "medium",
            "review_state": "pending_review",
            "action_plan_stage": None,
            "confidence": None,
            "regen_count": None,
            "regen_history": None,
            "metadata": {},
            "clause_index": None,
            "page_number": None,
            "span_start": None,
            "span_end": None,
            "created_at": now,
            "updated_at": now,
        }
    )

    assert record.document_id == document_id
    assert record.action_plan_stage == "extracted"
    assert record.regen_count == 0
    assert record.regen_history == []
