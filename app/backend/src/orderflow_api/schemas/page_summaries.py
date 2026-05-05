"""
Schema definitions for page-by-page summaries.

A page summary captures the narrative, key points, and critical highlights
from each page of a judgment document, with AI-generated analysis.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class HighlightItem(BaseModel):
    """A critical or important extract from the page."""

    text: str = Field(..., description="Direct quote or key phrase")
    significance: Literal["critical", "important", "contextual"] = Field(
        ..., description="Importance level for execution"
    )
    relevance: str | None = Field(
        default=None,
        description="Why this extract matters for decision or obligations",
    )


class ContextLink(BaseModel):
    """Reference to another page with related content."""

    page_number: int = Field(..., ge=1, description="Page number referenced")
    reason: str = Field(..., description="Why this page is related")


PlaceType = Literal["court", "property", "incident", "address", "jurisdiction", "other"]
GeocodeSource = Literal["nominatim", "cache", "fallback_court_metadata", "none"]


class ExtractedPlace(BaseModel):
    """A place mention extracted from a judgment page and optionally geocoded."""

    id: UUID
    name: str = Field(..., description="Raw place mention from the page text")
    normalized_name: str = Field(..., description="Normalized cache/deduplication key")
    place_type: PlaceType = "other"
    state: str | None = None
    district: str | None = None
    raw_text_span: str | None = Field(
        default=None,
        description="Short source snippet for tooltip and audit context",
    )
    lat: float | None = None
    lng: float | None = None
    geocode_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    geocode_source: GeocodeSource = "none"
    source_page_number: int = Field(..., ge=1)
    mention_count: int = Field(default=1, ge=1)


class PageSummaryRecord(BaseModel):
    """Complete summary of a single page with AI analysis."""

    id: UUID
    document_id: UUID
    page_number: int = Field(..., ge=1)

    # Extracted page content
    page_text: str = Field(..., description="Full text extracted from page")

    # AI-generated analysis
    summary: str = Field(..., description="2-3 sentence concise summary preserving legal context")
    key_points: list[str] = Field(
        default_factory=list,
        description="3-5 important points from this page",
    )
    important_highlights: list[HighlightItem] = Field(
        default_factory=list,
        description="Critical/important quotes with explanations",
    )

    # Connections
    context_links: list[ContextLink] = Field(
        default_factory=list,
        description="References to related pages",
    )
    obligation_ids: list[UUID] = Field(
        default_factory=list,
        description="Obligations mentioned on this page",
    )
    extracted_places: list[ExtractedPlace] = Field(
        default_factory=list,
        description="Geographic place mentions extracted from this page",
    )

    # Metadata
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="AI extraction confidence"
    )
    extraction_mode: Literal["ai", "deterministic"] = "ai"
    ai_model: str | None = Field(
        default=None, description="Model used for extraction (e.g., gpt-4o)"
    )
    ai_provider: str | None = Field(
        default=None, description="Provider name (openai, anthropic, etc.)"
    )
    content_hash: str | None = Field(
        default=None,
        description="SHA-256 hash of the normalized page text used for cache validation",
    )
    prompt_version: str | None = Field(
        default=None,
        description="Prompt version used to generate the page-level AI result",
    )
    source_excerpt: str | None = Field(
        default=None,
        description="Short source paragraph(s) used to generate this page result",
    )
    ai_token_usage: dict[str, Any] | None = Field(
        default=None,
        description="Provider token usage metadata, when available",
    )

    generated_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PageSummariesListData(BaseModel):
    """Container for a list of page summaries."""

    document_id: UUID
    total_pages: int = Field(..., description="Total page count in document")
    summary_count: int = Field(..., description="Number of summaries generated")
    items: list[PageSummaryRecord]


class PageSummariesEnvelope(BaseModel):
    """Standard API response envelope for page summaries."""

    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: PageSummariesListData
