"""
Cross-process arXiv request throttling and 429 backoff helpers.

Ensures >= ARXIV_MIN_INTERVAL between any arXiv HTTP call (API + PDF/abs)
across pipeline scripts and API handlers on the same host.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from typing import Optional

_SEVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_DIR = os.path.join(_SEVER_DIR, "database")
_LOCK_PATH = os.path.join(_DB_DIR, "arxiv_global.lock")
_STATE_PATH = os.path.join(_DB_DIR, "arxiv_rate_state.json")

# Exit code used by arxiv_search when partial pages were saved after rate limit.
ARXIV_EXIT_RATE_LIMIT_PARTIAL = 3


class RateLimitExhausted(Exception):
    """All retries for a single arXiv request exhausted due to HTTP 429."""

    def __init__(self, message: str = "arXiv rate limit (429) retries exhausted"):
        super().__init__(message)


def _load_config():
    from config.config import (
        ARXIV_429_BASE_WAIT,
        ARXIV_429_MAX_WAIT,
        ARXIV_MIN_INTERVAL,
    )

    return ARXIV_MIN_INTERVAL, ARXIV_429_BASE_WAIT, ARXIV_429_MAX_WAIT


def compute_429_wait(
    attempt: int,
    retry_after: Optional[int] = None,
    *,
    base_wait: Optional[float] = None,
    max_wait: Optional[float] = None,
) -> float:
    """Exponential backoff for 429; honours Retry-After when larger."""
    _, cfg_base, cfg_max = _load_config()
    base = float(base_wait if base_wait is not None else cfg_base)
    cap = float(max_wait if max_wait is not None else cfg_max)
    exp = base * (2 ** max(0, attempt - 1))
    wait = max(float(retry_after or 0), exp)
    return min(wait, cap)


def _read_last_request_ts() -> float:
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return float(data.get("last_request_ts", 0.0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0.0


def _write_last_request_ts(ts: float) -> None:
    os.makedirs(_DB_DIR, exist_ok=True)
    tmp = _STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"last_request_ts": ts}, f)
    os.replace(tmp, _STATE_PATH)


def _acquire_file_lock(lock_fh) -> None:
    if sys.platform == "win32":
        import msvcrt

        lock_fh.seek(0)
        # Lock 1 byte at start of file
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
def acquire_arxiv_slot():
    """Cross-process mutex for arXiv HTTP pacing."""
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


def wait_before_request(min_interval: Optional[float] = None) -> None:
    """Block until at least min_interval seconds since the last arXiv request."""
    interval, _, _ = _load_config()
    if min_interval is not None:
        interval = float(min_interval)

    with acquire_arxiv_slot():
        last_wall = _read_last_request_ts()
        wall_now = time.time()
        elapsed = wall_now - last_wall
        if last_wall > 0 and elapsed < interval:
            time.sleep(interval - elapsed)
        _write_last_request_ts(time.time())


def mark_request_completed() -> None:
    """Record request completion time (call after HTTP if not using wait_before_request only)."""
    with acquire_arxiv_slot():
        _write_last_request_ts(time.time())


def parse_retry_after(header_value: Optional[str]) -> Optional[int]:
    if not header_value:
        return None
    try:
        return int(header_value.strip())
    except (ValueError, TypeError):
        return None
