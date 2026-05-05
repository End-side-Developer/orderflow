"""
API routes for page-by-page summaries.

Endpoints:
- GET /api/v1/summaries/{document_id} - List summaries for a document
- POST /api/v1/summaries/{document_id}/generate - Generate summaries using AI
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from orderflow_api.api.document_persistence import get_persisted_document
from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.page_summary_engine import PageSummaryExtractor
from orderflow_api.core.config import settings
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.api.page_summary_persistence import (
    create_page_summary,
    list_page_summaries,
    delete_page_summaries,
    update_page_summary_places,
)
from orderflow_api.api.extraction_persistence import list_persisted_clauses
from orderflow_api.schemas.page_summaries import (
    PageSummariesEnvelope,
    PageSummariesListData,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["page_summaries"])


@router.get("/summaries/{document_id}", response_model=PageSummariesEnvelope)
async def list_page_summaries_route(
    document_id: UUID,
    request: Request = None,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> PageSummariesEnvelope:
    """
    GET /api/v1/summaries/{document_id}

    List all page-by-page summaries for a document, ordered by page number.

    Returns:
        PageSummariesEnvelope with list of PageSummaryRecord
    """
    request_id = getattr(request.state, "request_id", None) if request else None

    summaries = list_page_summaries(document_id)
    return PageSummariesEnvelope(
        request_id=request_id,
        data=PageSummariesListData(
            document_id=document_id,
            total_pages=len(summaries),
            summary_count=len(summaries),
            items=summaries,
        ),
    )


@router.post("/summaries/{document_id}/generate", response_model=PageSummariesEnvelope)
async def generate_page_summaries(
    document_id: UUID,
    ai_provider: str | None = Query(default=None),
    ai_model: str | None = Query(default=None),
    request: Request = None,
    _user=Depends(require_permission(Permission.EXTRACTION_RUN)),
) -> PageSummariesEnvelope:
    """
    POST /api/v1/summaries/{document_id}/generate

    Generate page-by-page summaries for a document using extracted clauses.
    Uses deterministic extraction from clauses as fallback (no AI required).

    Query parameters:
        ai_provider: Reserved for future AI integration
        ai_model: Reserved for future AI integration

    Returns:
        PageSummariesEnvelope with generated summaries
    """
    request_id = getattr(request.state, "request_id", None) if request else None

    # Delete existing summaries for this document
    delete_page_summaries(document_id)

    # Get clauses for the document
    clauses = list_persisted_clauses(document_id)
    if not clauses:
        raise HTTPException(
            status_code=404,
            detail="No clauses found for this document. Upload and process the document first.",
        )

    # Group clauses by page number
    pages: dict[int, list] = {}
    for clause in clauses:
        page_num = clause.page_number or 1
        if page_num not in pages:
            pages[page_num] = []
        pages[page_num].append(clause)

    # Generate summaries for each page
    for page_num, page_clauses in sorted(pages.items()):
        page_text = " ".join([c.text for c in page_clauses])
        sentences = [s.strip() for s in page_text.split(".") if s.strip()]
        summary = (
            ". ".join(sentences[:2])
            if sentences
            else f"Page {page_num} content extracted from document."
        )

        key_points = [c.text[:200] for c in page_clauses[:5]]

        important_highlights = [
            {
                "text": c.text[:150],
                "significance": "important" if i == 0 else "contextual",
                "relevance": "Extracted from judgment text",
            }
            for i, c in enumerate(page_clauses[:3])
        ]

        create_page_summary(
            document_id=document_id,
            page_number=page_num,
            page_text=page_text,
            summary=summary,
            key_points=key_points,
            important_highlights=important_highlights,
            context_links=[],
            obligation_ids=[],
            confidence=0.8,
            extraction_mode="deterministic",
            ai_model="clause_fallback",
            ai_provider="clauses",
        )

    # Return the newly generated summaries
    summaries = list_page_summaries(document_id)
    return PageSummariesEnvelope(
        request_id=request_id,
        data=PageSummariesListData(
            document_id=document_id,
            total_pages=len(summaries),
            summary_count=len(summaries),
            items=summaries,
        ),
    )


@router.post(
    "/summaries/{document_id}/places/refresh",
    response_model=PageSummariesEnvelope,
)
async def refresh_page_summary_places(
    document_id: UUID,
    ai_provider: str | None = Query(default=None),
    ai_model: str | None = Query(default=None),
    request: Request = None,
    _user=Depends(require_permission(Permission.EXTRACTION_RUN)),
) -> PageSummariesEnvelope:
    """
    POST /api/v1/summaries/{document_id}/places/refresh

    Refresh only page-level place extraction and geocoding. Existing summaries,
    highlights, key points, and context links are left untouched.
    """
    request_id = getattr(request.state, "request_id", None) if request else None
    summaries = list_page_summaries(document_id)
    if not summaries:
        raise HTTPException(
            status_code=404,
            detail="No page summaries found for this document. Generate summaries first.",
        )

    metadata = _document_metadata(document_id)
    state_hint, district_hint, court_fallback_query = _extract_cis_hints(metadata)
    provider = ai_provider or settings.orderflow_ai_default_provider
    model = ai_model or settings.orderflow_ai_default_model
    extractor = PageSummaryExtractor(
        ai_provider=provider,
        model=model,
        api_key=_api_key_for_provider(provider),
        temperature=0.1,
    )

    for summary in summaries:
        page_text = summary.page_text or ""
        if not page_text.strip():
            update_page_summary_places(summary.id, [])
            continue

        places = await extractor.extract_places_for_page(
            page_num=summary.page_number,
            page_text=page_text,
            state_hint=state_hint,
            district_hint=district_hint,
            court_fallback_query=court_fallback_query,
        )
        update_page_summary_places(summary.id, places)

    refreshed = list_page_summaries(document_id)
    return PageSummariesEnvelope(
        request_id=request_id,
        data=PageSummariesListData(
            document_id=document_id,
            total_pages=len(refreshed),
            summary_count=len(refreshed),
            items=refreshed,
        ),
    )


def _document_metadata(document_id: UUID) -> dict[str, object]:
    document = get_persisted_document(document_id)
    if document is None or document.metadata is None:
        return {}
    return document.metadata


def _extract_cis_hints(
    metadata: dict[str, object],
) -> tuple[str | None, str | None, str | None]:
    cis = metadata.get("cis")
    if not isinstance(cis, dict):
        return None, None, None

    state = _string_or_none(cis.get("state"))
    district = _string_or_none(cis.get("district"))
    court_name = _string_or_none(cis.get("court_name"))
    fallback_parts = [court_name, district, state, "India"]
    court_fallback_query = ", ".join(part for part in fallback_parts if part)
    return state, district, court_fallback_query or None


def _api_key_for_provider(provider: str) -> str | None:
    if provider == "gemini":
        return settings.orderflow_ai_gemini_api_key
    if provider == "openai":
        return settings.orderflow_ai_openai_api_key
    if provider == "anthropic":
        return settings.orderflow_ai_anthropic_api_key
    return None


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
