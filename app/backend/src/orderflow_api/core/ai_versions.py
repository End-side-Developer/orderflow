from __future__ import annotations

from typing import Final

# Page Extraction
PAGE_EXTRACTION_PROMPT_VERSION: Final = "intake_page_extraction_v1_0"
PAGE_EXTRACTION_MODEL: Final = "llama-3.1-8b-instant"
PAGE_EXTRACTION_PROVIDER: Final = "groq"

# Document Summary
DOCUMENT_SUMMARY_PROMPT_VERSION: Final = "doc_summary_generation_v1_0"
DOCUMENT_SUMMARY_MODEL: Final = "llama-3.1-8b-instant"
DOCUMENT_SUMMARY_PROVIDER: Final = "groq"

# Action Plan
ACTION_PLAN_PROMPT_VERSION: Final = "action_plan_generation_v1_0"
ACTION_PLAN_MODEL: Final = "llama-3.1-8b-instant"
ACTION_PLAN_PROVIDER: Final = "groq"

# Safe default fallback for old paths if any.
LEGACY_FALLBACK_PROMPT_VERSION: Final = "legacy_fallback_v0"
