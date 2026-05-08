"""Add rich cached page extraction fields.

Revision ID: 20260505_01_rich_page
Revises: 20260504_01
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Shortened from 20260505_01_page_summary_rich_extraction (40 chars) so the
# value fits the default alembic_version.version_num VARCHAR(32) column on
# Azure Postgres flexible server. Behaviour is unchanged.
revision = "20260505_01_rich_page"
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
