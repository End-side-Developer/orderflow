from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from orderflow_api.core.db import get_engine

PAGE_ANNOTATIONS_TABLE = sa.Table(
    "page_annotations",
    sa.MetaData(),
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
    sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("page_number", sa.Integer(), nullable=False),
    sa.Column("annotation_type", sa.String(length=32), nullable=False),
    sa.Column("text_content", sa.Text(), nullable=True),
    sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("color", sa.String(length=32), nullable=True),
    sa.Column("tooltip_text", sa.Text(), nullable=True),
    sa.Column("ai_generated", sa.Boolean(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


def create_annotation(
    document_id: UUID,
    page_number: int,
    annotation_type: str,
    text_content: str | None = None,
    bbox: dict | None = None,
    color: str | None = None,
    tooltip_text: str | None = None,
    ai_generated: bool = False,
) -> dict:
    annotation_id = uuid4()
    now = datetime.now(UTC)

    values = {
        "id": annotation_id,
        "document_id": document_id,
        "page_number": page_number,
        "annotation_type": annotation_type,
        "text_content": text_content,
        "bbox": bbox,
        "color": color,
        "tooltip_text": tooltip_text,
        "ai_generated": ai_generated,
        "created_at": now,
        "updated_at": now,
    }

    with get_engine().begin() as connection:
        connection.execute(sa.insert(PAGE_ANNOTATIONS_TABLE).values(**values))

    return values


def list_annotations(document_id: UUID, page_number: int | None = None) -> list[dict]:
    statement = sa.select(PAGE_ANNOTATIONS_TABLE).where(
        PAGE_ANNOTATIONS_TABLE.c.document_id == document_id
    )
    
    if page_number is not None:
        statement = statement.where(PAGE_ANNOTATIONS_TABLE.c.page_number == page_number)
    
    statement = statement.order_by(PAGE_ANNOTATIONS_TABLE.c.page_number)
    
    with get_engine().connect() as connection:
        rows = connection.execute(statement).mappings().fetchall()

    return [
        {
            "id": row["id"],
            "document_id": row["document_id"],
            "page_number": row["page_number"],
            "annotation_type": row["annotation_type"],
            "text_content": row["text_content"],
            "bbox": row["bbox"],
            "color": row["color"],
            "tooltip_text": row["tooltip_text"],
            "ai_generated": row["ai_generated"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def delete_annotations(document_id: UUID) -> int:
    statement = sa.delete(PAGE_ANNOTATIONS_TABLE).where(
        PAGE_ANNOTATIONS_TABLE.c.document_id == document_id
    )
    with get_engine().begin() as connection:
        result = connection.execute(statement)
    return result.rowcount


def update_annotation_bbox(annotation_id: UUID, bbox: dict) -> bool:
    now = datetime.now(UTC)
    statement = (
        sa.update(PAGE_ANNOTATIONS_TABLE)
        .where(PAGE_ANNOTATIONS_TABLE.c.id == annotation_id)
        .values(bbox=bbox, updated_at=now)
    )
    with get_engine().begin() as connection:
        result = connection.execute(statement)
    return result.rowcount > 0
