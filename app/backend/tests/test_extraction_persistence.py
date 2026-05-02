from orderflow_api.api.extraction_persistence import (
    _sanitize_database_json,
    _sanitize_database_text,
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
