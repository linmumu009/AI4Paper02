"""Durable, cross-process sliding-window rate limiting."""

from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Callable, Optional


_SEVER_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = os.environ.get(
    "AI4PAPERS_RATE_LIMIT_DB",
    str(_SEVER_ROOT / "database" / "security_rate_limits.db"),
)
_KEY_PEPPER = os.environ.get("AI4PAPERS_RATE_LIMIT_PEPPER", "ai4papers-rate-limit-v1")


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

    def check(self, key: str) -> None:
        normalized = str(key or "unknown").strip().lower() or "unknown"
        key_hash = _hash_key(self.bucket, normalized)
        now = float(self.clock())
        cutoff = now - self.window_seconds
        conn = _connect(self.db_path)
        try:
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
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()
