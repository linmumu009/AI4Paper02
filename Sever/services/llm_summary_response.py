"""Reliable extraction and retry handling for non-streaming LLM summaries."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional


_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def _response_diagnostics(response: Any) -> dict[str, Any]:
    choices = getattr(response, "choices", None) or []
    choice = choices[0] if choices else None
    return {
        "response_id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "choices": len(choices),
        "finish_reason": getattr(choice, "finish_reason", None),
    }


def _response_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "") if message is not None else ""
    return content.strip() if isinstance(content, str) else ""


def _is_retryable_exception(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    return status_code in _RETRYABLE_STATUS_CODES


def create_nonempty_completion(
    client: Any,
    *,
    request_kwargs: dict[str, Any],
    paper_id: str = "",
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    logger: Optional[Callable[[str], None]] = None,
    content_validator: Optional[Callable[[str], bool]] = None,
) -> str:
    """Return non-empty assistant content or raise after bounded retries.

    Empty successful responses are retried because several OpenAI-compatible
    providers occasionally return HTTP 200 with no choices or null content.
    Diagnostics intentionally exclude prompts and credentials.
    """
    attempts = max(1, int(max_attempts))
    log = logger or (lambda message: print(message, flush=True))
    last_diagnostics: dict[str, Any] = {}

    for attempt in range(1, attempts + 1):
        try:
            response = client.chat.completions.create(**request_kwargs)
        except Exception as exc:
            if attempt >= attempts or not _is_retryable_exception(exc):
                raise
            delay = max(0.0, float(base_delay_seconds)) * (2 ** (attempt - 1))
            log(
                f"[SUMMARY] retry paper={paper_id or '-'} attempt={attempt}/{attempts} "
                f"reason={type(exc).__name__} status={getattr(exc, 'status_code', None)} "
                f"delay={delay:.1f}s"
            )
            sleep(delay)
            continue

        content = _response_content(response)
        is_valid = bool(content) and (
            content_validator(content) if content_validator is not None else True
        )
        if is_valid:
            return content

        last_diagnostics = _response_diagnostics(response)
        reason = "invalid_content" if content else "empty_response"
        if attempt < attempts:
            delay = max(0.0, float(base_delay_seconds)) * (2 ** (attempt - 1))
            log(
                f"[SUMMARY] retry paper={paper_id or '-'} attempt={attempt}/{attempts} "
                f"reason={reason} diagnostics={last_diagnostics!r} "
                f"delay={delay:.1f}s"
            )
            sleep(delay)

    raise RuntimeError(
        f"summary provider returned no publishable content after {attempts} attempts; "
        f"paper={paper_id or '-'} diagnostics={last_diagnostics!r}"
    )
