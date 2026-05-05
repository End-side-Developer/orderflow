"""Add rich cached page extraction fields.

Revision ID: 20260505_01_page_summary_rich_extraction
Revises: 20260504_01_t12_intake_flow
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260505_01_page_summary_rich_extraction"
down_revision = "20260504_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "page_summaries",
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "page_summaries",
        sa.Column("dates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "page_summaries",
        sa.Column("directions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "page_summaries",
        sa.Column("departments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("page_summaries", "departments")
    op.drop_column("page_summaries", "directions")
    op.drop_column("page_summaries", "dates")
    op.drop_column("page_summaries", "entities")
