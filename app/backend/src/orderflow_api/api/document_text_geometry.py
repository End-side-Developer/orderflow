from __future__ import annotations

from io import BytesIO
import re
from typing import Any
from uuid import UUID, uuid4

from orderflow_api.api.extraction_engine import ParsedClause
from orderflow_api.schemas.visual_evidence import DocumentTextBoxRecord


def build_synthetic_clause_boxes(
    *,
    document_id: UUID,
    clauses: list[ParsedClause],
) -> list[DocumentTextBoxRecord]:
    """Create coarse page-relative boxes when no PDF/OCR geometry is available.

    These boxes are intentionally marked `synthetic`; they preserve the
    multi-line visual-reference contract without claiming pixel-perfect OCR.
    """

    grouped: dict[int, list[ParsedClause]] = {}
    for clause in clauses:
        page_number = clause.page_number or 1
        grouped.setdefault(page_number, []).append(clause)

    records: list[DocumentTextBoxRecord] = []
    for page_number, page_clauses in grouped.items():
        line_height = 0.026
        top = 0.08
        for index, clause in enumerate(page_clauses):
            row_top = min(0.94, top + (index * (line_height + 0.012)))
            records.append(
                DocumentTextBoxRecord(
                    id=uuid4(),
                    document_id=document_id,
                    page_number=page_number,
                    source="synthetic",
                    granularity="clause",
                    text=clause.text[:500],
                    normalized_text=" ".join(clause.normalized_text.split()),
                    text_start=clause.span_start,
                    text_end=clause.span_end,
                    bbox={
                        "left": 0.08,
                        "top": row_top,
                        "width": 0.84,
                        "height": line_height,
                    },
                    polygon=None,
                    confidence=min(0.5, clause.confidence),
                    engine="orderflow-synthetic-clause-layout",
                    engine_version="1",
                    page_width=1.0,
                    page_height=1.0,
                    coordinate_system="page_fraction_top_left",
                    created_at=_now_placeholder(),
                )
            )
    return records


def build_native_pdf_text_boxes(
    *,
    document_id: UUID,
    payload: bytes,
) -> list[DocumentTextBoxRecord]:
    """Best-effort native PDF text boxes via pypdf visitor callbacks."""

    try:
        from pypdf import PdfReader
    except Exception:
        return []

    try:
        reader = PdfReader(BytesIO(payload))
    except Exception:
        return []

    records: list[DocumentTextBoxRecord] = []
    global_offset = 0
    for page_index, page in enumerate(reader.pages, start=1):
        try:
            media_box = page.mediabox
            page_width = float(media_box.width) or 1.0
            page_height = float(media_box.height) or 1.0
        except Exception:
            page_width = 1.0
            page_height = 1.0

        page_cursor = global_offset

        def visitor_text(
            text: str,
            cm: list[float],
            tm: list[float],
            font_dict: dict[str, Any] | None,
            font_size: float,
        ) -> None:
            nonlocal page_cursor
            cleaned = _clean_text(text)
            if not cleaned:
                return
            x = _safe_float(tm[4] if len(tm) > 4 else 0.0)
            y = _safe_float(tm[5] if len(tm) > 5 else 0.0)
            size = max(1.0, _safe_float(font_size, fallback=10.0))
            width = min(page_width, max(size, len(cleaned) * size * 0.48))
            height = min(page_height, size * 1.25)
            top = max(0.0, page_height - y - height)
            start = page_cursor
            end = page_cursor + len(cleaned)
            page_cursor = end + 1
            records.append(
                DocumentTextBoxRecord(
                    id=uuid4(),
                    document_id=document_id,
                    page_number=page_index,
                    source="native_pdf",
                    granularity="line",
                    text=cleaned,
                    normalized_text=" ".join(cleaned.split()),
                    text_start=start,
                    text_end=end,
                    bbox={
                        "left": _fraction(x, page_width),
                        "top": _fraction(top, page_height),
                        "width": _fraction(width, page_width),
                        "height": _fraction(height, page_height),
                    },
                    polygon=None,
                    confidence=0.72,
                    engine="pypdf-visitor-text",
                    engine_version=None,
                    page_width=page_width,
                    page_height=page_height,
                    coordinate_system="page_fraction_top_left",
                    created_at=_now_placeholder(),
                )
            )

        try:
            extracted = page.extract_text(visitor_text=visitor_text) or ""
        except Exception:
            extracted = ""
        global_offset += len(extracted) + 1

    return records


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _fraction(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return round(min(1.0, max(0.0, value / total)), 6)


def _safe_float(value: Any, *, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _now_placeholder():
    from datetime import UTC, datetime

    return datetime.now(UTC)
