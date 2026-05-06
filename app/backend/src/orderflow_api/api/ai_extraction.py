from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import logging
import re
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

from orderflow_api.api.extraction_engine import (
    ParsedClause,
    ParsedObligation,
    build_clause_span_token,
)
from orderflow_api.core.config import settings
from orderflow_api.core.gemini_client import call_gemini_json, extract_gemini_text
from orderflow_api.schemas.extractions import IntakeAiOptions

_SUPPORTED_PROVIDERS = {"openai", "anthropic", "gemini", "groq"}
# _REMOTE_FALLBACK_ORDER = ("groq", "gemini", "openai", "anthropic")
_REMOTE_FALLBACK_ORDER = ()
_SOURCE_EXCERPT_CHARS = 240
_AI_EXTRACTION_MAX_ATTEMPTS = 3
_AI_EXTRACTION_RETRY_BASE_SECONDS = 0.25


@dataclass(frozen=True)
class AiExtractionAttempt:
    obligations: list[ParsedObligation]
    attempted: bool
    used_ai: bool
    provider: str | None
    model: str | None
    reason: str | None


@dataclass(frozen=True)
class _AiSelection:
    enabled: bool
    provider: str | None
    model: str | None
    api_key: str | None
    temperature: float
    max_obligations: int
    max_clauses: int
    max_clause_chars: int
    reason: str | None


def maybe_extract_obligations_with_ai(
    *,
    clauses: list[ParsedClause],
    document_id: UUID,
    ai_options: IntakeAiOptions | None,
) -> AiExtractionAttempt:
    selection = _resolve_ai_selection(ai_options)
    if not selection.enabled or selection.provider is None:
        return AiExtractionAttempt(
            obligations=[],
            attempted=False,
            used_ai=False,
            provider=selection.provider,
            model=selection.model,
            reason=selection.reason,
        )

    primary_attempt = _attempt_remote_provider_with_retries(
        clauses=clauses,
        document_id=document_id,
        selection=selection,
    )
    if primary_attempt.used_ai:
        return primary_attempt

    fallback_reasons: list[str] = []
    for provider in _REMOTE_FALLBACK_ORDER:
        if provider == selection.provider:
            continue

        fallback_selection = _resolve_ai_selection(ai_options, forced_provider=provider)
        if not fallback_selection.enabled or fallback_selection.provider is None:
            if fallback_selection.reason:
                fallback_reasons.append(fallback_selection.reason)
            continue

        fallback_attempt = _attempt_remote_provider_with_retries(
            clauses=clauses,
            document_id=document_id,
            selection=fallback_selection,
        )
        if fallback_attempt.used_ai:
            return AiExtractionAttempt(
                obligations=fallback_attempt.obligations,
                attempted=True,
                used_ai=True,
                provider=fallback_attempt.provider,
                model=fallback_attempt.model,
                reason=(
                    f"Primary provider '{selection.provider}' failed; "
                    f"used fallback provider '{fallback_attempt.provider}'."
                ),
            )

        if fallback_attempt.reason:
            fallback_reasons.append(fallback_attempt.reason)

    reason_parts = [part for part in [primary_attempt.reason, *fallback_reasons] if part]
    return AiExtractionAttempt(
        obligations=[],
        attempted=True,
        used_ai=False,
        provider=selection.provider,
        model=selection.model,
        reason="; ".join(reason_parts) if reason_parts else "AI extraction failed.",
    )


def _resolve_ai_selection(
    ai_options: IntakeAiOptions | None,
    forced_provider: str | None = None,
) -> _AiSelection:
    enabled = settings.orderflow_ai_enabled_default
    if ai_options is not None and ai_options.enabled is not None:
        enabled = ai_options.enabled

    if not enabled:
        return _AiSelection(
            enabled=False,
            provider=None,
            model=None,
            api_key=None,
            temperature=0.0,
            max_obligations=40,
            max_clauses=settings.orderflow_ai_max_clauses,
            max_clause_chars=settings.orderflow_ai_gemini_max_chars_per_clause,
            reason="AI extraction is disabled.",
        )

    allow_override = settings.orderflow_ai_allow_user_override
    requested_provider = ai_options.provider if ai_options is not None else None
    requested_model = ai_options.model if ai_options is not None else None
    requested_key = ai_options.api_key if ai_options is not None else None
    requested_temperature = ai_options.temperature if ai_options is not None else None
    requested_max = ai_options.max_obligations if ai_options is not None else None

    provider = forced_provider or settings.orderflow_ai_default_provider.strip().lower()
    requested_provider = requested_provider.strip().lower() if requested_provider else None

    if forced_provider is None and allow_override and requested_provider:
        provider = requested_provider

    model = _resolve_model_for_provider(
        provider=provider,
        requested_provider=requested_provider,
        requested_model=requested_model,
        allow_override=allow_override,
    )
    api_key: str | None = None

    if provider not in _SUPPORTED_PROVIDERS:
        return _AiSelection(
            enabled=False,
            provider=provider,
            model=model,
            api_key=None,
            temperature=0.0,
            max_obligations=40,
            max_clauses=settings.orderflow_ai_max_clauses,
            max_clause_chars=settings.orderflow_ai_gemini_max_chars_per_clause,
            reason=f"Unsupported AI provider: {provider}",
        )

    if provider == "openai":
        api_key = settings.orderflow_ai_openai_api_key
    elif provider == "anthropic":
        api_key = settings.orderflow_ai_anthropic_api_key
    elif provider == "gemini":
        api_key = settings.orderflow_ai_gemini_api_key
    elif provider == "groq":
        api_key = settings.orderflow_ai_groq_api_key

    if (
        allow_override
        and requested_key
        and (requested_provider is None or requested_provider == provider)
    ):
        api_key = requested_key.strip()

    if provider in {"openai", "anthropic", "gemini", "groq"} and not api_key:
        logger.warning(
            "AI extraction disabled: missing API key for provider '%s'. "
            "Set ORDERFLOW_AI_%s_API_KEY env var or pass one in request.",
            provider,
            provider.upper(),
        )
        return _AiSelection(
            enabled=False,
            provider=provider,
            model=model,
            api_key=None,
            temperature=0.0,
            max_obligations=40,
            max_clauses=settings.orderflow_ai_max_clauses,
            max_clause_chars=settings.orderflow_ai_gemini_max_chars_per_clause,
            reason=(
                f"Missing API key for provider '{provider}'. Set backend env key or pass one in"
                " request ai.api_key."
            ),
        )

    temperature = (
        requested_temperature if allow_override and requested_temperature is not None else 0.1
    )
    max_obligations = requested_max if allow_override and requested_max is not None else 40
    max_clauses = settings.orderflow_ai_max_clauses
    max_clause_chars = 1000

    if provider == "gemini":
        max_clauses = min(max_clauses, settings.orderflow_ai_gemini_max_clauses)
        max_clause_chars = settings.orderflow_ai_gemini_max_chars_per_clause

    return _AiSelection(
        enabled=True,
        provider=provider,
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_obligations=max_obligations,
        max_clauses=max_clauses,
        max_clause_chars=max_clause_chars,
        reason=None,
    )


def _resolve_model_for_provider(
    *,
    provider: str,
    requested_provider: str | None,
    requested_model: str | None,
    allow_override: bool,
) -> str:
    if (
        allow_override
        and requested_model
        and (requested_provider is None or requested_provider == provider)
    ):
        return requested_model.strip()

    configured_default_model = settings.orderflow_ai_default_model.strip()
    configured_default_provider = settings.orderflow_ai_default_provider.strip().lower()
    if configured_default_model and configured_default_provider == provider:
        return configured_default_model

    fallback_models = {
        "openai": "gpt-4.1-mini",
        "anthropic": "claude-3-5-sonnet-latest",
        "gemini": "gemini-2.0-flash",
        "groq": "llama-3.3-70b-versatile",
    }
    return fallback_models.get(provider, "gemini-2.0-flash")


def _attempt_remote_provider(
    *,
    clauses: list[ParsedClause],
    document_id: UUID,
    selection: _AiSelection,
) -> AiExtractionAttempt:
    try:
        candidates = _extract_candidates_with_remote_provider(clauses=clauses, selection=selection)
        obligations = _materialize_ai_obligations(
            clauses=clauses,
            document_id=document_id,
            candidates=candidates,
            selection=selection,
        )
    except Exception as exc:
        return AiExtractionAttempt(
            obligations=[],
            attempted=True,
            used_ai=False,
            provider=selection.provider,
            model=selection.model,
            reason=f"AI provider error ({selection.provider}): {exc}",
        )

    if not obligations:
        return AiExtractionAttempt(
            obligations=[],
            attempted=True,
            used_ai=False,
            provider=selection.provider,
            model=selection.model,
            reason=f"AI returned no actionable obligations ({selection.provider}).",
        )

    return AiExtractionAttempt(
        obligations=obligations,
        attempted=True,
        used_ai=True,
        provider=selection.provider,
        model=selection.model,
        reason=None,
    )


def _attempt_remote_provider_with_retries(
    *,
    clauses: list[ParsedClause],
    document_id: UUID,
    selection: _AiSelection,
) -> AiExtractionAttempt:
    attempts: list[AiExtractionAttempt] = []
    for attempt in range(1, _AI_EXTRACTION_MAX_ATTEMPTS + 1):
        result = _attempt_remote_provider(
            clauses=clauses,
            document_id=document_id,
            selection=selection,
        )
        if result.used_ai:
            if attempt == 1:
                return result
            return AiExtractionAttempt(
                obligations=result.obligations,
                attempted=True,
                used_ai=True,
                provider=result.provider,
                model=result.model,
                reason=f"AI extraction succeeded on retry attempt {attempt}.",
            )

        attempts.append(result)
        if not _should_retry_ai_attempt(result):
            return result
        if attempt < _AI_EXTRACTION_MAX_ATTEMPTS:
            time.sleep(_ai_retry_delay_seconds(result.reason, attempt))

    reason = "; ".join(item.reason or "AI extraction failed." for item in attempts)
    return AiExtractionAttempt(
        obligations=[],
        attempted=True,
        used_ai=False,
        provider=selection.provider,
        model=selection.model,
        reason=(
            f"AI extraction failed after {_AI_EXTRACTION_MAX_ATTEMPTS} attempts. {reason}"
        ),
    )


def _should_retry_ai_attempt(result: AiExtractionAttempt) -> bool:
    reason = (result.reason or "").lower()
    if "returned no actionable obligations" in reason:
        return False
    if any(marker in reason for marker in ("auth", "api key", "unsupported", "bad request")):
        return False
    return result.attempted and not result.used_ai


def _ai_retry_delay_seconds(reason: str | None, attempt: int) -> float:
    reason_text = reason or ""
    match = re.search(r"retry(?:_after_seconds)?[=: ]+(\d+)", reason_text, re.IGNORECASE)
    if match:
        return min(float(match.group(1)), 2.0)
    return _AI_EXTRACTION_RETRY_BASE_SECONDS * (2 ** max(attempt - 1, 0))


def _extract_candidates_with_remote_provider(
    *,
    clauses: list[ParsedClause],
    selection: _AiSelection,
) -> list[dict[str, object]]:
    selected_clauses = clauses[: selection.max_clauses]
    prompt_payload = [
        {
            "clause_index": clause.clause_index,
            "page_number": clause.page_number,
            "span_start": clause.span_start,
            "span_end": clause.span_end,
            "text": clause.normalized_text[: selection.max_clause_chars],
        }
        for clause in selected_clauses
    ]

    prompt = _build_prompt(prompt_payload, selection.max_obligations)
    if selection.provider == "openai":
        response_text = _call_openai(prompt=prompt, selection=selection)
    elif selection.provider == "anthropic":
        response_text = _call_anthropic(prompt=prompt, selection=selection)
    elif selection.provider == "gemini":
        response_text = _call_gemini(prompt=prompt, selection=selection)
    elif selection.provider == "groq":
        response_text = _call_groq(prompt=prompt, selection=selection)
    else:
        raise ValueError(f"Unsupported remote provider: {selection.provider}")

    parsed = _parse_json_payload(response_text)
    obligations = parsed.get("obligations")
    if not isinstance(obligations, list):
        return []

    return [item for item in obligations if isinstance(item, dict)]


def _build_prompt(clauses: list[dict[str, object]], max_obligations: int) -> str:
    return (
        "Extract legal/compliance obligations from court-order clauses. "
        "Return strict JSON only with this schema: "
        '{"obligations":[{"clause_index":int,"title":str,"description":str,'
        '"owner_hint":str|null,"due_date":"YYYY-MM-DD"|null,'
        '"priority":"low|medium|high|critical","confidence":0..1,'
        '"source_evidence":{"page_number":int|null,"clause_index":int,'
        '"clause_span":str|null,"excerpt":str}}]}. '
        "Use source_evidence values from the matching clause index; excerpt must be a "
        "short verbatim quote. If span_start/end are provided, set clause_span to "
        "p{page_number}:c{clause_index}:{span_start}-{span_end}; otherwise use "
        "clause-{clause_index}. For appeal, review, limitation, or legal remedy "
        "items, phrase the action as a legal-review task only; never present final "
        "legal advice or say an appeal must be filed. Use language like "
        "'review with authorized legal counsel'. "
        f"Limit to {max_obligations} obligations. Do not include markdown. "
        f"Clauses: {json.dumps(clauses, ensure_ascii=True)}"
    )


def _call_openai(*, prompt: str, selection: _AiSelection) -> str:
    body = {
        "model": selection.model,
        "temperature": selection.temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a legal obligation extraction assistant.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    response = _post_json(
        url="https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {selection.api_key}"},
        payload=body,
    )

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("OpenAI response missing choices")

    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("OpenAI response choice is invalid")

    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("OpenAI response missing message")

    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("OpenAI response content is invalid")

    return content


def _call_anthropic(*, prompt: str, selection: _AiSelection) -> str:
    body = {
        "model": selection.model,
        "max_tokens": 1400,
        "temperature": selection.temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = _post_json(
        url="https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": selection.api_key or "",
            "anthropic-version": "2023-06-01",
        },
        payload=body,
    )

    content = response.get("content")
    if not isinstance(content, list) or not content:
        raise ValueError("Anthropic response missing content")

    text_chunks: list[str] = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            text_chunks.append(item["text"])

    if not text_chunks:
        raise ValueError("Anthropic response text is empty")

    return "\n".join(text_chunks)


def _call_gemini(*, prompt: str, selection: _AiSelection) -> str:
    max_output_tokens = min(
        settings.orderflow_ai_gemini_max_output_tokens,
        max(768, selection.max_obligations * 96),
    )
    response = call_gemini_json(
        api_key=selection.api_key or "",
        model=selection.model,
        prompt=prompt,
        temperature=selection.temperature,
        max_output_tokens=max_output_tokens,
        request_label="obligation extraction",
    )
    return extract_gemini_text(response)


def _call_groq(*, prompt: str, selection: _AiSelection) -> str:
    # Use the official Groq SDK (httpx-based) with a custom User-Agent.
    # Cloudflare bans default Python/urllib/httpx TLS/UA signatures at
    # api.groq.com (error 1010).
    try:
        from groq import Groq
        import httpx
    except ImportError as exc:
        raise ValueError(
            "Groq SDK or httpx not installed. Run: pip install groq httpx"
        ) from exc

    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
    client = Groq(
        api_key=selection.api_key,
        timeout=settings.orderflow_ai_timeout_seconds,
        http_client=httpx.Client(
            http2=True,
            headers={"User-Agent": user_agent},
        ),
    )
    completion = client.chat.completions.create(
        model=selection.model,
        temperature=selection.temperature,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a legal obligation extraction assistant. "
                    "Return only valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    if not completion.choices:
        raise ValueError("Groq response missing choices")

    content = completion.choices[0].message.content
    if not isinstance(content, str) or not content:
        raise ValueError("Groq response content is empty")

    return content


def _post_json(*, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    base_headers = {
        "content-type": "application/json",
        "accept": "application/json",
    }
    base_headers.update(headers)

    request = urllib_request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=base_headers,
        method="POST",
    )

    try:
        with urllib_request.urlopen(
            request,
            timeout=settings.orderflow_ai_timeout_seconds,
        ) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"HTTP {exc.code}: {detail}") from exc

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Provider response is not a JSON object")

    return parsed


def _parse_json_payload(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(stripped[start : end + 1])
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("Provider returned invalid JSON payload")


def _materialize_ai_obligations(
    *,
    clauses: list[ParsedClause],
    document_id: UUID,
    candidates: list[dict[str, object]],
    selection: _AiSelection,
) -> list[ParsedObligation]:
    clause_by_index = {item.clause_index: item for item in clauses}
    obligations: list[ParsedObligation] = []

    for idx, candidate in enumerate(candidates[: selection.max_obligations], start=1):
        clause_index = _safe_int(candidate.get("clause_index"))
        clause = clause_by_index.get(clause_index) if clause_index is not None else None

        if clause is None:
            continue

        title = _safe_text(candidate.get("title")) or f"AI obligation {idx}"
        description = _safe_text(candidate.get("description")) or clause.normalized_text
        owner_hint = _safe_text(candidate.get("owner_hint"))
        due_date = _safe_date(candidate.get("due_date"))
        priority = _safe_priority(candidate.get("priority"))
        default_confidence = (
            float(clause.confidence) if isinstance(clause.confidence, (int, float)) else 0.7
        )
        confidence = _safe_float(candidate.get("confidence"), default=default_confidence)

        obligations.append(
            ParsedObligation(
                id=uuid4(),
                document_id=document_id,
                clause_id=clause.id,
                obligation_code=f"OBL-AI-{idx:03d}",
                title=title,
                description=description,
                owner_hint=owner_hint,
                due_date=due_date,
                status="draft",
                priority=priority,
                review_state="pending_review",
                confidence=confidence,
                citation_page_number=clause.page_number,
                citation_clause_span=build_clause_span_token(
                    clause_index=clause.clause_index,
                    page_number=clause.page_number,
                    span_start=clause.span_start,
                    span_end=clause.span_end,
                ),
                metadata={
                    "phase": "phase-b",
                    "source": "ai-extractor-v1",
                    "ai_provider": selection.provider,
                    "ai_model": selection.model,
                    "ai_temperature": selection.temperature,
                    "clause_index": clause.clause_index,
                    "source_evidence": _build_source_evidence(candidate, clause),
                },
            )
        )

    return obligations


def _safe_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _safe_float(value: object, *, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 1.0))
    if isinstance(value, str):
        try:
            return max(0.0, min(float(value.strip()), 1.0))
        except ValueError:
            return default
    return default


def _safe_date(value: object) -> date | None:
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _safe_priority(value: object) -> str:
    normalized = _safe_text(value)
    if normalized is None:
        return "medium"

    lowered = normalized.lower()
    if lowered in {"low", "medium", "high", "critical"}:
        return lowered

    return "medium"


def _truncate_text(value: str | None, max_chars: int) -> str | None:
    if not value:
        return None
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "..."


def _build_source_evidence(
    candidate: dict[str, object],
    clause: ParsedClause,
) -> dict[str, object]:
    candidate_evidence = candidate.get("source_evidence")
    excerpt = None
    if isinstance(candidate_evidence, dict):
        excerpt = _safe_text(candidate_evidence.get("excerpt"))
    if not excerpt:
        excerpt = clause.text or clause.normalized_text

    return {
        "page_number": clause.page_number,
        "clause_index": clause.clause_index,
        "clause_span": build_clause_span_token(
            clause_index=clause.clause_index,
            page_number=clause.page_number,
            span_start=clause.span_start,
            span_end=clause.span_end,
        ),
        "excerpt": _truncate_text(excerpt, _SOURCE_EXCERPT_CHARS),
    }


def extract_case_flow(
    *,
    metadata: dict[str, object] | None,
    summaries: list[object],
    obligations: list[object],
) -> dict[str, list[dict[str, object]]]:
    """Build a deterministic case-flow graph from extracted document signals."""
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []

    metadata_obj = _coerce_mapping(metadata)
    cis = _coerce_mapping(metadata_obj.get("cis"))

    parties: list[str] = []
    for key in ("petitioners", "respondents", "parties"):
        value = cis.get(key)
        if isinstance(value, list):
            parties.extend([str(item).strip() for item in value if str(item).strip()])
    parties = list(dict.fromkeys(parties))[:6]

    party_node_ids: list[str] = []
    for idx, party in enumerate(parties, start=1):
        node_id = f"party-{idx}"
        party_node_ids.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "node_type": "party",
                "label": party,
                "detail": "Party to the proceedings",
                "page_ref": None,
            }
        )

    event_node_ids: list[str] = []
    for summary in summaries[:12]:
        page_number = _safe_int(_read_field(summary, "page_number"))
        summary_text = _safe_text(_read_field(summary, "summary")) or "Proceeding update"
        label = f"Page {page_number}" if page_number else "Case event"
        node_id = f"event-{page_number or len(event_node_ids) + 1}"
        event_node_ids.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "node_type": "event",
                "label": label,
                "detail": summary_text[:220],
                "page_ref": page_number,
            }
        )

    first_event = event_node_ids[0] if event_node_ids else None
    if first_event:
        for party_node_id in party_node_ids:
            edges.append(
                {
                    "id": f"{party_node_id}->{first_event}",
                    "source": party_node_id,
                    "target": first_event,
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
    for summary in summaries:
        text = _safe_text(_read_field(summary, "summary")) or ""
        if not re.search(r"\b(order|directed|dispose|allowed|dismissed)\b", text, re.IGNORECASE):
            continue
        page_number = _safe_int(_read_field(summary, "page_number"))
        node_id = f"order-{len(order_node_ids) + 1}"
        order_node_ids.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "node_type": "order",
                "label": "Court order",
                "detail": text[:220],
                "page_ref": page_number,
            }
        )

    for order_node_id in order_node_ids:
        previous_event = event_node_ids[-1] if event_node_ids else None
        if previous_event:
            edges.append(
                {
                    "id": f"{previous_event}->{order_node_id}",
                    "source": previous_event,
                    "target": order_node_id,
                    "relation": "results_in",
                }
            )

    obligation_node_ids: list[str] = []
    for idx, obligation in enumerate(obligations[:20], start=1):
        title = _safe_text(_read_field(obligation, "title")) or "Obligation"
        citation = _read_field(obligation, "citation")
        page_ref = _safe_int(_read_field(citation, "page_number"))
        node_id = f"obligation-{idx}"
        obligation_node_ids.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "node_type": "obligation",
                "label": title[:120],
                "detail": _safe_text(_read_field(obligation, "description")),
                "page_ref": page_ref,
            }
        )

    for idx, obligation_node_id in enumerate(obligation_node_ids):
        source_order = order_node_ids[idx % len(order_node_ids)] if order_node_ids else None
        source_event = event_node_ids[-1] if event_node_ids else None
        source = source_order or source_event
        if source:
            edges.append(
                {
                    "id": f"{source}->{obligation_node_id}",
                    "source": source,
                    "target": obligation_node_id,
                    "relation": "creates",
                }
            )

    return {"nodes": nodes, "edges": edges}


def _read_field(value: object, field: str) -> object:
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)


def _coerce_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}
