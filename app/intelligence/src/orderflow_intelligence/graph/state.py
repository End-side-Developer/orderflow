from __future__ import annotations

from typing import Literal, TypedDict


class SourceHighlight(TypedDict):
    text: str
    start: int
    end: int


class ConfidenceComponent(TypedDict):
    directive_signal: float
    entity_presence: float
    temporal_signal: float
    overall: float


class ObligationStub(TypedDict):
    obligation_code: str
    title: str
    description: str
    confidence: float
    confidence_components: ConfidenceComponent
    source_highlights: list[SourceHighlight]
    page_number: int
    owner_hint: str
    due_date: str | None
    priority: str


ReviewDecision = Literal["approved", "rejected", "pending_review"]


class ReviewedObligation(TypedDict):
    obligation: ObligationStub
    review_decision: ReviewDecision
    review_note: str | None
    edited_title: str | None
    edited_description: str | None


GateDecision = Literal["pass", "low_confidence"]


class ExtractionGraphState(TypedDict):
    raw_text: str
    source_language: str
    translated_text: str | None
    processing_language: str
    use_translated_text: bool
    parsed_text: str
    page_number: int
    document_id: str
    obligations: list[ObligationStub]
    reviewed_obligations: list[ReviewedObligation]
    average_confidence: float
    confidence_threshold: float
    gate_decision: GateDecision
    requires_human_review: bool
    interrupt_reason: str | None
    extraction_mode: str
    ai_provider: str | None
    ai_model: str | None
    ai_failure_code: str | None
    ai_failure_message: str | None


def build_initial_state(
    raw_text: str,
    confidence_threshold: float,
    source_language: str = "en",
    translated_text: str | None = None,
    page_number: int = 1,
    document_id: str = "",
) -> ExtractionGraphState:
    return {
        "raw_text": raw_text,
        "source_language": source_language,
        "translated_text": translated_text,
        "processing_language": "en" if translated_text else source_language,
        "use_translated_text": bool(translated_text),
        "parsed_text": "",
        "page_number": page_number,
        "document_id": document_id,
        "obligations": [],
        "reviewed_obligations": [],
        "average_confidence": 0.0,
        "confidence_threshold": confidence_threshold,
        "gate_decision": "pass",
        "requires_human_review": False,
        "interrupt_reason": None,
        "extraction_mode": "deterministic",
        "ai_provider": None,
        "ai_model": None,
        "ai_failure_code": None,
        "ai_failure_message": None,
    }
