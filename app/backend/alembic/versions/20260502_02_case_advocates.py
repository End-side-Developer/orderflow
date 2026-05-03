"""Case-advocate linkage table.

Revision ID: 20260502_02
Revises: 20260502_01
Create Date: 2026-05-02 00:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260502_02"
down_revision = "20260502_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_advocates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "advocate_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("advocate_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False, server_default=sa.text("'counsel'")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'claimed'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "document_id",
            "advocate_user_id",
            name="uq_case_advocates_document_advocate",
        ),
        sa.CheckConstraint(
            "role IN ('counsel', 'co-counsel', 'consulting')",
            name="ck_case_advocates_role",
        ),
        sa.CheckConstraint(
            "status IN ('claimed', 'verified')",
            name="ck_case_advocates_status",
        ),
    )
    op.create_index(
        "ix_case_advocates_advocate_user_id",
        "case_advocates",
        ["advocate_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_case_advocates_document_id",
        "case_advocates",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_case_advocates_status",
        "case_advocates",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_case_advocates_status", table_name="case_advocates")
    op.drop_index("ix_case_advocates_document_id", table_name="case_advocates")
    op.drop_index("ix_case_advocates_advocate_user_id", table_name="case_advocates")
    op.drop_table("case_advocates")

