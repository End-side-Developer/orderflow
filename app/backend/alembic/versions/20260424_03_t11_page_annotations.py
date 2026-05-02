"""T11 page annotations

Revision ID: 20260424_03
Revises: 20260424_02
Create Date: 2026-04-24 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260424_03"
down_revision = "20260424_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "page_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("annotation_type", sa.String(length=32), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("tooltip_text", sa.Text(), nullable=True),
        sa.Column("ai_generated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
            "annotation_type IN ('highlight', 'note', 'obligation')",
            name="ck_page_annotations_type",
        ),
    )
    op.create_index("ix_page_annotations_document_id", "page_annotations", ["document_id"], unique=False)
    op.create_index("ix_page_annotations_page_number", "page_annotations", ["page_number"], unique=False)
    op.create_index("ix_page_annotations_type", "page_annotations", ["annotation_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_page_annotations_type", table_name="page_annotations")
    op.drop_index("ix_page_annotations_page_number", table_name="page_annotations")
    op.drop_index("ix_page_annotations_document_id", table_name="page_annotations")
    op.drop_table("page_annotations")
