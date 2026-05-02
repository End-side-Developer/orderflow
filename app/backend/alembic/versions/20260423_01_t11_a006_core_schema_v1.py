"""T11-A-006 core schema v1

Revision ID: 20260423_01
Revises:
Create Date: 2026-04-23 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260423_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_file_type", sa.String(length=100), nullable=True),
        sa.Column("source_file_size", sa.BigInteger(), nullable=True),
        sa.Column("object_key", sa.String(length=512), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'uploaded'")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            "status IN ('uploaded', 'processing', 'ready', 'failed')",
            name="ck_documents_status",
        ),
    )
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)
    op.create_index("ix_documents_created_at", "documents", ["created_at"], unique=False)

    op.create_table(
        "clauses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("clause_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
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
        sa.UniqueConstraint("document_id", "clause_index", name="uq_clauses_document_clause_index"),
    )
    op.create_index("ix_clauses_document_id", "clauses", ["document_id"], unique=False)
    op.create_index("ix_clauses_page_number", "clauses", ["page_number"], unique=False)

    op.create_table(
        "obligations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "clause_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clauses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("obligation_code", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_hint", sa.String(length=200), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default=sa.text("'medium'")),
        sa.Column(
            "review_state",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending_review'"),
        ),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            "status IN ('draft', 'active', 'completed', 'cancelled')",
            name="ck_obligations_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_obligations_priority",
        ),
        sa.CheckConstraint(
            "review_state IN ('pending_review', 'approved', 'rejected')",
            name="ck_obligations_review_state",
        ),
        sa.UniqueConstraint(
            "document_id",
            "obligation_code",
            name="uq_obligations_document_code",
        ),
    )
    op.create_index("ix_obligations_document_id", "obligations", ["document_id"], unique=False)
    op.create_index("ix_obligations_due_date", "obligations", ["due_date"], unique=False)
    op.create_index("ix_obligations_status", "obligations", ["status"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("actor_type", sa.String(length=64), nullable=False, server_default=sa.text("'system'")),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"], unique=False)
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_obligations_status", table_name="obligations")
    op.drop_index("ix_obligations_due_date", table_name="obligations")
    op.drop_index("ix_obligations_document_id", table_name="obligations")
    op.drop_table("obligations")

    op.drop_index("ix_clauses_page_number", table_name="clauses")
    op.drop_index("ix_clauses_document_id", table_name="clauses")
    op.drop_table("clauses")

    op.drop_index("ix_documents_created_at", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_table("documents")
