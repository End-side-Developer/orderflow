from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from orderflow_api.api import page_summary_persistence
from orderflow_api.api.page_summary_persistence import (
    MAX_PAGE_SUMMARY_SOURCE_EXCERPT_CHARS,
    create_page_summary,
    update_page_summary_source_metadata,
)


def test_create_page_summary_preserves_null_for_unprocessed_places(
    monkeypatch,
) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    class FakeConnection:
        def execute(self, statement):  # noqa: ANN001, ANN201
            captured.update(statement.compile(dialect=postgresql.dialect()).params)

    class FakeBegin:
        def __enter__(self):  # noqa: ANN201
            return FakeConnection()

        def __exit__(self, *args):  # noqa: ANN002
            return False

    class FakeEngine:
        def begin(self):  # noqa: ANN201
            return FakeBegin()

    monkeypatch.setattr(page_summary_persistence, "get_engine", lambda: FakeEngine())

    record = create_page_summary(
        document_id=uuid4(),
        page_number=1,
        page_text="The matter was heard in Delhi.",
        summary="The page records a hearing in Delhi.",
        key_points=[],
        important_highlights=[],
        context_links=[],
        obligation_ids=[],
        confidence=0.8,
        extraction_mode="deterministic",
        ai_model="clause_fallback",
        ai_provider="clauses",
    )

    assert captured["extracted_places"] is None
    assert record.extracted_places == []


def test_create_page_summary_sanitizes_source_excerpt_and_token_usage(
    monkeypatch,
) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    class FakeConnection:
        def execute(self, statement):  # noqa: ANN001, ANN201
            captured.update(statement.compile(dialect=postgresql.dialect()).params)

    class FakeBegin:
        def __enter__(self):  # noqa: ANN201
            return FakeConnection()

        def __exit__(self, *args):  # noqa: ANN002
            return False

    class FakeEngine:
        def begin(self):  # noqa: ANN201
            return FakeBegin()

    monkeypatch.setattr(page_summary_persistence, "get_engine", lambda: FakeEngine())

    long_excerpt = "\n".join(["  Paragraph with   spacing.  "] * 200)
    token_usage = {
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "raw_prompt": "must not be stored",
        "negative_tokens": -1,
        "cached_tokens": True,
    }

    record = create_page_summary(
        document_id=uuid4(),
        page_number=1,
        page_text="The matter was heard in Delhi.",
        summary="The page records a hearing in Delhi.",
        key_points=[],
        important_highlights=[],
        context_links=[],
        obligation_ids=[],
        confidence=0.8,
        source_excerpt=long_excerpt,
        ai_token_usage=token_usage,
    )

    assert isinstance(captured["source_excerpt"], str)
    assert MAX_PAGE_SUMMARY_SOURCE_EXCERPT_CHARS == 800
    assert len(captured["source_excerpt"]) <= 800
    assert len(captured["source_excerpt"]) <= MAX_PAGE_SUMMARY_SOURCE_EXCERPT_CHARS
    assert captured["source_excerpt"].endswith("[truncated]")
    assert "  " not in captured["source_excerpt"]
    assert captured["source_excerpt"] == record.source_excerpt
    assert captured["ai_token_usage"] == {
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
    }
    assert record.ai_token_usage == captured["ai_token_usage"]


def test_update_page_summary_source_metadata_sanitizes_update_values(
    monkeypatch,
) -> None:  # noqa: ANN001
    captured: dict[str, object] = {}

    class FakeResult:
        rowcount = 1

    class FakeConnection:
        def execute(self, statement):  # noqa: ANN001, ANN201
            captured.update(statement.compile(dialect=postgresql.dialect()).params)
            return FakeResult()

    class FakeBegin:
        def __enter__(self):  # noqa: ANN201
            return FakeConnection()

        def __exit__(self, *args):  # noqa: ANN002
            return False

    class FakeEngine:
        def begin(self):  # noqa: ANN201
            return FakeBegin()

    monkeypatch.setattr(page_summary_persistence, "get_engine", lambda: FakeEngine())

    update_page_summary_source_metadata(
        uuid4(),
        source_excerpt="  Short\n\nsource   excerpt  ",
        ai_token_usage={
            "prompt_tokens": 7,
            "completion_tokens": 3,
            "debug_payload": {"text": "drop"},
            "reasoning_tokens": -4,
        },
    )

    assert captured["source_excerpt"] == "Short source excerpt"
    assert captured["ai_token_usage"] == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
    }
