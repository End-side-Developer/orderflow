from __future__ import annotations

from typing import Final

# Page Extraction
PAGE_EXTRACTION_PROMPT_VERSION: Final = "intake_page_extraction_v1_0"
PAGE_EXTRACTION_MODEL: Final = "gemini-2.0-flash"
PAGE_EXTRACTION_PROVIDER: Final = "gemini"

# Document Summary
DOCUMENT_SUMMARY_PROMPT_VERSION: Final = "doc_summary_generation_v1_1"
DOCUMENT_SUMMARY_MODEL: Final = "gemini-2.0-flash"
DOCUMENT_SUMMARY_PROVIDER: Final = "gemini"

# Action Plan
ACTION_PLAN_PROMPT_VERSION: Final = "action_plan_generation_v1_0"
ACTION_PLAN_MODEL: Final = "gemini-2.0-flash"
ACTION_PLAN_PROVIDER: Final = "gemini"

# Safe default fallback for old paths if any.
LEGACY_FALLBACK_PROMPT_VERSION: Final = "legacy_fallback_v0"
