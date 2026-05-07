"""
API routes for page annotations.

Endpoints:
- GET /api/v1/annotations/{document_id} - List annotations for a document
- POST /api/v1/annotations/{document_id}/generate - Generate annotations from summaries
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.api.page_annotation_persistence import (
    create_annotation,
    list_annotations,
    delete_annotations,
    update_annotation_bbox,
)
from orderflow_api.api.document_text_box_persistence import resolve_citation_visual_refs
from orderflow_api.api.page_summary_persistence import list_page_summaries
from orderflow_api.schemas.page_annotations import (
    PageAnnotationsEnvelope,
    PageAnnotationsListData,
    AnnotationCoordinatesUpdateRequest,
    AnnotationCoordinatesUpdateEnvelope,
    AnnotationCoordinatesUpdateData,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["page_annotations"])


@router.get("/annotations/{document_id}", response_model=PageAnnotationsEnvelope)
async def list_annotations_route(
    document_id: UUID,
    page_number: int | None = Query(default=None),
    request: Request = None,
    _user=Depends(require_permission(Permission.CASE_READ)),
) -> PageAnnotationsEnvelope:
    """
    GET /api/v1/annotations/{document_id}

    List all annotations for a document, optionally filtered by page number.

    Returns:
        PageAnnotationsEnvelope with list of annotations
    """
    request_id = getattr(request.state, "request_id", None) if request else None

    annotations = _hydrate_annotation_visual_refs(list_annotations(document_id, page_number))
    return PageAnnotationsEnvelope(
        request_id=request_id,
        data=PageAnnotationsListData(
            document_id=document_id,
            total_annotations=len(annotations),
            items=annotations,
        )
    )


@router.post("/annotations/{document_id}/generate", response_model=PageAnnotationsEnvelope)
async def generate_annotations_route(
    document_id: UUID,
    request: Request = None,
    _user=Depends(require_permission(Permission.EXTRACTION_RUN)),
) -> PageAnnotationsEnvelope:
    """
    POST /api/v1/annotations/{document_id}/generate

    Generate annotations from page summaries using deterministic extraction.
    Maps highlights from summaries to annotation records.

    Returns:
        PageAnnotationsEnvelope with generated annotations
    """
    request_id = getattr(request.state, "request_id", None) if request else None

    # Delete existing annotations for this document
    delete_annotations(document_id)

    # Get page summaries
    summaries = list_page_summaries(document_id)
    if not summaries:
        raise HTTPException(
            status_code=404,
            detail="No summaries found for this document. Generate summaries first."
        )

    # Generate annotations from summaries
    for summary in summaries:
        # Create highlight annotations from important_highlights
        for idx, highlight in enumerate(summary.important_highlights):
            # Handle both dict and Pydantic model formats
            if isinstance(highlight, dict):
                significance = highlight.get("significance", "contextual")
                text = highlight.get("text", "")
                relevance = highlight.get("relevance")
            else:
                significance = getattr(highlight, "significance", "contextual")
                text = getattr(highlight, "text", "")
                relevance = getattr(highlight, "relevance", None)
            
            color = "red" if significance == "critical" else "orange"
            if significance == "contextual":
                color = "yellow"

            create_annotation(
                document_id=document_id,
                page_number=summary.page_number,
                annotation_type="highlight",
                text_content=text,
                color=color,
                tooltip_text=relevance,
                ai_generated=False,
            )

        # Create obligation annotations
        for obligation_id in summary.obligation_ids:
            create_annotation(
                document_id=document_id,
                page_number=summary.page_number,
                annotation_type="obligation",
                text_content=f"Obligation: {obligation_id}",
                color="blue",
                tooltip_text="Click to view obligation details",
                ai_generated=False,
            )

    # Return the newly generated annotations
    annotations = _hydrate_annotation_visual_refs(list_annotations(document_id))
    return PageAnnotationsEnvelope(
        request_id=request_id,
        data=PageAnnotationsListData(
            document_id=document_id,
            total_annotations=len(annotations),
            items=annotations,
        )
    )


@router.post("/annotations/{document_id}/coordinates", response_model=AnnotationCoordinatesUpdateEnvelope)
async def update_annotation_coordinates_route(
    document_id: UUID,
    request_data: AnnotationCoordinatesUpdateRequest,
    request: Request = None,
    _user=Depends(require_permission(Permission.EXTRACTION_RUN)),
) -> AnnotationCoordinatesUpdateEnvelope:
    """
    POST /api/v1/annotations/{document_id}/coordinates

    Update bounding box coordinates for annotations based on PDF text extraction.

    Returns:
        AnnotationCoordinatesUpdateEnvelope with update count
    """
    request_id = getattr(request.state, "request_id", None) if request else None

    updated_count = 0
    for update in request_data.updates:
        success = update_annotation_bbox(
            annotation_id=update.annotation_id,
            bbox={
                "x": update.bbox.x,
                "y": update.bbox.y,
                "width": update.bbox.width,
                "height": update.bbox.height,
            }
        )
        if success:
            updated_count += 1

    return AnnotationCoordinatesUpdateEnvelope(
        request_id=request_id,
        data=AnnotationCoordinatesUpdateData(updated_count=updated_count),
    )


def _hydrate_annotation_visual_refs(annotations: list[dict]) -> list[dict]:
    hydrated: list[dict] = []
    for annotation in annotations:
        visual_refs = []
        text = annotation.get("text_content")
        page_number = annotation.get("page_number")
        document_id = annotation.get("document_id")
        if isinstance(text, str) and isinstance(page_number, int):
            try:
                visual_refs = [
                    ref.model_dump(mode="json")
                    for ref in resolve_citation_visual_refs(
                        document_id=document_id,
                        page_number=page_number,
                        span_start=None,
                        span_end=None,
                        clause_text=text,
                        max_refs=8,
                    )
                ]
            except Exception:
                visual_refs = []
        boxes = [ref["bbox"] for ref in visual_refs if isinstance(ref, dict) and "bbox" in ref]
        hydrated.append({**annotation, "visual_refs": visual_refs, "boxes": boxes})
    return hydrated
