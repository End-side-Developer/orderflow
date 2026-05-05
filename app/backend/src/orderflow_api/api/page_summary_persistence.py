from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from orderflow_api.core.db import get_engine
from orderflow_api.schemas.page_summaries import ExtractedPlace, PageSummaryRecord

MAX_PAGE_SUMMARY_SOURCE_EXCERPT_CHARS = 800
ALLOWED_AI_TOKEN_USAGE_KEYS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "cached_tokens",
        "reasoning_tokens",
    }
)

PAGE_SUMMARIES_TABLE = sa.Table(
    "page_summaries",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("page_number", sa.Integer(), nullable=False),
    sa.Column("page_text", sa.Text(), nullable=True),
    sa.Column("summary", sa.Text(), nullable=True),
    sa.Column("key_points", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("important_highlights", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("dates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("directions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("departments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("context_links", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("obligation_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
    sa.Column("extracted_places", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
    sa.Column("extraction_mode", sa.String(length=32), nullable=False),
    sa.Column("ai_model", sa.String(length=100), nullable=True),
    sa.Column("ai_provider", sa.String(length=50), nullable=True),
    sa.Column("content_hash", sa.String(length=64), nullable=True),
    sa.Column("prompt_version", sa.String(length=80), nullable=True),
    sa.Column("source_excerpt", sa.Text(), nullable=True),
    sa.Column("ai_token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


def create_page_summary(
    document_id: UUID,
    page_number: int,
    page_text: str | None = None,
    summary: str | None = None,
    key_points: list[str] | None = None,
    important_highlights: list[dict] | None = None,
    entities: list[dict] | None = None,
    dates: list[dict] | None = None,
    directions: list[dict] | None = None,
    departments: list[dict] | None = None,
    context_links: list[dict] | None = None,
    obligation_ids: list[UUID] | None = None,
    extracted_places: list[ExtractedPlace | dict[str, Any]] | None = None,
    confidence: float | None = None,
    extraction_mode: str = "deterministic",
    ai_model: str | None = None,
    ai_provider: str | None = None,
    content_hash: str | None = None,
    prompt_version: str | None = None,
    source_excerpt: str | None = None,
    ai_token_usage: dict[str, Any] | None = None,
) -> PageSummaryRecord:
    summary_id = uuid4()
    now = datetime.now(UTC)
    stored_places = None if extracted_places is None else _serialize_places(extracted_places)

    values = {
        "id": summary_id,
        "document_id": document_id,
        "page_number": page_number,
        "page_text": page_text,
        "summary": summary,
        "key_points": key_points,
        "important_highlights": important_highlights,
        "entities": entities,
        "dates": dates,
        "directions": directions,
        "departments": departments,
        "context_links": context_links,
        "obligation_ids": obligation_ids,
        "extracted_places": stored_places,
        "confidence": confidence,
        "extraction_mode": extraction_mode,
        "ai_model": ai_model,
        "ai_provider": ai_provider,
        "content_hash": content_hash,
        "prompt_version": prompt_version,
        "source_excerpt": _sanitize_source_excerpt(source_excerpt),
        "ai_token_usage": _sanitize_ai_token_usage(ai_token_usage),
        "generated_at": now,
        "created_at": now,
        "updated_at": now,
    }

    with get_engine().begin() as connection:
        connection.execute(sa.insert(PAGE_SUMMARIES_TABLE).values(**values))

    return PageSummaryRecord(
        **{
            **values,
            "entities": entities or [],
            "dates": dates or [],
            "directions": directions or [],
            "departments": departments or [],
            "extracted_places": stored_places or [],
        }
    )


def upsert_page_summary(
    document_id: UUID,
    page_number: int,
    page_text: str | None = None,
    summary: str | None = None,
    key_points: list[str] | None = None,
    important_highlights: list[dict] | None = None,
    entities: list[dict] | None = None,
    dates: list[dict] | None = None,
    directions: list[dict] | None = None,
    departments: list[dict] | None = None,
    context_links: list[dict] | None = None,
    obligation_ids: list[UUID] | None = None,
    extracted_places: list[ExtractedPlace | dict[str, Any]] | None = None,
    confidence: float | None = None,
    extraction_mode: str = "deterministic",
    ai_model: str | None = None,
    ai_provider: str | None = None,
    content_hash: str | None = None,
    prompt_version: str | None = None,
    source_excerpt: str | None = None,
    ai_token_usage: dict[str, Any] | None = None,
) -> PageSummaryRecord:
    summary_id = uuid4()
    now = datetime.now(UTC)
    stored_places = None if extracted_places is None else _serialize_places(extracted_places)
    values = {
        "id": summary_id,
        "document_id": document_id,
        "page_number": page_number,
        "page_text": page_text,
        "summary": summary,
        "key_points": key_points,
        "important_highlights": important_highlights,
        "entities": entities,
        "dates": dates,
        "directions": directions,
        "departments": departments,
        "context_links": context_links,
        "obligation_ids": obligation_ids,
        "extracted_places": stored_places,
        "confidence": confidence,
        "extraction_mode": extraction_mode,
        "ai_model": ai_model,
        "ai_provider": ai_provider,
        "content_hash": content_hash,
        "prompt_version": prompt_version,
        "source_excerpt": _sanitize_source_excerpt(source_excerpt),
        "ai_token_usage": _sanitize_ai_token_usage(ai_token_usage),
        "generated_at": now,
        "created_at": now,
        "updated_at": now,
    }

    statement = postgresql.insert(PAGE_SUMMARIES_TABLE).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[
            PAGE_SUMMARIES_TABLE.c.document_id,
            PAGE_SUMMARIES_TABLE.c.page_number,
        ],
        set_={
            "page_text": statement.excluded.page_text,
            "summary": statement.excluded.summary,
            "key_points": statement.excluded.key_points,
            "important_highlights": statement.excluded.important_highlights,
            "entities": statement.excluded.entities,
            "dates": statement.excluded.dates,
            "directions": statement.excluded.directions,
            "departments": statement.excluded.departments,
            "context_links": statement.excluded.context_links,
            "obligation_ids": statement.excluded.obligation_ids,
            "extracted_places": statement.excluded.extracted_places,
            "confidence": statement.excluded.confidence,
            "extraction_mode": statement.excluded.extraction_mode,
            "ai_model": statement.excluded.ai_model,
            "ai_provider": statement.excluded.ai_provider,
            "content_hash": statement.excluded.content_hash,
            "prompt_version": statement.excluded.prompt_version,
            "source_excerpt": statement.excluded.source_excerpt,
            "ai_token_usage": statement.excluded.ai_token_usage,
            "generated_at": statement.excluded.generated_at,
            "updated_at": now,
        },
    )

    with get_engine().begin() as connection:
        connection.execute(statement)

    record = get_page_summary_by_document_page(document_id, page_number)
    if record is None:
        raise ValueError(f"Page summary upsert failed: {document_id} page {page_number}")
    return record


def get_page_summary_by_document_page(
    document_id: UUID,
    page_number: int,
) -> PageSummaryRecord | None:
    statement = (
        sa.select(PAGE_SUMMARIES_TABLE)
        .where(PAGE_SUMMARIES_TABLE.c.document_id == document_id)
        .where(PAGE_SUMMARIES_TABLE.c.page_number == page_number)
        .limit(1)
    )
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()

    if row is None:
        return None
    return _to_page_summary(row)


def get_cached_page_summary(
    document_id: UUID,
    page_number: int,
    *,
    content_hash: str,
    prompt_version: str,
    ai_model: str | None = None,
    ai_provider: str | None = None,
) -> PageSummaryRecord | None:
    """
    Retrieves a cached AI summary for a specific page if it exactly matches the extraction context.

    Cache-hit rules for page extraction:
    1. `document_id` and `page_number` must match exactly (locates the correct logical page).
    2. `content_hash` must match exactly. This hash normalizes whitespace but ensures the
       underlying OCR/PDF text has not fundamentally changed since the summary was created.
    3. `prompt_version` must match exactly. If the system prompt instructions change, the
       old summary is considered invalid and a cache miss occurs.
    4. Optional model metadata (`ai_model`, `ai_provider`): If specified, the cached summary
       must have been produced by the same underlying model constraints. If not specified,
       any model's output for the matching prompt+content is accepted.

    Returns the PageSummaryRecord on a cache hit, or None when new extraction is required.
    """
    filters = [
        PAGE_SUMMARIES_TABLE.c.document_id == document_id,
        PAGE_SUMMARIES_TABLE.c.page_number == page_number,
        PAGE_SUMMARIES_TABLE.c.content_hash == content_hash,
        PAGE_SUMMARIES_TABLE.c.prompt_version == prompt_version,
    ]
    if ai_model is not None:
        filters.append(PAGE_SUMMARIES_TABLE.c.ai_model == ai_model)
    if ai_provider is not None:
        filters.append(PAGE_SUMMARIES_TABLE.c.ai_provider == ai_provider)

    statement = (
        sa.select(PAGE_SUMMARIES_TABLE)
        .where(*filters)
        .order_by(PAGE_SUMMARIES_TABLE.c.updated_at.desc())
        .limit(1)
    )
    with get_engine().connect() as connection:
        row = connection.execute(statement).mappings().first()

    if row is None:
        return None
    return _to_page_summary(row)


def list_page_summaries(document_id: UUID) -> list[PageSummaryRecord]:
    statement = (
        sa.select(PAGE_SUMMARIES_TABLE)
        .where(PAGE_SUMMARIES_TABLE.c.document_id == document_id)
        .order_by(PAGE_SUMMARIES_TABLE.c.page_number)
    )
    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().fetchall()

    return [_to_page_summary(row) for row in rows]


def list_page_summaries_missing_extracted_places(
    limit: int = 100,
    exclude_ids: set[UUID] | None = None,
) -> list[PageSummaryRecord]:
    """Return summaries whose map extraction has never been processed."""
    safe_limit = max(1, limit)
    filters = [PAGE_SUMMARIES_TABLE.c.extracted_places.is_(None)]
    if exclude_ids:
        filters.append(PAGE_SUMMARIES_TABLE.c.id.notin_(list(exclude_ids)))

    statement = (
        sa.select(PAGE_SUMMARIES_TABLE)
        .where(*filters)
        .order_by(PAGE_SUMMARIES_TABLE.c.document_id, PAGE_SUMMARIES_TABLE.c.page_number)
        .limit(safe_limit)
    )
    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().fetchall()

    return [_to_page_summary(row, extracted_places=[]) for row in rows]


def update_page_summary_places(
    summary_id: UUID,
    extracted_places: list[ExtractedPlace | dict[str, Any]],
) -> None:
    statement = (
        sa.update(PAGE_SUMMARIES_TABLE)
        .where(PAGE_SUMMARIES_TABLE.c.id == summary_id)
        .values(
            extracted_places=_serialize_places(extracted_places),
            updated_at=datetime.now(UTC),
        )
    )
    with get_engine().begin() as connection:
        result = connection.execute(statement)
    if result.rowcount == 0:
        raise ValueError(f"Page summary not found: {summary_id}")


def update_document_page_places(
    document_id: UUID,
    page_number: int,
    extracted_places: list[ExtractedPlace | dict[str, Any]],
) -> None:
    statement = (
        sa.update(PAGE_SUMMARIES_TABLE)
        .where(PAGE_SUMMARIES_TABLE.c.document_id == document_id)
        .where(PAGE_SUMMARIES_TABLE.c.page_number == page_number)
        .values(
            extracted_places=_serialize_places(extracted_places),
            updated_at=datetime.now(UTC),
        )
    )
    with get_engine().begin() as connection:
        result = connection.execute(statement)
    if result.rowcount == 0:
        raise ValueError(f"Page summary not found: {document_id} page {page_number}")


def update_page_summary_source_metadata(
    summary_id: UUID,
    *,
    source_excerpt: str | None = None,
    ai_token_usage: dict[str, Any] | None = None,
) -> None:
    statement = (
        sa.update(PAGE_SUMMARIES_TABLE)
        .where(PAGE_SUMMARIES_TABLE.c.id == summary_id)
        .values(
            source_excerpt=_sanitize_source_excerpt(source_excerpt),
            ai_token_usage=_sanitize_ai_token_usage(ai_token_usage),
            updated_at=datetime.now(UTC),
        )
    )
    with get_engine().begin() as connection:
        result = connection.execute(statement)
    if result.rowcount == 0:
        raise ValueError(f"Page summary not found: {summary_id}")


def delete_page_summaries(document_id: UUID) -> int:
    statement = sa.delete(PAGE_SUMMARIES_TABLE).where(
        PAGE_SUMMARIES_TABLE.c.document_id == document_id
    )
    with get_engine().begin() as connection:
        result = connection.execute(statement)
    return result.rowcount


def _to_page_summary(
    row,
    *,
    extracted_places: list[dict[str, Any]] | None = None,
) -> PageSummaryRecord:
    places = extracted_places if extracted_places is not None else row["extracted_places"] or []
    return PageSummaryRecord(
        id=row["id"],
        document_id=row["document_id"],
        page_number=row["page_number"],
        page_text=row["page_text"],
        summary=row["summary"],
        key_points=row["key_points"] or [],
        important_highlights=row["important_highlights"] or [],
        entities=row["entities"] or [],
        dates=row["dates"] or [],
        directions=row["directions"] or [],
        departments=row["departments"] or [],
        context_links=row["context_links"] or [],
        obligation_ids=row["obligation_ids"] or [],
        extracted_places=places,
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        extraction_mode=row["extraction_mode"],
        ai_model=row["ai_model"],
        ai_provider=row["ai_provider"],
        content_hash=row["content_hash"],
        prompt_version=row["prompt_version"],
        source_excerpt=row["source_excerpt"],
        ai_token_usage=row["ai_token_usage"],
        generated_at=row["generated_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _sanitize_source_excerpt(source_excerpt: str | None) -> str | None:
    if source_excerpt is None:
        return None

    cleaned = " ".join(source_excerpt.split())
    if not cleaned:
        return None

    if len(cleaned) <= MAX_PAGE_SUMMARY_SOURCE_EXCERPT_CHARS:
        return cleaned

    suffix = " [truncated]"
    return cleaned[: MAX_PAGE_SUMMARY_SOURCE_EXCERPT_CHARS - len(suffix)].rstrip() + suffix


def _sanitize_ai_token_usage(
    ai_token_usage: dict[str, Any] | None
) -> dict[str, int | float] | None:
    if not ai_token_usage:
        return None

    sanitized: dict[str, int | float] = {}
    for key, value in ai_token_usage.items():
        if key not in ALLOWED_AI_TOKEN_USAGE_KEYS:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value < 0:
            continue
        sanitized[key] = value

    return sanitized or None


def _serialize_places(
    extracted_places: list[ExtractedPlace | dict[str, Any]],
) -> list[dict[str, Any]]:
    if not extracted_places:
        return []

    serialized: list[dict[str, Any]] = []
    for place in extracted_places:
        if isinstance(place, ExtractedPlace):
            serialized.append(place.model_dump(mode="json"))
        else:
            serialized.append(ExtractedPlace(**place).model_dump(mode="json"))
    return serialized
