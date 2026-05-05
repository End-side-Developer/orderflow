from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from orderflow_api.api import page_summary_engine
from orderflow_api.api.page_summary_engine import PageSummaryExtractor
from orderflow_api.core.ai_versions import PAGE_EXTRACTION_PROMPT_VERSION
from orderflow_api.schemas.page_summaries import PageSummaryRecord


def test_ai_extraction_logs_provider_error_without_secret(monkeypatch, caplog) -> None:
    secret = "sk-live-secret-from-env"

    async def fake_call_gemini(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError(f"provider rejected api_key={secret}")

    extractor = PageSummaryExtractor(ai_provider="gemini", model="gemini", api_key=secret)
    monkeypatch.setattr(extractor, "_call_gemini", fake_call_gemini)

    with caplog.at_level(logging.ERROR, logger=page_summary_engine.__name__):
        result = asyncio.run(
            extractor._ai_extract_page(
                page_num=1,
                page_text="The court directed the department to file a status report.",
                total_pages=1,
            )
        )

    assert result["summary"]
    assert "RuntimeError" in caplog.text
    assert secret not in caplog.text
    assert "api_key" not in caplog.text


def test_cache_hit_zero_ai_calls(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    dummy_summary = _page_summary_record(
        document_id=document_id,
        page_number=1,
        summary="Cached summary",
    )
    ai_calls: list[dict[str, object]] = []

    async def fake_ai_extract_page(*args, **kwargs):  # noqa: ANN002, ANN003
        ai_calls.append(kwargs)
        return {}

    cache_calls: list[dict[str, object]] = []

    def fake_get_cached_page_summary(**kwargs):  # noqa: ANN003
        cache_calls.append(kwargs)
        return dummy_summary

    monkeypatch.setattr(PageSummaryExtractor, "_ai_extract_page", fake_ai_extract_page)
    monkeypatch.setattr(
        page_summary_engine,
        "get_cached_page_summary",
        fake_get_cached_page_summary,
    )

    extractor = PageSummaryExtractor(ai_provider="gemini", model="gemini", api_key="key")
    records = asyncio.run(
        _collect_summaries(
            extractor,
            document_id=document_id,
            pages={1: "The matter was heard before Delhi High Court."},
            bypass_cache=False,
        )
    )

    assert len(records) == 1
    assert ai_calls == []
    assert records[0].summary == "Cached summary"
    assert cache_calls[0]["prompt_version"] == PAGE_EXTRACTION_PROMPT_VERSION


def test_cache_miss_calls_ai_and_persists_summary(monkeypatch) -> None:  # noqa: ANN001
    document_id = uuid4()
    ai_calls: list[dict[str, object]] = []
    create_calls: list[dict[str, object]] = []

    async def fake_ai_extract_page(*args, **kwargs):  # noqa: ANN002, ANN003
        ai_calls.append(kwargs)
        return {
            "summary": "AI summary",
            "key_points": ["point"],
            "highlights": [],
            "places": [],
            "confidence": 0.85,
        }

    def fake_create_page_summary(**kwargs):  # noqa: ANN003
        create_calls.append(kwargs)
        return _page_summary_record(
            document_id=kwargs["document_id"],
            page_number=kwargs["page_number"],
            summary=kwargs["summary"],
            content_hash=kwargs["content_hash"],
            prompt_version=kwargs["prompt_version"],
            ai_model=kwargs["ai_model"],
            ai_provider=kwargs["ai_provider"],
            source_excerpt=kwargs["source_excerpt"],
        )

    monkeypatch.setattr(PageSummaryExtractor, "_ai_extract_page", fake_ai_extract_page)
    monkeypatch.setattr(page_summary_engine, "get_cached_page_summary", lambda **kwargs: None)
    monkeypatch.setattr(page_summary_engine, "create_page_summary", fake_create_page_summary)
    monkeypatch.setattr(PageSummaryExtractor, "_find_context_links", lambda *args, **kwargs: [])
    monkeypatch.setattr(page_summary_engine, "geocode_places", lambda places, **kwargs: places)
    monkeypatch.setattr(page_summary_engine, "build_extracted_places", lambda places, **kwargs: [])

    extractor = PageSummaryExtractor(ai_provider="gemini", model="gemini", api_key="key")
    records = asyncio.run(
        _collect_summaries(
            extractor,
            document_id=document_id,
            pages={1: "Miss cache test"},
            bypass_cache=False,
        )
    )

    assert len(records) == 1
    assert len(ai_calls) == 1
    assert len(create_calls) == 1
    assert create_calls[0]["prompt_version"] == PAGE_EXTRACTION_PROMPT_VERSION
    assert create_calls[0]["source_excerpt"] == "Miss cache test"


def test_bypass_cache_flag_invalidates_cache(monkeypatch) -> None:  # noqa: ANN001
    ai_calls: list[dict[str, object]] = []
    cache_calls: list[dict[str, object]] = []

    async def fake_ai_extract_page(*args, **kwargs):  # noqa: ANN002, ANN003
        ai_calls.append(kwargs)
        return {"summary": "New AI summary"}

    def fake_get_cached_page_summary(**kwargs):  # noqa: ANN003
        cache_calls.append(kwargs)
        return _page_summary_record(summary="Would have hit")

    def fake_create_page_summary(**kwargs):  # noqa: ANN003
        return _page_summary_record(
            document_id=kwargs["document_id"],
            page_number=kwargs["page_number"],
            summary=kwargs["summary"],
        )

    monkeypatch.setattr(
        page_summary_engine,
        "get_cached_page_summary",
        fake_get_cached_page_summary,
    )
    monkeypatch.setattr(page_summary_engine, "create_page_summary", fake_create_page_summary)
    monkeypatch.setattr(PageSummaryExtractor, "_ai_extract_page", fake_ai_extract_page)
    monkeypatch.setattr(PageSummaryExtractor, "_find_context_links", lambda *args, **kwargs: [])
    monkeypatch.setattr(page_summary_engine, "geocode_places", lambda places, **kwargs: places)
    monkeypatch.setattr(page_summary_engine, "build_extracted_places", lambda places, **kwargs: [])

    extractor = PageSummaryExtractor(ai_provider="gemini", model="gemini", api_key="key")
    asyncio.run(
        _collect_summaries(
            extractor,
            document_id=uuid4(),
            pages={1: "Text"},
            bypass_cache=True,
        )
    )

    assert cache_calls == []
    assert len(ai_calls) == 1


async def _collect_summaries(
    extractor: PageSummaryExtractor,
    *,
    document_id: UUID,
    pages: dict[int, str],
    bypass_cache: bool,
) -> list[PageSummaryRecord]:
    return [
        record
        async for record in extractor.extract_page_summaries(
            document_id=document_id,
            pages=pages,
            bypass_cache=bypass_cache,
        )
    ]


def _page_summary_record(
    *,
    document_id: UUID | None = None,
    page_number: int = 1,
    summary: str = "summary",
    content_hash: str | None = "hash",
    prompt_version: str | None = PAGE_EXTRACTION_PROMPT_VERSION,
    ai_model: str | None = "gemini",
    ai_provider: str | None = "gemini",
    source_excerpt: str | None = "excerpt",
) -> PageSummaryRecord:
    now = datetime.now(UTC)
    return PageSummaryRecord(
        id=uuid4(),
        document_id=document_id or uuid4(),
        page_number=page_number,
        page_text="page text",
        summary=summary,
        key_points=[],
        important_highlights=[],
        context_links=[],
        obligation_ids=[],
        extracted_places=[],
        confidence=0.99,
        extraction_mode="ai",
        ai_model=ai_model,
        ai_provider=ai_provider,
        content_hash=content_hash,
        prompt_version=prompt_version,
        source_excerpt=source_excerpt,
        ai_token_usage=None,
        generated_at=now,
        created_at=now,
        updated_at=now,
    )
