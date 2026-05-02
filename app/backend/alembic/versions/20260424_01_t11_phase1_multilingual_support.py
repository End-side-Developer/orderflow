"""T11-Phase-1-001 Add multi-language support to documents

Revision ID: 20260424_01
Revises: 20260423_02
Create Date: 2026-04-24 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260424_01"
down_revision = "20260423_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add language detection and translation fields to documents table."""
    op.add_column(
        "documents",
        sa.Column(
            "source_language",
            sa.String(length=8),
            nullable=False,
            server_default="en",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "auto_detected_language",
            sa.String(length=8),
            nullable=True,
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "language_confidence",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
            server_default="1.0000",
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "translated_text_stored",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # Add indexes for language-based queries
    op.create_index("ix_documents_source_language", "documents", ["source_language"], unique=False)
    op.create_index(
        "ix_documents_auto_detected_language",
        "documents",
        ["auto_detected_language"],
        unique=False,
    )

    # Add check constraint to validate language codes
    op.create_check_constraint(
        "ck_documents_source_language",
        "documents",
        "source_language IN ('en', 'hi', 'ta', 'te', 'kn', 'ml', 'mr')",
    )
    op.create_check_constraint(
        "ck_documents_auto_detected_language",
        "documents",
        "auto_detected_language IS NULL OR auto_detected_language IN ('en', 'hi', 'ta', 'te', 'kn', 'ml', 'mr')",
    )


def downgrade() -> None:
    """Remove language detection and translation fields from documents table."""
    op.drop_constraint("ck_documents_auto_detected_language", "documents", type_="check")
    op.drop_constraint("ck_documents_source_language", "documents", type_="check")
    op.drop_index("ix_documents_auto_detected_language", table_name="documents")
    op.drop_index("ix_documents_source_language", table_name="documents")
    op.drop_column("documents", "translated_text_stored")
    op.drop_column("documents", "language_confidence")
    op.drop_column("documents", "auto_detected_language")
    op.drop_column("documents", "source_language")
