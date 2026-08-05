"""
Cross-process OpenRouter free-tier request throttling and 429 backoff helpers.

Enforces a sliding-window RPM cap (default 18/min, below OpenRouter's 20/min
free-models-per-min limit) across pipeline subprocesses and API handlers.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from typing import Any, List, Optional

_SEVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_DIR = os.path.join(_SEVER_DIR, "database")
_LOCK_PATH = os.path.join(_DB_DIR, "openrouter_global.lock")
_STATE_PATH = os.path.join(_DB_DIR, "openrouter_rate_state.json")

_WINDOW_SECONDS = 60.0


class OpenRouterRateLimitExhausted(Exception):
    """All retries for a single OpenRouter request exhausted due to HTTP 429."""

    def __init__(self, message: str = "OpenRouter rate limit (429) retries exhausted"):
        super().__init__(message)


def _load_config():
    from config.config import (
        OPENROUTER_429_BASE_WAIT,
        OPENROUTER_429_MAX_RETRIES,
        OPENROUTER_429_MAX_WAIT,
        OPENROUTER_FREE_RPM,
    )

    return OPENROUTER_FREE_RPM, OPENROUTER_429_BASE_WAIT, OPENROUTER_429_MAX_WAIT, OPENROUTER_429_MAX_RETRIES


def compute_429_wait(
    attempt: int,
    retry_after: Optional[float] = None,
    *,
    base_wait: Optional[float] = None,
    max_wait: Optional[float] = None,
) -> float:
    """Exponential backoff for 429; honours Retry-After when larger."""
    _, cfg_base, cfg_max, _ = _load_config()
    base = float(base_wait if base_wait is not None else cfg_base)
    cap = float(max_wait if max_wait is not None else cfg_max)
    exp = base * (2 ** max(0, attempt - 1))
    wait = max(float(retry_after or 0), exp)
    return min(wait, cap)


def parse_retry_after(header_value: Optional[str]) -> Optional[float]:
    if not header_value:
        return None
    try:
        return float(header_value.strip())
    except (ValueError, TypeError):
        return None


def parse_rate_limit_reset_ms(header_value: Optional[str]) -> Optional[float]:
    """Parse X-RateLimit-Reset (milliseconds since epoch) to seconds-from-now."""
    if not header_value:
        return None
    try:
        reset_ms = float(header_value.strip())
        wait = (reset_ms / 1000.0) - time.time()
        return max(0.0, wait)
    except (ValueError, TypeError):
        return None


def extract_retry_wait_from_exception(exc: Exception) -> Optional[float]:
    """Best-effort wait hint from OpenAI RateLimitError / APIStatusError."""
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        retry_after = parse_retry_after(headers.get("Retry-After") or headers.get("retry-after"))
        if retry_after is not None:
            return retry_after
        reset_wait = parse_rate_limit_reset_ms(
            headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
        )
        if reset_wait is not None:
            return reset_wait

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        meta = (body.get("error") or {}).get("metadata") or {}
        hdrs = meta.get("headers") or {}
        reset_wait = parse_rate_limit_reset_ms(hdrs.get("X-RateLimit-Reset"))
        if reset_wait is not None:
            return reset_wait

    return None


def is_rate_limit_error(exc: Exception) -> bool:
    try:
        from openai import APIStatusError, RateLimitError
    except ImportError:
        RateLimitError = type(None)  # type: ignore
        APIStatusError = type(None)  # type: ignore

    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIStatusError) and getattr(exc, "status_code", None) == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg


def _acquire_file_lock(lock_fh) -> None:
    if sys.platform == "win32":
        import msvcrt

        lock_fh.seek(0)
        msvcrt.locking(lock_fh.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)


def _release_file_lock(lock_fh) -> None:
    if sys.platform == "win32":
        import msvcrt

        lock_fh.seek(0)
        try:
            msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl

        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


@contextmanager
def acquire_openrouter_lock():
    """Cross-process mutex for OpenRouter RPM pacing."""
    os.makedirs(_DB_DIR, exist_ok=True)
    lock_fh = open(_LOCK_PATH, "a+", encoding="utf-8")
    try:
        _acquire_file_lock(lock_fh)
        yield
    finally:
        try:
            _release_file_lock(lock_fh)
        finally:
            lock_fh.close()


def _read_window() -> List[float]:
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("timestamps", [])
        return [float(t) for t in raw if isinstance(t, (int, float))]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []


def _write_window(timestamps: List[float]) -> None:
    os.makedirs(_DB_DIR, exist_ok=True)
    tmp = _STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"timestamps": timestamps}, f)
    os.replace(tmp, _STATE_PATH)


def wait_for_openrouter_slot() -> None:
    """Block until a request slot is available under the global RPM cap."""
    rpm, _, _, _ = _load_config()
    rpm = max(1, int(rpm))

    with acquire_openrouter_lock():
        while True:
            now = time.time()
            window = [t for t in _read_window() if now - t < _WINDOW_SECONDS]
            if len(window) < rpm:
                window.append(now)
                _write_window(window)
                return
            sleep_for = _WINDOW_SECONDS - (now - window[0]) + 0.05
            if sleep_for > 0:
                time.sleep(sleep_for)


def get_window_usage() -> dict[str, Any]:
    """Return current sliding-window usage (for diagnostics)."""
    rpm, _, _, _ = _load_config()
    now = time.time()
    window = [t for t in _read_window() if now - t < _WINDOW_SECONDS]
    return {
        "rpm_limit": rpm,
        "used_in_window": len(window),
        "remaining": max(0, int(rpm) - len(window)),
    }
