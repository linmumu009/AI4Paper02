"""Durable, cross-process sliding-window rate limiting."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional


_SEVER_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = os.environ.get(
    "AI4PAPERS_RATE_LIMIT_DB",
    str(_SEVER_ROOT / "database" / "security_rate_limits.db"),
)
_KEY_PEPPER = os.environ.get("AI4PAPERS_RATE_LIMIT_PEPPER", "ai4papers-rate-limit-v1")
logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        super().__init__("rate limit exceeded")
        self.retry_after_seconds = max(1, int(retry_after_seconds))


def _connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limit_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket      TEXT NOT NULL,
            key_hash    TEXT NOT NULL,
            occurred_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rate_limit_lookup "
        "ON rate_limit_events(bucket, key_hash, occurred_at)"
    )
    return conn


def _hash_key(bucket: str, key: str) -> str:
    value = f"{_KEY_PEPPER}\n{bucket}\n{key}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


class PersistentRateLimiter:
    """Atomically enforce a host-local sliding window across restarts."""

    def __init__(
        self,
        *,
        bucket: str,
        max_attempts: int,
        window_seconds: int,
        db_path: Optional[str] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not bucket or max_attempts <= 0 or window_seconds <= 0:
            raise ValueError("invalid rate limiter configuration")
        self.bucket = bucket
        self.max_attempts = int(max_attempts)
        self.window_seconds = int(window_seconds)
        self.db_path = str(db_path or _DB_PATH)
        self.clock = clock
        self._fallback_events: dict[str, deque[float]] = {}
        self._fallback_lock = threading.Lock()
        self._last_storage_warning = float("-inf")

    def _check_memory_fallback(self, key_hash: str, now: float) -> None:
        """Keep rate limiting effective when the durable store is temporarily unwritable."""
        cutoff = now - self.window_seconds
        with self._fallback_lock:
            events = self._fallback_events.setdefault(key_hash, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.max_attempts:
                retry_after = math.ceil(events[0] + self.window_seconds - now)
                raise RateLimitExceeded(retry_after)
            events.append(now)

    def _warn_storage_fallback(self, exc: sqlite3.Error) -> None:
        monotonic_now = time.monotonic()
        if monotonic_now - self._last_storage_warning < 60:
            return
        self._last_storage_warning = monotonic_now
        logger.warning(
            "rate_limit_service: durable store unavailable for bucket=%s; "
            "using process-local fallback (%s)",
            self.bucket,
            type(exc).__name__,
        )

    def check(self, key: str) -> None:
        normalized = str(key or "unknown").strip().lower() or "unknown"
        key_hash = _hash_key(self.bucket, normalized)
        now = float(self.clock())
        cutoff = now - self.window_seconds
        conn: sqlite3.Connection | None = None
        try:
            conn = _connect(self.db_path)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM rate_limit_events WHERE bucket = ? AND occurred_at <= ?",
                (self.bucket, cutoff),
            )
            rows = conn.execute(
                """
                SELECT occurred_at
                FROM rate_limit_events
                WHERE bucket = ? AND key_hash = ? AND occurred_at > ?
                ORDER BY occurred_at ASC
                """,
                (self.bucket, key_hash, cutoff),
            ).fetchall()
            if len(rows) >= self.max_attempts:
                retry_after = math.ceil(
                    float(rows[0][0]) + self.window_seconds - now
                )
                conn.commit()
                raise RateLimitExceeded(retry_after)
            conn.execute(
                "INSERT INTO rate_limit_events(bucket, key_hash, occurred_at) "
                "VALUES (?, ?, ?)",
                (self.bucket, key_hash, now),
            )
            conn.commit()
        except sqlite3.Error as exc:
            if conn is not None and conn.in_transaction:
                conn.rollback()
            self._warn_storage_fallback(exc)
            self._check_memory_fallback(key_hash, now)
        except Exception:
            if conn is not None and conn.in_transaction:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()
