"""Shared invariants for model responses that must contain user-visible text."""

from __future__ import annotations

from typing import Any


class EmptyLlmResponseError(RuntimeError):
    """Raised when an upstream model reports success without usable text."""


def require_nonempty_text(value: Any, *, operation: str) -> str:
    """Return stripped model text or fail before an empty result is published."""
    if not isinstance(value, str) or not value.strip():
        raise EmptyLlmResponseError(
            f"model returned empty content during {operation or 'unknown operation'}"
        )
    return value.strip()
