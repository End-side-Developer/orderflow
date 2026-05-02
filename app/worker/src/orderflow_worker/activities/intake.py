from __future__ import annotations

from datetime import UTC, datetime

from temporalio import activity


@activity.defn
async def parse_stub_activity(payload: dict[str, str]) -> dict[str, str]:
    document_id = payload.get("document_id", "unknown")
    return {
        "document_id": document_id,
        "parsed": "true",
        "parsed_at": datetime.now(UTC).isoformat(),
        "source_language": payload.get("source_language", "en"),
        "translation_status": payload.get("translation_status", "not_required"),
    }


@activity.defn
async def translate_document_if_needed_activity(payload: dict[str, str]) -> dict[str, str]:
    source_language = payload.get("source_language", "en").strip().lower()
    translated_text_stored = payload.get("translated_text_stored", "false") == "true"

    if source_language == "en":
        return {
            **payload,
            "translation_required": "false",
            "translation_status": "not_required",
        }

    if translated_text_stored:
        return {
            **payload,
            "translation_required": "false",
            "translation_status": "already_translated",
        }

    return {
        **payload,
        "translation_required": "true",
        "translation_status": "pending_backend_translation",
        "translation_target_language": "en",
    }
