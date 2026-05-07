"""Add OCR metadata to page summaries.

Revision ID: 20260506_01_ocr_metadata
Revises: 20260505_01_rich_extract
Create Date: 2026-05-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260506_01_ocr_metadata"
down_revision = "20260505_01_rich_extract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "page_summaries",
        sa.Column(
            "text_source",
            sa.String(length=32),
            nullable=False,
            server_default="native_pdf",
        ),
    )
    op.add_column("page_summaries", sa.Column("ocr_engine", sa.String(length=64), nullable=True))
    op.add_column(
        "page_summaries",
        sa.Column("ocr_engine_version", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "page_summaries",
        sa.Column("ocr_confidence", sa.Numeric(5, 4), nullable=True),
    )
    op.add_column(
        "page_summaries",
        sa.Column("ocr_language", sa.String(length=32), nullable=True),
    )
    op.add_column("page_summaries", sa.Column("ocr_error", sa.String(length=240), nullable=True))
    op.create_check_constraint(
        "ck_page_summaries_text_source",
        "page_summaries",
        "text_source IN ('native_pdf', 'ocr', 'low_text_fallback')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_page_summaries_text_source", "page_summaries", type_="check")
    op.drop_column("page_summaries", "ocr_error")
    op.drop_column("page_summaries", "ocr_language")
    op.drop_column("page_summaries", "ocr_confidence")
    op.drop_column("page_summaries", "ocr_engine_version")
    op.drop_column("page_summaries", "ocr_engine")
    op.drop_column("page_summaries", "text_source")
