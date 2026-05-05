from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio import exceptions as temporal_exceptions

with workflow.unsafe.imports_passed_through():
    from orderflow_worker.core.config import settings
    from orderflow_worker.activities.intake import (
        DEFAULT_ACTION_PLAN_PROMPT_VERSION,
        DEFAULT_DOCUMENT_SUMMARY_PROMPT_VERSION,
        DEFAULT_PAGE_EXTRACTION_MODEL,
        DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION,
        DEFAULT_PAGE_EXTRACTION_PROVIDER,
        activity_extract_action_plan,
        activity_extract_page_cached,
        activity_generate_full_summary,
        activity_list_completed_pages,
        activity_mark_intake_stage,
        activity_pause_intake_job,
        activity_resume_intake_job,
        translate_document_if_needed_activity,
    )


ACTIVITY_TIMEOUT = timedelta(minutes=5)
TRANSLATION_TIMEOUT = timedelta(seconds=30)
RATE_LIMIT_BUFFER_SECONDS = 5
RECOVERY_SUCCESS_TARGET = 5


@workflow.defn(name="orderflow-intake-workflow")
class IntakeWorkflow:
    def __init__(self) -> None:
        self._advance_to_summary = False
        self._advance_to_action_plan = False
        self._finalize_review = False

    @workflow.signal(name="advance_to_summary")
    async def signal_advance_to_summary(self) -> None:
        self._advance_to_summary = True

    @workflow.signal(name="advance_to_action_plan")
    async def signal_advance_to_action_plan(self) -> None:
        self._advance_to_action_plan = True

    @workflow.signal(name="finalize")
    async def signal_finalize(self) -> None:
        self._finalize_review = True

    @workflow.run
    async def run(self, payload: dict[str, str]) -> dict[str, Any]:
        document_id = _payload_text(payload, "document_id", "unknown")
        stages: list[dict[str, Any]] = []
        retry_traces: list[dict[str, str | int]] = []

        translation_context = await workflow.execute_activity(
            translate_document_if_needed_activity,
            payload,
            start_to_close_timeout=TRANSLATION_TIMEOUT,
        )
        stages.append(
            _stage_result(
                name="translation",
                status="completed",
                detail=translation_context.get("translation_status"),
            )
        )
        self._advance_to_summary = self._advance_to_summary or _payload_bool(
            translation_context,
            "auto_advance_summary",
        )
        self._advance_to_action_plan = self._advance_to_action_plan or _payload_bool(
            translation_context, "auto_advance_action_plan"
        )
        self._finalize_review = self._finalize_review or _payload_bool(
            translation_context,
            "auto_finalize_review",
        )

        page_numbers = _page_numbers_from_payload(translation_context)
        current_concurrency, max_concurrency = _resolve_page_concurrency(
            translation_context,
        )
        completed_lookup = await workflow.execute_activity(
            activity_list_completed_pages,
            _completed_pages_context(
                translation_context,
                page_numbers=page_numbers,
            ),
            start_to_close_timeout=TRANSLATION_TIMEOUT,
        )
        completed_pages = _completed_pages_by_number(completed_lookup)
        page_results_by_number: dict[int, dict[str, Any]] = {
            page_number: completed_page for page_number, completed_page in completed_pages.items()
        }
        pages_to_extract = _pages_to_extract(
            page_numbers,
            page_results_by_number,
        )

        page_index = 0
        success_streak = 0
        while page_index < len(pages_to_extract):
            page_chunk = pages_to_extract[page_index : page_index + current_concurrency]
            page_tasks = [
                workflow.execute_activity(
                    activity_extract_page_cached,
                    _page_extraction_context(
                        translation_context,
                        page_number=page_number,
                        total_pages=max(page_numbers),
                    ),
                    start_to_close_timeout=ACTIVITY_TIMEOUT,
                )
                for page_number in page_chunk
            ]
            page_results = await asyncio.gather(
                *page_tasks,
                return_exceptions=True,
            )
            for page_number, page_result in zip(page_chunk, page_results):
                while isinstance(page_result, Exception):
                    rate_limit = _rate_limit_details(page_result)
                    if rate_limit is None:
                        raise page_result

                    success_streak = 0
                    (
                        current_concurrency,
                        pause_seconds,
                    ) = _rate_limit_backoff_plan(
                        current_concurrency,
                        rate_limit.retry_after_seconds,
                    )
                    paused_until = workflow.now() + timedelta(seconds=pause_seconds)
                    retry_traces.append(
                        _workflow_trace_attributes(
                            document_id=document_id,
                            workflow_stage="pages_extracting",
                            page_number=page_number,
                            retry_state="paused",
                            retry_after_seconds=rate_limit.retry_after_seconds,
                            current_concurrency=current_concurrency,
                        )
                    )
                    await workflow.execute_activity(
                        activity_pause_intake_job,
                        {
                            "document_id": document_id,
                            "retry_after_seconds": rate_limit.retry_after_seconds,
                            "paused_until": paused_until.isoformat(),
                            "error_code": rate_limit.error_code,
                            "error_message": rate_limit.error_message,
                            "current_concurrency": current_concurrency,
                        },
                        start_to_close_timeout=TRANSLATION_TIMEOUT,
                    )
                    await workflow.sleep(timedelta(seconds=pause_seconds))
                    await workflow.execute_activity(
                        activity_resume_intake_job,
                        {
                            "document_id": document_id,
                            "current_concurrency": current_concurrency,
                        },
                        start_to_close_timeout=TRANSLATION_TIMEOUT,
                    )
                    try:
                        page_result = await workflow.execute_activity(
                            activity_extract_page_cached,
                            _page_extraction_context(
                                translation_context,
                                page_number=page_number,
                                total_pages=max(page_numbers),
                            ),
                            start_to_close_timeout=ACTIVITY_TIMEOUT,
                        )
                    except Exception as exc:
                        page_result = exc

                page_results_by_number[page_number] = page_result
                success_streak += 1
                (
                    current_concurrency,
                    success_streak,
                    should_update,
                ) = _maybe_restore_concurrency(
                    success_streak,
                    current_concurrency,
                    max_concurrency,
                )
                if should_update:
                    await workflow.execute_activity(
                        activity_resume_intake_job,
                        {
                            "document_id": document_id,
                            "current_concurrency": current_concurrency,
                        },
                        start_to_close_timeout=TRANSLATION_TIMEOUT,
                    )
            page_index += len(page_chunk)

        page_results = [
            page_results_by_number[page_number]
            for page_number in page_numbers
            if page_number in page_results_by_number
        ]

        pages_done = await workflow.execute_activity(
            activity_mark_intake_stage,
            {"document_id": document_id, "stage": "pages_done"},
            start_to_close_timeout=TRANSLATION_TIMEOUT,
        )
        stages.append(
            _stage_result(
                name="page_extraction",
                status="completed",
                detail={
                    "stage": pages_done.get("stage"),
                    "skipped_completed": len(completed_pages),
                    "extracted_pages": (len(page_numbers) - len(completed_pages)),
                    "current_concurrency": current_concurrency,
                    "max_concurrency": max_concurrency,
                },
            )
        )

        summary_gate_detail = "auto_advance_summary"
        if not self._advance_to_summary:
            await workflow.wait_condition(lambda: self._advance_to_summary)
            summary_gate_detail = "advance_to_summary_signal"
        stages.append(
            _stage_result(
                name="summary_gate",
                status="completed",
                detail=summary_gate_detail,
            )
        )

        summary_result = await workflow.execute_activity(
            activity_generate_full_summary,
            _summary_context(translation_context),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        stages.append(
            _stage_result(
                name="summary",
                status="completed",
                detail=summary_result.get("job_stage"),
            )
        )

        action_plan_gate_detail = "auto_advance_action_plan"
        if not self._advance_to_action_plan:
            await workflow.wait_condition(lambda: self._advance_to_action_plan)
            action_plan_gate_detail = "advance_to_action_plan_signal"
        stages.append(
            _stage_result(
                name="action_plan_gate",
                status="completed",
                detail=action_plan_gate_detail,
            )
        )

        action_plan_result = await workflow.execute_activity(
            activity_extract_action_plan,
            _action_plan_context(translation_context),
            start_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        stages.append(
            _stage_result(
                name="action_plan",
                status="completed",
                detail=action_plan_result.get("job_stage"),
            )
        )

        finalization_gate_detail = "auto_finalize_review"
        if not self._finalize_review:
            await workflow.wait_condition(lambda: self._finalize_review)
            finalization_gate_detail = "finalize_signal"
        stages.append(
            _stage_result(
                name="finalization_gate",
                status="completed",
                detail=finalization_gate_detail,
            )
        )

        finalized = await workflow.execute_activity(
            activity_mark_intake_stage,
            {"document_id": document_id, "stage": "finalized"},
            start_to_close_timeout=TRANSLATION_TIMEOUT,
        )
        stages.append(
            _stage_result(
                name="finalization",
                status="completed",
                detail=finalized.get("stage"),
            )
        )

        return _workflow_result(
            document_id=document_id,
            state="finalized",
            stages=stages,
            page_results=page_results,
            summary=summary_result,
            action_plan=action_plan_result,
            awaiting="complete",
            retry_traces=retry_traces,
        )


def _workflow_result(
    *,
    document_id: str,
    state: str,
    stages: list[dict[str, Any]],
    page_results: list[dict[str, Any]],
    awaiting: str,
    summary: dict[str, Any] | None = None,
    action_plan: dict[str, Any] | None = None,
    retry_traces: list[dict[str, str | int]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "document_id": document_id,
        "state": state,
        "awaiting": awaiting,
        "stages": stages,
        "page_count": len(page_results),
        "pages": page_results,
        "trace": _workflow_trace_attributes(
            document_id=document_id,
            workflow_stage=state,
        ),
    }
    if retry_traces:
        result["retry_traces"] = retry_traces
    if summary is not None:
        result["summary"] = summary
    if action_plan is not None:
        result["action_plan"] = action_plan
    return result


def _stage_result(
    *,
    name: str,
    status: str,
    detail: object | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "detail": detail,
    }


def _workflow_trace_attributes(
    *,
    document_id: str,
    workflow_stage: str,
    page_number: int | None = None,
    cache_status: str | None = None,
    retry_state: str | None = None,
    retry_after_seconds: int | None = None,
    current_concurrency: int | None = None,
) -> dict[str, str | int]:
    attributes: dict[str, str | int] = {
        "orderflow.document_id": document_id,
        "orderflow.workflow.stage": workflow_stage,
    }
    if page_number is not None:
        attributes["orderflow.page_number"] = page_number
    if cache_status:
        attributes["orderflow.cache.status"] = cache_status
    if retry_state:
        attributes["orderflow.retry.state"] = retry_state
    if retry_after_seconds is not None:
        attributes["orderflow.retry.after_seconds"] = retry_after_seconds
    if current_concurrency is not None:
        attributes["orderflow.concurrency.current"] = current_concurrency
    return attributes


def _page_extraction_context(
    payload: dict[str, str],
    *,
    page_number: int,
    total_pages: int,
) -> dict[str, str]:
    page_context = {
        **payload,
        "page_number": str(page_number),
        "total_pages": str(total_pages),
        "prompt_version": _payload_text(
            payload,
            "page_prompt_version",
            _payload_text(
                payload,
                "prompt_version",
                DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION,
            ),
        ),
    }
    content_hash = _page_value(payload, "content_hash", page_number)
    if content_hash is not None:
        page_context["content_hash"] = content_hash

    page_text = _page_value(payload, "page_text", page_number)
    if page_text is not None:
        page_context["page_text"] = page_text

    return page_context


def _summary_context(payload: dict[str, str]) -> dict[str, str]:
    return {
        "document_id": _payload_text(payload, "document_id", ""),
        "prompt_version": _payload_text(
            payload,
            "summary_prompt_version",
            DEFAULT_DOCUMENT_SUMMARY_PROMPT_VERSION,
        ),
        "ai_provider": _payload_text(payload, "summary_ai_provider", "openai"),
        "ai_model": _payload_text(payload, "summary_ai_model", "gpt-4o"),
        "bypass_cache": _payload_text(payload, "bypass_cache", "false"),
    }


def _action_plan_context(payload: dict[str, str]) -> dict[str, str]:
    return {
        "document_id": _payload_text(payload, "document_id", ""),
        "prompt_version": _payload_text(
            payload,
            "action_plan_prompt_version",
            DEFAULT_ACTION_PLAN_PROMPT_VERSION,
        ),
        "ai_provider": _payload_text(
            payload,
            "action_plan_ai_provider",
            "openai",
        ),
        "ai_model": _payload_text(payload, "action_plan_ai_model", "gpt-4o"),
    }


def _completed_pages_context(
    payload: dict[str, str],
    *,
    page_numbers: list[int],
) -> dict[str, str]:
    context = {
        "document_id": _payload_text(payload, "document_id", ""),
        "page_numbers": ",".join(str(page_number) for page_number in page_numbers),
        "total_pages": str(max(page_numbers) if page_numbers else 1),
        "prompt_version": _payload_text(
            payload,
            "page_prompt_version",
            _payload_text(
                payload,
                "prompt_version",
                DEFAULT_PAGE_EXTRACTION_PROMPT_VERSION,
            ),
        ),
        "ai_provider": _payload_text(
            payload,
            "page_ai_provider",
            _payload_text(
                payload,
                "ai_provider",
                DEFAULT_PAGE_EXTRACTION_PROVIDER,
            ),
        ),
        "ai_model": _payload_text(
            payload,
            "page_ai_model",
            _payload_text(payload, "ai_model", DEFAULT_PAGE_EXTRACTION_MODEL),
        ),
        "bypass_cache": _payload_text(payload, "bypass_cache", "false"),
    }
    for page_number in page_numbers:
        content_hash = _page_value(payload, "content_hash", page_number)
        if content_hash is not None:
            context[f"content_hash_{page_number}"] = content_hash
    return context


def _completed_pages_by_number(
    completed_lookup: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    completed_pages = completed_lookup.get("completed_pages", [])
    if not isinstance(completed_pages, list):
        return {}

    by_page: dict[int, dict[str, Any]] = {}
    for completed_page in completed_pages:
        if not isinstance(completed_page, dict):
            continue
        page_number = _positive_int(
            completed_page.get("page_number"),
            default=0,
        )
        if page_number >= 1:
            by_page[page_number] = completed_page
    return by_page


def _page_numbers_from_payload(payload: dict[str, str]) -> list[int]:
    explicit_pages = _payload_text(payload, "page_numbers", "")
    page_numbers = [
        number
        for item in explicit_pages.split(",")
        for number in [_positive_int(item, default=0)]
        if number >= 1
    ]
    if page_numbers:
        return sorted(set(page_numbers))

    total_pages = _positive_int(
        _payload_text(
            payload,
            "total_pages",
            _payload_text(payload, "pages_total", "1"),
        ),
        default=1,
    )
    return list(range(1, total_pages + 1))


def _resolve_page_concurrency(payload: dict[str, str]) -> tuple[int, int]:
    minimum = max(1, settings.orderflow_intake_min_concurrency)
    maximum = max(minimum, settings.orderflow_intake_max_concurrency)
    requested = _positive_int(
        _payload_text(payload, "current_concurrency", str(minimum)),
        default=minimum,
    )
    return min(max(requested, minimum), maximum), maximum


def _chunked(items: list[int], size: int) -> list[list[int]]:
    chunk_size = max(1, size)
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _pages_to_extract(
    page_numbers: list[int],
    completed_pages: dict[int, dict[str, Any]],
) -> list[int]:
    return [page_number for page_number in page_numbers if page_number not in completed_pages]


@dataclass(frozen=True)
class RateLimitDetails:
    retry_after_seconds: int
    error_code: str
    error_message: str


def _rate_limit_details(error: Exception) -> RateLimitDetails | None:
    if isinstance(error, temporal_exceptions.ActivityError):
        cause = error.cause
        if isinstance(cause, Exception):
            return _rate_limit_details(cause)
        return None

    if not isinstance(error, temporal_exceptions.ApplicationError):
        return None
    if error.type != "rate_limit":
        return None

    details = error.details or []
    for item in details:
        if not isinstance(item, dict):
            continue
        retry_after_seconds = _positive_int(
            item.get("retry_after_seconds"),
            default=0,
        )
        if retry_after_seconds <= 0:
            continue
        return RateLimitDetails(
            retry_after_seconds=retry_after_seconds,
            error_code=_payload_text(item, "error_code", "rate_limit"),
            error_message=_payload_text(
                item,
                "error_message",
                "Rate limit encountered.",
            ),
        )
    return None


def _halve_concurrency(current: int) -> int:
    return max(1, current // 2)


def _rate_limit_backoff_plan(
    current: int,
    retry_after_seconds: int,
) -> tuple[int, int]:
    new_concurrency = _halve_concurrency(current)
    pause_seconds = max(1, retry_after_seconds) + RATE_LIMIT_BUFFER_SECONDS
    return new_concurrency, pause_seconds


def _maybe_restore_concurrency(
    success_streak: int,
    current: int,
    maximum: int,
) -> tuple[int, int, bool]:
    if current >= maximum:
        return current, success_streak, False
    if success_streak < RECOVERY_SUCCESS_TARGET:
        return current, success_streak, False

    restored = min(maximum, max(1, current * 2))
    return restored, 0, restored != current


def _page_value(
    payload: dict[str, str],
    field_name: str,
    page_number: int,
) -> str | None:
    for key in (
        f"{field_name}_{page_number}",
        f"page_{page_number}_{field_name}",
    ):
        value = _payload_text(payload, key, "")
        if value:
            return value
    return _payload_text(payload, field_name, "") or None


def _payload_bool(payload: dict[str, str], key: str) -> bool:
    return _payload_text(payload, key, "false").lower() in {"1", "true", "yes"}


def _payload_text(payload: dict[str, str], key: str, default: str) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if value >= 1 else default
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed >= 1 else default
    return default
