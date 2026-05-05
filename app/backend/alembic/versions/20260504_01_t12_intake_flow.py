"""Add gated intake flow job state.

Revision ID: 20260504_01
Revises: 20260503_01
Create Date: 2026-05-04 08:41:39
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260504_01"
down_revision = "20260503_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=40), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("pages_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_page", sa.Integer(), nullable=True),
        sa.Column("current_page_excerpt", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_concurrency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
        sa.Column(
            "finalized_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "stage IN ("
            "'pending', "
            "'pages_extracting', "
            "'pages_done', "
            "'summary_pending', "
            "'summary_done', "
            "'action_plan_pending', "
            "'action_plan_done', "
            "'review_in_progress', "
            "'finalized'"
            ")",
            name="ck_extraction_jobs_stage",
        ),
        sa.CheckConstraint("pages_total >= 0", name="ck_extraction_jobs_pages_total_nonnegative"),
        sa.CheckConstraint(
            "pages_completed >= 0",
            name="ck_extraction_jobs_pages_completed_nonnegative",
        ),
        sa.CheckConstraint(
            "current_page IS NULL OR current_page >= 1",
            name="ck_extraction_jobs_current_page_positive",
        ),
        sa.CheckConstraint(
            "retry_after_seconds IS NULL OR retry_after_seconds >= 0",
            name="ck_extraction_jobs_retry_after_nonnegative",
        ),
        sa.CheckConstraint(
            "current_concurrency >= 1",
            name="ck_extraction_jobs_current_concurrency_positive",
        ),
        sa.UniqueConstraint("document_id", name="uq_extraction_jobs_document_id"),
    )
    op.create_index("ix_extraction_jobs_stage", "extraction_jobs", ["stage"], unique=False)
    op.create_index(
        "ix_extraction_jobs_paused_until",
        "extraction_jobs",
        ["paused_until"],
        unique=False,
    )

    op.create_table(
        "document_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_basics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("petitioner", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("respondent", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("departments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("key_directives", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("important_dates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "responsible_departments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("flow_graph", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("map_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("ai_model", sa.String(length=100), nullable=True),
        sa.Column("ai_provider", sa.String(length=50), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
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
        sa.UniqueConstraint("document_id", name="uq_document_summaries_document_id"),
    )
    op.create_index(
        "ix_document_summaries_prompt_version",
        "document_summaries",
        ["prompt_version"],
        unique=False,
    )
    op.create_index(
        "ix_document_summaries_cache_lookup",
        "document_summaries",
        ["document_id", "prompt_version"],
        unique=False,
    )

    op.add_column(
        "page_summaries",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "page_summaries",
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "page_summaries",
        sa.Column("source_excerpt", sa.Text(), nullable=True),
    )
    op.add_column(
        "page_summaries",
        sa.Column("ai_token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_page_summaries_cache_lookup",
        "page_summaries",
        ["document_id", "page_number", "content_hash", "prompt_version"],
        unique=False,
    )

    op.add_column(
        "obligations",
        sa.Column("nature_of_action", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "obligations",
        sa.Column(
            "action_plan_stage",
            sa.String(length=40),
            nullable=False,
            server_default=sa.text("'extracted'"),
        ),
    )
    op.add_column(
        "obligations",
        sa.Column("regen_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "obligations",
        sa.Column("regen_history", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        "ck_obligations_nature_of_action",
        "obligations",
        "nature_of_action IS NULL OR nature_of_action IN ("
        "'compliance', "
        "'directive', "
        "'investigation', "
        "'report_filing', "
        "'payment', "
        "'notice', "
        "'appointment', "
        "'submission', "
        "'document_submission', "
        "'compliance_report', "
        "'policy', "
        "'policy_decision', "
        "'reconsideration', "
        "'hearing', "
        "'hearing_review', "
        "'appeal_review', "
        "'record_update', "
        "'other'"
        ")",
    )
    op.create_check_constraint(
        "ck_obligations_action_plan_stage",
        "obligations",
        "action_plan_stage IN ("
        "'extracted', "
        "'in_action_plan', "
        "'review_pending', "
        "'approved', "
        "'rejected', "
        "'edited'"
        ")",
    )
    op.create_check_constraint(
        "ck_obligations_regen_count_nonnegative",
        "obligations",
        "regen_count >= 0",
    )
    op.create_index(
        "ix_obligations_action_plan_stage",
        "obligations",
        ["action_plan_stage"],
        unique=False,
    )
    op.create_index(
        "ix_obligations_document_action_plan_stage",
        "obligations",
        ["document_id", "action_plan_stage"],
        unique=False,
    )
    op.create_index(
        "ix_obligations_review_state",
        "obligations",
        ["review_state"],
        unique=False,
    )
    op.create_index(
        "ix_obligations_nature_of_action",
        "obligations",
        ["nature_of_action"],
        unique=False,
    )
    op.create_index(
        "ix_obligations_owner_hint",
        "obligations",
        ["owner_hint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_obligations_owner_hint", table_name="obligations")
    op.drop_index("ix_obligations_nature_of_action", table_name="obligations")
    op.drop_index("ix_obligations_review_state", table_name="obligations")
    op.drop_index(
        "ix_obligations_document_action_plan_stage",
        table_name="obligations",
    )
    op.drop_index("ix_obligations_action_plan_stage", table_name="obligations")
    op.drop_constraint(
        "ck_obligations_regen_count_nonnegative",
        "obligations",
        type_="check",
    )
    op.drop_constraint(
        "ck_obligations_action_plan_stage",
        "obligations",
        type_="check",
    )
    op.drop_constraint(
        "ck_obligations_nature_of_action",
        "obligations",
        type_="check",
    )
    op.drop_column("obligations", "regen_history")
    op.drop_column("obligations", "regen_count")
    op.drop_column("obligations", "action_plan_stage")
    op.drop_column("obligations", "nature_of_action")
    op.drop_index("ix_page_summaries_cache_lookup", table_name="page_summaries")
    op.drop_column("page_summaries", "ai_token_usage")
    op.drop_column("page_summaries", "source_excerpt")
    op.drop_column("page_summaries", "prompt_version")
    op.drop_column("page_summaries", "content_hash")
    op.drop_index(
        "ix_document_summaries_cache_lookup",
        table_name="document_summaries",
    )
    op.drop_index(
        "ix_document_summaries_prompt_version",
        table_name="document_summaries",
    )
    op.drop_table("document_summaries")
    op.drop_index("ix_extraction_jobs_paused_until", table_name="extraction_jobs")
    op.drop_index("ix_extraction_jobs_stage", table_name="extraction_jobs")
    op.drop_table("extraction_jobs")
