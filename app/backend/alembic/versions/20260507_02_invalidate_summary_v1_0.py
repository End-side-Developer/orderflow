"""Invalidate document summaries generated with prompt version v1_0.

The summary enrichment prompt was updated in v1_1 to include AI-based
extraction of case basics (court_name, petitioner, respondent, judge_name).
Any row saved under the old version would have deterministic-only (regex)
values for those fields, which are known to be inaccurate for non-standard
judgment layouts. Deleting them forces the worker to regenerate each summary
with the corrected prompt on the next request.

Revision ID: 20260507_02_inv_summary_v1_0
Revises: 20260507_01_text_boxes
Create Date: 2026-05-07 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260507_02_inv_summary_v1_0"
down_revision = "20260507_01_text_boxes"
branch_labels = None
depends_on = None

_OLD_VERSION = "doc_summary_generation_v1_0"


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM document_summaries WHERE prompt_version = :ver"
        ).bindparams(ver=_OLD_VERSION)
    )


def downgrade() -> None:
    # Deleted rows cannot be restored — a downgrade would require re-running
    # the summary generation workflow for every document, which is out of scope
    # for a schema rollback. No-op is intentional.
    pass
