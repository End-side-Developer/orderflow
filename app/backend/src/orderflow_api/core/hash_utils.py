from __future__ import annotations

import hashlib
import re

_WHITESPACE_NORMALIZER = re.compile(r"\s+")


def calculate_page_content_hash(page_text: str | None) -> str:
    """
    Calculates a deterministic SHA-256 hash (64 hex characters) of a given page text.
    Whitespace is normalized to a single space, and leading/trailing spaces are stripped,
    ensuring that minor OCR/parsing formatting changes don't break the cache.
    """
    if not page_text:
        return hashlib.sha256(b"").hexdigest()

    normalized = _WHITESPACE_NORMALIZER.sub(" ", page_text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
