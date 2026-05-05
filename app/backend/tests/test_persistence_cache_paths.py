from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from orderflow_api.api import document_summary_persistence, page_summary_persistence
from orderflow_api.schemas.extractions import IntakeAiOptions


def test_page_summary_cache_lookup_uses_full_metadata_key(monkeypatch) -> None:  # noqa: ANN001
    captured_statements: list[dict[str, object]] = []
    document_id = uuid4()
    now = datetime.now(UTC)

    row = {
        "id": uuid4(),
        "document_id": document_id,
        "page_number": 2,
        "page_text": "page text",
        "summary": "cached summary",
        "key_points": [],
        "important_highlights": [],
        "context_links": [],
        "obligation_ids": [],
        "extracted_places": [],
        "confidence": 0.9,
        "extraction_mode": "ai",
        "ai_model": "gpt-4",
        "ai_provider": "openai",
        "content_hash": "hashxyz123",
        "prompt_version": "v2.1",
        "source_excerpt": "excerpt",
        "ai_token_usage": {"input_tokens": 10},
        "generated_at": now,
        "created_at": now,
        "updated_at": now,
    }

    monkeypatch.setattr(
        page_summary_persistence,
        "get_engine",
        lambda: _FakeReadEngine(captured_statements, row),
    )

    record = page_summary_persistence.get_cached_page_summary(
        document_id=document_id,
        page_number=2,
        content_hash="hashxyz123",
        prompt_version="v2.1",
        ai_model="gpt-4",
        ai_provider="openai",
    )

    assert record is not None
    assert record.summary == "cached summary"
    params = captured_statements[0]["params"]
    assert _param_value(params, document_id)
    assert _param_value(params, 2)
    assert _param_value(params, "hashxyz123")
    assert _param_value(params, "v2.1")
    assert _param_value(params, "gpt-4")
    assert _param_value(params, "openai")


def test_page_summary_cache_miss_returns_none(monkeypatch) -> None:  # noqa: ANN001
    captured_statements: list[dict[str, object]] = []
    monkeypatch.setattr(
        page_summary_persistence,
        "get_engine",
        lambda: _FakeReadEngine(captured_statements, None),
    )

    record = page_summary_persistence.get_cached_page_summary(
        document_id=uuid4(),
        page_number=2,
        content_hash="changed-hash",
        prompt_version="changed-version",
        ai_model="gpt-4",
        ai_provider="openai",
    )

    assert record is None
    params = captured_statements[0]["params"]
    assert _param_value(params, "changed-hash")
    assert _param_value(params, "changed-version")


def test_document_summary_cache_lookup_uses_prompt_and_provider_metadata(
    monkeypatch,
) -> None:  # noqa: ANN001
    captured_statements: list[dict[str, object]] = []
    document_id = uuid4()
    now = datetime.now(UTC)
    row = {
        "id": uuid4(),
        "document_id": document_id,
        "case_basics": {},
        "overview": "cached overview",
        "entities": [],
        "petitioner": {},
        "respondent": {},
        "departments": [],
        "key_directives": [],
        "important_dates": [],
        "responsible_departments": [],
        "flow_graph": None,
        "map_data": None,
        "confidence": 0.8,
        "prompt_version": "doc-v1",
        "ai_model": "claude",
        "ai_provider": "anthropic",
        "generated_at": now,
        "created_at": now,
        "updated_at": now,
    }

    monkeypatch.setattr(
        document_summary_persistence,
        "get_engine",
        lambda: _FakeReadEngine(captured_statements, row),
    )

    record = document_summary_persistence.get_document_summary(
        document_id=document_id,
        prompt_version="doc-v1",
        ai_model="claude",
        ai_provider="anthropic",
    )

    assert record is not None
    assert record.overview == "cached overview"
    params = captured_statements[0]["params"]
    assert _param_value(params, document_id)
    assert _param_value(params, "doc-v1")
    assert _param_value(params, "claude")
    assert _param_value(params, "anthropic")


def test_intake_ai_options_excludes_api_key_from_serialized_metadata() -> None:
    payload = IntakeAiOptions(
        enabled=True,
        provider="gemini",
        model="gemini-test",
        api_key="super-secret-key",
    )

    serialized = payload.model_dump()

    assert "api_key" not in serialized
    assert serialized["provider"] == "gemini"


class _FakeReadEngine:
    def __init__(
        self,
        captured_statements: list[dict[str, object]],
        row: dict[str, object] | None,
    ) -> None:
        self._captured_statements = captured_statements
        self._row = row

    def connect(self):  # noqa: ANN201
        return _FakeConnect(self._captured_statements, self._row)


class _FakeConnect:
    def __init__(
        self,
        captured_statements: list[dict[str, object]],
        row: dict[str, object] | None,
    ) -> None:
        self._captured_statements = captured_statements
        self._row = row

    def __enter__(self):  # noqa: ANN201
        return _FakeConnection(self._captured_statements, self._row)

    def __exit__(self, *args):  # noqa: ANN002
        return False


class _FakeConnection:
    def __init__(
        self,
        captured_statements: list[dict[str, object]],
        row: dict[str, object] | None,
    ) -> None:
        self._captured_statements = captured_statements
        self._row = row

    def execute(self, statement):  # noqa: ANN001, ANN201
        compiled = statement.compile(dialect=postgresql.dialect())
        self._captured_statements.append({"sql": str(compiled), "params": compiled.params})
        return _FakeResult(self._row)


class _FakeResult:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    def mappings(self):  # noqa: ANN201
        return self

    def first(self):  # noqa: ANN201
        return self._row


def _param_value(params: object, expected_value: object) -> bool:
    if not isinstance(params, dict):
        return False
    return any(value == expected_value for value in params.values())
