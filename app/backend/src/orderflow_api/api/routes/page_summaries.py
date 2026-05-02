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

from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.api.page_summary_persistence import (
    create_page_summary,
    list_page_summaries,
    delete_page_summaries,
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
        )
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
            detail="No clauses found for this document. Upload and process the document first."
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
        summary = ". ".join(sentences[:2]) if sentences else f"Page {page_num} content extracted from document."
        
        key_points = [c.text[:200] for c in page_clauses[:5]]
        
        important_highlights = [
            {
                "text": c.text[:150],
                "significance": "important" if i == 0 else "contextual",
                "relevance": "Extracted from judgment text"
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
        )
    )
