from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from orderflow_intelligence.core.config import settings
from orderflow_intelligence.core.gemini_client import (
    GeminiError,
    call_gemini_json,
    extract_gemini_text,
)
from orderflow_intelligence.graph.state import (
    ConfidenceComponent,
    ExtractionGraphState,
    GateDecision,
    ObligationStub,
    ReviewedObligation,
    SourceHighlight,
    build_initial_state,
)

logger = logging.getLogger(__name__)

_LOW_CONFIDENCE_INTERRUPT_REASON = "LOW_CONFIDENCE_REQUIRES_HUMAN_REVIEW"
_AI_OBLIGATION_EXTRACTION_MAX_ATTEMPTS = 3
_AI_OBLIGATION_EXTRACTION_RETRY_BASE_SECONDS = 0.25


# ──── Node 1: Parse Input ────


def parse_input(state: ExtractionGraphState) -> dict[str, Any]:
    source_text = state["translated_text"] or state["raw_text"]
    normalized_text = " ".join(source_text.split())
    using_translation = bool(state["translated_text"])
    processing_language = "en" if using_translation else state["source_language"]
    return {
        "parsed_text": normalized_text,
        "use_translated_text": using_translation,
        "processing_language": processing_language,
    }


# ──── Node 2: Extract Obligations (LLM + Deterministic fallback) ────

_OBLIGATION_EXTRACTION_PROMPT = """You are a legal obligation extractor for an enterprise legal workflow system called OrderFlow.

Analyze the following text from Page {page_number} of a court judgment or legal document.

Extract ALL mandatory obligations, directives, compliance requirements, or court orders from this text.

Return a strict JSON response with EXACTLY this structure (no markdown, no extra text):
{{
  "obligations": [
    {{
      "title": "Short descriptive title of the obligation (max 80 chars)",
      "description": "Full description of what must be done, by whom, and by when",
      "owner_hint": "The party responsible (e.g. Petitioner, Respondent, Court Registry, or Unknown)",
      "due_date": "Date string if mentioned (e.g. 2024-03-15), or null",
      "priority": "One of: low | medium | high | critical",
      "source_text": "The exact text snippet from the document that this obligation was extracted from",
      "directive_signal": 0.0_to_1.0_confidence_that_this_is_a_mandatory_directive,
      "entity_signal": 0.0_to_1.0_confidence_that_responsible_party_is_identified,
      "temporal_signal": 0.0_to_1.0_confidence_that_deadline_or_timeline_is_clear
    }}
  ]
}}

Rules:
- Only extract genuine obligations (shall, must, required to, directed to, ordered to, comply with).
- Do NOT extract advisory or permissive language (may, can, should consider).
- Each obligation must have a clear source_text quote from the document.
- Rate confidence signals honestly: directive_signal measures how mandatory the language is,
  entity_signal measures how clearly the responsible party is identified,
  temporal_signal measures how clear the deadline is.
- Return empty obligations array if no obligations are found on this page.

Text to analyze:
{text}"""


def _compute_confidence(directive: float, entity: float, temporal: float) -> ConfidenceComponent:
    weights = {
        "directive_signal": 0.50,
        "entity_presence": 0.25,
        "temporal_signal": 0.25,
    }
    overall = (
        directive * weights["directive_signal"]
        + entity * weights["entity_presence"]
        + temporal * weights["temporal_signal"]
    )
    return ConfidenceComponent(
        directive_signal=round(directive, 3),
        entity_presence=round(entity, 3),
        temporal_signal=round(temporal, 3),
        overall=round(overall, 3),
    )


def _find_source_highlight(parsed_text: str, source_text: str) -> list[SourceHighlight]:
    highlights: list[SourceHighlight] = []
    if not source_text:
        return highlights
    snippet = source_text[:60].strip()
    idx = parsed_text.find(snippet)
    if idx >= 0:
        highlights.append(SourceHighlight(text=source_text, start=idx, end=idx + len(source_text)))
    else:
        highlights.append(SourceHighlight(text=source_text, start=0, end=len(source_text)))
    return highlights


def _gemini_retry_delay_seconds(error: GeminiError | None, attempt: int) -> float:
    retry_after = getattr(error, "retry_after_seconds", None)
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        return min(float(retry_after), 2.0)
    return _AI_OBLIGATION_EXTRACTION_RETRY_BASE_SECONDS * (2 ** max(attempt - 1, 0))


_AiExtractionResult = tuple[list[ObligationStub], str | None, str | None]


def _extract_with_gemini(parsed_text: str, page_number: int) -> _AiExtractionResult:
    """Returns (obligations, failure_code, failure_message).

    On success: ([..], None, None) or ([], None, None) if AI returned nothing.
    On failure: ([], "<code>", "<message>") so the caller can surface the
    reason instead of silently dropping back to the deterministic extractor.
    """
    gemini_key = getattr(settings, "orderflow_ai_gemini_api_key", None)
    if not gemini_key:
        return (
            [],
            "gemini_missing_key",
            "Gemini API key not configured — fell back to deterministic extractor.",
        )

    configured_model = settings.orderflow_ai_default_model.strip()
    model = (
        configured_model if configured_model.lower().startswith("gemini") else "gemini-2.0-flash"
    )

    prompt = _OBLIGATION_EXTRACTION_PROMPT.format(
        page_number=page_number,
        text=parsed_text[: settings.orderflow_ai_gemini_page_extraction_prompt_chars],
    )

    result: dict[str, Any] | None = None
    last_failure: tuple[str, str] | None = None
    for attempt in range(1, _AI_OBLIGATION_EXTRACTION_MAX_ATTEMPTS + 1):
        try:
            response = call_gemini_json(
                api_key=gemini_key,
                model=model,
                prompt=prompt,
                temperature=0.1,
                max_output_tokens=min(settings.orderflow_ai_gemini_max_output_tokens, 1200),
                request_label="page obligation extraction",
            )
            text_response = extract_gemini_text(response)
            result = json.loads(text_response)
            break
        except GeminiError as exc:
            logger.warning(
                "Gemini extraction failure: %s (%s), attempt=%s/%s",
                exc.code,
                exc,
                attempt,
                _AI_OBLIGATION_EXTRACTION_MAX_ATTEMPTS,
            )
            last_failure = (exc.code, str(exc))
            if not exc.retryable or attempt >= _AI_OBLIGATION_EXTRACTION_MAX_ATTEMPTS:
                return ([], exc.code, str(exc))
            time.sleep(_gemini_retry_delay_seconds(exc, attempt))
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            logger.warning(
                "Failed to parse Gemini extraction response, attempt=%s/%s: %s",
                attempt,
                _AI_OBLIGATION_EXTRACTION_MAX_ATTEMPTS,
                exc,
            )
            last_failure = ("gemini_invalid_json", "Gemini returned non-JSON text.")
            if attempt >= _AI_OBLIGATION_EXTRACTION_MAX_ATTEMPTS:
                return ([], last_failure[0], last_failure[1])
            time.sleep(_gemini_retry_delay_seconds(None, attempt))
        except Exception as exc:
            logger.warning(
                "Unexpected Gemini call failure, attempt=%s/%s: %s",
                attempt,
                _AI_OBLIGATION_EXTRACTION_MAX_ATTEMPTS,
                exc,
            )
            last_failure = ("gemini_unexpected_error", str(exc))
            if attempt >= _AI_OBLIGATION_EXTRACTION_MAX_ATTEMPTS:
                return ([], last_failure[0], last_failure[1])
            time.sleep(_gemini_retry_delay_seconds(None, attempt))

    if result is None:
        code, message = last_failure or ("gemini_unexpected_error", "Gemini extraction failed.")
        return ([], code, message)

    obligations: list[ObligationStub] = []
    for i, item in enumerate(result.get("obligations", [])):
        if not isinstance(item, dict) or "title" not in item:
            continue
        directive = float(item.get("directive_signal", 0.5))
        entity = float(item.get("entity_signal", 0.5))
        temporal = float(item.get("temporal_signal", 0.5))
        components = _compute_confidence(directive, entity, temporal)
        source_text = str(item.get("source_text", ""))
        obligations.append(
            ObligationStub(
                obligation_code=f"OBL-P{page_number}-{i + 1:03d}",
                title=str(item.get("title", "Untitled obligation"))[:80],
                description=str(item.get("description", "")),
                confidence=components["overall"],
                confidence_components=components,
                source_highlights=_find_source_highlight(parsed_text, source_text),
                page_number=page_number,
                owner_hint=str(item.get("owner_hint", "Unknown")),
                due_date=item.get("due_date") if item.get("due_date") else None,
                priority=str(item.get("priority", "medium")),
            )
        )

    return (obligations, None, None)


def _extract_deterministic(parsed_text: str, page_number: int) -> list[ObligationStub]:
    directive_patterns = [
        r"\bshall\s+b",
        r"\bmust\s+b",
        r"\brequired\s+to\b",
        r"\bdirected\s+to\b",
        r"\bordered\s+to\b",
        r"\bdirected\s+that\b",
        r"\bshall\s+file\b",
        r"\bshall\s+submit\b",
        r"\bshall\s+comply\b",
        r"\bshall\s+pay\b",
        r"\bshall\s+provide\b",
        r"\bshall\s+ensure\b",
        r"\bshall\s+appear\b",
        r"\bshall\s+be\s+done\b",
        r"\bcomply\s+with\b",
    ]

    obligations: list[ObligationStub] = []
    sentences = re.split(r"(?<=[.!?])\s+", parsed_text)

    for i, sentence in enumerate(sentences):
        sentence_lower = sentence.lower()
        has_directive = any(re.search(pattern, sentence_lower) for pattern in directive_patterns)
        if not has_directive:
            continue

        has_entity = bool(
            re.search(
                r"\b(petitioner|respondent|appellant|appellee|plaintiff|defendant|court|registry|authority|commission|tribunal)\b",
                sentence_lower,
            )
        )
        has_temporal = bool(
            re.search(
                r"\b(within\s+\d+\s+days?|in\s+\d+\s+days?|by\s+\d{1,2}[^a-z]*\d{4}|on\s+or\s+before|before\s+\d|not\s+later\s+than|within\s+the\s+period)\b",
                sentence_lower,
            )
        )

        directive_signal = 0.85 if has_directive else 0.3
        entity_signal = 0.7 if has_entity else 0.3
        temporal_signal = 0.8 if has_temporal else 0.2

        components = _compute_confidence(directive_signal, entity_signal, temporal_signal)

        owner = "Unknown"
        for party in [
            "petitioner",
            "respondent",
            "appellant",
            "plaintiff",
            "defendant",
        ]:
            if party in sentence_lower:
                owner = party.capitalize()
                break

        due_date = None
        date_match = re.search(r"(?:within|in)\s+(\d+)\s+days?", sentence_lower)
        if date_match:
            due_date = f"within {date_match.group(1)} days"

        priority = "high" if has_temporal and has_entity else "medium" if has_directive else "low"

        obligations.append(
            ObligationStub(
                obligation_code=f"OBL-P{page_number}-{len(obligations) + 1:03d}",
                title=sentence[:80].strip(),
                description=sentence.strip(),
                confidence=components["overall"],
                confidence_components=components,
                source_highlights=[
                    SourceHighlight(
                        text=sentence.strip(),
                        start=parsed_text.find(sentence.strip()),
                        end=parsed_text.find(sentence.strip()) + len(sentence.strip()),
                    )
                ],
                page_number=page_number,
                owner_hint=owner,
                due_date=due_date,
                priority=priority,
            )
        )

    return obligations


def extract_obligations(state: ExtractionGraphState) -> dict[str, Any]:
    parsed_text = state["parsed_text"]
    page_number = state["page_number"]

    llm_obligations, ai_failure_code, ai_failure_message = _extract_with_gemini(
        parsed_text, page_number
    )

    if ai_failure_code and ai_failure_code != "gemini_missing_key":
        raise RuntimeError(
            f"Gemini obligation extraction failed after retry attempts: {ai_failure_message}"
        )

    if llm_obligations or ai_failure_code is None:
        obligations = llm_obligations
        extraction_mode = "ai"
        ai_provider = "gemini"
        ai_model = settings.orderflow_ai_default_model
    else:
        obligations = _extract_deterministic(parsed_text, page_number)
        extraction_mode = "deterministic"
        ai_provider = None
        ai_model = None

    avg_confidence = (
        round(sum(o["confidence"] for o in obligations) / len(obligations), 3)
        if obligations
        else 0.0
    )

    return {
        "obligations": obligations,
        "average_confidence": avg_confidence,
        "extraction_mode": extraction_mode,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "ai_failure_code": ai_failure_code,
        "ai_failure_message": ai_failure_message,
    }


# ──── Node 3: Confidence Gate ────


def confidence_gate(state: ExtractionGraphState) -> dict[str, Any]:
    has_obligations = len(state["obligations"]) > 0
    low_confidence = has_obligations and state["average_confidence"] < state["confidence_threshold"]
    gate_decision: GateDecision = "low_confidence" if low_confidence else "pass"

    return {
        "gate_decision": gate_decision,
        "requires_human_review": low_confidence,
        "interrupt_reason": (_LOW_CONFIDENCE_INTERRUPT_REASON if low_confidence else None),
    }


# ──── Node 4: Human Review (LangGraph interrupt for HITL) ────


def human_review_node(state: ExtractionGraphState) -> dict[str, Any]:
    reviewed: list[ReviewedObligation] = []
    for obl in state["obligations"]:
        reviewed.append(
            ReviewedObligation(
                obligation=obl,
                review_decision="pending_review",
                review_note=None,
                edited_title=None,
                edited_description=None,
            )
        )
    return {"reviewed_obligations": reviewed}


def _route_from_gate(state: ExtractionGraphState) -> str:
    if state["gate_decision"] == "low_confidence":
        return "human_review"
    if len(state["obligations"]) > 0:
        return "auto_approve_high_confidence"
    return "end_no_obligations"


def auto_approve_high_confidence(state: ExtractionGraphState) -> dict[str, Any]:
    reviewed: list[ReviewedObligation] = []
    for obl in state["obligations"]:
        reviewed.append(
            ReviewedObligation(
                obligation=obl,
                review_decision="approved",
                review_note="Auto-approved: high confidence extraction",
                edited_title=None,
                edited_description=None,
            )
        )
    return {"reviewed_obligations": reviewed}


def end_no_obligations(state: ExtractionGraphState) -> dict[str, Any]:
    return {"reviewed_obligations": []}


# ──── Graph Builder ────

_graph_instance: Any | None = None
_graph_with_checkpointer: Any | None = None


def build_intake_graph() -> Any:
    global _graph_instance

    if _graph_instance is None:
        graph = StateGraph(ExtractionGraphState)

        graph.add_node("parse_input", parse_input)
        graph.add_node("extract_obligations", extract_obligations)
        graph.add_node("confidence_gate", confidence_gate)
        graph.add_node("human_review", human_review_node)
        graph.add_node("auto_approve_high_confidence", auto_approve_high_confidence)
        graph.add_node("end_no_obligations", end_no_obligations)

        graph.add_edge(START, "parse_input")
        graph.add_edge("parse_input", "extract_obligations")
        graph.add_edge("extract_obligations", "confidence_gate")

        graph.add_conditional_edges(
            "confidence_gate",
            _route_from_gate,
            {
                "human_review": "human_review",
                "auto_approve_high_confidence": "auto_approve_high_confidence",
                "end_no_obligations": "end_no_obligations",
            },
        )

        graph.add_edge("human_review", END)
        graph.add_edge("auto_approve_high_confidence", END)
        graph.add_edge("end_no_obligations", END)

        _graph_instance = graph.compile()

    return _graph_instance


def build_intake_graph_with_checkpointer() -> Any:
    global _graph_with_checkpointer

    if _graph_with_checkpointer is None:
        graph = StateGraph(ExtractionGraphState)

        graph.add_node("parse_input", parse_input)
        graph.add_node("extract_obligations", extract_obligations)
        graph.add_node("confidence_gate", confidence_gate)
        graph.add_node("human_review", human_review_node)
        graph.add_node("auto_approve_high_confidence", auto_approve_high_confidence)
        graph.add_node("end_no_obligations", end_no_obligations)

        graph.add_edge(START, "parse_input")
        graph.add_edge("parse_input", "extract_obligations")
        graph.add_edge("extract_obligations", "confidence_gate")

        graph.add_conditional_edges(
            "confidence_gate",
            _route_from_gate,
            {
                "human_review": "human_review",
                "auto_approve_high_confidence": "auto_approve_high_confidence",
                "end_no_obligations": "end_no_obligations",
            },
        )

        graph.add_edge("human_review", END)
        graph.add_edge("auto_approve_high_confidence", END)
        graph.add_edge("end_no_obligations", END)

        checkpointer = MemorySaver()
        _graph_with_checkpointer = graph.compile(checkpointer=checkpointer)

    return _graph_with_checkpointer


def run_extraction_graph(
    raw_text: str,
    confidence_threshold: float,
    source_language: str = "en",
    translated_text: str | None = None,
    page_number: int = 1,
    document_id: str = "",
) -> ExtractionGraphState:
    initial_state = build_initial_state(
        raw_text=raw_text,
        confidence_threshold=confidence_threshold,
        source_language=source_language,
        translated_text=translated_text,
        page_number=page_number,
        document_id=document_id,
    )
    result = build_intake_graph().invoke(initial_state)
    return cast(ExtractionGraphState, result)


def run_extraction_graph_with_defaults(
    raw_text: str, page_number: int = 1, document_id: str = ""
) -> ExtractionGraphState:
    return run_extraction_graph(
        raw_text=raw_text,
        confidence_threshold=settings.orderflow_ai_confidence_threshold,
        page_number=page_number,
        document_id=document_id,
    )
