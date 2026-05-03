"""Persist cached case-flow graph on documents.

Revision ID: 20260502_03
Revises: 20260502_02
Create Date: 2026-05-03 01:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260502_03"
down_revision = "20260502_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "case_flow_graph",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "case_flow_graph")
