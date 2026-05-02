from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from uuid import UUID, uuid4

from orderflow_api.api.extraction_engine import (
    ParsedClause,
    ParsedObligation,
    build_clause_span_token,
    extract_obligations as extract_obligations_deterministic,
)
from orderflow_api.core.config import settings
from orderflow_api.core.gemini_client import call_gemini_json, extract_gemini_text
from orderflow_api.schemas.extractions import IntakeAiOptions

_SUPPORTED_PROVIDERS = {"openai", "anthropic", "gemini", "groq"}
# _REMOTE_FALLBACK_ORDER = ("groq", "gemini", "openai", "anthropic")
_REMOTE_FALLBACK_ORDER = ()

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

    primary_attempt = _attempt_remote_provider(
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

        fallback_attempt = _attempt_remote_provider(
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

    reason_parts = [
        part for part in [primary_attempt.reason, *fallback_reasons] if part
    ]
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
    requested_provider = (
        requested_provider.strip().lower() if requested_provider else None
    )

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
        requested_temperature
        if allow_override and requested_temperature is not None
        else 0.1
    )
    max_obligations = (
        requested_max if allow_override and requested_max is not None else 40
    )
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
        candidates = _extract_candidates_with_remote_provider(
            clauses=clauses, selection=selection
        )
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
        '"priority":"low|medium|high|critical","confidence":0..1}]}. '
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

    client = Groq(
        api_key=selection.api_key,
        timeout=settings.orderflow_ai_timeout_seconds,
        http_client=httpx.Client(
            http2=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            }
        )
    )
    completion = client.chat.completions.create(
        model=selection.model,
        temperature=selection.temperature,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are a legal obligation extraction assistant. Return only valid JSON.",
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


def _post_json(
    *, url: str, headers: dict[str, str], payload: dict[str, Any]
) -> dict[str, Any]:
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
            float(clause.confidence)
            if isinstance(clause.confidence, (int, float))
            else 0.7
        )
        confidence = _safe_float(
            candidate.get("confidence"), default=default_confidence
        )

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
