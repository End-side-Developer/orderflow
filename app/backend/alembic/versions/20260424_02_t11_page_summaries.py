"""T11 page summaries

Revision ID: 20260424_02
Revises: 20260424_01
Create Date: 2026-04-24 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260424_02"
down_revision = "20260424_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "page_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("page_text", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_points", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("important_highlights", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("context_links", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("obligation_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("extraction_mode", sa.String(length=32), nullable=False, server_default=sa.text("'ai'")),
        sa.Column("ai_model", sa.String(length=100), nullable=True),
        sa.Column("ai_provider", sa.String(length=50), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "extraction_mode IN ('ai', 'deterministic')",
            name="ck_page_summaries_extraction_mode",
        ),
        sa.UniqueConstraint("document_id", "page_number", name="uq_page_summaries_document_page"),
    )
    op.create_index("ix_page_summaries_document_id", "page_summaries", ["document_id"], unique=False)
    op.create_index("ix_page_summaries_page_number", "page_summaries", ["page_number"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_page_summaries_page_number", table_name="page_summaries")
    op.drop_index("ix_page_summaries_document_id", table_name="page_summaries")
    op.drop_table("page_summaries")
