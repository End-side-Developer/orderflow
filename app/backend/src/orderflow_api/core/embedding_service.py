"""Local sentence-transformer embedding service.

Wraps `sentence-transformers/all-MiniLM-L6-v2` (384 dim) for two consumers:
1. Proof verifier — semantic similarity between obligation text and proof text.
2. Case clustering — pgvector cosine search over obligation embeddings.

Model is loaded lazily on first use and cached for the process lifetime.
If `sentence-transformers` is not installed, the service falls back to a
deterministic hash-based pseudo-embedding so callers always get a vector
of the right shape (degraded relevance, but no crashes during dev).
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
from typing import Iterable

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model_lock = threading.Lock()
_model = None
_model_load_failed = False


def _load_model():
    """Lazy-load the sentence-transformer. Returns None if unavailable."""
    global _model, _model_load_failed
    if _model is not None or _model_load_failed:
        return _model
    with _model_lock:
        if _model is not None or _model_load_failed:
            return _model
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            model_name = os.environ.get(
                "ORDERFLOW_EMBEDDING_MODEL", DEFAULT_MODEL_NAME
            )
            logger.info("Loading sentence-transformer model: %s", model_name)
            _model = SentenceTransformer(model_name)
        except Exception as exc:
            logger.warning(
                "sentence-transformers unavailable (%s); falling back to "
                "deterministic hash embeddings. Install sentence-transformers "
                "for production-quality similarity.",
                exc,
            )
            _model_load_failed = True
            _model = None
        return _model


def _hash_fallback_embedding(text: str) -> list[float]:
    """Deterministic 384-dim pseudo-embedding from SHA-256 of token chunks.

    Use only when the real model is unavailable. Token-overlap quality at best.
    """
    text = (text or "").strip().lower()
    if not text:
        return [0.0] * EMBEDDING_DIM

    # Build vector by hashing overlapping token windows into bins.
    vector = [0.0] * EMBEDDING_DIM
    tokens = [t for t in text.split() if t]
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        # Map digest bytes (32) into 384 dims by repeating + sign-flipping.
        for i in range(EMBEDDING_DIM):
            byte = digest[i % 32]
            sign = 1.0 if (i // 32) % 2 == 0 else -1.0
            vector[i] += sign * (byte / 255.0)

    # L2 normalize.
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


def embed_text(text: str) -> list[float]:
    """Embed a single string. Returns a 384-dim list of floats."""
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIM
    model = _load_model()
    if model is None:
        return _hash_fallback_embedding(text)
    try:
        vec = model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]
    except Exception as exc:
        logger.warning("Embedding encode failed (%s); using fallback.", exc)
        return _hash_fallback_embedding(text)


def embed_batch(texts: Iterable[str]) -> list[list[float]]:
    """Embed multiple strings. Preserves input order."""
    items = list(texts)
    if not items:
        return []
    model = _load_model()
    if model is None:
        return [_hash_fallback_embedding(t) for t in items]
    try:
        vecs = model.encode(items, normalize_embeddings=True, batch_size=32)
        return [[float(x) for x in v] for v in vecs]
    except Exception as exc:
        logger.warning("Batch embedding failed (%s); using fallback.", exc)
        return [_hash_fallback_embedding(t) for t in items]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]. Returns 0.0 for zero vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def is_real_model_loaded() -> bool:
    """For diagnostics — true if the actual transformer is in memory."""
    return _model is not None and not _model_load_failed
