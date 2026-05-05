from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from pathlib import Path
import re
import sys
from typing import Any
from uuid import UUID

from temporalio import activity
from temporalio import exceptions as temporal_exceptions

from orderflow_worker.core.ai_versions import (
    PAGE_EXTRACTION_PROMPT_VERSION,
    PAGE_EXTRACTION_MODEL,
    PAGE_EXTRACTION_PROVIDER,
    DOCUMENT_SUMMARY_PROMPT_VERSION,
    DOCUMENT_SUMMARY_MODEL,
    DOCUMENT_SUMMARY_PROVIDER,
    ACTION_PLAN_PROMPT_VERSION,
    ACTION_PLAN_MODEL,
    ACTION_PLAN_PROVIDER,
)

logger = logging.getLogger(__name__)

DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION = PAGE_EXTRACTION_PROMPT_VERSION
DEFAULT_PAGE_EXTRACTION_MODEL = PAGE_EXTRACTION_MODEL
DEFAULT_PAGE_EXTRACTION_PROVIDER = PAGE_EXTRACTION_PROVIDER
DEFAULT_DOCUMENT_SUMMARY_PROMPT_VERSION = DOCUMENT_SUMMARY_PROMPT_VERSION
DEFAULT_DOCUMENT_SUMMARY_MODEL = DOCUMENT_SUMMARY_MODEL
DEFAULT_DOCUMENT_SUMMARY_PROVIDER = DOCUMENT_SUMMARY_PROVIDER
DEFAULT_ACTION_PLAN_PROMPT_VERSION = ACTION_PLAN_PROMPT_VERSION
DEFAULT_ACTION_PLAN_MODEL = ACTION_PLAN_MODEL
DEFAULT_ACTION_PLAN_PROVIDER = ACTION_PLAN_PROVIDER
SUMMARY_DONE_STAGES = {
    "summary_done",
    "action_plan_pending",
    "action_plan_done",
    "review_in_progress",
    "finalized",
}
ACTION_PLAN_ITEM_STAGES = {
    "in_action_plan",
    "review_pending",
    "approved",
    "rejected",
    "edited",
}
ACTION_PLAN_DONE_STAGES = {
    "action_plan_done",
    "review_in_progress",
    "finalized",
}
INTAKE_STAGE_VALUES = {
    "pending",
    "pages_extracting",
    "pages_done",
    "summary_pending",
    "summary_done",
    "action_plan_pending",
    "action_plan_done",
    "review_in_progress",
    "finalized",
}
MAX_SOURCE_EXCERPT_CHARS = 800


@activity.defn
async def activity_extract_page_cached(
    document_id: dict[str, Any] | str,
    page_number: int | str | None = None,
    content_hash: str | None = None,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    context = _normalize_page_extraction_context(
        document_id=document_id,
        page_number=page_number,
        content_hash=content_hash,
        prompt_version=prompt_version,
    )
    backend = _load_page_extraction_backend()

    try:
        return await _run_page_extraction_cached(context, backend)
    except Exception as exc:
        _record_page_extraction_failure(
            backend=backend,
            context=context,
            error=exc,
        )
        rate_limit_error = _rate_limit_application_error(exc)
        if rate_limit_error is not None:
            raise rate_limit_error from exc
        raise


async def _run_page_extraction_cached(
    context: PageExtractionContext,
    backend: PageExtractionBackend,
) -> dict[str, Any]:
    if not context.bypass_cache and context.content_hash:
        cached = backend.get_cached_page_summary(
            document_id=context.document_uuid,
            page_number=context.page_number,
            content_hash=context.content_hash,
            prompt_version=context.prompt_version,
            ai_model=context.ai_model,
            ai_provider=context.ai_provider,
        )
        if cached is not None:
            job_progress = _update_page_extraction_progress(
                backend=backend,
                context=context,
                summary_record=cached,
                cache_status="hit",
            )
            _log_worker_cache_hit(
                document_id=context.document_id,
                resource="page_summary",
                workflow_stage="pages_extracting",
                cache_status="hit",
                prompt_version=context.prompt_version,
                ai_provider=context.ai_provider,
                ai_model=context.ai_model,
                page_number=context.page_number,
                summary_id=getattr(cached, "id", None),
            )
            return _page_extraction_result(
                context=context,
                cache_status="hit",
                summary_record=cached,
                job_progress=job_progress,
            )

    page_text = context.page_text or _load_page_text_from_clauses(
        backend,
        context,
    )
    if not page_text.strip():
        # Raise a specific message that _user_facing_page_error recognizes
        # so the UI surfaces an OCR guidance message instead of a raw ValueError.
        raise ValueError(
            "Unable to extract text from PDF: no readable text layer found"
        )

    effective_content_hash = context.content_hash or backend.calculate_page_content_hash(page_text)
    if not context.bypass_cache and not context.content_hash:
        cached = backend.get_cached_page_summary(
            document_id=context.document_uuid,
            page_number=context.page_number,
            content_hash=effective_content_hash,
            prompt_version=context.prompt_version,
            ai_model=context.ai_model,
            ai_provider=context.ai_provider,
        )
        if cached is not None:
            cached_context = context.with_content_hash(effective_content_hash)
            job_progress = _update_page_extraction_progress(
                backend=backend,
                context=cached_context,
                summary_record=cached,
                cache_status="hit",
            )
            _log_worker_cache_hit(
                document_id=cached_context.document_id,
                resource="page_summary",
                workflow_stage="pages_extracting",
                cache_status="hit",
                prompt_version=cached_context.prompt_version,
                ai_provider=cached_context.ai_provider,
                ai_model=cached_context.ai_model,
                page_number=cached_context.page_number,
                summary_id=getattr(cached, "id", None),
            )
            return _page_extraction_result(
                context=cached_context,
                cache_status="hit",
                summary_record=cached,
                job_progress=job_progress,
            )

    extractor = backend.PageSummaryExtractor(
        ai_provider=context.ai_provider,
        model=context.ai_model,
        api_key=_api_key_for_provider(backend.settings, context.ai_provider),
        temperature=context.temperature,
    )
    extraction = await extractor._ai_extract_page(
        page_num=context.page_number,
        page_text=page_text,
        total_pages=context.total_pages,
    )
    context_links = extractor._find_context_links(
        page_num=context.page_number,
        page_text=page_text,
        all_pages={context.page_number: page_text},
    )
    raw_places = extraction.get("places", [])
    place_candidates = (
        [item for item in raw_places if isinstance(item, dict)]
        if isinstance(raw_places, list)
        else []
    )
    extracted_places = backend.geocode_places(
        backend.build_extracted_places(
            place_candidates,
            page_number=context.page_number,
        )
    )

    summary_record = backend.upsert_page_summary(
        document_id=context.document_uuid,
        page_number=context.page_number,
        page_text=page_text,
        summary=_text_or_default(extraction.get("summary"), ""),
        key_points=_string_list(extraction.get("key_points")),
        important_highlights=_dict_list(extraction.get("highlights")),
        entities=_dict_list(extraction.get("entities")),
        dates=_dict_list(extraction.get("dates")),
        directions=_dict_list(extraction.get("directions")),
        departments=_dict_list(extraction.get("departments")),
        context_links=[link for link in context_links if isinstance(link, dict)],
        obligation_ids=_page_obligation_ids(backend, context),
        extracted_places=extracted_places,
        confidence=_confidence_or_default(extraction.get("confidence")),
        extraction_mode="ai",
        ai_model=context.ai_model,
        ai_provider=context.ai_provider,
        content_hash=effective_content_hash,
        prompt_version=context.prompt_version,
        source_excerpt=_truncate_text(page_text, MAX_SOURCE_EXCERPT_CHARS),
        ai_token_usage=_dict_or_none(extraction.get("ai_token_usage")),
    )
    completed_context = context.with_content_hash(effective_content_hash)
    job_progress = _update_page_extraction_progress(
        backend=backend,
        context=completed_context,
        summary_record=summary_record,
        cache_status="miss_generated",
    )
    return _page_extraction_result(
        context=completed_context,
        cache_status="miss_generated",
        summary_record=summary_record,
        job_progress=job_progress,
    )


@activity.defn
async def activity_list_completed_pages(
    payload: dict[str, Any] | str,
) -> dict[str, Any]:
    context = _normalize_completed_pages_context(payload)
    backend = _load_completed_pages_backend()

    if context.bypass_cache:
        return _completed_pages_result(context, [], None)

    completed_pages = [
        result
        for summary in backend.list_page_summaries(context.document_uuid)
        for result in [_completed_page_result(context, summary)]
        if result is not None
    ]
    completed_pages.sort(key=lambda item: item["page_number"])
    if completed_pages:
        _log_worker_cache_hit(
            document_id=context.document_id,
            resource="page_summary",
            workflow_stage="pages_extracting",
            cache_status="skipped_completed",
            prompt_version=context.prompt_version,
            ai_provider=context.ai_provider,
            ai_model=context.ai_model,
            hit_count=len(completed_pages),
            page_numbers=[item["page_number"] for item in completed_pages],
        )

    job_progress = None
    if completed_pages:
        page_numbers = [item["page_number"] for item in completed_pages]
        job_progress = backend.update_extraction_job_progress(
            context.document_uuid,
            pages_total=context.total_pages,
            pages_completed=len(page_numbers),
            current_page=max(page_numbers),
            current_page_excerpt={
                "cache_status": "skipped_completed",
                "skipped_page_numbers": page_numbers,
            },
        )

    return _completed_pages_result(context, completed_pages, job_progress)


@activity.defn
async def activity_mark_intake_stage(
    document_id: dict[str, Any] | str,
    stage: str | None = None,
) -> dict[str, Any]:
    context = _normalize_stage_marker_context(
        document_id=document_id,
        stage=stage,
    )
    backend = _load_stage_marker_backend()
    job = backend.update_extraction_job_stage(
        context.document_uuid,
        context.stage,
    )
    if job is None:
        raise ValueError(f"Extraction job not found: {context.document_id}")
    return {
        "document_id": context.document_id,
        "stage": getattr(job, "stage", context.stage),
        "job": _record_payload(job),
    }


@activity.defn
async def activity_pause_intake_job(
    payload: dict[str, Any] | str,
) -> dict[str, Any]:
    context = _normalize_pause_context(payload)
    backend = _load_pause_backend()
    job = backend.pause_extraction_job(
        context.document_uuid,
        retry_after_seconds=context.retry_after_seconds,
        paused_until=context.paused_until,
        error_code=context.error_code,
        error_message=context.error_message,
        current_concurrency=context.current_concurrency,
    )
    if job is None:
        raise ValueError(f"Extraction job not found: {context.document_id}")
    return {
        "document_id": context.document_id,
        "paused_until": context.paused_until.isoformat(),
        "retry_after_seconds": context.retry_after_seconds,
        "current_concurrency": context.current_concurrency,
        "trace": _trace_attributes(
            document_id=context.document_id,
            workflow_stage="pages_extracting",
            retry_state="paused",
            retry_after_seconds=context.retry_after_seconds,
            paused_until=context.paused_until.isoformat(),
            current_concurrency=context.current_concurrency,
        ),
        "job": _record_payload(job),
    }


@activity.defn
async def activity_resume_intake_job(
    payload: dict[str, Any] | str,
) -> dict[str, Any]:
    context = _normalize_resume_context(payload)
    backend = _load_pause_backend()
    job = backend.resume_extraction_job(
        context.document_uuid,
        current_concurrency=context.current_concurrency,
    )
    if job is None:
        raise ValueError(f"Extraction job not found: {context.document_id}")
    return {
        "document_id": context.document_id,
        "current_concurrency": context.current_concurrency,
        "trace": _trace_attributes(
            document_id=context.document_id,
            workflow_stage="pages_extracting",
            retry_state="resumed",
            current_concurrency=context.current_concurrency,
        ),
        "job": _record_payload(job),
    }


@activity.defn
async def activity_generate_full_summary(
    document_id: dict[str, Any] | str,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    context = _normalize_document_summary_context(
        document_id=document_id,
        prompt_version=prompt_version,
    )
    backend = _load_document_summary_backend()

    if not context.bypass_cache:
        cached = backend.get_document_summary(
            context.document_uuid,
            prompt_version=context.prompt_version,
            ai_model=context.ai_model,
            ai_provider=context.ai_provider,
        )
        if cached is not None:
            job_stage = _mark_summary_done(backend, context)
            _log_worker_cache_hit(
                document_id=context.document_id,
                resource="document_summary",
                workflow_stage=job_stage,
                cache_status="hit",
                prompt_version=context.prompt_version,
                ai_provider=context.ai_provider,
                ai_model=context.ai_model,
                summary_id=getattr(cached, "id", None),
                job_stage=job_stage,
            )
            return _document_summary_result(
                context=context,
                cache_status="hit",
                summary_record=cached,
                job_stage=job_stage,
            )

    page_summaries = backend.list_page_summaries(context.document_uuid)
    if not page_summaries:
        message = "Cached page summaries are required before full summary generation"
        raise ValueError(f"{message}: document_id={context.document_id}")

    obligations = backend.list_persisted_obligations(context.document_uuid)
    payload = _build_document_summary_payload(
        context=context,
        page_summaries=page_summaries,
        obligations=obligations,
    )

    # Enrich overview and key_directives with AI if available.
    backend_settings = getattr(backend, "settings", None)
    api_key = _api_key_for_provider(backend_settings, context.ai_provider)
    if api_key and context.ai_provider in {"gemini", "groq"}:
        try:
            enriched = _ai_enrich_document_summary(
                context=context,
                payload=payload,
                api_key=api_key,
                page_summaries=page_summaries,
            )
            if enriched:
                payload = enriched
        except Exception as exc:
            logger.warning(
                "AI enrichment of document summary failed for %s: %s: %s",
                context.document_id,
                type(exc).__name__,
                exc,
            )

    summary_record = backend.upsert_document_summary(
        document_id=context.document_uuid,
        prompt_version=context.prompt_version,
        case_basics=payload["case_basics"],
        overview=payload["overview"],
        key_directives=payload["key_directives"],
        important_dates=payload["important_dates"],
        entities_involved=payload["entities_involved"],
        responsible_departments=payload["responsible_departments"],
        flow_graph=payload["flow_graph"],
        map_data=payload["map_data"],
        confidence=payload["confidence"],
        ai_model=context.ai_model,
        ai_provider=context.ai_provider,
    )
    return _document_summary_result(
        context=context,
        cache_status="miss_generated",
        summary_record=summary_record,
        job_stage=_mark_summary_done(backend, context),
    )


@activity.defn
async def activity_extract_action_plan(
    document_id: dict[str, Any] | str,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    context = _normalize_action_plan_context(
        document_id=document_id,
        prompt_version=prompt_version,
    )
    backend = _load_action_plan_backend()

    current_job = backend.get_extraction_job(context.document_uuid)
    current_stage = getattr(current_job, "stage", None)
    if current_stage not in SUMMARY_DONE_STAGES:
        raise ValueError(
            "Summary must be completed before action-plan generation: "
            f"document_id={context.document_id} "
            f"current_stage={current_stage}"
        )

    obligations = backend.list_persisted_obligations(context.document_uuid)
    action_items = _filter_action_plan_items(obligations)
    extracted_items = _filter_extracted_obligations(obligations)
    action_plan_cache_valid = _action_plan_cache_matches_context(
        action_items,
        context,
    )
    if current_stage in ACTION_PLAN_DONE_STAGES and action_items:
        if not action_plan_cache_valid:
            raise ValueError(
                "Existing action plan was generated with a different "
                "prompt/model/provider; use per-item regeneration instead: "
                f"document_id={context.document_id}"
            )
        _log_worker_cache_hit(
            document_id=context.document_id,
            resource="action_plan",
            workflow_stage=str(current_stage),
            cache_status="hit",
            prompt_version=context.prompt_version,
            ai_provider=context.ai_provider,
            ai_model=context.ai_model,
            hit_count=len(action_items),
            job_stage=str(current_stage),
        )
        return _action_plan_result(
            context=context,
            cache_status="hit",
            action_items=action_items,
            job_stage=str(current_stage),
            extraction_mode="cached_action_plan",
            ai_reason=None,
        )
    if action_items and not extracted_items:
        if not action_plan_cache_valid:
            raise ValueError(
                "Existing action plan was generated with a different "
                "prompt/model/provider; use per-item regeneration instead: "
                f"document_id={context.document_id}"
            )
        job_stage = _mark_action_plan_done(backend, context)
        _log_worker_cache_hit(
            document_id=context.document_id,
            resource="action_plan",
            workflow_stage=job_stage,
            cache_status="hit",
            prompt_version=context.prompt_version,
            ai_provider=context.ai_provider,
            ai_model=context.ai_model,
            hit_count=len(action_items),
            job_stage=job_stage,
        )
        return _action_plan_result(
            context=context,
            cache_status="hit",
            action_items=action_items,
            job_stage=job_stage,
            extraction_mode="cached_action_plan",
            ai_reason=None,
        )

    source_items = extracted_items
    extraction_mode = "persisted_extractions"
    ai_reason = None
    if not source_items:
        (
            source_items,
            extraction_mode,
            ai_reason,
        ) = _extract_obligations_for_action_plan(backend, context)

    if not source_items:
        message = "No extracted obligations are available"
        raise ValueError(
            f"{message} for action-plan generation: " f"document_id={context.document_id}",
        )

    updated_items = []
    for obligation in source_items:
        nature = _text_or_default(
            getattr(obligation, "nature_of_action", None), ""
        ) or _classify_nature_of_action(obligation)
        update_values = {
            "action_plan_stage": "in_action_plan",
            "nature_of_action": nature,
            "metadata": _action_plan_metadata(context, obligation),
            **_appeal_guardrail_text_updates(obligation, nature),
        }
        updated = backend.update_persisted_obligation(obligation.id, **update_values)
        if updated is None:
            raise ValueError(
                "Action-plan obligation update failed: "
                f"document_id={context.document_id} "
                f"obligation_id={obligation.id}"
            )
        _record_action_plan_generation_audit(
            backend=backend,
            context=context,
            obligation=updated,
            nature_of_action=nature,
        )
        updated_items.append(updated)

    all_items = _filter_action_plan_items(backend.list_persisted_obligations(context.document_uuid))
    job_stage = _mark_action_plan_done(backend, context)
    return _action_plan_result(
        context=context,
        cache_status="miss_generated",
        action_items=all_items or updated_items,
        job_stage=job_stage,
        extraction_mode=extraction_mode,
        ai_reason=ai_reason,
    )


@activity.defn
async def translate_document_if_needed_activity(
    payload: dict[str, str],
) -> dict[str, str]:
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


@dataclass(frozen=True)
class PageExtractionContext:
    document_id: str
    document_uuid: UUID
    page_number: int
    content_hash: str
    prompt_version: str
    page_text: str
    total_pages: int
    ai_provider: str
    ai_model: str
    temperature: float
    bypass_cache: bool
    source_language: str
    translation_status: str
    translation_required: str

    def with_content_hash(self, content_hash: str) -> "PageExtractionContext":
        return PageExtractionContext(
            document_id=self.document_id,
            document_uuid=self.document_uuid,
            page_number=self.page_number,
            content_hash=content_hash,
            prompt_version=self.prompt_version,
            page_text=self.page_text,
            total_pages=self.total_pages,
            ai_provider=self.ai_provider,
            ai_model=self.ai_model,
            temperature=self.temperature,
            bypass_cache=self.bypass_cache,
            source_language=self.source_language,
            translation_status=self.translation_status,
            translation_required=self.translation_required,
        )


@dataclass(frozen=True)
class DocumentSummaryContext:
    document_id: str
    document_uuid: UUID
    prompt_version: str
    ai_provider: str
    ai_model: str
    bypass_cache: bool


@dataclass(frozen=True)
class StageMarkerContext:
    document_id: str
    document_uuid: UUID
    stage: str


@dataclass(frozen=True)
class PauseContext:
    document_id: str
    document_uuid: UUID
    retry_after_seconds: int
    paused_until: datetime
    error_code: str
    error_message: str
    current_concurrency: int


@dataclass(frozen=True)
class ResumeContext:
    document_id: str
    document_uuid: UUID
    current_concurrency: int


@dataclass(frozen=True)
class UserFacingPageError:
    code: str
    category: str
    message: str
    partial_failure: bool


@dataclass(frozen=True)
class CompletedPagesContext:
    document_id: str
    document_uuid: UUID
    page_numbers: set[int]
    content_hashes: dict[int, str]
    prompt_version: str
    ai_provider: str
    ai_model: str
    total_pages: int
    bypass_cache: bool


@dataclass(frozen=True)
class ActionPlanContext:
    document_id: str
    document_uuid: UUID
    prompt_version: str
    ai_provider: str
    ai_model: str
    temperature: float
    max_obligations: int


@dataclass(frozen=True)
class PageExtractionBackend:
    PageSummaryExtractor: Any
    build_extracted_places: Any
    calculate_page_content_hash: Any
    fail_extraction_job: Any
    geocode_places: Any
    get_cached_page_summary: Any
    list_page_summaries: Any
    list_persisted_clauses: Any
    list_persisted_obligations: Any
    settings: Any
    update_extraction_job_progress: Any
    upsert_page_summary: Any


@dataclass(frozen=True)
class DocumentSummaryBackend:
    get_document_summary: Any
    get_extraction_job: Any
    list_page_summaries: Any
    list_persisted_obligations: Any
    update_extraction_job_stage: Any
    upsert_document_summary: Any


@dataclass(frozen=True)
class StageMarkerBackend:
    update_extraction_job_stage: Any


@dataclass(frozen=True)
class PauseResumeBackend:
    pause_extraction_job: Any
    resume_extraction_job: Any


@dataclass(frozen=True)
class CompletedPagesBackend:
    list_page_summaries: Any
    update_extraction_job_progress: Any


@dataclass(frozen=True)
class ActionPlanBackend:
    IntakeAiOptions: Any
    ParsedClause: Any
    extract_obligations: Any
    get_extraction_job: Any
    list_persisted_clauses: Any
    list_persisted_obligations: Any
    maybe_extract_obligations_with_ai: Any
    record_persisted_obligation_audit_event: Any
    replace_document_extraction: Any
    update_extraction_job_stage: Any
    update_persisted_obligation: Any


def _normalize_page_extraction_context(
    *,
    document_id: dict[str, Any] | str,
    page_number: int | str | None,
    content_hash: str | None,
    prompt_version: str | None,
) -> PageExtractionContext:
    payload = document_id if isinstance(document_id, dict) else {}
    document_id_value = _string_value(payload.get("document_id") if payload else document_id)
    if document_id_value is None:
        raise ValueError("document_id is required for page extraction")

    document_uuid = UUID(document_id_value)
    normalized_page_number = _positive_int(
        payload.get("page_number") if payload else page_number,
        default=1,
    )
    normalized_prompt_version = (
        _string_value(payload.get("prompt_version") if payload else prompt_version)
        or DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION
    )
    normalized_content_hash = _string_value(
        payload.get("content_hash") if payload else content_hash
    )

    return PageExtractionContext(
        document_id=document_id_value,
        document_uuid=document_uuid,
        page_number=normalized_page_number,
        content_hash=normalized_content_hash or "",
        prompt_version=normalized_prompt_version,
        page_text=_string_value(payload.get("page_text")) or "",
        total_pages=_positive_int(
            payload.get("total_pages"),
            default=normalized_page_number,
        ),
        ai_provider=(_string_value(payload.get("ai_provider")) or DEFAULT_PAGE_EXTRACTION_PROVIDER),
        ai_model=(_string_value(payload.get("ai_model")) or DEFAULT_PAGE_EXTRACTION_MODEL),
        temperature=_float_value(payload.get("temperature"), default=0.3),
        bypass_cache=_bool_value(payload.get("bypass_cache")),
        source_language=_string_value(payload.get("source_language")) or "en",
        translation_status=(_string_value(payload.get("translation_status")) or "not_required"),
        translation_required=(_string_value(payload.get("translation_required")) or "false"),
    )


def _normalize_document_summary_context(
    *,
    document_id: dict[str, Any] | str,
    prompt_version: str | None,
) -> DocumentSummaryContext:
    payload = document_id if isinstance(document_id, dict) else {}
    document_id_value = _string_value(payload.get("document_id") if payload else document_id)
    if document_id_value is None:
        raise ValueError("document_id is required for full summary generation")

    normalized_prompt_version = (
        _string_value(payload.get("prompt_version") if payload else prompt_version)
        or DEFAULT_DOCUMENT_SUMMARY_PROMPT_VERSION
    )
    return DocumentSummaryContext(
        document_id=document_id_value,
        document_uuid=UUID(document_id_value),
        prompt_version=normalized_prompt_version,
        ai_provider=(
            _string_value(payload.get("ai_provider")) or DEFAULT_DOCUMENT_SUMMARY_PROVIDER
        ),
        ai_model=(_string_value(payload.get("ai_model")) or DEFAULT_DOCUMENT_SUMMARY_MODEL),
        bypass_cache=_bool_value(payload.get("bypass_cache")),
    )


def _normalize_stage_marker_context(
    *,
    document_id: dict[str, Any] | str,
    stage: str | None,
) -> StageMarkerContext:
    payload = document_id if isinstance(document_id, dict) else {}
    document_id_value = _string_value(payload.get("document_id") if payload else document_id)
    if document_id_value is None:
        raise ValueError("document_id is required for intake stage updates")

    stage_value = _string_value(payload.get("stage") if payload else stage)
    if stage_value not in INTAKE_STAGE_VALUES:
        raise ValueError(f"Unsupported intake stage: {stage_value}")

    return StageMarkerContext(
        document_id=document_id_value,
        document_uuid=UUID(document_id_value),
        stage=stage_value,
    )


def _normalize_pause_context(payload: dict[str, Any] | str) -> PauseContext:
    raw_payload = payload if isinstance(payload, dict) else {}
    document_id_value = _string_value(raw_payload.get("document_id") if raw_payload else payload)
    if document_id_value is None:
        raise ValueError("document_id is required for intake pause")

    retry_after_seconds = _positive_int(
        raw_payload.get("retry_after_seconds"),
        default=1,
    )
    paused_until = _datetime_value(raw_payload.get("paused_until"))
    if paused_until is None:
        paused_until = datetime.now(UTC)

    return PauseContext(
        document_id=document_id_value,
        document_uuid=UUID(document_id_value),
        retry_after_seconds=retry_after_seconds,
        paused_until=paused_until,
        error_code=(_string_value(raw_payload.get("error_code")) or "rate_limit"),
        error_message=(
            _string_value(raw_payload.get("error_message")) or "Rate limit encountered."
        ),
        current_concurrency=_positive_int(
            raw_payload.get("current_concurrency"),
            default=1,
        ),
    )


def _normalize_resume_context(payload: dict[str, Any] | str) -> ResumeContext:
    raw_payload = payload if isinstance(payload, dict) else {}
    document_id_value = _string_value(raw_payload.get("document_id") if raw_payload else payload)
    if document_id_value is None:
        raise ValueError("document_id is required for intake resume")

    return ResumeContext(
        document_id=document_id_value,
        document_uuid=UUID(document_id_value),
        current_concurrency=_positive_int(
            raw_payload.get("current_concurrency"),
            default=1,
        ),
    )


def _normalize_completed_pages_context(
    payload: dict[str, Any] | str,
) -> CompletedPagesContext:
    raw_payload = payload if isinstance(payload, dict) else {}
    document_id_value = _string_value(raw_payload.get("document_id") if raw_payload else payload)
    if document_id_value is None:
        raise ValueError("document_id is required for completed-page lookup")

    page_numbers = _page_numbers_from_completed_payload(raw_payload)
    prompt_version = (
        _string_value(raw_payload.get("prompt_version")) or DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION
    )
    ai_provider = _string_value(raw_payload.get("ai_provider")) or DEFAULT_PAGE_EXTRACTION_PROVIDER
    ai_model = _string_value(raw_payload.get("ai_model")) or DEFAULT_PAGE_EXTRACTION_MODEL
    total_pages = _positive_int(
        raw_payload.get("total_pages"),
        default=max(page_numbers) if page_numbers else 1,
    )
    content_hashes = {
        page_number: content_hash
        for page_number in page_numbers
        for content_hash in [_page_content_hash_from_payload(raw_payload, page_number)]
        if content_hash
    }
    return CompletedPagesContext(
        document_id=document_id_value,
        document_uuid=UUID(document_id_value),
        page_numbers=set(page_numbers),
        content_hashes=content_hashes,
        prompt_version=prompt_version,
        ai_provider=ai_provider,
        ai_model=ai_model,
        total_pages=total_pages,
        bypass_cache=_bool_value(raw_payload.get("bypass_cache")),
    )


def _normalize_action_plan_context(
    *,
    document_id: dict[str, Any] | str,
    prompt_version: str | None,
) -> ActionPlanContext:
    payload = document_id if isinstance(document_id, dict) else {}
    document_id_value = _string_value(payload.get("document_id") if payload else document_id)
    if document_id_value is None:
        raise ValueError("document_id is required for action-plan generation")

    normalized_prompt_version = (
        _string_value(payload.get("prompt_version") if payload else prompt_version)
        or DEFAULT_ACTION_PLAN_PROMPT_VERSION
    )
    return ActionPlanContext(
        document_id=document_id_value,
        document_uuid=UUID(document_id_value),
        prompt_version=normalized_prompt_version,
        ai_provider=(_string_value(payload.get("ai_provider")) or DEFAULT_ACTION_PLAN_PROVIDER),
        ai_model=(_string_value(payload.get("ai_model")) or DEFAULT_ACTION_PLAN_MODEL),
        temperature=_float_value(payload.get("temperature"), default=0.1),
        max_obligations=_positive_int(
            payload.get("max_obligations"),
            default=40,
        ),
    )


def _load_page_extraction_backend() -> PageExtractionBackend:
    _ensure_backend_src_on_path()
    from orderflow_api.api.extraction_job_persistence import (  # noqa: PLC0415
        fail_extraction_job,
        update_extraction_job_progress,
    )
    from orderflow_api.api.extraction_persistence import (  # noqa: PLC0415
        list_persisted_clauses,
        list_persisted_obligations,
    )
    from orderflow_api.api.geocoding_service import (  # noqa: PLC0415
        build_extracted_places,
        geocode_places,
    )
    from orderflow_api.api.page_summary_engine import (  # noqa: PLC0415
        PageSummaryExtractor,
    )
    from orderflow_api.api.page_summary_persistence import (  # noqa: PLC0415
        get_cached_page_summary,
        list_page_summaries,
        upsert_page_summary,
    )
    from orderflow_api.core.config import settings  # noqa: PLC0415
    from orderflow_api.core.hash_utils import (  # noqa: PLC0415
        calculate_page_content_hash,
    )

    return PageExtractionBackend(
        PageSummaryExtractor=PageSummaryExtractor,
        build_extracted_places=build_extracted_places,
        calculate_page_content_hash=calculate_page_content_hash,
        fail_extraction_job=fail_extraction_job,
        geocode_places=geocode_places,
        get_cached_page_summary=get_cached_page_summary,
        list_page_summaries=list_page_summaries,
        list_persisted_clauses=list_persisted_clauses,
        list_persisted_obligations=list_persisted_obligations,
        settings=settings,
        update_extraction_job_progress=update_extraction_job_progress,
        upsert_page_summary=upsert_page_summary,
    )


def _load_document_summary_backend() -> DocumentSummaryBackend:
    _ensure_backend_src_on_path()
    from orderflow_api.api import (  # noqa: PLC0415
        document_summary_persistence as dsp,
    )
    from orderflow_api.api.extraction_job_persistence import (  # noqa: PLC0415
        get_extraction_job,
        update_extraction_job_stage,
    )
    from orderflow_api.api.extraction_persistence import (  # noqa: PLC0415
        list_persisted_obligations,
    )
    from orderflow_api.api.page_summary_persistence import (  # noqa: PLC0415
        list_page_summaries,
    )

    return DocumentSummaryBackend(
        get_document_summary=dsp.get_document_summary,
        get_extraction_job=get_extraction_job,
        list_page_summaries=list_page_summaries,
        list_persisted_obligations=list_persisted_obligations,
        update_extraction_job_stage=update_extraction_job_stage,
        upsert_document_summary=dsp.upsert_document_summary,
    )


def _load_stage_marker_backend() -> StageMarkerBackend:
    _ensure_backend_src_on_path()
    from orderflow_api.api.extraction_job_persistence import (  # noqa: PLC0415
        update_extraction_job_stage,
    )

    return StageMarkerBackend(
        update_extraction_job_stage=update_extraction_job_stage,
    )


def _load_pause_backend() -> PauseResumeBackend:
    _ensure_backend_src_on_path()
    from orderflow_api.api.extraction_job_persistence import (  # noqa: PLC0415
        pause_extraction_job,
        resume_extraction_job,
    )

    return PauseResumeBackend(
        pause_extraction_job=pause_extraction_job,
        resume_extraction_job=resume_extraction_job,
    )


def _load_completed_pages_backend() -> CompletedPagesBackend:
    _ensure_backend_src_on_path()
    from orderflow_api.api.extraction_job_persistence import (  # noqa: PLC0415
        update_extraction_job_progress,
    )
    from orderflow_api.api.page_summary_persistence import (  # noqa: PLC0415
        list_page_summaries,
    )

    return CompletedPagesBackend(
        list_page_summaries=list_page_summaries,
        update_extraction_job_progress=update_extraction_job_progress,
    )


def _load_action_plan_backend() -> ActionPlanBackend:
    _ensure_backend_src_on_path()
    from orderflow_api.api.ai_extraction import (  # noqa: PLC0415
        maybe_extract_obligations_with_ai,
    )
    from orderflow_api.api.extraction_engine import (  # noqa: PLC0415
        ParsedClause,
        extract_obligations,
    )
    from orderflow_api.api.extraction_job_persistence import (  # noqa: PLC0415
        get_extraction_job,
        update_extraction_job_stage,
    )
    from orderflow_api.api.extraction_persistence import (  # noqa: PLC0415
        list_persisted_clauses,
        list_persisted_obligations,
        record_persisted_obligation_audit_event,
        replace_document_extraction,
        update_persisted_obligation,
    )
    from orderflow_api.schemas.extractions import (  # noqa: PLC0415
        IntakeAiOptions,
    )

    return ActionPlanBackend(
        IntakeAiOptions=IntakeAiOptions,
        ParsedClause=ParsedClause,
        extract_obligations=extract_obligations,
        get_extraction_job=get_extraction_job,
        list_persisted_clauses=list_persisted_clauses,
        list_persisted_obligations=list_persisted_obligations,
        maybe_extract_obligations_with_ai=maybe_extract_obligations_with_ai,
        record_persisted_obligation_audit_event=(record_persisted_obligation_audit_event),
        replace_document_extraction=replace_document_extraction,
        update_extraction_job_stage=update_extraction_job_stage,
        update_persisted_obligation=update_persisted_obligation,
    )


def _ensure_backend_src_on_path() -> None:
    app_root = Path(__file__).resolve().parents[4]
    backend_src = app_root / "backend" / "src"
    if backend_src.exists() and str(backend_src) not in sys.path:
        sys.path.insert(0, str(backend_src))


def _load_page_text_from_clauses(
    backend: PageExtractionBackend,
    context: PageExtractionContext,
) -> str:
    # Check if any clauses exist for this document at all (any page).
    # If not, the intake extraction step was never run; seed clauses from the PDF now.
    all_clauses = backend.list_persisted_clauses(document_id=context.document_uuid)
    if not all_clauses:
        _seed_clauses_from_pdf(context.document_uuid)

    clauses = backend.list_persisted_clauses(
        document_id=context.document_uuid,
        page_number=context.page_number,
    )
    return " ".join(
        clause.text.strip()
        for clause in clauses
        if (isinstance(getattr(clause, "text", None), str) and clause.text.strip())
    )


def _seed_clauses_from_pdf(document_uuid: UUID) -> None:
    """Fetch the document PDF from object storage, extract + segment text, and persist clauses.

    This runs when the page-extraction workflow fires before the frontend's
    intake-extraction step has had a chance to populate clauses in the DB.
    """
    _ensure_backend_src_on_path()
    try:
        from orderflow_api.api.document_persistence import (  # noqa: PLC0415
            get_persisted_document,
        )
        from orderflow_api.api.extraction_engine import (  # noqa: PLC0415
            decode_document_text,
            segment_clauses,
        )
        from orderflow_api.api.extraction_persistence import (  # noqa: PLC0415
            replace_document_extraction,
        )
        from orderflow_api.core.storage import (  # noqa: PLC0415
            build_object_storage_client,
            get_object_bytes,
        )

        document = get_persisted_document(document_uuid)
        if document is None or not document.object_key:
            return

        storage_client = build_object_storage_client()
        payload = get_object_bytes(storage_client, document.object_key)
        if not payload:
            return

        raw_text = decode_document_text(
            payload,
            document.source_file_type,
            document.source_file_name,
        )
        clauses = segment_clauses(raw_text=raw_text, document_id=document_uuid)
        if clauses:
            replace_document_extraction(
                document_id=document_uuid,
                clauses=clauses,
                obligations=[],
            )
    except Exception:
        # Swallow errors — caller will raise OCR error if text is still empty.
        pass


def _page_obligation_ids(
    backend: PageExtractionBackend,
    context: PageExtractionContext,
) -> list[UUID]:
    obligations = backend.list_persisted_obligations(context.document_uuid)
    ids: list[UUID] = []
    for obligation in obligations:
        citation = getattr(obligation, "citation", None)
        if citation is None or getattr(citation, "page_number", None) != context.page_number:
            continue
        obligation_id = getattr(obligation, "id", None)
        if isinstance(obligation_id, UUID):
            ids.append(obligation_id)
    return ids


def _ai_enrich_document_summary(
    *,
    context: Any,
    payload: dict[str, Any],
    api_key: str,
    page_summaries: list[Any],
) -> dict[str, Any] | None:
    """Use AI to enrich the document summary overview and key_directives."""
    _ensure_backend_src_on_path()

    # Build a concise prompt from page summaries
    summaries_text = ""
    for ps in page_summaries[:10]:
        summary_text = getattr(ps, "summary", None) or getattr(ps, "page_text", None) or ""
        if summary_text:
            summaries_text += f"Page {getattr(ps, 'page_number', '?')}: {summary_text[:500]}\n"

    if not summaries_text.strip():
        return None

    prompt = (
        "You are a legal document analyst. Given these page summaries of a court judgment, "
        "produce a concise but comprehensive overview and identify the key directives.\n\n"
        f"Page summaries:\n{summaries_text[:6000]}\n\n"
        "Return ONLY valid JSON with this structure:\n"
        '{"overview": "2-4 sentence synthesis of the judgment", '
        '"key_directives": [{"directive": "text of directive", '
        '"source_page": null, "urgency": "high|medium|low"}]}\n'
        "Keep key_directives to at most 8 items."
    )

    try:
        if context.ai_provider == "gemini":
            from orderflow_api.core.gemini_client import call_gemini_json, extract_gemini_text

            response = call_gemini_json(
                api_key=api_key,
                model=context.ai_model or "gemini-2.0-flash",
                prompt=prompt,
                temperature=0.2,
                max_output_tokens=2048,
                request_label="document_summary_enrichment",
            )
            text = extract_gemini_text(response)
        elif context.ai_provider == "groq":
            from orderflow_api.core.gemini_client import call_groq_json, extract_gemini_text

            response = call_groq_json(
                api_key=api_key,
                model=context.ai_model,
                prompt=prompt,
                temperature=0.2,
                request_label="document_summary_enrichment",
            )
            text = extract_gemini_text(response)
        else:
            return None

        import json as _json

        parsed = _json.loads(text)
        if not isinstance(parsed, dict):
            return None

        enriched = {**payload}
        if "overview" in parsed and isinstance(parsed["overview"], str) and parsed["overview"].strip():
            enriched["overview"] = parsed["overview"]
        if "key_directives" in parsed and isinstance(parsed["key_directives"], list):
            enriched["key_directives"] = parsed["key_directives"]
        return enriched

    except Exception:
        return None


def _build_document_summary_payload(
    *,
    context: DocumentSummaryContext,
    page_summaries: list[Any],
    obligations: list[Any],
) -> dict[str, Any]:
    case_basics = _extract_case_basics(page_summaries, obligations)
    overview = _build_document_overview(
        page_summaries,
        obligations,
        case_basics,
    )
    case_basics["main_subject"] = _first_key_point(page_summaries)
    case_basics["directive_summary"] = overview
    return {
        "case_basics": case_basics,
        "overview": overview,
        "key_directives": _build_key_directives(obligations),
        "important_dates": _build_important_dates(
            obligations,
            page_summaries,
        ),
        "entities_involved": _build_entities(obligations),
        "responsible_departments": _build_responsible_departments(obligations),
        "flow_graph": _build_flow_graph(
            context,
            page_summaries,
            obligations,
            case_basics,
        ),
        "map_data": _build_map_data(page_summaries),
        "confidence": _average_confidence([*page_summaries, *obligations]),
    }


def _extract_case_basics(
    page_summaries: list[Any],
    obligations: list[Any],
) -> dict[str, Any]:
    case_text = _case_text_from_summaries(page_summaries)
    petitioner, respondent = _extract_parties(case_text)
    case_number = _extract_case_number(case_text)
    court_name = _extract_court_name(case_text)
    case_type = _infer_case_type(case_number, case_text)
    order_date = _extract_order_date(case_text)
    judge_name = _extract_judge_name(case_text)
    department_involved = _infer_department_involved(obligations)
    return {
        "case_number": case_number,
        "court_name": court_name,
        "case_type": case_type,
        "order_date": order_date,
        "petitioner": petitioner,
        "respondent": respondent,
        "judge_name": judge_name,
        "department_involved": department_involved,
        "disposal_status": None,
        "main_subject": None,
        "directive_summary": None,
    }


def _case_text_from_summaries(
    page_summaries: list[Any],
    *,
    max_pages: int = 2,
    max_chars: int = 8000,
) -> str:
    def sort_key(summary: Any) -> int:
        page_number = getattr(summary, "page_number", None)
        return page_number if isinstance(page_number, int) else 9999

    parts: list[str] = []
    for summary in sorted(page_summaries, key=sort_key)[:max_pages]:
        page_text = _text_or_default(getattr(summary, "page_text", None), "")
        if not page_text:
            page_text = _text_or_default(getattr(summary, "summary", None), "")
        if not page_text:
            page_text = _text_or_default(
                getattr(summary, "source_excerpt", None),
                "",
            )
        if page_text:
            parts.append(page_text)

    combined = "\n".join(parts)
    if len(combined) > max_chars:
        combined = combined[:max_chars]
    return combined


def _extract_case_number(text: str) -> str | None:
    patterns = [
        r"\b([A-Z][A-Z.() /-]{1,30}No\.?\s*\d+[A-Z0-9/-]*)",
        r"\b(Case\s+No\.?\s*[:\-]?\s*[A-Za-z0-9/-]+)",
        r"\b(Writ\s+Petition\s*\(.*?\)?\s*No\.?\s*\d+[A-Za-z0-9/-]*)",
    ]
    return _first_regex_match(text, patterns)


def _extract_court_name(text: str) -> str | None:
    patterns = [
        r"IN\s+THE\s+([A-Z\s]+COURT[^\n]*)",
        r"(Supreme Court of India)",
        r"(High Court of [A-Za-z\s]+)",
        r"(High Court at [A-Za-z\s]+)",
        r"(District Court[^\n]*)",
        r"(Court of [A-Za-z\s]+)",
    ]
    return _first_regex_match(text, patterns, flags=re.IGNORECASE)


def _extract_order_date(text: str) -> str | None:
    dated_line = _first_regex_match(
        text,
        [
            r"Date of Order\s*[:\-]?\s*([^\n]+)",
            r"Order dated\s*[:\-]?\s*([^\n]+)",
            r"Judgment dated\s*[:\-]?\s*([^\n]+)",
            r"Dated\s*[:\-]?\s*([^\n]+)",
        ],
        flags=re.IGNORECASE,
    )
    if dated_line:
        date_match = _first_regex_match(
            dated_line,
            [
                r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
                r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b",
            ],
        )
        if date_match:
            return date_match

    return _first_regex_match(
        text,
        [
            r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
            r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b",
        ],
    )


def _extract_parties(text: str) -> tuple[str | None, str | None]:
    lines = _non_empty_lines(text)
    petitioner = _first_label_value(lines, "petitioner")
    respondent = _first_label_value(lines, "respondent")
    if petitioner or respondent:
        return petitioner, respondent

    versus_line = _first_regex_match(text, [r"(.+?)\s+v(?:s\.?|ersus)\s+(.+)"])
    if versus_line:
        parts = re.split(r"\s+v(?:s\.?|ersus)\s+", versus_line, flags=re.IGNORECASE)
        if len(parts) >= 2:
            return parts[0].strip() or None, parts[1].strip() or None
    return None, None


def _extract_judge_name(text: str) -> str | None:
    lines = _non_empty_lines(text)
    for line in lines:
        if "CORAM" in line.upper():
            after = line.split(":", 1)[-1].strip()
            if after:
                return after
    return _first_regex_match(
        text,
        [r"HON'BLE\s+[^\n,]+JUSTICE\s+[A-Za-z .]+"],
        flags=re.IGNORECASE,
    )


def _infer_case_type(case_number: str | None, text: str) -> str | None:
    haystack = f"{case_number or ''} {text}".upper()
    if "W.P." in haystack or "WP" in haystack or "WRIT PETITION" in haystack:
        return "Writ Petition"
    if "CWP" in haystack:
        return "Civil Writ Petition"
    if "SLP" in haystack or "S.L.P" in haystack:
        return "Special Leave Petition"
    if "CRIMINAL APPEAL" in haystack or "CRL" in haystack:
        return "Criminal Appeal"
    if "CIVIL APPEAL" in haystack:
        return "Civil Appeal"
    if "RFA" in haystack:
        return "Regular First Appeal"
    if "RSA" in haystack:
        return "Regular Second Appeal"
    if "LPA" in haystack:
        return "Letters Patent Appeal"
    if "OA" in haystack or "O.A." in haystack:
        return "Original Application"
    return None


def _infer_department_involved(obligations: list[Any]) -> str | None:
    counts: dict[str, int] = {}
    for obligation in obligations:
        owner = _text_or_default(getattr(obligation, "owner_hint", None), "")
        if not owner:
            continue
        counts[owner] = counts.get(owner, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def _first_label_value(lines: list[str], label: str) -> str | None:
    label_upper = label.upper()
    for line in lines:
        if label_upper not in line.upper():
            continue
        match = re.match(r"^(.*?)(?:\s+|\.{2,})" + label_upper + r"\b", line, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip(" .:-")
            if value:
                return value
        parts = re.split(r"\b" + label_upper + r"\b", line, flags=re.IGNORECASE)
        if len(parts) >= 2 and parts[0].strip():
            return parts[0].strip(" .:-")
        if len(parts) >= 2 and parts[1].strip():
            return parts[1].strip(" .:-")
    return None


def _first_regex_match(
    text: str,
    patterns: list[str],
    *,
    flags: int = 0,
) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if not match:
            continue
        if match.lastindex:
            return match.group(match.lastindex).strip()
        return match.group(0).strip()
    return None


def _non_empty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _build_document_overview(
    page_summaries: list[Any],
    obligations: list[Any],
    case_basics: dict[str, Any] | None = None,
) -> str:
    basics = case_basics or {}
    page_count = len(page_summaries)
    obligation_count = len(obligations)
    summary_parts = [
        _text_or_default(getattr(summary, "summary", None), "") for summary in page_summaries[:3]
    ]
    summary_text = " ".join(part for part in summary_parts if part)
    key_points = _collect_key_points(page_summaries)

    narrative: list[str] = []
    case_type = basics.get("case_type") or "a case"
    case_number = basics.get("case_number")
    court_name = basics.get("court_name")
    header = f"This judgment concerns {case_type}"
    if case_number:
        header = f"{header} (Case {case_number})"
    header += "."
    if court_name:
        header += f" It was heard by {court_name}."
    narrative.append(header)

    petitioner = basics.get("petitioner")
    respondent = basics.get("respondent")
    if petitioner or respondent:
        if petitioner and respondent:
            narrative.append(f"The petitioner {petitioner} filed the matter against {respondent}.")
        elif petitioner:
            narrative.append(f"The petitioner is {petitioner}.")
        elif respondent:
            narrative.append(f"The respondent is {respondent}.")

    order_date = basics.get("order_date")
    if order_date:
        narrative.append(f"The order date recorded is {order_date}.")

    if summary_text:
        narrative.append(_truncate_text(summary_text, 700))
    else:
        narrative.append("No page narrative was available in the cached page summaries.")

    if key_points:
        narrative.append("Key points noted: " f"{_truncate_text('; '.join(key_points), 240)}.")

    if obligations:
        obligation_titles = _collect_obligation_titles(obligations)
        if obligation_titles:
            narrative.append(
                "Key directions include: " f"{_truncate_text('; '.join(obligation_titles), 260)}."
            )

    narrative.append(
        f"Generated from {page_count} cached page summary record(s) and "
        f"{obligation_count} extracted obligation record(s)."
    )

    overview = " ".join(part for part in narrative if part)
    return _truncate_text(overview, 1200)


def _collect_key_points(page_summaries: list[Any]) -> list[str]:
    points: list[str] = []
    for summary in page_summaries:
        key_points = getattr(summary, "key_points", None)
        if not isinstance(key_points, list):
            continue
        for item in key_points:
            if isinstance(item, str) and item.strip():
                points.append(item.strip())
            if len(points) >= 5:
                return points
    return points


def _collect_obligation_titles(obligations: list[Any]) -> list[str]:
    titles: list[str] = []
    for obligation in obligations:
        title = _text_or_default(getattr(obligation, "title", None), "")
        if title:
            titles.append(title)
        if len(titles) >= 4:
            break
    return titles


def _first_key_point(page_summaries: list[Any]) -> str | None:
    for summary in page_summaries:
        key_points = getattr(summary, "key_points", None)
        if not isinstance(key_points, list):
            continue
        for item in key_points:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _build_key_directives(obligations: list[Any]) -> list[dict[str, Any]]:
    directives: list[dict[str, Any]] = []
    for obligation in obligations[:25]:
        title = _text_or_default(getattr(obligation, "title", None), "")
        description = _text_or_default(
            getattr(obligation, "description", None),
            "",
        )
        direction_text = title or description
        if not direction_text:
            continue
        page_number = _citation_page_number(obligation)
        inference_text = " ".join(part for part in [title, description] if part)
        directive_kind = _infer_directive_kind(inference_text)
        compliance_required = _infer_compliance_flag(directive_kind)
        directives.append(
            {
                "direction_text": _truncate_text(direction_text, 600),
                "source_page_number": page_number,
                "source_paragraph_reference": _citation_paragraph_reference(obligation),
                "source_excerpt": _truncate_text(description or title, 800),
                "confidence": _confidence_or_none(getattr(obligation, "confidence", None)),
                "directive_kind": directive_kind,
                "compliance_required": compliance_required,
                "source_evidence": _source_evidence(
                    page_number=page_number,
                    excerpt=description or title,
                    confidence=getattr(obligation, "confidence", None),
                ),
            }
        )
    return directives


def _infer_directive_kind(direction_text: str) -> str:
    normalized = direction_text.lower()
    if re.search(r"\b(may|should|recommended)\b", normalized):
        return "advisory"
    if re.search(
        r"\b(shall|must|directed to|ordered to|is directed to|are directed to)\b",
        normalized,
    ):
        return "mandatory"
    return "needs_review"


def _infer_compliance_flag(directive_kind: str) -> str:
    if directive_kind == "mandatory":
        return "yes"
    if directive_kind == "advisory":
        return "needs_review"
    return "needs_review"


def _citation_paragraph_reference(obligation: Any) -> str | None:
    citation = getattr(obligation, "citation", None)
    if citation is None:
        return None
    clause_span = getattr(citation, "clause_span", None)
    if isinstance(clause_span, str) and clause_span.strip():
        return clause_span.strip()
    clause_index = getattr(citation, "clause_index", None)
    if isinstance(clause_index, int):
        return f"Clause {clause_index}"
    return None


def _build_important_dates(
    obligations: list[Any],
    page_summaries: list[Any],
) -> list[dict[str, Any]]:
    dates: list[dict[str, Any]] = []
    for obligation in obligations:
        due_date = getattr(obligation, "due_date", None)
        if due_date is None:
            continue
        title = _text_or_default(
            getattr(obligation, "title", None),
            "Action item",
        )
        page_number = _citation_page_number(obligation)
        dates.append(
            {
                "label": f"{_truncate_text(title, 120)} due date",
                "date_text": (
                    due_date.isoformat() if hasattr(due_date, "isoformat") else str(due_date)
                ),
                "source": "obligation_due_date",
                "is_inferred": bool(
                    _text_or_default(
                        getattr(obligation, "deadline_source", None),
                        "",
                    )
                ),
                "confidence": _confidence_or_none(getattr(obligation, "confidence", None)),
                "source_evidence": _source_evidence(
                    page_number=page_number,
                    excerpt=title,
                    confidence=getattr(obligation, "confidence", None),
                ),
            }
        )
    timeline_dates = _extract_timeline_dates_from_pages(page_summaries)
    return [*dates, *timeline_dates][:25]


def _extract_timeline_dates_from_pages(
    page_summaries: list[Any],
    *,
    max_items: int = 10,
) -> list[dict[str, Any]]:
    timeline_dates: list[dict[str, Any]] = []
    for summary in page_summaries:
        page_text = _text_or_default(getattr(summary, "page_text", None), "")
        if not page_text:
            page_text = _text_or_default(getattr(summary, "summary", None), "")
        if not page_text:
            continue
        matches = re.findall(
            r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b",
            page_text,
        )
        for match in matches:
            timeline_dates.append(
                {
                    "label": "Referenced date",
                    "date_text": match,
                    "source": "page_summary_text",
                    "is_inferred": False,
                    "confidence": _confidence_or_none(getattr(summary, "confidence", None)),
                    "source_evidence": _source_evidence(
                        page_number=getattr(summary, "page_number", None),
                        excerpt=match,
                        confidence=getattr(summary, "confidence", None),
                    ),
                }
            )
            if len(timeline_dates) >= max_items:
                return timeline_dates
    return timeline_dates


def _build_entities(obligations: list[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    entities: list[dict[str, Any]] = []
    for obligation in obligations:
        owner = _text_or_default(getattr(obligation, "owner_hint", None), "")
        if not owner:
            continue
        key = owner.lower()
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            {
                "name": owner,
                "entity_type": "department",
                "role": "responsible_owner",
                "source_page_number": _citation_page_number(obligation),
                "confidence": _confidence_or_none(getattr(obligation, "confidence", None)),
                "metadata": {
                    "source": "obligation_owner_hint",
                    "source_evidence": _source_evidence(
                        page_number=_citation_page_number(obligation),
                        excerpt=getattr(obligation, "title", None),
                        confidence=getattr(obligation, "confidence", None),
                    ),
                },
            }
        )
    return entities


def _build_responsible_departments(
    obligations: list[Any],
) -> list[dict[str, Any]]:
    departments: dict[str, list[Any]] = {}
    for obligation in obligations:
        owner = _text_or_default(
            getattr(obligation, "owner_hint", None),
            "Unassigned",
        )
        departments.setdefault(owner, []).append(obligation)

    return [
        {
            "primary_department": owner,
            "supporting_departments": [],
            "legal_department_role": None,
            "petitioner": _text_or_default(
                getattr(items[0], "petitioner", None),
                None,
            ),
            "respondent": _text_or_default(
                getattr(items[0], "respondent", None),
                None,
            ),
            "reason": f"{len(items)} action item(s) reference this owner.",
            "source_evidence": _source_evidence(
                page_number=_citation_page_number(items[0]),
                excerpt=getattr(items[0], "title", None),
                confidence=getattr(items[0], "confidence", None),
            ),
        }
        for owner, items in sorted(departments.items())
    ]


def _build_flow_graph(
    context: DocumentSummaryContext,
    page_summaries: list[Any],
    obligations: list[Any],
    case_basics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    basics = case_basics or {}
    petitioner = _text_or_default(basics.get("petitioner"), "")
    respondent = _text_or_default(basics.get("respondent"), "")
    nodes = [
        {
            "id": "judgment",
            "node_type": "order",
            "label": "Judgment",
            "detail": "Source judgment document",
            "page_ref": None,
        }
    ]
    edges: list[dict[str, str]] = []

    party_node_ids: list[str] = []
    for label, detail in ((petitioner, "Petitioner"), (respondent, "Respondent")):
        if not label:
            continue
        node_id = f"party-{len(party_node_ids) + 1}"
        party_node_ids.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "node_type": "party",
                "label": label,
                "detail": detail,
                "page_ref": None,
            }
        )

    ordered_summaries = sorted(
        page_summaries,
        key=lambda summary: getattr(summary, "page_number", 9999),
    )
    event_node_ids: list[str] = []

    for summary in ordered_summaries[:30]:
        page_number = getattr(summary, "page_number", None)
        if not isinstance(page_number, int):
            continue
        page_id = f"page-{page_number}"
        event_node_ids.append(page_id)
        nodes.append(
            {
                "id": page_id,
                "node_type": "event",
                "label": f"Page {page_number}",
                "detail": _truncate_text(
                    getattr(summary, "summary", "") or "",
                    180,
                ),
                "page_ref": page_number,
            }
        )
        edges.append(
            {
                "id": f"judgment-to-{page_id}",
                "source": "judgment",
                "target": page_id,
                "relation": "contains",
            }
        )

    for party_node_id in party_node_ids:
        if event_node_ids:
            edges.append(
                {
                    "id": f"{party_node_id}->{event_node_ids[0]}",
                    "source": party_node_id,
                    "target": event_node_ids[0],
                    "relation": "involved_in",
                }
            )

    for left, right in zip(event_node_ids, event_node_ids[1:]):
        edges.append(
            {
                "id": f"{left}->{right}",
                "source": left,
                "target": right,
                "relation": "next",
            }
        )

    order_node_ids: list[str] = []
    for summary in ordered_summaries:
        summary_text = _text_or_default(getattr(summary, "summary", None), "")
        if not re.search(
            r"\b(order|directed|dispose|allowed|dismissed)\b",
            summary_text,
            re.IGNORECASE,
        ):
            continue
        page_number = getattr(summary, "page_number", None)
        node_id = f"order-{len(order_node_ids) + 1}"
        order_node_ids.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "node_type": "order",
                "label": "Court order",
                "detail": _truncate_text(summary_text, 180),
                "page_ref": page_number if isinstance(page_number, int) else None,
            }
        )

    for order_node_id in order_node_ids:
        if event_node_ids:
            edges.append(
                {
                    "id": f"{event_node_ids[-1]}->{order_node_id}",
                    "source": event_node_ids[-1],
                    "target": order_node_id,
                    "relation": "results_in",
                }
            )

    for index, obligation in enumerate(obligations[:30], start=1):
        obligation_id = f"obligation-{index}"
        page_number = _citation_page_number(obligation)
        nodes.append(
            {
                "id": obligation_id,
                "node_type": "obligation",
                "label": _truncate_text(
                    getattr(obligation, "title", "") or "",
                    120,
                ),
                "detail": _truncate_text(
                    getattr(obligation, "description", "") or "",
                    180,
                ),
                "page_ref": page_number,
            }
        )
        edges.append(
            {
                "id": f"support-{obligation_id}",
                "source": (
                    f"page-{page_number}"
                    if page_number and f"page-{page_number}" in event_node_ids
                    else (order_node_ids[-1] if order_node_ids else "judgment")
                ),
                "target": obligation_id,
                "relation": "creates",
            }
        )

    return {
        "document_id": context.document_id,
        "nodes": nodes,
        "edges": edges,
        "narrative_steps": [
            f"Summarized {len(page_summaries)} cached page(s).",
            f"Linked {len(obligations)} extracted obligation(s).",
        ],
    }


def _build_map_data(page_summaries: list[Any]) -> dict[str, Any]:
    places: list[dict[str, Any]] = []
    geocoded: list[dict[str, Any]] = []
    seen: set[str] = set()
    distinct_districts: set[str] = set()
    distinct_pages: set[int] = set()

    for summary in page_summaries:
        for place in getattr(summary, "extracted_places", []) or []:
            payload = place.model_dump(mode="json") if hasattr(place, "model_dump") else dict(place)
            key = str(payload.get("normalized_name") or payload.get("name") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            places.append(payload)

            lat = payload.get("lat")
            lng = payload.get("lng")
            if lat is None or lng is None:
                continue

            geocoded.append(payload)
            district = str(
                payload.get("district")
                or payload.get("normalized_name")
                or payload.get("name")
                or ""
            ).strip()
            if district:
                distinct_districts.add(district.lower())

            page_number = payload.get("source_page_number")
            if isinstance(page_number, int):
                distinct_pages.add(page_number)

    if len(geocoded) < 3:
        return {
            "available": False,
            "reason": ("Map flow not generated: fewer than 3 geocoded places were " "available."),
            "places": [],
            "flow": [],
        }

    if len(distinct_districts) < 2:
        return {
            "available": False,
            "reason": (
                "Map flow not generated: fewer than 2 distinct districts or "
                "cities were detected."
            ),
            "places": [],
            "flow": [],
        }

    if len(distinct_pages) < 2:
        return {
            "available": False,
            "reason": (
                "Map flow not generated: location evidence was limited to a " "single page."
            ),
            "places": [],
            "flow": [],
        }

    return {
        "available": True,
        "reason": "Built from place mentions already extracted at page level.",
        "places": geocoded[:50],
        "flow": [],
    }


def _source_evidence(
    *,
    page_number: int | None,
    excerpt: object,
    confidence: object,
) -> list[dict[str, Any]]:
    return [
        {
            "page_number": page_number,
            "source_excerpt": _truncate_text(
                _text_or_default(excerpt, ""),
                800,
            ),
            "confidence": _confidence_or_none(confidence),
        }
    ]


def _citation_page_number(obligation: Any) -> int | None:
    citation = getattr(obligation, "citation", None)
    page_number = getattr(citation, "page_number", None)
    return page_number if isinstance(page_number, int) else None


def _average_confidence(items: list[Any]) -> float | None:
    values = [
        float(value)
        for item in items
        for value in [getattr(item, "confidence", None)]
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _confidence_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and 0 <= float(value) <= 1:
        return float(value)
    return None


def _truncate_text(value: object, max_chars: int) -> str:
    text = _text_or_default(value, "")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _update_page_extraction_progress(
    *,
    backend: PageExtractionBackend,
    context: PageExtractionContext,
    summary_record: Any,
    cache_status: str,
) -> Any:
    completed_pages = _completed_page_numbers(backend, context)
    pages_completed = len(completed_pages)
    pages_total = max(
        context.total_pages,
        pages_completed,
        max(completed_pages) if completed_pages else context.page_number,
    )
    job = backend.update_extraction_job_progress(
        context.document_uuid,
        pages_total=pages_total,
        pages_completed=pages_completed,
        current_page=context.page_number,
        current_page_excerpt=_page_progress_excerpt(
            context=context,
            summary_record=summary_record,
            cache_status=cache_status,
        ),
    )
    if job is None:
        raise ValueError(f"Extraction job not found: {context.document_id}")
    return job


def _record_page_extraction_failure(
    *,
    backend: PageExtractionBackend,
    context: PageExtractionContext,
    error: Exception,
) -> None:
    completed_pages = _completed_page_numbers(
        backend,
        context,
        include_current=False,
    )
    pages_completed = len(completed_pages)
    pages_total = max(
        context.total_pages,
        pages_completed,
        max(completed_pages) if completed_pages else context.page_number,
    )
    user_error = _user_facing_page_error(
        error,
        page_number=context.page_number,
        pages_completed=pages_completed,
        pages_total=pages_total,
    )
    error_excerpt = {
        "page_number": context.page_number,
        "cache_status": "failed",
        "error_code": user_error.code,
        "error_category": user_error.category,
        "error_message": user_error.message,
        "partial_failure": user_error.partial_failure,
        "technical_error_type": type(error).__name__,
        "content_hash": context.content_hash or None,
        "source_excerpt": _truncate_text(context.page_text, 360) or None,
        "trace": _trace_attributes(
            document_id=context.document_id,
            workflow_stage="pages_extracting",
            page_number=context.page_number,
            cache_status="failed",
        ),
    }

    try:
        backend.update_extraction_job_progress(
            context.document_uuid,
            pages_total=pages_total,
            pages_completed=pages_completed,
            current_page=context.page_number,
            current_page_excerpt=error_excerpt,
        )
    except Exception:
        pass

    try:
        backend.fail_extraction_job(
            context.document_uuid,
            error_code=user_error.code,
            error_message=user_error.message,
        )
    except Exception:
        pass


def _user_facing_page_error(
    error: Exception,
    *,
    page_number: int | None,
    pages_completed: int = 0,
    pages_total: int = 0,
) -> UserFacingPageError:
    code = _string_value(getattr(error, "code", None)) or ""
    text = f"{code} {type(error).__name__} {error}".lower()
    partial_failure = pages_completed > 0

    if _matches_any(text, ("ocr", "no readable text layer", "text-readable pdf")):
        result = UserFacingPageError(
            code="ocr_required",
            category="ocr_failure",
            message=(
                "This PDF page could not be read as text. Run OCR or upload a "
                "text-readable PDF, then restart intake."
            ),
            partial_failure=partial_failure,
        )
    elif _matches_any(text, ("invalid_json", "invalid json", "jsondecodeerror")):
        result = UserFacingPageError(
            code="ai_invalid_json",
            category="invalid_ai_json",
            message=(
                "AI response was not valid JSON. Retry intake; completed pages "
                "will be reused."
            ),
            partial_failure=partial_failure,
        )
    elif _matches_any(text, ("timeout", "timed out")):
        result = UserFacingPageError(
            code="ai_timeout",
            category="timeout",
            message=(
                "AI provider timed out while extracting this page. Retry intake; "
                "completed pages will be reused."
            ),
            partial_failure=partial_failure,
        )
    elif _matches_any(
        text,
        ("network", "connection", "dns", "tls", "ssl", "refused", "unreachable"),
    ):
        result = UserFacingPageError(
            code="ai_network_error",
            category="network",
            message=(
                "Network problem while contacting the AI provider. Check "
                "connectivity and retry; completed pages will be reused."
            ),
            partial_failure=partial_failure,
        )
    elif _matches_any(text, ("tpm", "token-per-minute", "tokens_per_minute")):
        result = UserFacingPageError(
            code="ai_rate_limit_tpm",
            category="tpm_limit",
            message=(
                "AI TPM limit reached. Reduce concurrency or prompt size, then "
                "retry after the pause."
            ),
            partial_failure=partial_failure,
        )
    elif _retry_after_seconds(error) is not None or _matches_any(
        text,
        ("rpm", "request-per-minute", "requests_per_minute", "rate limit", "quota"),
    ):
        result = UserFacingPageError(
            code="ai_rate_limit_rpm",
            category="rpm_limit",
            message=(
                "AI RPM limit reached. OrderFlow paused intake and will retry "
                "when capacity is available."
            ),
            partial_failure=partial_failure,
        )
    elif partial_failure:
        result = UserFacingPageError(
            code="partial_page_failure",
            category="partial_page_failure",
            message="Retry intake; completed pages will be reused.",
            partial_failure=True,
        )
    else:
        page = f"Page {page_number}" if page_number is not None else "This page"
        result = UserFacingPageError(
            code="page_extraction_failed",
            category="page_extraction_failed",
            message=f"{page} could not be extracted. Retry intake or inspect the PDF.",
            partial_failure=False,
        )

    if partial_failure:
        progress = _partial_failure_prefix(
            page_number=page_number,
            pages_completed=pages_completed,
            pages_total=pages_total,
        )
        return UserFacingPageError(
            code=result.code,
            category=result.category,
            message=f"{progress} {result.message}",
            partial_failure=True,
        )
    return result


def _matches_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _partial_failure_prefix(
    *,
    page_number: int | None,
    pages_completed: int,
    pages_total: int,
) -> str:
    page = f"Page {page_number}" if page_number is not None else "A page"
    total = f" of {pages_total}" if pages_total > 0 else ""
    plural = "" if pages_completed == 1 else "s"
    verb = "was" if pages_completed == 1 else "were"
    return f"{page} failed after {pages_completed}{total} page{plural} {verb} saved."


def _rate_limit_application_error(
    error: Exception,
) -> temporal_exceptions.ApplicationError | None:
    retry_after_seconds = _retry_after_seconds(error)
    if retry_after_seconds is None:
        return None

    user_error = _user_facing_page_error(error, page_number=None)
    return temporal_exceptions.ApplicationError(
        "Rate limit encountered",
        {
            "retry_after_seconds": retry_after_seconds,
            "error_code": user_error.code,
            "error_category": user_error.category,
            "error_message": user_error.message,
        },
        type="rate_limit",
        non_retryable=True,
    )


def _retry_after_seconds(error: Exception) -> int | None:
    retry_after = getattr(error, "retry_after_seconds", None)
    if isinstance(retry_after, bool):
        return None
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        return int(max(1, retry_after))
    return None


def _completed_page_numbers(
    backend: PageExtractionBackend,
    context: PageExtractionContext,
    *,
    include_current: bool = True,
) -> set[int]:
    page_numbers = {
        page_number
        for summary in backend.list_page_summaries(context.document_uuid)
        for page_number in [getattr(summary, "page_number", None)]
        if isinstance(page_number, int) and page_number >= 1
    }
    if include_current:
        page_numbers.add(context.page_number)
    return page_numbers


def _page_progress_excerpt(
    *,
    context: PageExtractionContext,
    summary_record: Any,
    cache_status: str,
) -> dict[str, Any]:
    payload = _record_payload(summary_record)
    summary_id = payload.get("id")
    return {
        "page_number": context.page_number,
        "cache_status": cache_status,
        "summary_id": str(summary_id) if summary_id is not None else None,
        "content_hash": context.content_hash or payload.get("content_hash"),
        "source_excerpt": _truncate_text(
            payload.get("source_excerpt") or payload.get("summary") or context.page_text,
            360,
        ),
    }


def _filter_action_plan_items(obligations: list[Any]) -> list[Any]:
    return [
        obligation
        for obligation in obligations
        if getattr(obligation, "action_plan_stage", None) in ACTION_PLAN_ITEM_STAGES
    ]


def _filter_extracted_obligations(obligations: list[Any]) -> list[Any]:
    return [
        obligation
        for obligation in obligations
        if getattr(obligation, "action_plan_stage", "extracted") == "extracted"
    ]


def _action_plan_generation_metadata(
    context: ActionPlanContext,
) -> dict[str, dict[str, str]]:
    return {
        "action_plan_generation": {
            "prompt_version": context.prompt_version,
            "ai_provider": context.ai_provider,
            "ai_model": context.ai_model,
        }
    }


def _action_plan_metadata(
    context: ActionPlanContext,
    obligation: Any,
) -> dict[str, dict[str, object]]:
    metadata: dict[str, dict[str, object]] = {
        **_action_plan_generation_metadata(context),
        "action_plan_source_evidence": _action_plan_source_evidence_status(obligation),
    }
    guardrail = _appeal_guardrail_metadata(obligation)
    if guardrail:
        metadata["appeal_language_guardrail"] = guardrail
    return metadata


def _action_plan_source_evidence_status(obligation: Any) -> dict[str, object]:
    source_evidence = _first_source_evidence_payload(obligation)
    page_number = _citation_page_number(obligation) or _positive_int(
        source_evidence.get("page_number"),
        default=0,
    )
    if page_number <= 0:
        page_number = None

    source_excerpt = _text_or_default(
        source_evidence.get("excerpt") or source_evidence.get("source_excerpt"),
        "",
    )
    confidence = _confidence_or_none(getattr(obligation, "confidence", None))

    missing_fields = []
    if page_number is None:
        missing_fields.append("source_page")
    if not source_excerpt:
        missing_fields.append("source_excerpt")
    if confidence is None:
        missing_fields.append("confidence")

    return {
        "status": "needs_human_review" if missing_fields else "ready",
        "missing_fields": missing_fields,
        "page_number": page_number,
        "source_excerpt": _truncate_text(source_excerpt, 360) if source_excerpt else None,
        "confidence": confidence,
    }


def _first_source_evidence_payload(obligation: Any) -> dict[str, Any]:
    metadata = _mapping_or_empty(getattr(obligation, "metadata", None))
    source_evidence = metadata.get("source_evidence")
    if isinstance(source_evidence, dict):
        return source_evidence
    if isinstance(source_evidence, list):
        for item in source_evidence:
            if isinstance(item, dict):
                return item
    return {}


def _appeal_guardrail_text_updates(
    obligation: Any,
    nature_of_action: str,
) -> dict[str, str]:
    if nature_of_action != "appeal_review":
        return {}

    title = _text_or_default(getattr(obligation, "title", None), "")
    description = _text_or_default(getattr(obligation, "description", None), "")
    if _has_appeal_guardrail(title) and _has_appeal_guardrail(description):
        return {}

    source_excerpt = _text_or_default(
        _first_source_evidence_payload(obligation).get("excerpt"),
        description or title,
    )
    safe_description = (
        "Review possible appeal, review, limitation, or legal-remedy options with "
        "authorized legal counsel before any filing. This is not final legal advice."
    )
    if source_excerpt:
        safe_description = (
            f"{safe_description} Source basis: {_truncate_text(source_excerpt, 220)}"
        )

    return {
        "title": "Legal review for appeal or review remedy",
        "description": safe_description,
    }


def _appeal_guardrail_metadata(obligation: Any) -> dict[str, object]:
    text = " ".join(
        part
        for part in [
            _text_or_default(getattr(obligation, "title", None), ""),
            _text_or_default(getattr(obligation, "description", None), ""),
        ]
        if part
    ).lower()
    if not any(term in text for term in ("appeal", "review petition", "limitation")):
        return {}
    return {
        "status": "legal_review_required",
        "message": (
            "This action item is not final legal advice; verify remedy, "
            "limitation, and filing strategy with authorized legal counsel."
        ),
    }


def _has_appeal_guardrail(text: str) -> bool:
    lowered = text.lower()
    return (
        "not final legal advice" in lowered
        or "not legal advice" in lowered
        or "authorized legal counsel" in lowered
    )


def _action_plan_cache_matches_context(
    action_items: list[Any],
    context: ActionPlanContext,
) -> bool:
    return bool(action_items) and all(
        _action_plan_item_matches_context(item, context) for item in action_items
    )


def _action_plan_item_matches_context(
    obligation: Any,
    context: ActionPlanContext,
) -> bool:
    metadata = _mapping_or_empty(getattr(obligation, "metadata", None))
    generation = _mapping_or_empty(metadata.get("action_plan_generation"))
    return (
        generation.get("prompt_version") == context.prompt_version
        and generation.get("ai_provider") == context.ai_provider
        and generation.get("ai_model") == context.ai_model
    )


def _mapping_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_obligations_for_action_plan(
    backend: ActionPlanBackend,
    context: ActionPlanContext,
) -> tuple[list[Any], str, str | None]:
    clauses = backend.list_persisted_clauses(context.document_uuid)
    if not clauses:
        return [], "no_clauses", "No persisted clauses were available."

    parsed_clauses = _to_parsed_clauses(backend, clauses)
    ai_options = backend.IntakeAiOptions(
        enabled=True,
        provider=_ai_provider_option(context.ai_provider),
        model=context.ai_model,
        temperature=context.temperature,
        max_obligations=context.max_obligations,
    )
    ai_attempt = backend.maybe_extract_obligations_with_ai(
        clauses=parsed_clauses,
        document_id=context.document_uuid,
        ai_options=ai_options,
    )
    parsed_obligations = list(getattr(ai_attempt, "obligations", []) or [])
    extraction_mode = "ai" if getattr(ai_attempt, "used_ai", False) else ""
    if not parsed_obligations:
        parsed_obligations = backend.extract_obligations(
            clauses=parsed_clauses,
            document_id=context.document_uuid,
        )
        extraction_mode = (
            "ai_fallback" if getattr(ai_attempt, "attempted", False) else "deterministic"
        )

    if not parsed_obligations:
        return [], extraction_mode, getattr(ai_attempt, "reason", None)

    _, persisted_obligations = backend.replace_document_extraction(
        document_id=context.document_uuid,
        clauses=parsed_clauses,
        obligations=parsed_obligations,
    )
    ai_reason = getattr(ai_attempt, "reason", None)
    return persisted_obligations, extraction_mode, ai_reason


def _to_parsed_clauses(
    backend: ActionPlanBackend,
    clauses: list[Any],
) -> list[Any]:
    parsed_clauses = []
    for clause in clauses:
        text = _text_or_default(getattr(clause, "text", None), "")
        normalized = _text_or_default(
            getattr(clause, "normalized_text", None),
            text,
        )
        if not text and not normalized:
            continue
        parsed_clauses.append(
            backend.ParsedClause(
                id=clause.id,
                document_id=clause.document_id,
                clause_index=clause.clause_index,
                page_number=getattr(clause, "page_number", None),
                span_start=getattr(clause, "span_start", None),
                span_end=getattr(clause, "span_end", None),
                text=text or normalized,
                normalized_text=normalized or text,
                confidence=_confidence_or_none(getattr(clause, "confidence", None)) or 0.68,
            )
        )
    return parsed_clauses


def _ai_provider_option(provider: str) -> str | None:
    if provider in {"openai", "anthropic", "gemini", "groq"}:
        return provider
    return None


def _mark_summary_done(
    backend: DocumentSummaryBackend,
    context: DocumentSummaryContext,
) -> str:
    current_job = backend.get_extraction_job(context.document_uuid)
    current_stage = getattr(current_job, "stage", None)
    if current_stage in SUMMARY_DONE_STAGES:
        return str(current_stage)

    job = backend.update_extraction_job_stage(
        context.document_uuid,
        "summary_done",
    )
    if job is None:
        raise ValueError(f"Extraction job not found: {context.document_id}")
    return str(getattr(job, "stage", "summary_done"))


def _mark_action_plan_done(
    backend: ActionPlanBackend,
    context: ActionPlanContext,
) -> str:
    current_job = backend.get_extraction_job(context.document_uuid)
    current_stage = getattr(current_job, "stage", None)
    if current_stage in ACTION_PLAN_DONE_STAGES:
        return str(current_stage)

    job = backend.update_extraction_job_stage(
        context.document_uuid,
        "action_plan_done",
    )
    if job is None:
        raise ValueError(f"Extraction job not found: {context.document_id}")
    return str(getattr(job, "stage", "action_plan_done"))


def _record_action_plan_generation_audit(
    *,
    backend: ActionPlanBackend,
    context: ActionPlanContext,
    obligation: Any,
    nature_of_action: str,
) -> None:
    try:
        backend.record_persisted_obligation_audit_event(
            obligation_id=obligation.id,
            action="action_plan.item.generated",
            actor_type="system",
            actor_id="orderflow_worker",
            request_id=None,
            payload={
                "document_id": context.document_id,
                "prompt_version": context.prompt_version,
                "ai_provider": context.ai_provider,
                "ai_model": context.ai_model,
                "action_plan_stage": "in_action_plan",
                "nature_of_action": nature_of_action,
            },
        )
    except Exception:
        pass


def _classify_nature_of_action(obligation: Any) -> str:
    text = " ".join(
        part
        for part in [
            _text_or_default(getattr(obligation, "title", None), ""),
            _text_or_default(getattr(obligation, "description", None), ""),
        ]
        if part
    ).lower()
    if not text:
        return "other"

    checks = [
        (
            "appeal_review",
            (
                "appeal",
                "review petition",
                "review application",
                "legal review",
                "limitation",
            ),
        ),
        ("payment", ("payment", "pay ", "arrear", "salary", "pension")),
        ("payment", ("compensation", "refund", "amount", "costs")),
        ("appointment", ("appoint", "appointment", "recruit", "posting")),
        ("compliance_report", ("compliance report", "status report")),
        ("report_filing", ("file report", "submit report", "affidavit")),
        ("document_submission", ("produce", "submit document", "furnish")),
        ("submission", ("submit", "file ", "representation")),
        ("policy", ("policy", "scheme", "guideline", "circular")),
        (
            "reconsideration",
            ("reconsider", "consider afresh", "fresh consideration"),
        ),
        ("hearing", ("hearing", "personal hearing", "oral hearing")),
        ("record_update", ("record", "register", "mutation", "update")),
        ("notice", ("notice", "notify", "intimation")),
        ("investigation", ("inquiry", "investigation", "enquiry")),
        ("compliance", ("comply", "compliance", "implement")),
        ("directive", ("directed", "ordered", "shall", "must")),
    ]
    for nature, keywords in checks:
        if any(keyword in text for keyword in keywords):
            return nature
    return "other"


def _trace_attributes(
    *,
    document_id: str,
    workflow_stage: str | None = None,
    page_number: int | None = None,
    cache_status: str | None = None,
    retry_state: str | None = None,
    retry_after_seconds: int | None = None,
    paused_until: str | None = None,
    current_concurrency: int | None = None,
) -> dict[str, str | int]:
    attributes: dict[str, str | int] = {"orderflow.document_id": document_id}
    if workflow_stage:
        attributes["orderflow.workflow.stage"] = workflow_stage
    if page_number is not None:
        attributes["orderflow.page_number"] = page_number
    if cache_status:
        attributes["orderflow.cache.status"] = cache_status
    if retry_state:
        attributes["orderflow.retry.state"] = retry_state
    if retry_after_seconds is not None:
        attributes["orderflow.retry.after_seconds"] = retry_after_seconds
    if paused_until:
        attributes["orderflow.retry.paused_until"] = paused_until
    if current_concurrency is not None:
        attributes["orderflow.concurrency.current"] = current_concurrency
    return attributes


def _log_worker_cache_hit(
    *,
    document_id: str,
    resource: str,
    workflow_stage: str,
    cache_status: str,
    prompt_version: str | None = None,
    ai_provider: str | None = None,
    ai_model: str | None = None,
    page_number: int | None = None,
    summary_id: object | None = None,
    hit_count: int | None = None,
    page_numbers: list[int] | None = None,
    job_stage: str | None = None,
) -> None:
    attributes: dict[str, object] = {
        "orderflow.document_id": document_id,
        "orderflow.workflow.stage": workflow_stage,
        "orderflow.cache.status": cache_status,
        "orderflow.cache.resource": resource,
    }
    if prompt_version:
        attributes["orderflow.prompt_version"] = prompt_version
    if ai_provider:
        attributes["orderflow.ai_provider"] = ai_provider
    if ai_model:
        attributes["orderflow.ai_model"] = ai_model
    if page_number is not None:
        attributes["orderflow.page_number"] = page_number
    if summary_id is not None:
        attributes["orderflow.summary_id"] = str(summary_id)
    if hit_count is not None:
        attributes["orderflow.cache.hit_count"] = hit_count
    if page_numbers is not None:
        attributes["orderflow.page_numbers"] = page_numbers
    if job_stage:
        attributes["orderflow.job_stage"] = job_stage

    logger.info("orderflow_worker_cache_hit", extra={"orderflow": attributes})


def _page_extraction_result(
    *,
    context: PageExtractionContext,
    cache_status: str,
    summary_record: Any,
    job_progress: Any,
) -> dict[str, Any]:
    summary_payload = _record_payload(summary_record)
    progress_payload = _record_payload(job_progress)
    return {
        "document_id": context.document_id,
        "page_number": str(context.page_number),
        "content_hash": context.content_hash,
        "prompt_version": context.prompt_version,
        "cache_status": cache_status,
        "trace": _trace_attributes(
            document_id=context.document_id,
            workflow_stage="pages_extracting",
            page_number=context.page_number,
            cache_status=cache_status,
        ),
        "summary_id": summary_payload.get("id"),
        "summary": summary_payload.get("summary"),
        "confidence": summary_payload.get("confidence"),
        "ai_model": summary_payload.get("ai_model"),
        "ai_provider": summary_payload.get("ai_provider"),
        "summary_record": summary_payload,
        "source_language": context.source_language,
        "translation_status": context.translation_status,
        "translation_required": context.translation_required,
        "job_progress": progress_payload,
    }


def _document_summary_result(
    *,
    context: DocumentSummaryContext,
    cache_status: str,
    summary_record: Any,
    job_stage: str | None,
) -> dict[str, Any]:
    summary_payload = (
        summary_record.model_dump(mode="json")
        if hasattr(summary_record, "model_dump")
        else dict(summary_record)
    )
    return {
        "document_id": context.document_id,
        "prompt_version": context.prompt_version,
        "cache_status": cache_status,
        "trace": _trace_attributes(
            document_id=context.document_id,
            workflow_stage=job_stage or "summary_done",
            cache_status=cache_status,
        ),
        "summary_id": summary_payload.get("id"),
        "overview": summary_payload.get("overview"),
        "confidence": summary_payload.get("confidence"),
        "ai_model": summary_payload.get("ai_model"),
        "ai_provider": summary_payload.get("ai_provider"),
        "job_stage": job_stage,
        "summary_record": summary_payload,
    }


def _action_plan_result(
    *,
    context: ActionPlanContext,
    cache_status: str,
    action_items: list[Any],
    job_stage: str,
    extraction_mode: str,
    ai_reason: str | None,
) -> dict[str, Any]:
    item_payloads = [_record_payload(item) for item in action_items]
    return {
        "document_id": context.document_id,
        "prompt_version": context.prompt_version,
        "cache_status": cache_status,
        "trace": _trace_attributes(
            document_id=context.document_id,
            workflow_stage=job_stage,
            cache_status=cache_status,
        ),
        "action_item_count": len(item_payloads),
        "job_stage": job_stage,
        "extraction_mode": extraction_mode,
        "ai_provider": context.ai_provider,
        "ai_model": context.ai_model,
        "ai_reason": ai_reason,
        "items": item_payloads,
    }


def _completed_pages_result(
    context: CompletedPagesContext,
    completed_pages: list[dict[str, Any]],
    job_progress: Any,
) -> dict[str, Any]:
    page_numbers = [item["page_number"] for item in completed_pages]
    return {
        "document_id": context.document_id,
        "completed_page_numbers": page_numbers,
        "completed_pages": completed_pages,
        "skipped_count": len(completed_pages),
        "trace": _trace_attributes(
            document_id=context.document_id,
            workflow_stage="pages_extracting",
            cache_status="skipped_completed" if completed_pages else None,
        ),
        "job_progress": _record_payload(job_progress) if job_progress is not None else None,
    }


def _completed_page_result(
    context: CompletedPagesContext,
    summary_record: Any,
) -> dict[str, Any] | None:
    summary_payload = _record_payload(summary_record)
    page_number = _positive_int(
        summary_payload.get("page_number"),
        default=0,
    )
    if page_number < 1 or page_number not in context.page_numbers:
        return None

    content_hash = _string_value(summary_payload.get("content_hash"))
    expected_hash = context.content_hashes.get(page_number)
    if expected_hash and content_hash != expected_hash:
        return None
    if content_hash is None:
        return None

    if summary_payload.get("prompt_version") != context.prompt_version:
        return None
    if summary_payload.get("ai_provider") != context.ai_provider:
        return None
    if summary_payload.get("ai_model") != context.ai_model:
        return None

    return {
        "document_id": context.document_id,
        "page_number": page_number,
        "content_hash": content_hash,
        "prompt_version": context.prompt_version,
        "cache_status": "skipped_completed",
        "trace": _trace_attributes(
            document_id=context.document_id,
            workflow_stage="pages_extracting",
            page_number=page_number,
            cache_status="skipped_completed",
        ),
        "summary_id": summary_payload.get("id"),
        "summary": summary_payload.get("summary"),
        "confidence": summary_payload.get("confidence"),
        "ai_model": summary_payload.get("ai_model"),
        "ai_provider": summary_payload.get("ai_provider"),
        "summary_record": summary_payload,
        "job_progress": None,
    }


def _record_payload(record: Any) -> dict[str, Any]:
    if hasattr(record, "model_dump"):
        return record.model_dump(mode="json")
    if isinstance(record, dict):
        return record
    if hasattr(record, "__dict__"):
        return dict(record.__dict__)
    return dict(record)


def _api_key_for_provider(settings: Any, provider: str) -> str | None:
    if provider == "gemini":
        return getattr(settings, "orderflow_ai_gemini_api_key", None)
    if provider == "openai":
        return getattr(settings, "orderflow_ai_openai_api_key", None)
    if provider == "anthropic":
        return getattr(settings, "orderflow_ai_anthropic_api_key", None)
    if provider == "groq":
        return getattr(settings, "orderflow_ai_groq_api_key", None)
    return None


def _page_numbers_from_completed_payload(payload: dict[str, Any]) -> list[int]:
    explicit_pages = _string_value(payload.get("page_numbers")) or ""
    page_numbers = [
        page_number
        for item in explicit_pages.split(",")
        for page_number in [_positive_int(item, default=0)]
        if page_number >= 1
    ]
    if page_numbers:
        return sorted(set(page_numbers))

    total_pages = _positive_int(
        payload.get("total_pages") or payload.get("pages_total"),
        default=1,
    )
    return list(range(1, total_pages + 1))


def _page_content_hash_from_payload(
    payload: dict[str, Any],
    page_number: int,
) -> str | None:
    for key in (
        f"content_hash_{page_number}",
        f"page_{page_number}_content_hash",
    ):
        value = _string_value(payload.get(key))
        if value:
            return value
    return None


def _string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _datetime_value(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if value >= 1 else default
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            parsed = int(stripped)
            return parsed if parsed >= 1 else default
    return default


def _float_value(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _text_or_default(value: object, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict_or_none(value: object) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _confidence_or_default(value: object) -> float:
    if isinstance(value, bool):
        return 0.85
    if isinstance(value, (int, float)) and 0 <= float(value) <= 1:
        return float(value)
    return 0.85
