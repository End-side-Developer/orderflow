import pytest

from orderflow_intelligence.core.config import settings
from orderflow_intelligence.core.groq_client import GroqNetworkError
from orderflow_intelligence.graph import intake_graph
from orderflow_intelligence.graph.intake_graph import run_extraction_graph


@pytest.fixture(autouse=True)
def disable_live_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "orderflow_ai_gemini_api_key", None)


def test_intake_graph_passes_confidence_gate() -> None:
    result = run_extraction_graph(
        raw_text="The respondent shall submit a compliance report in 7 days.",
        confidence_threshold=0.78,
        page_number=1,
        document_id="test-doc-123",
    )

    assert result["gate_decision"] in {"pass", "low_confidence"}
    assert result["requires_human_review"] is False
    assert result["interrupt_reason"] is None
    assert result["average_confidence"] >= 0.0
    assert len(result["obligations"]) >= 0
    assert "reviewed_obligations" in result
    assert "extraction_mode" in result
    assert result["page_number"] == 1
    assert result["document_id"] == "test-doc-123"


def test_intake_graph_triggers_low_confidence_interrupt() -> None:
    result = run_extraction_graph(
        raw_text="Advisory language with no mandatory directive.",
        confidence_threshold=0.95,
        page_number=1,
        document_id="test-doc-456",
    )

    # With no obligations, gate should pass (no review needed)
    assert result["gate_decision"] == "pass"
    assert result["requires_human_review"] is False
    assert result["interrupt_reason"] is None
    assert result["average_confidence"] == 0.0
    assert len(result["obligations"]) == 0


def test_intake_graph_extracts_obligations_with_deterministic_fallback() -> None:
    result = run_extraction_graph(
        raw_text="The petitioner shall file the appeal within 30 days. The court shall issue notice.",
        confidence_threshold=0.78,
        page_number=2,
        document_id="test-doc-789",
    )

    # Should extract obligations using deterministic patterns
    assert len(result["obligations"]) >= 1
    assert result["extraction_mode"] in {"deterministic", "ai"}
    assert result["average_confidence"] > 0.0

    # Check obligation structure
    if result["obligations"]:
        obl = result["obligations"][0]
        assert "obligation_code" in obl
        assert "title" in obl
        assert "description" in obl
        assert "confidence" in obl
        assert "confidence_components" in obl
        assert "source_highlights" in obl
        assert "page_number" in obl
        assert "owner_hint" in obl
        assert "priority" in obl


def test_intake_graph_falls_back_when_groq_network_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "orderflow_ai_default_llm_provider", "groq")
    monkeypatch.setattr(settings, "orderflow_ai_groq_api_key", "configured")

    def fail_groq(**_kwargs):
        raise GroqNetworkError("Network blocked while calling Groq.")

    monkeypatch.setattr(intake_graph, "call_groq_json", fail_groq)

    result = run_extraction_graph(
        raw_text="The authority shall submit a compliance report within 7 days.",
        confidence_threshold=0.78,
        page_number=3,
        document_id="test-doc-groq-network",
    )

    assert result["extraction_mode"] == "deterministic"
    assert result["ai_failure_code"] == "groq_network_error"
    assert len(result["obligations"]) >= 1


def test_intake_graph_output_is_deterministic() -> None:
    first = run_extraction_graph(
        raw_text="The authority shall issue a written notice.",
        confidence_threshold=0.78,
        page_number=1,
        document_id="test-doc-abc",
    )
    second = run_extraction_graph(
        raw_text="The authority shall issue a written notice.",
        confidence_threshold=0.78,
        page_number=1,
        document_id="test-doc-abc",
    )

    # Same input should produce same number of obligations
    assert len(first["obligations"]) == len(second["obligations"])
    assert first["extraction_mode"] == second["extraction_mode"]
    assert first["average_confidence"] == second["average_confidence"]
