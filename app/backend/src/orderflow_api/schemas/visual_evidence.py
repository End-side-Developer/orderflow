from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


TextBoxSource = Literal["native_pdf", "ocr", "synthetic"]
TextBoxGranularity = Literal["char", "word", "line", "clause"]


class NormalizedBBox(BaseModel):
    """Page-relative rectangle, expressed as 0..1 fractions."""

    left: float = Field(..., ge=0.0, le=1.0)
    top: float = Field(..., ge=0.0, le=1.0)
    width: float = Field(..., ge=0.0, le=1.0)
    height: float = Field(..., ge=0.0, le=1.0)


class CitationVisualRef(BaseModel):
    page_number: int = Field(..., ge=1)
    bbox: NormalizedBBox
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: TextBoxSource
    granularity: TextBoxGranularity


class DocumentTextBoxRecord(BaseModel):
    id: UUID
    document_id: UUID
    page_number: int = Field(..., ge=1)
    source: TextBoxSource
    granularity: TextBoxGranularity
    text: str
    normalized_text: str | None = None
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, ge=0)
    bbox: NormalizedBBox
    polygon: list[dict[str, float]] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    engine: str | None = None
    engine_version: str | None = None
    page_width: float | None = Field(default=None, gt=0)
    page_height: float | None = Field(default=None, gt=0)
    coordinate_system: str = "page_fraction_top_left"
    created_at: datetime

    class Config:
        from_attributes = True
