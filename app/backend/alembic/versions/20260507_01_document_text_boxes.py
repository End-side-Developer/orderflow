"""Add durable document text boxes.

Revision ID: 20260507_01_text_boxes
Revises: 20260506_01_ocr_metadata
Create Date: 2026-05-07 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260507_01_text_boxes"
down_revision = "20260506_01_ocr_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_text_boxes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.Column(
            "coordinate_system",
            sa.String(length=64),
            nullable=False,
            server_default="page_fraction_top_left",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("page_number >= 1", name="ck_document_text_boxes_page_number"),
        sa.CheckConstraint(
            "source IN ('native_pdf', 'ocr', 'synthetic')",
            name="ck_document_text_boxes_source",
        ),
        sa.CheckConstraint(
            "granularity IN ('char', 'word', 'line', 'clause')",
            name="ck_document_text_boxes_granularity",
        ),
    )
    op.create_index(
        "ix_document_text_boxes_document_page",
        "document_text_boxes",
        ["document_id", "page_number"],
        unique=False,
    )
    op.create_index(
        "ix_document_text_boxes_span",
        "document_text_boxes",
        ["document_id", "text_start", "text_end"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_text_boxes_span", table_name="document_text_boxes")
    op.drop_index("ix_document_text_boxes_document_page", table_name="document_text_boxes")
    op.drop_table("document_text_boxes")
