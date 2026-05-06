from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from orderflow_api.api.ai_extraction import maybe_extract_obligations_with_ai
from orderflow_api.api.dependencies.auth import require_permission
from orderflow_api.api.document_persistence import get_persisted_document
from orderflow_api.api.extraction_engine import (
    decode_document_text,
    extract_obligations,
    segment_clauses,
)
from orderflow_api.api.extraction_persistence import replace_document_extraction
from orderflow_api.api.response import success
from orderflow_api.core.auth.permissions import Permission
from orderflow_api.core.config import settings
from orderflow_api.core.language_service import detect_language
from orderflow_api.core.storage import build_object_storage_client, get_object_bytes
from orderflow_api.core.translation_service import (
    TranslationService,
    TranslationServiceConfig,
    TranslationServiceError,
)
from orderflow_api.schemas.extractions import (
    IntakeExtractionEnvelope,
    IntakeExtractionRequest,
    IntakeExtractionResult,
)

router = APIRouter(tags=["extractions"])


@router.post(
    "/extractions/intake/run",
    response_model=IntakeExtractionEnvelope,
    status_code=status.HTTP_200_OK,
)
async def run_intake_extraction_route(
    request: Request,
    payload: IntakeExtractionRequest,
    _user=Depends(require_permission(Permission.EXTRACTION_RUN)),
) -> dict[str, object]:
    document = get_persisted_document(payload.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.object_key:
        raise HTTPException(status_code=400, detail="Document object key is missing")

    try:
        storage_client = build_object_storage_client()
        file_payload = get_object_bytes(storage_client, document.object_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Document read failed: {exc}") from exc

    try:
        raw_text = decode_document_text(
            file_payload,
            document.source_file_type,
            document.source_file_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _, processing_text, translation_note = await _prepare_text_for_extraction(
        raw_text=raw_text,
        source_language=document.source_language,
    )

    clauses = segment_clauses(raw_text=processing_text, document_id=payload.document_id)
    ai_attempt = maybe_extract_obligations_with_ai(
        clauses=clauses,
        document_id=payload.document_id,
        ai_options=payload.ai,
    )

    extraction_mode = "deterministic"
    ai_reason = ai_attempt.reason
    if translation_note:
        ai_reason = f"{ai_reason}; {translation_note}" if ai_reason else translation_note
    obligations = ai_attempt.obligations

    if not obligations and ai_attempt.attempted:
        raise HTTPException(
            status_code=502,
            detail=ai_reason or "AI extraction failed after retry attempts.",
        )

    if not obligations:
        obligations = extract_obligations(clauses=clauses, document_id=payload.document_id)
        extraction_mode = "deterministic"
    else:
        extraction_mode = "ai"

    try:
        persisted_clauses, persisted_obligations = replace_document_extraction(
            document_id=payload.document_id,
            clauses=clauses,
            obligations=obligations,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Extraction persistence failed: {exc}"
        ) from exc

    result = IntakeExtractionResult(
        document_id=payload.document_id,
        clause_count=len(persisted_clauses),
        obligation_count=len(persisted_obligations),
        extraction_mode=extraction_mode,
        ai_provider=ai_attempt.provider,
        ai_model=ai_attempt.model,
        ai_reason=ai_reason,
        clauses=persisted_clauses,
        obligations=persisted_obligations,
    )
    request_id = getattr(request.state, "request_id", None)
    return success(
        data=result,
        request_id=request_id,
        message="intake_extraction_completed",
    )


async def _prepare_text_for_extraction(
    raw_text: str,
    source_language: str,
) -> tuple[str, str, str | None]:
    detected = detect_language(raw_text)
    detected_language = detected.detected_language if detected.is_supported else "en"
    effective_language = _normalize_language(source_language) or detected_language

    if effective_language == "en":
        note = None
        if source_language != detected_language and detected.confidence >= 0.75:
            note = f"language_auto_detected={detected_language}"
        return effective_language, raw_text, note

    translator = TranslationService(
        config=TranslationServiceConfig(
            service_url=settings.orderflow_translation_service_url,
            api_key=settings.orderflow_translation_api_key,
            timeout_seconds=settings.orderflow_translation_timeout_seconds,
            max_retries=settings.orderflow_translation_max_retries,
        ),
    )

    try:
        translated_text = await translator.translate(
            text=raw_text,
            source_lang=effective_language,
            target_lang="en",
            use_cache=False,
        )
    except TranslationServiceError:
        return (
            effective_language,
            raw_text,
            f"translation_failed_fallback source_language={effective_language}",
        )

    return (
        effective_language,
        translated_text,
        f"translated_to_en source_language={effective_language}",
    )


def _normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    code = value.strip().lower()
    if code in {"en", "hi", "ta", "te", "kn", "ml", "mr"}:
        return code
    return None
