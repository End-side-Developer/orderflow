"""T11 obligation embeddings (pgvector)

Adds a 384-dimensional embedding column to obligations + ivfflat
cosine index. Powers AI-powered case clustering (P1-3) by replacing
token-overlap similarity with semantic search.

Revision ID: 20260430_01
Revises: 20260424_03
Create Date: 2026-04-30 00:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260430_01"
down_revision = "20260424_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector extension may already be enabled — IF NOT EXISTS keeps this idempotent.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Use raw SQL for the vector column type so we don't depend on the pgvector
    # SQLAlchemy adapter being installed at migration time.
    op.execute("ALTER TABLE obligations ADD COLUMN IF NOT EXISTS embedding vector(384)")

    # ivfflat with cosine distance is the standard pgvector recipe for
    # similarity search. lists=100 is sane for ≤100k rows; tune later.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_obligations_embedding_cosine
        ON obligations
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_obligations_embedding_cosine")
    op.execute("ALTER TABLE obligations DROP COLUMN IF EXISTS embedding")
    # Intentionally do not drop the vector extension — other tables may need it.
