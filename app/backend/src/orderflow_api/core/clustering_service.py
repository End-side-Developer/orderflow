"""Case clustering & semantic similarity (P1-3).

Backed by pgvector (`obligations.embedding VECTOR(384)`). Provides:
- `embed_obligation(obligation)` — compute embedding from title + description.
- `backfill_missing_embeddings(limit)` — populate the column for legacy rows.
- `find_similar_obligations(obligation_id, k)` — cosine NN search.
- `find_similar_to_text(text, k)` — semantic search from arbitrary text.

The implementation falls back gracefully:
- If pgvector / the embedding column is missing, the search returns [].
- If the embedding model is unavailable, the deterministic hash-based
  fallback in `embedding_service` still produces vectors so writes don't
  fail; quality is degraded but the pipeline keeps running.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

import sqlalchemy as sa

from orderflow_api.core import embedding_service
from orderflow_api.core.db import get_engine

logger = logging.getLogger(__name__)


@dataclass
class SimilarObligation:
    obligation_id: UUID
    document_id: UUID
    title: str
    distance: float  # cosine distance (smaller = more similar)
    similarity: float  # 1 - distance


def _vector_literal(vec: list[float]) -> str:
    """pgvector accepts text input like '[1,2,3]'. Floats stringified."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def _obligation_text(title: str, description: str | None) -> str:
    parts = [title or ""]
    if description:
        parts.append(description)
    return "\n".join(p for p in parts if p)


def embed_obligation_text(title: str, description: str | None) -> list[float]:
    text = _obligation_text(title, description)
    return embedding_service.embed_text(text)


def write_obligation_embedding(obligation_id: UUID, embedding: list[float]) -> bool:
    """Write the embedding for a single obligation. Returns success."""
    try:
        with get_engine().begin() as connection:
            connection.execute(
                sa.text(
                    "UPDATE obligations SET embedding = CAST(:vec AS vector) " "WHERE id = :oid"
                ),
                {"vec": _vector_literal(embedding), "oid": str(obligation_id)},
            )
        return True
    except Exception as exc:
        logger.warning(
            "Could not write embedding for %s — pgvector may not be available: %s",
            obligation_id,
            exc,
        )
        return False


def backfill_missing_embeddings(limit: int = 500) -> int:
    """Populate `embedding` for any obligation rows missing one.

    Returns the number of rows updated.
    """
    try:
        with get_engine().connect() as connection:
            rows = (
                connection.execute(
                    sa.text(
                        "SELECT id, title, description FROM obligations "
                        "WHERE embedding IS NULL "
                        "LIMIT :lim"
                    ),
                    {"lim": limit},
                )
                .mappings()
                .fetchall()
            )
    except Exception as exc:
        logger.warning("Backfill scan failed: %s", exc)
        return 0

    if not rows:
        return 0

    updated = 0
    for row in rows:
        embedding = embed_obligation_text(row["title"], row.get("description"))
        if write_obligation_embedding(row["id"], embedding):
            updated += 1
    return updated


def find_similar_obligations(obligation_id: UUID, k: int = 5) -> list[SimilarObligation]:
    """Cosine-NN search for obligations similar to the target.

    Excludes the target itself. Returns up to k results.
    """
    try:
        with get_engine().connect() as connection:
            rows = (
                connection.execute(
                    sa.text(
                        """
                    SELECT
                        o.id AS obligation_id,
                        o.document_id,
                        o.title,
                        (o.embedding <=> target.embedding) AS distance
                    FROM obligations o
                    JOIN (
                        SELECT embedding FROM obligations WHERE id = :oid
                    ) AS target ON TRUE
                    WHERE o.id <> :oid
                      AND o.embedding IS NOT NULL
                      AND target.embedding IS NOT NULL
                    ORDER BY distance ASC
                    LIMIT :k
                    """
                    ),
                    {"oid": str(obligation_id), "k": k},
                )
                .mappings()
                .fetchall()
            )
    except Exception as exc:
        logger.warning("Similar-obligation search failed: %s", exc)
        return []

    return [
        SimilarObligation(
            obligation_id=row["obligation_id"],
            document_id=row["document_id"],
            title=row["title"],
            distance=float(row["distance"]),
            similarity=max(0.0, 1.0 - float(row["distance"])),
        )
        for row in rows
    ]


def find_similar_to_text(text: str, k: int = 5) -> list[SimilarObligation]:
    """Semantic search from raw text, e.g. judge dictation."""
    if not text or not text.strip():
        return []
    embedding = embedding_service.embed_text(text)
    try:
        with get_engine().connect() as connection:
            rows = (
                connection.execute(
                    sa.text(
                        """
                    SELECT
                        id AS obligation_id,
                        document_id,
                        title,
                        (embedding <=> CAST(:vec AS vector)) AS distance
                    FROM obligations
                    WHERE embedding IS NOT NULL
                    ORDER BY distance ASC
                    LIMIT :k
                    """
                    ),
                    {"vec": _vector_literal(embedding), "k": k},
                )
                .mappings()
                .fetchall()
            )
    except Exception as exc:
        logger.warning("Text-similarity search failed: %s", exc)
        return []

    return [
        SimilarObligation(
            obligation_id=row["obligation_id"],
            document_id=row["document_id"],
            title=row["title"],
            distance=float(row["distance"]),
            similarity=max(0.0, 1.0 - float(row["distance"])),
        )
        for row in rows
    ]


def write_embeddings_for_new_obligations(items: Iterable) -> int:
    """Convenience helper called after a batch insert to populate embeddings."""
    count = 0
    for o in items:
        embedding = embed_obligation_text(o.title, o.description)
        if write_obligation_embedding(o.id, embedding):
            count += 1
    return count
