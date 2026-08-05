"""Redact credentials from logs and generate safe public error references."""

from __future__ import annotations

import logging
import re
import secrets
import traceback
from typing import Any


_REDACTED = "[REDACTED]"
_PUBLIC_ERROR_RE = re.compile(r"错误编号：[0-9a-f]{12}")
_ERROR_REFERENCE_RE = re.compile(r"^[0-9a-f]{12}$")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|"
    r"token|secret|password|signature|sig)=)[^&#\s]+"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_ENCRYPTED_SECRET_RE = re.compile(r"enc:v1:[A-Za-z0-9_-]{12,}")
_API_KEY_RE = re.compile(r"\bsk-(?:or-v1-)?[A-Za-z0-9._-]{8,}")
_ASSIGNMENT_RE = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|apikey|authorization|access[_-]?token|"
    r"refresh[_-]?token|token|secret|password|signature)[\"']?\s*[:=]\s*)"
    r"([\"']?)([^\"'\s,;&]{1,})([\"']?)"
)


def redact_sensitive_text(value: Any, *, max_length: int = 8000) -> str:
    text = str(value or "")
    text = _QUERY_SECRET_RE.sub(lambda match: match.group(1) + _REDACTED, text)
    text = _BEARER_RE.sub("Bearer " + _REDACTED, text)
    text = _ENCRYPTED_SECRET_RE.sub(_REDACTED, text)
    text = _API_KEY_RE.sub(_REDACTED, text)
    text = _ASSIGNMENT_RE.sub(
        lambda match: match.group(1)
        + (match.group(2) or "")
        + _REDACTED
        + (match.group(4) or ""),
        text,
    )
    if len(text) > max_length:
        text = text[:max_length] + "...[TRUNCATED]"
    return text


def format_sanitized_exception(exc: BaseException) -> str:
    rendered = "".join(
        traceback.TracebackException.from_exception(
            exc,
            capture_locals=False,
        ).format()
    )
    return redact_sensitive_text(rendered)


def log_internal_error(
    logger: logging.Logger,
    operation: str,
    exc: BaseException,
    *,
    request_path: str = "",
) -> str:
    reference = secrets.token_hex(6)
    logger.error(
        "internal_error ref=%s operation=%s path=%s\n%s",
        reference,
        redact_sensitive_text(operation, max_length=200),
        redact_sensitive_text(request_path, max_length=500),
        format_sanitized_exception(exc),
    )
    return reference


def public_error_detail(reference: str, action: str = "服务暂时不可用") -> str:
    return f"{action}（错误编号：{reference}）"


def is_public_error_detail(value: Any) -> bool:
    return bool(_PUBLIC_ERROR_RE.search(str(value or "")))


def is_error_reference(value: Any) -> bool:
    return bool(_ERROR_REFERENCE_RE.fullmatch(str(value or "")))
