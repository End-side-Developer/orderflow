from uuid import uuid4

import orderflow_api.api.ai_extraction as ai_extraction
from orderflow_api.api.extraction_engine import ParsedClause
from orderflow_api.schemas.extractions import IntakeAiOptions


def _set_ai_settings(monkeypatch, **overrides) -> None:  # noqa: ANN001
    baseline = {
        "orderflow_ai_enabled_default": False,
        "orderflow_ai_allow_user_override": True,
        "orderflow_ai_default_provider": "gemini",
        "orderflow_ai_default_model": "gemini-2.0-flash",
        "orderflow_ai_openai_api_key": None,
        "orderflow_ai_anthropic_api_key": None,
        "orderflow_ai_gemini_api_key": None,
        "orderflow_ai_timeout_seconds": 45,
        "orderflow_ai_gemini_rate_limit_enabled": True,
        "orderflow_ai_gemini_requests_per_minute": 15,
        "orderflow_ai_gemini_tokens_per_minute": 1_000_000,
        "orderflow_ai_gemini_requests_per_day": 1_500,
        "orderflow_ai_gemini_tokens_per_day": 1_000_000,
        "orderflow_ai_gemini_max_wait_seconds": 90,
        "orderflow_ai_gemini_chars_per_token": 4,
        "orderflow_ai_gemini_max_output_tokens": 2048,
        "orderflow_ai_gemini_max_clauses": 24,
        "orderflow_ai_gemini_max_chars_per_clause": 600,
        "orderflow_ai_gemini_judgment_prompt_chars": 9000,
        "orderflow_ai_gemini_page_insight_prompt_chars": 4000,
        "orderflow_ai_max_clauses": 120,
    }
    baseline.update(overrides)

    for key, value in baseline.items():
        monkeypatch.setattr(ai_extraction.settings, key, value)


def _make_clause(*, clause_index: int, text: str) -> ParsedClause:
    document_id = uuid4()
    return ParsedClause(
        id=uuid4(),
        document_id=document_id,
        clause_index=clause_index,
        page_number=1,
        span_start=10 * clause_index,
        span_end=(10 * clause_index) + len(text),
        text=text,
        normalized_text=text,
        confidence=0.84,
    )


def test_maybe_extract_obligations_with_ai_returns_disabled_reason(monkeypatch) -> None:
    _set_ai_settings(monkeypatch, orderflow_ai_enabled_default=False)
    document_id = uuid4()
    clauses = [_make_clause(clause_index=1, text="District administration shall file report.")]

    result = ai_extraction.maybe_extract_obligations_with_ai(
        clauses=clauses,
        document_id=document_id,
        ai_options=None,
    )

    assert result.attempted is False
    assert result.used_ai is False
    assert result.reason == "AI extraction is disabled."
    assert result.obligations == []


def test_gemini_provider_honors_user_overrides(monkeypatch) -> None:
    _set_ai_settings(
        monkeypatch,
        orderflow_ai_enabled_default=True,
        orderflow_ai_gemini_api_key="gm-default-key",
    )
    document_id = uuid4()
    clauses = [
        _make_clause(clause_index=1, text="District administration shall file report."),
        _make_clause(clause_index=2, text="Counsel office shall submit affidavit."),
    ]

    def fake_call_gemini_json(**kwargs):
        assert kwargs["api_key"] == "gm-user-key"
        assert kwargs["model"] == "gemini-2.5-pro"
        assert kwargs["request_label"] == "obligation extraction"
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"obligations":[{"clause_index":1,"title":"File report",'
                                    '"description":"District administration shall file report.",'
                                    '"owner_hint":"District administration","due_date":null,'
                                    '"priority":"high","confidence":0.92}]}'
                                )
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_extraction, "call_gemini_json", fake_call_gemini_json)

    result = ai_extraction.maybe_extract_obligations_with_ai(
        clauses=clauses,
        document_id=document_id,
        ai_options=IntakeAiOptions(
            enabled=True,
            provider="gemini",
            model="gemini-2.5-pro",
            api_key="gm-user-key",
            temperature=0.3,
            max_obligations=1,
        ),
    )

    assert result.attempted is True
    assert result.used_ai is True
    assert result.provider == "gemini"
    assert result.model == "gemini-2.5-pro"
    assert len(result.obligations) == 1
    assert result.obligations[0].metadata["source"] == "ai-extractor-v1"
    assert result.obligations[0].metadata["ai_provider"] == "gemini"
    assert result.obligations[0].metadata["ai_model"] == "gemini-2.5-pro"
    assert result.obligations[0].metadata["ai_temperature"] == 0.3


def test_openai_selection_requires_api_key(monkeypatch) -> None:
    _set_ai_settings(
        monkeypatch,
        orderflow_ai_enabled_default=True,
        orderflow_ai_allow_user_override=False,
        orderflow_ai_default_provider="openai",
        orderflow_ai_openai_api_key=None,
    )
    document_id = uuid4()
    clauses = [_make_clause(clause_index=1, text="District administration shall file report.")]

    result = ai_extraction.maybe_extract_obligations_with_ai(
        clauses=clauses,
        document_id=document_id,
        ai_options=None,
    )

    assert result.attempted is False
    assert result.used_ai is False
    assert result.provider == "openai"
    assert "Missing API key" in (result.reason or "")


def test_openai_returns_no_actionable_obligations(monkeypatch) -> None:
    _set_ai_settings(
        monkeypatch,
        orderflow_ai_enabled_default=True,
        orderflow_ai_default_provider="openai",
        orderflow_ai_openai_api_key="sk-test-key",
    )
    document_id = uuid4()
    clauses = [_make_clause(clause_index=1, text="District administration shall file report.")]

    def fake_post_json(*, url: str, headers: dict[str, str], payload: dict[str, object]):
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"obligations": []}',
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_extraction, "_post_json", fake_post_json)

    result = ai_extraction.maybe_extract_obligations_with_ai(
        clauses=clauses,
        document_id=document_id,
        ai_options=IntakeAiOptions(enabled=True),
    )

    assert result.attempted is True
    assert result.used_ai is False
    assert result.provider == "openai"
    assert "AI returned no actionable obligations (openai)." in (result.reason or "")
    assert result.obligations == []


def test_openai_materializes_ai_obligation(monkeypatch) -> None:
    _set_ai_settings(
        monkeypatch,
        orderflow_ai_enabled_default=True,
        orderflow_ai_default_provider="openai",
        orderflow_ai_default_model="gpt-4.1-mini",
        orderflow_ai_openai_api_key="sk-test-key",
    )
    document_id = uuid4()
    clauses = [
        _make_clause(
            clause_index=7,
            text="District administration shall submit compliance affidavit in 7 days.",
        )
    ]

    def fake_post_json(*, url: str, headers: dict[str, str], payload: dict[str, object]):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"obligations":[{"clause_index":7,"title":"Submit affidavit",'
                            '"description":"Submit compliance affidavit",'
                            '"owner_hint":"District administration",'
                            '"due_date":"2026-05-01","priority":"high","confidence":0.91}]}'
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr(ai_extraction, "_post_json", fake_post_json)

    result = ai_extraction.maybe_extract_obligations_with_ai(
        clauses=clauses,
        document_id=document_id,
        ai_options=IntakeAiOptions(enabled=True),
    )

    assert result.attempted is True
    assert result.used_ai is True
    assert result.provider == "openai"
    assert len(result.obligations) == 1
    assert result.obligations[0].obligation_code == "OBL-AI-001"
    assert result.obligations[0].title == "Submit affidavit"
    assert result.obligations[0].metadata["ai_provider"] == "openai"
    source = result.obligations[0].metadata["source_evidence"]
    assert source["clause_index"] == 7
    assert source["page_number"] == 1
    assert "affidavit" in (source["excerpt"] or "")


def test_action_plan_prompt_includes_source_evidence_schema() -> None:
    prompt = ai_extraction._build_prompt(
        [{"clause_index": 1, "page_number": 1, "text": "Sample clause"}],
        3,
    )

    assert '"source_evidence"' in prompt
    assert '"clause_span"' in prompt
    assert '"excerpt"' in prompt
    assert "never present final legal advice" in prompt
    assert "authorized legal counsel" in prompt


def test_gemini_selection_requires_api_key(monkeypatch) -> None:
    _set_ai_settings(
        monkeypatch,
        orderflow_ai_enabled_default=True,
        orderflow_ai_allow_user_override=False,
        orderflow_ai_default_provider="gemini",
        orderflow_ai_gemini_api_key=None,
    )
    document_id = uuid4()
    clauses = [_make_clause(clause_index=1, text="District administration shall file report.")]

    result = ai_extraction.maybe_extract_obligations_with_ai(
        clauses=clauses,
        document_id=document_id,
        ai_options=None,
    )

    assert result.attempted is False
    assert result.used_ai is False
    assert result.provider == "gemini"
    assert "Missing API key" in (result.reason or "")


def test_gemini_selection_applies_quota_friendly_prompt_budget(monkeypatch) -> None:
    _set_ai_settings(
        monkeypatch,
        orderflow_ai_enabled_default=True,
        orderflow_ai_gemini_api_key="gm-test-key",
        orderflow_ai_max_clauses=120,
        orderflow_ai_gemini_max_clauses=24,
        orderflow_ai_gemini_max_chars_per_clause=600,
    )

    selection = ai_extraction._resolve_ai_selection(
        IntakeAiOptions(enabled=True, provider="gemini")
    )

    assert selection.enabled is True
    assert selection.provider == "gemini"
    assert selection.max_clauses == 24
    assert selection.max_clause_chars == 600


def test_falls_back_to_gemini_when_openai_fails(monkeypatch) -> None:
    monkeypatch.setattr(ai_extraction, "_REMOTE_FALLBACK_ORDER", ("gemini",))
    _set_ai_settings(
        monkeypatch,
        orderflow_ai_enabled_default=True,
        orderflow_ai_default_provider="openai",
        orderflow_ai_default_model="gpt-4.1-mini",
        orderflow_ai_openai_api_key="sk-test-key",
        orderflow_ai_gemini_api_key="gm-test-key",
    )
    document_id = uuid4()
    clauses = [
        _make_clause(
            clause_index=7,
            text="District administration shall submit compliance affidavit in 7 days.",
        )
    ]

    def fake_post_json(*, url: str, headers: dict[str, str], payload: dict[str, object]):
        if "openai.com" in url:
            raise ValueError("OpenAI temporary outage")

        raise ValueError("Unexpected provider URL")

    monkeypatch.setattr(ai_extraction, "_post_json", fake_post_json)
    monkeypatch.setattr(
        ai_extraction,
        "call_gemini_json",
        lambda **kwargs: {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"obligations":[{"clause_index":7,"title":"Submit affidavit",'
                                    '"description":"Submit compliance affidavit",'
                                    '"owner_hint":"District administration",'
                                    '"due_date":"2026-05-01","priority":"high","confidence":0.91}]}'
                                )
                            }
                        ]
                    }
                }
            ]
        },
    )

    result = ai_extraction.maybe_extract_obligations_with_ai(
        clauses=clauses,
        document_id=document_id,
        ai_options=IntakeAiOptions(enabled=True, provider="openai"),
    )

    assert result.attempted is True
    assert result.used_ai is True
    assert result.provider == "gemini"
    assert "Primary provider 'openai' failed" in (result.reason or "")
    assert len(result.obligations) == 1
    assert result.obligations[0].metadata["ai_provider"] == "gemini"
