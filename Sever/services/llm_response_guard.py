"""Shared invariants for model responses that must contain user-visible text."""

from __future__ import annotations

from typing import Any, TypeVar


_StructuredValue = TypeVar("_StructuredValue", dict, list, tuple)


class EmptyLlmResponseError(RuntimeError):
    """Raised when an upstream model reports success without usable text."""


class InvalidLlmResponseError(RuntimeError):
    """Raised when model text cannot produce a usable structured result."""


def require_nonempty_text(value: Any, *, operation: str) -> str:
    """Return stripped model text or fail before an empty result is published."""
    if not isinstance(value, str) or not value.strip():
        raise EmptyLlmResponseError(
            f"model returned empty content during {operation or 'unknown operation'}"
        )
    return value.strip()


def has_meaningful_text(value: Any) -> bool:
    """Return whether a nested payload contains at least one visible string."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(has_meaningful_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_meaningful_text(item) for item in value)
    return False


def require_meaningful_structure(
    value: _StructuredValue,
    *,
    operation: str,
) -> _StructuredValue:
    """Reject parsed model payloads that contain no user-visible information."""
    if not isinstance(value, (dict, list, tuple)) or not has_meaningful_text(value):
        raise InvalidLlmResponseError(
            f"model returned invalid or empty structured content during "
            f"{operation or 'unknown operation'}"
        )
    return value
