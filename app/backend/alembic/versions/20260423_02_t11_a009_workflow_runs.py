"""T11-A-009 workflow run tracking

Revision ID: 20260423_02
Revises: 20260423_01
Create Date: 2026-04-23 00:30:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260423_02"
down_revision = "20260423_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("workflow_run_id", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_documents_workflow_run_id", "documents", ["workflow_run_id"], unique=False)

    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workflow_type", sa.String(length=64), nullable=False),
        sa.Column("workflow_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("task_queue", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('started', 'completed', 'failed')",
            name="ck_workflow_runs_status",
        ),
        sa.UniqueConstraint("workflow_id", name="uq_workflow_runs_workflow_id"),
        sa.UniqueConstraint("run_id", name="uq_workflow_runs_run_id"),
    )
    op.create_index("ix_workflow_runs_document_id", "workflow_runs", ["document_id"], unique=False)
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_document_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_index("ix_documents_workflow_run_id", table_name="documents")
    op.drop_column("documents", "workflow_run_id")
