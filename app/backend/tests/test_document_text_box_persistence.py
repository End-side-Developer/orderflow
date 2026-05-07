from datetime import UTC, datetime
from uuid import uuid4

from orderflow_api.api import document_text_box_persistence as persistence
from orderflow_api.schemas.obligations import ObligationCitation
from orderflow_api.schemas.visual_evidence import DocumentTextBoxRecord


def test_resolve_citation_visual_refs_matches_span_intersections(monkeypatch) -> None:
    document_id = uuid4()
    now = datetime.now(UTC)
    boxes = [
        DocumentTextBoxRecord(
            id=uuid4(),
            document_id=document_id,
            page_number=2,
            source="ocr",
            granularity="line",
            text="The department shall",
            normalized_text="The department shall",
            text_start=100,
            text_end=120,
            bbox={"left": 0.1, "top": 0.2, "width": 0.5, "height": 0.03},
            confidence=0.9,
            created_at=now,
        ),
        DocumentTextBoxRecord(
            id=uuid4(),
            document_id=document_id,
            page_number=2,
            source="ocr",
            granularity="line",
            text="submit the report.",
            normalized_text="submit the report.",
            text_start=121,
            text_end=140,
            bbox={"left": 0.1, "top": 0.24, "width": 0.45, "height": 0.03},
            confidence=0.88,
            created_at=now,
        ),
    ]

    monkeypatch.setattr(persistence, "list_document_text_boxes", lambda *_args, **_kwargs: boxes)

    refs = persistence.resolve_citation_visual_refs(
        document_id=document_id,
        page_number=2,
        span_start=110,
        span_end=130,
    )

    assert [ref.text for ref in refs] == ["The department shall", "submit the report."]
    assert refs[0].bbox.left == 0.1


def test_obligation_citation_keeps_visual_refs_backward_compatible() -> None:
    citation = ObligationCitation(page_number=1, clause_span="p1:c1:0-20")

    assert citation.visual_refs == []
