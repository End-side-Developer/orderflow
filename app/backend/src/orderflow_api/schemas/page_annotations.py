"""
Schema definitions for page annotations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

AnnotationType = Literal["highlight", "note", "obligation"]


class PageAnnotationRecord(BaseModel):
    """Complete annotation record for a page."""

    id: UUID
    document_id: UUID
    page_number: int
    annotation_type: AnnotationType
    text_content: str | None = None
    bbox: dict | None = None  # {x, y, width, height}
    color: str | None = None
    tooltip_text: str | None = None
    ai_generated: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PageAnnotationsListData(BaseModel):
    """Container for a list of page annotations."""

    document_id: UUID
    total_annotations: int
    items: list[PageAnnotationRecord]


class PageAnnotationsEnvelope(BaseModel):
    """Standard API response envelope for page annotations."""

    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: PageAnnotationsListData


class BboxSchema(BaseModel):
    """Bounding box schema."""
    x: float
    y: float
    width: float
    height: float


class AnnotationCoordinateUpdate(BaseModel):
    """Request to update annotation coordinates."""
    annotation_id: UUID
    bbox: BboxSchema


class AnnotationCoordinatesUpdateRequest(BaseModel):
    """Request body for updating multiple annotation coordinates."""
    updates: list[AnnotationCoordinateUpdate]


class AnnotationCoordinatesUpdateData(BaseModel):
    """Response data for coordinate updates."""
    updated_count: int


class AnnotationCoordinatesUpdateEnvelope(BaseModel):
    """Response envelope for coordinate updates."""
    ok: Literal[True] = True
    message: str = "ok"
    request_id: str | None = None
    data: AnnotationCoordinatesUpdateData
