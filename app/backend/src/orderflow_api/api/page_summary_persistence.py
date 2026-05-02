from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from orderflow_api.core.db import get_engine
from orderflow_api.schemas.page_summaries import PageSummaryRecord

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
    sa.Column("context_links", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("obligation_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
    sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
    sa.Column("extraction_mode", sa.String(length=32), nullable=False),
    sa.Column("ai_model", sa.String(length=100), nullable=True),
    sa.Column("ai_provider", sa.String(length=50), nullable=True),
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
    context_links: list[dict] | None = None,
    obligation_ids: list[UUID] | None = None,
    confidence: float | None = None,
    extraction_mode: str = "deterministic",
    ai_model: str | None = None,
    ai_provider: str | None = None,
) -> PageSummaryRecord:
    summary_id = uuid4()
    now = datetime.now(UTC)

    values = {
        "id": summary_id,
        "document_id": document_id,
        "page_number": page_number,
        "page_text": page_text,
        "summary": summary,
        "key_points": key_points,
        "important_highlights": important_highlights,
        "context_links": context_links,
        "obligation_ids": obligation_ids,
        "confidence": confidence,
        "extraction_mode": extraction_mode,
        "ai_model": ai_model,
        "ai_provider": ai_provider,
        "generated_at": now,
        "created_at": now,
        "updated_at": now,
    }

    with get_engine().begin() as connection:
        connection.execute(sa.insert(PAGE_SUMMARIES_TABLE).values(**values))

    return PageSummaryRecord(**values)


def list_page_summaries(document_id: UUID) -> list[PageSummaryRecord]:
    statement = (
        sa.select(PAGE_SUMMARIES_TABLE)
        .where(PAGE_SUMMARIES_TABLE.c.document_id == document_id)
        .order_by(PAGE_SUMMARIES_TABLE.c.page_number)
    )
    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().fetchall()

    return [
        PageSummaryRecord(
            id=row["id"],
            document_id=row["document_id"],
            page_number=row["page_number"],
            page_text=row["page_text"],
            summary=row["summary"],
            key_points=row["key_points"] or [],
            important_highlights=row["important_highlights"] or [],
            context_links=row["context_links"] or [],
            obligation_ids=row["obligation_ids"] or [],
            confidence=float(row["confidence"]) if row["confidence"] is not None else None,
            extraction_mode=row["extraction_mode"],
            ai_model=row["ai_model"],
            ai_provider=row["ai_provider"],
            generated_at=row["generated_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def delete_page_summaries(document_id: UUID) -> int:
    statement = sa.delete(PAGE_SUMMARIES_TABLE).where(
        PAGE_SUMMARIES_TABLE.c.document_id == document_id
    )
    with get_engine().begin() as connection:
        result = connection.execute(statement)
    return result.rowcount
