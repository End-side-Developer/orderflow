from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import threading
import time
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from orderflow_api.core.config import settings


@dataclass
class _ReservationEntry:
    reservation_id: str
    timestamp: float
    tokens: int


# ──────────────────────────────────────────────────────────────────────────────
# Structured Gemini error taxonomy
#
# Every code is mapped to a stable wire-level identifier the UI can switch on
# (so reviewers see actionable copy + retry guidance instead of a raw 502).
# ──────────────────────────────────────────────────────────────────────────────


class GeminiError(ValueError):
    """Base class for all Gemini provider failures.

    Subclasses set ``code`` (machine-readable, stable) and ``http_status``
    (recommended HTTP code if surfaced by an API route).
    """

    code: str = "gemini_error"
    http_status: int = 502
    retryable: bool = False
    retry_after_seconds: int | None = None

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: int | None = None,
        provider_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        if retry_after_seconds is not None:
            self.retry_after_seconds = retry_after_seconds
        self.provider_detail = provider_detail

    def to_envelope(self) -> dict[str, object]:
        envelope: dict[str, object] = {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }
        if self.retry_after_seconds is not None:
            envelope["retry_after_seconds"] = self.retry_after_seconds
        if self.provider_detail:
            envelope["provider_detail"] = self.provider_detail
        return envelope


class GeminiQuotaError(GeminiError):
    code = "gemini_quota_exhausted"
    http_status = 429
    retryable = True
    retry_after_seconds = 60


class GeminiAuthError(GeminiError):
    code = "gemini_auth_error"
    http_status = 401
    retryable = False


class GeminiBadRequestError(GeminiError):
    code = "gemini_bad_request"
    http_status = 400
    retryable = False


class GeminiServerError(GeminiError):
    code = "gemini_server_error"
    http_status = 502
    retryable = True
    retry_after_seconds = 15


class GeminiTimeoutError(GeminiError):
    code = "gemini_timeout"
    http_status = 504
    retryable = True
    retry_after_seconds = 10


class GeminiNetworkError(GeminiError):
    code = "gemini_network_error"
    http_status = 503
    retryable = True
    retry_after_seconds = 5


class GeminiInvalidJsonError(GeminiError):
    code = "gemini_invalid_json"
    http_status = 502
    retryable = True


class GeminiEmptyResponseError(GeminiError):
    code = "gemini_empty_response"
    http_status = 502
    retryable = True


class GeminiSafetyBlockedError(GeminiError):
    code = "gemini_safety_blocked"
    http_status = 422
    retryable = False


# ──────────────────────────────────────────────────────────────────────────────
# In-process token-bucket rate limiter
# ──────────────────────────────────────────────────────────────────────────────


class _GeminiQuotaGuard:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._minute_entries: deque[_ReservationEntry] = deque()
        self._day_entries: deque[_ReservationEntry] = deque()
        self._day_key = self._current_day_key()
        self._sequence = 0

    def reserve(self, *, tokens: int) -> _ReservationEntry:
        if not settings.orderflow_ai_gemini_rate_limit_enabled:
            return _ReservationEntry(
                reservation_id="gemini-rate-limit-disabled",
                timestamp=time.monotonic(),
                tokens=max(tokens, 1),
            )

        if tokens <= 0:
            tokens = 1

        deadline = time.monotonic() + max(settings.orderflow_ai_gemini_max_wait_seconds, 0)

        while True:
            with self._lock:
                now = time.monotonic()
                self._reset_day_if_needed()
                self._prune_minute_window(now)

                day_requests = len(self._day_entries)
                day_tokens = sum(entry.tokens for entry in self._day_entries)

                if day_requests + 1 > settings.orderflow_ai_gemini_requests_per_day:
                    raise GeminiQuotaError(
                        "Gemini daily request budget reached for this process. "
                        "Wait for the next quota reset (UTC midnight) or raise the daily request cap.",
                        retry_after_seconds=self._seconds_until_utc_midnight(),
                    )

                if day_tokens + tokens > settings.orderflow_ai_gemini_tokens_per_day:
                    raise GeminiQuotaError(
                        "Gemini daily token budget reached for this process. "
                        "Reduce prompt size or wait for the next quota reset.",
                        retry_after_seconds=self._seconds_until_utc_midnight(),
                    )

                wait_for_requests = self._request_wait_seconds(now)
                wait_for_tokens = self._token_wait_seconds(now, tokens)
                wait_seconds = max(wait_for_requests, wait_for_tokens)

                if wait_seconds <= 0:
                    self._sequence += 1
                    reservation = _ReservationEntry(
                        reservation_id=f"gemini-{self._sequence}",
                        timestamp=now,
                        tokens=tokens,
                    )
                    self._minute_entries.append(reservation)
                    self._day_entries.append(reservation)
                    return reservation

            if time.monotonic() + wait_seconds > deadline:
                raise GeminiQuotaError(
                    "Gemini per-minute quota is saturated and would require waiting longer than "
                    f"{settings.orderflow_ai_gemini_max_wait_seconds} seconds. "
                    "Reduce concurrency or prompt size, then retry.",
                    retry_after_seconds=int(max(wait_seconds, 1)),
                )

            time.sleep(min(max(wait_seconds, 0.05), 5.0))

    def commit(self, reservation: _ReservationEntry, *, actual_tokens: int | None) -> None:
        if not settings.orderflow_ai_gemini_rate_limit_enabled:
            return

        if actual_tokens is None or actual_tokens <= 0:
            return

        with self._lock:
            for queue in (self._minute_entries, self._day_entries):
                for entry in queue:
                    if entry.reservation_id == reservation.reservation_id:
                        entry.tokens = actual_tokens

    def release(self, reservation: _ReservationEntry) -> None:
        if not settings.orderflow_ai_gemini_rate_limit_enabled:
            return

        with self._lock:
            self._minute_entries = deque(
                entry
                for entry in self._minute_entries
                if entry.reservation_id != reservation.reservation_id
            )
            self._day_entries = deque(
                entry
                for entry in self._day_entries
                if entry.reservation_id != reservation.reservation_id
            )

    def _current_day_key(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _seconds_until_utc_midnight(self) -> int:
        now = datetime.now(UTC)
        seconds_today = now.hour * 3600 + now.minute * 60 + now.second
        return max(86_400 - seconds_today, 60)

    def _reset_day_if_needed(self) -> None:
        day_key = self._current_day_key()
        if day_key != self._day_key:
            self._day_key = day_key
            self._day_entries.clear()

    def _prune_minute_window(self, now: float) -> None:
        while self._minute_entries and now - self._minute_entries[0].timestamp >= 60.0:
            self._minute_entries.popleft()

    def _request_wait_seconds(self, now: float) -> float:
        next_request_count = len(self._minute_entries) + 1
        requests_per_minute = settings.orderflow_ai_gemini_requests_per_minute
        if next_request_count <= requests_per_minute:
            return 0.0

        overflow_index = next_request_count - requests_per_minute - 1
        if overflow_index < 0 or overflow_index >= len(self._minute_entries):
            overflow_index = 0
        return max(self._minute_entries[overflow_index].timestamp + 60.0 - now, 0.0)

    def _token_wait_seconds(self, now: float, tokens: int) -> float:
        minute_tokens = sum(entry.tokens for entry in self._minute_entries)
        tokens_per_minute = settings.orderflow_ai_gemini_tokens_per_minute
        if minute_tokens + tokens <= tokens_per_minute:
            return 0.0

        tokens_to_free = (minute_tokens + tokens) - tokens_per_minute
        freed_tokens = 0
        for entry in self._minute_entries:
            freed_tokens += entry.tokens
            if freed_tokens >= tokens_to_free:
                return max(entry.timestamp + 60.0 - now, 0.0)

        return 60.0


_GEMINI_QUOTA_GUARD = _GeminiQuotaGuard()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / settings.orderflow_ai_gemini_chars_per_token))


def extract_gemini_text(response: dict[str, object]) -> str:
    """Extract concatenated text from a Gemini response.

    Distinguishes safety / recitation blocks from genuinely empty responses so
    the UI can show distinct guidance.
    """
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        prompt_feedback = response.get("promptFeedback")
        if isinstance(prompt_feedback, dict):
            block_reason = prompt_feedback.get("blockReason")
            if isinstance(block_reason, str) and block_reason:
                raise GeminiSafetyBlockedError(
                    f"Gemini blocked the prompt before generating any output (reason: {block_reason}).",
                    provider_detail=block_reason,
                )
        raise GeminiEmptyResponseError("Gemini response contains no candidates.")

    text_chunks: list[str] = []
    finish_reasons: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        finish_reason = candidate.get("finishReason")
        if isinstance(finish_reason, str):
            finish_reasons.append(finish_reason)
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text_chunks.append(part["text"])

    if not text_chunks:
        for reason in finish_reasons:
            if reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"}:
                raise GeminiSafetyBlockedError(
                    f"Gemini stopped generation due to a {reason.lower()} filter. "
                    "Try rephrasing the source text or escalate to manual review.",
                    provider_detail=reason,
                )
            if reason == "MAX_TOKENS":
                raise GeminiEmptyResponseError(
                    "Gemini hit the max_output_tokens cap before producing any text. "
                    "Reduce prompt size or raise ORDERFLOW_AI_GEMINI_MAX_OUTPUT_TOKENS."
                )
        raise GeminiEmptyResponseError("Gemini response contained no text parts.")

    return "\n".join(text_chunks)


def extract_gemini_total_tokens(response: dict[str, object]) -> int | None:
    usage_metadata = response.get("usageMetadata")
    if not isinstance(usage_metadata, dict):
        return None

    total_tokens = usage_metadata.get("totalTokenCount")
    if isinstance(total_tokens, int) and total_tokens > 0:
        return total_tokens

    prompt_tokens = usage_metadata.get("promptTokenCount")
    candidate_tokens = usage_metadata.get("candidatesTokenCount")
    if isinstance(prompt_tokens, int) and isinstance(candidate_tokens, int):
        return prompt_tokens + candidate_tokens

    return None


def _classify_http_error(exc: urllib_error.HTTPError, label: str) -> GeminiError:
    detail = ""
    try:
        detail = exc.read().decode("utf-8", errors="replace")
    except Exception:
        detail = ""

    detail_upper = detail.upper()
    short_detail = detail[:500] if detail else None

    if exc.code == 429 or "RESOURCE_EXHAUSTED" in detail_upper:
        return GeminiQuotaError(
            f"Gemini rejected the {label} request because quota was exhausted. "
            "Wait for quota to refresh or raise the per-minute / per-day caps.",
            provider_detail=short_detail,
        )
    if exc.code in {401, 403}:
        return GeminiAuthError(
            f"Gemini rejected the {label} request: API key is missing, invalid, or unauthorized "
            "for this model. Check ORDERFLOW_AI_GEMINI_API_KEY.",
            provider_detail=short_detail,
        )
    if exc.code == 400:
        return GeminiBadRequestError(
            f"Gemini rejected the {label} request as malformed (HTTP 400). "
            "The model name or prompt structure may be invalid.",
            provider_detail=short_detail,
        )
    if 500 <= exc.code < 600:
        return GeminiServerError(
            f"Gemini service returned HTTP {exc.code} on the {label} request. "
            "This is usually transient — retry shortly.",
            provider_detail=short_detail,
        )
    return GeminiError(
        f"Gemini returned an unexpected HTTP {exc.code} on the {label} request.",
        provider_detail=short_detail,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────


def call_gemini_json(
    *,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float,
    max_output_tokens: int,
    request_label: str,
) -> dict[str, object]:
    encoded_model = urllib_parse.quote(model, safe="")
    reserve_tokens = estimate_text_tokens(prompt) + max(max_output_tokens, 1)
    reservation = _GEMINI_QUOTA_GUARD.reserve(tokens=reserve_tokens)

    request = urllib_request.Request(
        url=(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{encoded_model}:generateContent?key={api_key}"
        ),
        data=json.dumps(
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "responseMimeType": "application/json",
                    "maxOutputTokens": max_output_tokens,
                },
            }
        ).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(
            request,
            timeout=settings.orderflow_ai_timeout_seconds,
        ) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib_error.HTTPError as exc:
        _GEMINI_QUOTA_GUARD.release(reservation)
        raise _classify_http_error(exc, request_label) from exc
    except TimeoutError as exc:
        _GEMINI_QUOTA_GUARD.release(reservation)
        raise GeminiTimeoutError(
            f"Gemini did not respond within {settings.orderflow_ai_timeout_seconds}s for the "
            f"{request_label} request. Retry or increase ORDERFLOW_AI_TIMEOUT_SECONDS.",
        ) from exc
    except urllib_error.URLError as exc:
        _GEMINI_QUOTA_GUARD.release(reservation)
        # Catches DNS failure, refused connection, TLS issues, and network timeouts
        reason = getattr(exc, "reason", exc)
        is_timeout = isinstance(reason, TimeoutError) or "timed out" in str(reason).lower()
        if is_timeout:
            raise GeminiTimeoutError(
                f"Network timeout while calling Gemini for the {request_label} request: {reason}",
            ) from exc
        raise GeminiNetworkError(
            f"Network error while calling Gemini for the {request_label} request: {reason}",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - genuine catch-all for unknown urllib failures
        _GEMINI_QUOTA_GUARD.release(reservation)
        raise GeminiError(f"Gemini request failed unexpectedly for {request_label}: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        _GEMINI_QUOTA_GUARD.release(reservation)
        raise GeminiInvalidJsonError(
            "Gemini response body is not valid JSON.",
            provider_detail=raw[:300] if raw else None,
        ) from exc

    if not isinstance(parsed, dict):
        _GEMINI_QUOTA_GUARD.release(reservation)
        raise GeminiInvalidJsonError("Gemini response is not a JSON object.")

    _GEMINI_QUOTA_GUARD.commit(
        reservation,
        actual_tokens=extract_gemini_total_tokens(parsed),
    )
    return parsed
