from __future__ import annotations

from orderflow_api.core.config import settings


class GroqError(ValueError):
    code: str = "groq_error"
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


class GroqQuotaError(GroqError):
    code = "groq_quota_exhausted"
    http_status = 429
    retryable = True
    retry_after_seconds = 60


class GroqAuthError(GroqError):
    code = "groq_auth_error"
    http_status = 401


class GroqBadRequestError(GroqError):
    code = "groq_bad_request"
    http_status = 400


class GroqServerError(GroqError):
    code = "groq_server_error"
    http_status = 502
    retryable = True
    retry_after_seconds = 15


class GroqTimeoutError(GroqError):
    code = "groq_timeout"
    http_status = 504
    retryable = True
    retry_after_seconds = 10


class GroqNetworkError(GroqError):
    code = "groq_network_error"
    http_status = 503
    retryable = True
    retry_after_seconds = 5


def extract_groq_text(response: dict[str, object]) -> str:
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GroqError("Groq response contains no candidates.")

    text_chunks: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
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
        raise GroqError("Groq response contained no text parts.")
    return "\n".join(text_chunks)


def call_groq_json(
    *,
    api_key: str,
    model: str | None = None,
    prompt: str,
    temperature: float,
    request_label: str,
) -> dict[str, object]:
    """Call Groq's OpenAI-compatible chat completions endpoint."""
    import httpx

    resolved_model = model or settings.orderflow_ai_default_model or "llama-3.3-70b-versatile"
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    try:
        with httpx.Client(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": user_agent,
            },
        ) as client:
            res = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={
                    "model": resolved_model,
                    "response_format": {"type": "json_object"},
                    "temperature": temperature,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a legal AI assistant. Output ONLY valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=settings.orderflow_ai_timeout_seconds,
            )
            res.raise_for_status()
            data = res.json()
            content = data["choices"][0]["message"]["content"]
            return {"candidates": [{"content": {"parts": [{"text": content}]}}]}
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else None
        retry_after = None
        if exc.response is not None:
            raw_retry_after = exc.response.headers.get("retry-after")
            if raw_retry_after and raw_retry_after.isdigit():
                retry_after = int(raw_retry_after)
        status_code = exc.response.status_code if exc.response is not None else 0
        if status_code == 429:
            raise GroqQuotaError(
                f"Groq rejected the {request_label} request because quota or rate limit was reached.",
                retry_after_seconds=retry_after,
                provider_detail=detail,
            ) from exc
        if status_code in {401, 403}:
            raise GroqAuthError(
                f"Groq rejected the {request_label} request. Check ORDERFLOW_AI_GROQ_API_KEY.",
                provider_detail=detail,
            ) from exc
        if status_code == 400:
            raise GroqBadRequestError(
                f"Groq rejected the {request_label} request. Check ORDERFLOW_AI_DEFAULT_MODEL.",
                provider_detail=detail,
            ) from exc
        if 500 <= status_code < 600:
            raise GroqServerError(
                f"Groq service returned HTTP {status_code} for the {request_label} request.",
                provider_detail=detail,
            ) from exc
        raise GroqError(
            f"Groq request failed with HTTP {status_code} for {request_label}.",
            provider_detail=detail,
        ) from exc
    except httpx.TimeoutException as exc:
        raise GroqTimeoutError(
            f"Groq did not respond within {settings.orderflow_ai_timeout_seconds}s for {request_label}."
        ) from exc
    except httpx.RequestError as exc:
        raise GroqNetworkError(
            f"Network error while calling Groq for {request_label}: {exc}"
        ) from exc
    except Exception as exc:
        raise GroqError(
            f"Groq request failed: {exc}",
            provider_detail="groq_failed",
        ) from exc
