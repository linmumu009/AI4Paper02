"""
OpenRouter 免费 API Key 池服务层。

表结构
-------
    openrouter_key_pool (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key     TEXT NOT NULL UNIQUE,
        enabled     INTEGER NOT NULL DEFAULT 1,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )

    openrouter_key_usage_daily (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        key_id      INTEGER NOT NULL REFERENCES openrouter_key_pool(id),
        usage_date  TEXT NOT NULL,   -- ISO date YYYY-MM-DD (UTC)
        used_count  INTEGER NOT NULL DEFAULT 0,
        UNIQUE(key_id, usage_date)
    )

    openrouter_key_pool_settings (
        id          INTEGER PRIMARY KEY CHECK (id = 1),  -- single-row
        daily_limit INTEGER NOT NULL DEFAULT 50,
        updated_at  TEXT NOT NULL
    )
"""

import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from services.secret_storage_service import decrypt_secret, encrypt_secret

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_DIR = os.path.join(_BASE_DIR, "database")
_DB_PATH = os.path.join(_DB_DIR, "paper_analysis.db")
_COOLDOWN_PATH = os.path.join(_DB_DIR, "openrouter_key_cooldown.json")
_POOL_LOCK_PATH = os.path.join(_DB_DIR, "openrouter_pool.lock")

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD in UTC."""
    return datetime.now(timezone.utc).date().isoformat()


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


def _read_cooldowns() -> Dict[str, float]:
    try:
        with open(_COOLDOWN_PATH, "r", encoding="utf-8") as f:
            import json
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        return {str(k): float(v) for k, v in raw.items()}
    except (OSError, ValueError, TypeError):
        return {}


def _write_cooldowns(data: Dict[str, float]) -> None:
    import json

    os.makedirs(_DB_DIR, exist_ok=True)
    tmp = _COOLDOWN_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, _COOLDOWN_PATH)


def mark_key_cooldown(key_id: int, cooldown_seconds: float) -> None:
    """Mark a pool key as cooling down after a 429 response."""
    os.makedirs(_DB_DIR, exist_ok=True)
    lock_fh = open(_POOL_LOCK_PATH, "a+", encoding="utf-8")
    try:
        _acquire_file_lock(lock_fh)
        cooldowns = _read_cooldowns()
        until = time.time() + max(0.0, float(cooldown_seconds))
        existing = float(cooldowns.get(str(key_id), 0.0))
        cooldowns[str(key_id)] = max(existing, until)
        _write_cooldowns(cooldowns)
    finally:
        try:
            _release_file_lock(lock_fh)
        finally:
            lock_fh.close()


def _is_key_cooling(key_id: int, cooldowns: Dict[str, float]) -> bool:
    until = float(cooldowns.get(str(key_id), 0.0))
    return until > time.time()


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they do not exist."""
    conn = _connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS openrouter_key_pool (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key     TEXT NOT NULL UNIQUE,
                enabled     INTEGER NOT NULL DEFAULT 1,
                sort_order  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS openrouter_key_usage_daily (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id      INTEGER NOT NULL REFERENCES openrouter_key_pool(id) ON DELETE CASCADE,
                usage_date  TEXT NOT NULL,
                used_count  INTEGER NOT NULL DEFAULT 0,
                UNIQUE(key_id, usage_date)
            );

            CREATE TABLE IF NOT EXISTS openrouter_key_pool_settings (
                id          INTEGER PRIMARY KEY CHECK (id = 1),
                daily_limit INTEGER NOT NULL DEFAULT 50,
                updated_at  TEXT NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_daily_limit() -> int:
    """Return configured daily limit per key (default 50)."""
    conn = _connect()
    try:
        row = conn.execute("SELECT daily_limit FROM openrouter_key_pool_settings WHERE id = 1").fetchone()
        return int(row["daily_limit"]) if row else 50
    finally:
        conn.close()


def set_daily_limit(limit: int) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO openrouter_key_pool_settings (id, daily_limit, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET daily_limit = excluded.daily_limit, updated_at = excluded.updated_at
            """,
            (limit, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Key pool CRUD
# ---------------------------------------------------------------------------

def _mask_key(key: str) -> str:
    """Return a partially masked key for display: sk-or-v1-xxxx...xxxx"""
    if len(key) <= 12:
        return "****"
    return key[:10] + "..." + key[-4:]


def save_pool(keys_text: str, daily_limit: int) -> Dict[str, Any]:
    """
    Replace the pool with the keys provided as a newline-separated string.

    Existing keys that are still in the new list are kept (preserving their
    usage history).  Keys removed from the list are deleted.  New keys are
    inserted.  Sort order follows line position.

    Returns pool_status after saving.
    """
    raw_keys = [k.strip() for k in keys_text.splitlines() if k.strip()]
    # Deduplicate while preserving order
    seen: set = set()
    keys: List[str] = []
    for k in raw_keys:
        if k not in seen:
            seen.add(k)
            keys.append(k)

    now = _now_iso()
    conn = _connect()
    try:
        existing_rows = conn.execute("SELECT id, api_key FROM openrouter_key_pool").fetchall()
        existing_map: Dict[str, int] = {
            decrypt_secret(r["api_key"]): r["id"] for r in existing_rows
        }
        new_key_set = set(keys)

        # Delete removed keys
        for old_key, old_id in existing_map.items():
            if old_key not in new_key_set:
                conn.execute("DELETE FROM openrouter_key_pool WHERE id = ?", (old_id,))

        # Upsert remaining / new keys with updated sort_order
        for order, key in enumerate(keys):
            if key in existing_map:
                conn.execute(
                    "UPDATE openrouter_key_pool SET sort_order = ?, enabled = 1, updated_at = ? WHERE id = ?",
                    (order, now, existing_map[key]),
                )
            else:
                conn.execute(
                    "INSERT INTO openrouter_key_pool (api_key, enabled, sort_order, created_at, updated_at) VALUES (?, 1, ?, ?, ?)",
                    (encrypt_secret(key), order, now, now),
                )

        # Persist daily_limit
        conn.execute(
            """
            INSERT INTO openrouter_key_pool_settings (id, daily_limit, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET daily_limit = excluded.daily_limit, updated_at = excluded.updated_at
            """,
            (daily_limit, now),
        )
        conn.commit()
    finally:
        conn.close()

    return get_pool_status()


def get_pool_status() -> Dict[str, Any]:
    """
    Return pool settings and per-key status (masked).

    Shape::

        {
            "daily_limit": 50,
            "total_keys": 3,
            "available_keys": 2,
            "keys": [
                {
                    "id": 1,
                    "masked_key": "sk-or-v1-ab...cd12",
                    "enabled": true,
                    "used_today": 30,
                    "remaining_today": 20,
                }
            ]
        }
    """
    today = _today_str()
    conn = _connect()
    try:
        limit = get_daily_limit()
        rows = conn.execute(
            "SELECT id, api_key, enabled FROM openrouter_key_pool ORDER BY sort_order, id"
        ).fetchall()

        keys_info: List[Dict[str, Any]] = []
        available = 0
        for row in rows:
            usage_row = conn.execute(
                "SELECT used_count FROM openrouter_key_usage_daily WHERE key_id = ? AND usage_date = ?",
                (row["id"], today),
            ).fetchone()
            used = int(usage_row["used_count"]) if usage_row else 0
            remaining = max(0, limit - used)
            is_available = bool(row["enabled"]) and remaining > 0
            if is_available:
                available += 1
            keys_info.append({
                "id": row["id"],
                "masked_key": _mask_key(decrypt_secret(row["api_key"])),
                "enabled": bool(row["enabled"]),
                "used_today": used,
                "remaining_today": remaining,
            })

        return {
            "daily_limit": limit,
            "total_keys": len(keys_info),
            "available_keys": available,
            "keys": keys_info,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Key selection (used at call time)
# ---------------------------------------------------------------------------

def select_available_key() -> Dict[str, Any]:
    """
    Return the enabled key with the lowest today-usage that is still below
    the daily limit and not in 429 cooldown.

    Returns dict with ``id`` and ``api_key``.
    Raises ``RuntimeError`` when no key is available.
    """
    today = _today_str()
    limit = get_daily_limit()
    os.makedirs(_DB_DIR, exist_ok=True)
    lock_fh = open(_POOL_LOCK_PATH, "a+", encoding="utf-8")
    try:
        _acquire_file_lock(lock_fh)
        cooldowns = _read_cooldowns()
        now = time.time()
        pruned = {k: v for k, v in cooldowns.items() if float(v) > now}
        if pruned != cooldowns:
            _write_cooldowns(pruned)
        cooldowns = pruned

        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT p.id, p.api_key, COALESCE(u.used_count, 0) AS used_count
                FROM openrouter_key_pool p
                LEFT JOIN openrouter_key_usage_daily u
                       ON u.key_id = p.id AND u.usage_date = ?
                WHERE p.enabled = 1
                  AND COALESCE(u.used_count, 0) < ?
                ORDER BY COALESCE(u.used_count, 0), p.sort_order, p.id
                """,
                (today, limit),
            ).fetchall()
        finally:
            conn.close()

        for row in rows:
            if not _is_key_cooling(int(row["id"]), cooldowns):
                return {"id": row["id"], "api_key": decrypt_secret(row["api_key"])}
    finally:
        try:
            _release_file_lock(lock_fh)
        finally:
            lock_fh.close()

    raise RuntimeError(
        "OpenRouter Key 池已耗尽（今日所有 Key 均已达到每日调用上限或处于 429 冷却中），"
        "请稍后重试、明天再试或增加 Key / 调整每日上限。"
    )


def record_success(key_id: int) -> None:
    """Increment the usage counter for key_id on today's date."""
    today = _today_str()
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO openrouter_key_usage_daily (key_id, usage_date, used_count)
            VALUES (?, ?, 1)
            ON CONFLICT(key_id, usage_date) DO UPDATE SET used_count = used_count + 1
            """,
            (key_id, today),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Free model list
# ---------------------------------------------------------------------------

def fetch_free_models(timeout: int = 15) -> List[Dict[str, Any]]:
    """
    Fetch the OpenRouter model list and return only the free models
    (pricing.prompt == "0" and pricing.completion == "0").

    Returns a list of dicts with keys: id, name, context_length.
    Raises requests.RequestException on network error.
    """
    url = f"{_OPENROUTER_BASE_URL}/models"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json().get("data", [])

    free_models = []
    for m in data:
        pricing = m.get("pricing", {})
        if pricing.get("prompt") == "0" and pricing.get("completion") == "0":
            free_models.append({
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "context_length": m.get("context_length"),
            })

    free_models.sort(key=lambda x: x["id"])
    return free_models


# Ensure tables exist on import
init_db()
