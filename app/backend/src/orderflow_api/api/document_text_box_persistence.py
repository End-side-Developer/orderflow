from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import re
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import RowMapping

from orderflow_api.core.db import get_engine
from orderflow_api.schemas.visual_evidence import CitationVisualRef, DocumentTextBoxRecord

DOCUMENT_TEXT_BOXES_TABLE = sa.Table(
    "document_text_boxes",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("page_number", sa.Integer(), nullable=False),
    sa.Column("source", sa.String(length=32), nullable=False),
    sa.Column("granularity", sa.String(length=32), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("normalized_text", sa.Text(), nullable=True),
    sa.Column("text_start", sa.Integer(), nullable=True),
    sa.Column("text_end", sa.Integer(), nullable=True),
    sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("polygon", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
    sa.Column("engine", sa.String(length=64), nullable=True),
    sa.Column("engine_version", sa.String(length=120), nullable=True),
    sa.Column("page_width", sa.Numeric(12, 4), nullable=True),
    sa.Column("page_height", sa.Numeric(12, 4), nullable=True),
    sa.Column("coordinate_system", sa.String(length=64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

_WORD_PATTERN = re.compile(r"\w+", re.UNICODE)


def replace_document_text_boxes(
    document_id: UUID,
    boxes: list[DocumentTextBoxRecord | dict[str, Any]],
) -> list[DocumentTextBoxRecord]:
    now = datetime.now(UTC)
    rows = [_row_from_box(document_id, box, now) for box in boxes]

    with get_engine().begin() as connection:
        connection.execute(
            sa.delete(DOCUMENT_TEXT_BOXES_TABLE).where(
                DOCUMENT_TEXT_BOXES_TABLE.c.document_id == document_id
            )
        )
        for chunk in _chunk_rows(rows, 500):
            if chunk:
                connection.execute(sa.insert(DOCUMENT_TEXT_BOXES_TABLE).values(chunk))

    return list_document_text_boxes(document_id)


def list_document_text_boxes(
    document_id: UUID,
    *,
    page_number: int | None = None,
) -> list[DocumentTextBoxRecord]:
    statement = (
        sa.select(DOCUMENT_TEXT_BOXES_TABLE)
        .where(DOCUMENT_TEXT_BOXES_TABLE.c.document_id == document_id)
        .order_by(
            DOCUMENT_TEXT_BOXES_TABLE.c.page_number.asc(),
            DOCUMENT_TEXT_BOXES_TABLE.c.text_start.asc().nulls_last(),
            DOCUMENT_TEXT_BOXES_TABLE.c.id.asc(),
        )
    )
    if page_number is not None:
        statement = statement.where(DOCUMENT_TEXT_BOXES_TABLE.c.page_number == page_number)

    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().all()

    return [_to_record(row) for row in rows]


def resolve_citation_visual_refs(
    *,
    document_id: UUID,
    page_number: int | None,
    span_start: int | None,
    span_end: int | None,
    clause_text: str | None = None,
    max_refs: int = 12,
) -> list[CitationVisualRef]:
    if page_number is None:
        return []

    boxes = list_document_text_boxes(document_id, page_number=page_number)
    if not boxes:
        return []

    matched: list[DocumentTextBoxRecord] = []
    if span_start is not None and span_end is not None and span_start < span_end:
        matched = [
            box
            for box in boxes
            if box.text_start is not None
            and box.text_end is not None
            and box.text_start < span_end
            and box.text_end > span_start
        ]

    if not matched and clause_text:
        matched = _fuzzy_match_boxes(boxes, clause_text)

    return [
        CitationVisualRef(
            page_number=box.page_number,
            bbox=box.bbox,
            text=box.text,
            confidence=box.confidence,
            source=box.source,
            granularity=box.granularity,
        )
        for box in matched[: max(max_refs, 1)]
    ]


def _fuzzy_match_boxes(
    boxes: list[DocumentTextBoxRecord],
    clause_text: str,
) -> list[DocumentTextBoxRecord]:
    clause_tokens = set(_tokens(clause_text))
    if not clause_tokens:
        return []

    scored: list[tuple[float, DocumentTextBoxRecord]] = []
    for box in boxes:
        box_tokens = set(_tokens(box.normalized_text or box.text))
        if not box_tokens:
            continue
        score = len(clause_tokens & box_tokens) / max(len(box_tokens), 1)
        if score >= 0.45:
            scored.append((score, box))

    scored.sort(
        key=lambda item: (
            item[1].text_start if item[1].text_start is not None else 10**12,
            -item[0],
        )
    )
    return [box for _, box in scored]


def _tokens(value: str) -> list[str]:
    return [match.group(0).casefold() for match in _WORD_PATTERN.finditer(value or "")]


def _row_from_box(
    document_id: UUID,
    box: DocumentTextBoxRecord | dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    payload = box.model_dump(mode="json") if isinstance(box, DocumentTextBoxRecord) else dict(box)
    bbox = _sanitize_bbox(payload.get("bbox"))
    text = _sanitize_text(payload.get("text")) or "[unreadable text box]"
    return {
        "id": payload.get("id") or uuid4(),
        "document_id": document_id,
        "page_number": max(1, int(payload.get("page_number") or 1)),
        "source": _safe_choice(payload.get("source"), {"native_pdf", "ocr", "synthetic"}, "synthetic"),
        "granularity": _safe_choice(payload.get("granularity"), {"char", "word", "line", "clause"}, "line"),
        "text": text,
        "normalized_text": _sanitize_text(payload.get("normalized_text")) or _normalize_text(text),
        "text_start": _safe_int(payload.get("text_start")),
        "text_end": _safe_int(payload.get("text_end")),
        "bbox": bbox,
        "polygon": payload.get("polygon") if isinstance(payload.get("polygon"), list) else None,
        "confidence": _safe_confidence(payload.get("confidence")),
        "engine": _sanitize_text(payload.get("engine"), max_chars=64),
        "engine_version": _sanitize_text(payload.get("engine_version"), max_chars=120),
        "page_width": _safe_positive_float(payload.get("page_width")),
        "page_height": _safe_positive_float(payload.get("page_height")),
        "coordinate_system": "page_fraction_top_left",
        "created_at": now,
    }


def _to_record(row: RowMapping) -> DocumentTextBoxRecord:
    return DocumentTextBoxRecord(
        id=row["id"],
        document_id=row["document_id"],
        page_number=row["page_number"],
        source=row["source"],
        granularity=row["granularity"],
        text=row["text"],
        normalized_text=row["normalized_text"],
        text_start=row["text_start"],
        text_end=row["text_end"],
        bbox=row["bbox"],
        polygon=row["polygon"],
        confidence=_to_float(row["confidence"]),
        engine=row["engine"],
        engine_version=row["engine_version"],
        page_width=_to_float(row["page_width"]),
        page_height=_to_float(row["page_height"]),
        coordinate_system=row["coordinate_system"],
        created_at=row["created_at"],
    )


def _sanitize_bbox(value: Any) -> dict[str, float]:
    source = value if isinstance(value, dict) else {}
    left = _clamp_fraction(source.get("left", source.get("x", 0.0)))
    top = _clamp_fraction(source.get("top", source.get("y", 0.0)))
    width = _clamp_fraction(source.get("width", 0.01))
    height = _clamp_fraction(source.get("height", 0.01))
    if left + width > 1:
        width = max(0.0, 1.0 - left)
    if top + height > 1:
        height = max(0.0, 1.0 - top)
    return {"left": left, "top": top, "width": width, "height": height}


def _clamp_fraction(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(min(1.0, max(0.0, number)), 6)


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _safe_positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _safe_confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, number))


def _safe_choice(value: Any, allowed: set[str], fallback: str) -> str:
    return value if isinstance(value, str) and value in allowed else fallback


def _sanitize_text(value: Any, *, max_chars: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = "".join(ch for ch in value if ch == "\n" or ord(ch) >= 0x20).strip()
    if not cleaned:
        return None
    return cleaned[:max_chars] if max_chars else cleaned


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (float, int)):
        return float(value)
    return None


def _chunk_rows(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]
