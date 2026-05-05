from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from orderflow_api.main import app
from orderflow_api.schemas.documents import DocumentRecord
from orderflow_api.schemas.page_summaries import ExtractedPlace, PageSummaryRecord


client = TestClient(app)


def test_summaries_endpoint_includes_extracted_places(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    summary = _summary(document_id=document_id)

    monkeypatch.setattr(
        "orderflow_api.api.routes.page_summaries.list_page_summaries",
        lambda value: [summary] if value == document_id else [],
    )

    response = client.get(f"/api/v1/summaries/{document_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    places = payload["data"]["items"][0]["extracted_places"]
    assert places[0]["name"] == "Delhi High Court"
    assert places[0]["lat"] == 28.6139


def test_places_refresh_endpoint_updates_only_places_column(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    before = _summary(document_id=document_id, extracted_places=[])
    after = _summary(document_id=document_id)
    updates: list[tuple[int, list[ExtractedPlace]]] = []

    call_count = {"list": 0}

    def fake_list(value):  # noqa: ANN001
        call_count["list"] += 1
        if value != document_id:
            return []
        return [before] if call_count["list"] == 1 else [after]

    async def fake_extract_places_for_page(self, **kwargs):  # noqa: ANN001, ANN003
        return after.extracted_places

    monkeypatch.setattr(
        "orderflow_api.api.routes.page_summaries.list_page_summaries",
        fake_list,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.page_summaries.get_persisted_document",
        lambda value: _document(document_id) if value == document_id else None,
    )
    monkeypatch.setattr(
        "orderflow_api.api.routes.page_summaries.update_page_summary_places",
        lambda summary_id, places: updates.append((before.page_number, places)),
    )
    monkeypatch.setattr(
        "orderflow_api.api.page_summary_engine.PageSummaryExtractor.extract_places_for_page",
        fake_extract_places_for_page,
    )

    response = client.post(f"/api/v1/summaries/{document_id}/places/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["items"][0]["summary"] == before.summary
    assert payload["data"]["items"][0]["extracted_places"][0]["name"] == "Delhi High Court"
    assert updates
    assert updates[0][0] == 1


def _summary(
    *,
    document_id,
    extracted_places: list[ExtractedPlace] | None = None,
) -> PageSummaryRecord:
    now = datetime.now(UTC)
    return PageSummaryRecord(
        id=uuid4(),
        document_id=document_id,
        page_number=1,
        page_text="The matter was heard before Delhi High Court.",
        summary="The page records proceedings before the Delhi High Court.",
        key_points=[],
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
