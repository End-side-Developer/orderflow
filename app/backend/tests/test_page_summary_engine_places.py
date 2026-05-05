from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from orderflow_api.api import page_summary_engine
from orderflow_api.api.page_summary_engine import PageSummaryExtractor
from orderflow_api.schemas.page_summaries import PageSummaryRecord


def test_ai_extract_returns_places(monkeypatch) -> None:  # noqa: ANN001
    def fake_call_gemini_json(**kwargs):  # noqa: ANN003
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"summary":"Page mentions Delhi High Court.",'
                                    '"key_points":["Delhi High Court heard the matter"],'
                                    '"highlights":[],'
                                    '"places":[{"name":"Delhi High Court",'
                                    '"place_type":"court","state":"Delhi",'
                                    '"district":"New Delhi",'
                                    '"raw_text_span":"before Delhi High Court",'
                                    '"mention_count":1}],'
                                    '"confidence":0.9}'
                                )
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(page_summary_engine, "call_gemini_json", fake_call_gemini_json)
    monkeypatch.setattr(page_summary_engine, "geocode_places", lambda places, **kwargs: places)
    monkeypatch.setattr(page_summary_engine, "get_cached_page_summary", lambda **kwargs: None)
    monkeypatch.setattr(
        page_summary_engine,
        "create_page_summary",
        _record_from_create_kwargs,
    )

    extractor = PageSummaryExtractor(
        ai_provider="gemini",
        model="gemini-test",
        api_key="test-key",
    )

    async def _run():
        return [
            record
            async for record in extractor.extract_page_summaries(
                document_id=uuid4(),
                pages={1: "The matter was heard before Delhi High Court."},
            )
        ]

    records = asyncio.run(_run())

    assert len(records) == 1
    assert len(records[0].extracted_places) == 1
    assert records[0].extracted_places[0].name == "Delhi High Court"


def test_extraction_handles_missing_places_field(monkeypatch) -> None:  # noqa: ANN001
    def fake_call_gemini_json(**kwargs):  # noqa: ANN003
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"summary":"No place field here.",'
                                    '"key_points":["Point"],"highlights":[],"confidence":0.8}'
                                )
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(page_summary_engine, "call_gemini_json", fake_call_gemini_json)
    monkeypatch.setattr(page_summary_engine, "geocode_places", lambda places, **kwargs: places)
    monkeypatch.setattr(page_summary_engine, "get_cached_page_summary", lambda **kwargs: None)
    monkeypatch.setattr(
        page_summary_engine,
        "create_page_summary",
        _record_from_create_kwargs,
    )

    extractor = PageSummaryExtractor(
        ai_provider="gemini",
        model="gemini-test",
        api_key="test-key",
    )

    async def _run():
        return [
            record
            async for record in extractor.extract_page_summaries(
                document_id=uuid4(),
                pages={1: "This page has no concrete locations."},
            )
        ]

    records = asyncio.run(_run())

    assert len(records) == 1
    assert records[0].extracted_places == []


def test_geocoding_failure_persists_with_null_coords(monkeypatch) -> None:  # noqa: ANN001
    async def fake_ai_extract_places_only(self, **kwargs):  # noqa: ANN001, ANN003
        return {
            "places": [
                {
                    "name": "Asdfqwerville",
                    "place_type": "other",
                    "mention_count": 1,
                }
            ]
        }

    def fake_geocode_places(places, **kwargs):  # noqa: ANN001, ANN003
        return [
            place.model_copy(
                update={
                    "lat": None,
                    "lng": None,
                    "geocode_source": "none",
                    "geocode_confidence": 0.0,
                }
            )
            for place in places
        ]

    monkeypatch.setattr(
        PageSummaryExtractor,
        "_ai_extract_places_only",
        fake_ai_extract_places_only,
    )
    monkeypatch.setattr(page_summary_engine, "geocode_places", fake_geocode_places)

    extractor = PageSummaryExtractor(
        ai_provider="gemini",
        model="gemini-test",
        api_key="test-key",
    )
    places = asyncio.run(
        extractor.extract_places_for_page(
            page_num=2,
            page_text="The incident happened in Asdfqwerville.",
        )
    )

    assert len(places) == 1
    assert places[0].lat is None
    assert places[0].lng is None
    assert places[0].geocode_source == "none"


def _record_from_create_kwargs(**kwargs: Any) -> PageSummaryRecord:
    now = datetime.now(UTC)
    return PageSummaryRecord(
        id=uuid4(),
        document_id=kwargs["document_id"],
        page_number=kwargs["page_number"],
        page_text=kwargs["page_text"],
        summary=kwargs["summary"],
        key_points=kwargs.get("key_points") or [],
        important_highlights=kwargs.get("important_highlights") or [],
        context_links=kwargs.get("context_links") or [],
        obligation_ids=kwargs.get("obligation_ids") or [],
        extracted_places=kwargs.get("extracted_places") or [],
        confidence=kwargs.get("confidence"),
        extraction_mode=kwargs.get("extraction_mode", "ai"),
        ai_model=kwargs.get("ai_model"),
        ai_provider=kwargs.get("ai_provider"),
        content_hash=kwargs.get("content_hash"),
        prompt_version=kwargs.get("prompt_version"),
        source_excerpt=kwargs.get("source_excerpt"),
        ai_token_usage=kwargs.get("ai_token_usage"),
        generated_at=now,
        created_at=now,
        updated_at=now,
    )
