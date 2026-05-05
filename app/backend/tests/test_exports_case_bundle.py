from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from orderflow_api.main import app
from orderflow_api.schemas.documents import DocumentRecord
from orderflow_api.schemas.page_summaries import ExtractedPlace, PageSummaryRecord

client = TestClient(app)


def test_case_bundle_pdf_endpoint_returns_attachment(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()

    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.get_persisted_document",
        lambda value: _document(document_id) if value == document_id else None,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.list_page_summaries",
        lambda value: [_summary(document_id)] if value == document_id else [],
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.render_summary_map",
        lambda places: b"summary-map",
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.render_page_map",
        lambda places, page_number: b"page-map",
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports._html_to_pdf_bytes",
        lambda rendered_html, fallback_text: b"%PDF-1.4\nfake\n%%EOF\n",
    )

    response = client.post(
        "/api/v1/exports/case-bundle/pdf",
        json={
            "document_id": str(document_id),
            "include_summary_map": True,
            "include_per_page_maps": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "case-bundle-case.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_case_bundle_pdf_endpoint_returns_404_for_missing_document(
    monkeypatch,
) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.get_persisted_document",
        lambda value: None,
    )

    response = client.post(
        "/api/v1/exports/case-bundle/pdf",
        json={
            "document_id": str(uuid4()),
            "include_summary_map": True,
            "include_per_page_maps": True,
        },
    )

    assert response.status_code == 404


def test_case_bundle_pdf_endpoint_handles_no_places(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    summary = _summary(document_id, extracted_places=[])

    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.get_persisted_document",
        lambda value: _document(document_id) if value == document_id else None,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports.list_page_summaries",
        lambda value: [summary] if value == document_id else [],
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.exports._html_to_pdf_bytes",
        lambda rendered_html, fallback_text: b"%PDF-1.4\nno-map\n%%EOF\n",
    )

    response = client.post(
        "/api/v1/exports/case-bundle/pdf",
        json={
            "document_id": str(document_id),
            "include_summary_map": True,
            "include_per_page_maps": True,
        },
    )

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


def _document(document_id) -> DocumentRecord:  # noqa: ANN001
    now = datetime.now(UTC)
    return DocumentRecord(
        id=document_id,
        source_file_name="case.pdf",
        source_file_type="application/pdf",
        source_file_size=100,
        object_key=None,
        checksum_sha256=None,
        workflow_run_id=None,
        status="ready",
        metadata={"cis": {"court_name": "Delhi High Court", "state": "Delhi"}},
        created_at=now,
        updated_at=now,
    )


def _summary(
    document_id,
    *,
    extracted_places: list[ExtractedPlace] | None = None,
) -> PageSummaryRecord:  # noqa: ANN001
    now = datetime.now(UTC)
    return PageSummaryRecord(
        id=uuid4(),
        document_id=document_id,
        page_number=1,
        page_text="The matter was heard before Delhi High Court.",
        summary="The page records proceedings before the Delhi High Court.",
        key_points=["Proceedings are before the court."],
        important_highlights=[],
        context_links=[],
        obligation_ids=[],
        extracted_places=(
            extracted_places
            if extracted_places is not None
            else [
                ExtractedPlace(
                    id=uuid4(),
                    name="Delhi High Court",
                    normalized_name="delhi high court",
                    place_type="court",
                    state="Delhi",
                    district="New Delhi",
                    raw_text_span="before Delhi High Court",
                    lat=28.6139,
                    lng=77.209,
                    geocode_confidence=0.9,
                    geocode_source="nominatim",
                    source_page_number=1,
                    mention_count=1,
                )
            ]
        ),
        confidence=0.8,
        extraction_mode="deterministic",
        ai_model="clause_fallback",
        ai_provider="clauses",
        generated_at=now,
        created_at=now,
        updated_at=now,
    )
