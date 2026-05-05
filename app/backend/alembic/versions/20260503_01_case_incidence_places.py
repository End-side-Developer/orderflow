"""Add case incidence places and geocode cache.

Revision ID: 20260503_01
Revises: 20260502_03
Create Date: 2026-05-03 12:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260503_01"
down_revision = "20260502_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "page_summaries",
        sa.Column(
            "extracted_places",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.create_table(
        "geocode_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("state_hint", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lng", sa.Numeric(10, 7), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("provider_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("negative_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "normalized_name",
            "state_hint",
            name="uq_geocode_cache_normalized_state",
        ),
    )
    op.create_index(
        "ix_geocode_cache_normalized_name",
        "geocode_cache",
        ["normalized_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_geocode_cache_normalized_name", table_name="geocode_cache")
    op.drop_table("geocode_cache")
    op.drop_column("page_summaries", "extracted_places")

