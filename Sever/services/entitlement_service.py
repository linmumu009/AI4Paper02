"""
Entitlement service — centralised quota and feature-access logic.

Tier hierarchy:  free < pro < pro_plus

Quota period types:
  - "daily"   : resets each calendar day  (period_key = "YYYY-MM-DD")
  - "monthly" : resets each calendar month (period_key = "YYYY-MM")
  - "total"   : never resets (used for free-tier lifetime upload cap)
  - None      : unlimited — no tracking needed

Feature keys used in usage_quotas / TIER_ENTITLEMENTS:
  "chat"       — paper/general AI chat messages
  "compare"    — compare sessions started
  "research"   — deep-research sessions started (start + followup + continue-round3)
  "idea_gen"   — idea-candidate generation calls
  "upload"     — user-uploaded papers processed
  "translate"  — full-text paper translation (LLM-heavy; parallel chunked calls)
  "export"     — DOCX / PDF export (quota-tracked across all tiers)

Boolean-gated features (no quota table row, just config lookup):
  "general_chat"      — general AI assistant availability
  "note_file_upload"  — note attachments upload
  "llm_preset"        — custom LLM preset management
  "prompt_preset"     — custom prompt preset management
  "export_docx_pdf"   — DOCX / PDF export availability gate (all tiers now True)
  "batch_export"      — batch ZIP export
  "translate"         — full-text paper translation gate (all tiers now True)

Per-session limits (returned as config, not tracked in usage_quotas):
  "compare_max_items"        — max papers per compare session
  "kb_paper_limit"           — max papers saved to knowledge base (total)
  "kb_folder_limit"          — max KB folders (total)
  "kb_note_limit"            — max KB notes (total)
  "kb_compare_result_limit"  — max saved compare results (total)
  "browse_limit"             — max daily visible papers in digest/list
  "research_history_days"    — how many days of research history to retain
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

# ---------------------------------------------------------------------------
# Tier entitlement configuration (single source of truth)
# ---------------------------------------------------------------------------

_UNLIMITED = None  # sentinel for "no cap"

TIER_ENTITLEMENTS: dict[str, dict[str, Any]] = {
    "free": {
        # --- quota-tracked features ---
        "chat_limit": 10,
        "chat_period": "daily",
        "compare_limit": 3,
        "compare_period": "monthly",
        "research_limit": 2,
        "research_period": "monthly",
        "idea_gen_limit": 3,
        "idea_gen_period": "monthly",
        # changed from 5/total to 2/monthly so quota resets and users stay engaged
        "upload_limit": 2,
        "upload_period": "monthly",
        "translate_limit": 2,
        "translate_period": "monthly",
        "export_limit": 2,
        "export_period": "monthly",
        # --- per-session caps ---
        "compare_max_items": 2,
        # --- storage caps ---
        "kb_paper_limit": 20,
        "kb_folder_limit": 3,
        "kb_note_limit": 10,
        "kb_compare_result_limit": 3,
        # --- browse (digest / paper list) daily visible paper count ---
        "browse_limit": 3,
        # --- history retention ---
        "research_history_days": 3,
        # --- boolean gates ---
        "general_chat": False,
        "note_file_upload": False,
        "llm_preset": False,
        "prompt_preset": False,
        "export_docx_pdf": True,
        "batch_export": False,
        "translate": True,
    },
    "pro": {
        "chat_limit": _UNLIMITED,
        "chat_period": None,
        "compare_limit": 30,
        "compare_period": "monthly",
        "research_limit": 15,
        "research_period": "monthly",
        "idea_gen_limit": 30,
        "idea_gen_period": "monthly",
        "upload_limit": 30,
        "upload_period": "monthly",
        "translate_limit": 15,
        "translate_period": "monthly",
        "export_limit": 15,
        "export_period": "monthly",
        "compare_max_items": 5,
        "kb_paper_limit": 100,
        "kb_folder_limit": 10,
        "kb_note_limit": 50,
        "kb_compare_result_limit": 20,
        "browse_limit": 9,
        "research_history_days": 14,
        "general_chat": True,
        "note_file_upload": True,
        "llm_preset": True,
        "prompt_preset": True,
        "export_docx_pdf": True,
        "batch_export": False,
        "translate": True,
    },
    "pro_plus": {
        "chat_limit": _UNLIMITED,
        "chat_period": None,
        "compare_limit": 100,
        "compare_period": "monthly",
        "research_limit": 50,
        "research_period": "monthly",
        "idea_gen_limit": 100,
        "idea_gen_period": "monthly",
        "upload_limit": 100,
        "upload_period": "monthly",
        "translate_limit": 28,
        "translate_period": "monthly",
        "export_limit": 28,
        "export_period": "monthly",
        "compare_max_items": 8,
        "kb_paper_limit": 500,
        "kb_folder_limit": 30,
        "kb_note_limit": 200,
        "kb_compare_result_limit": 100,
        "browse_limit": _UNLIMITED,
        # max 30 days; no permanent storage commitment
        "research_history_days": 30,
        "general_chat": True,
        "note_file_upload": True,
        "llm_preset": True,
        "prompt_preset": True,
        "export_docx_pdf": True,
        "batch_export": True,
        "translate": True,
    },
}

# Engagement reward delta boosts (added ON TOP of tier baseline)
# Keys match feature names used in this service
ENGAGEMENT_BOOST_DELTAS: dict[str, dict[str, Any]] = {
    "day2_chat_boost_ticket": {
        "chat_input_multiplier": 1.5,   # multiplies the chat service's input_hard_limit
    },
    "day3_fast_track_ticket": {
        "upload_priority": 1,           # not a numeric delta, handled separately
    },
    "day4_idea_boost_ticket": {
        "idea_atoms_limit_multiplier": 1.5,  # multiplies the atom retrieval pool in idea generation
    },
    "day5_compare_plus_ticket": {
        "compare_max_items_delta": 2,
    },
    "day7_research_accelerator": {
        "research_input_multiplier": 1.5,
        "research_max_top_n": 30,
    },
    "day30_compare_premium_ticket": {
        "compare_max_items_delta": 4,
    },
    "day60_research_premium_ticket": {
        "research_input_multiplier": 2.0,
        "research_max_top_n": 30,
        "compare_max_items_delta": 4,
    },
}

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _today_key() -> str:
    return _now_utc().date().isoformat()


def _month_key() -> str:
    return _now_utc().strftime("%Y-%m")


def _period_key(period: str) -> str:
    if period == "daily":
        return _today_key()
    if period == "monthly":
        return _month_key()
    if period == "total":
        return "total"
    return "total"


def init_db() -> None:
    """Create usage_quotas table if it doesn't exist (called from api.py startup)."""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS usage_quotas (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                feature      TEXT    NOT NULL,
                period_key   TEXT    NOT NULL,
                usage_count  INTEGER NOT NULL DEFAULT 0,
                last_used_at TEXT,
                UNIQUE(user_id, feature, period_key)
            );
            CREATE INDEX IF NOT EXISTS idx_usage_quotas_user_feature
                ON usage_quotas(user_id, feature, period_key);
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tier resolution helpers
# ---------------------------------------------------------------------------

def _get_user_tier(user_id: int, conn: sqlite3.Connection) -> str:
    """Read tier from auth_users; returns 'free' if missing."""
    row = conn.execute(
        "SELECT role, tier, tier_expires_at FROM auth_users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return "free"
    role = (row["role"] or "user").strip()
    if role in ("admin", "superadmin"):
        return "pro_plus"
    tier = (row["tier"] or "free").strip()
    if tier not in TIER_ENTITLEMENTS:
        return "free"
    # Check expiry inline (mirrors auth_service._ensure_user_tier_not_expired)
    if tier in ("pro", "pro_plus"):
        expires_at = row["tier_expires_at"]
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp <= _now_utc():
                    return "free"
            except ValueError:
                pass
    return tier


def get_tier_entitlements(tier: str) -> dict[str, Any]:
    """Return the raw entitlement config for a tier (no usage data)."""
    return dict(TIER_ENTITLEMENTS.get(tier, TIER_ENTITLEMENTS["free"]))


# ---------------------------------------------------------------------------
# Usage quota helpers
# ---------------------------------------------------------------------------

def _get_usage(conn: sqlite3.Connection, user_id: int, feature: str, period: str) -> int:
    pk = _period_key(period)
    row = conn.execute(
        "SELECT usage_count FROM usage_quotas WHERE user_id = ? AND feature = ? AND period_key = ?",
        (user_id, feature, pk),
    ).fetchone()
    return int(row["usage_count"]) if row else 0


def check_quota(
    user_id: int,
    feature: str,
) -> dict[str, Any]:
    """
    Check whether the user has quota remaining for *feature*.

    Returns:
        {
            "allowed": bool,
            "limit": int | None,
            "used": int,
            "remaining": int | None,
            "period": str | None,
        }
    """
    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
        ent = TIER_ENTITLEMENTS[tier]
        limit = ent.get(f"{feature}_limit")
        period = ent.get(f"{feature}_period")

        if limit is _UNLIMITED or limit is None:
            return {"allowed": True, "limit": None, "used": 0, "remaining": None, "period": period}

        used = _get_usage(conn, user_id, feature, period)
        remaining = max(0, limit - used)
        return {
            "allowed": used < limit,
            "limit": limit,
            "used": used,
            "remaining": remaining,
            "period": period,
        }
    finally:
        conn.close()


def consume_quota(
    user_id: int,
    feature: str,
) -> dict[str, Any]:
    """
    Atomically increment usage for *feature* by 1.
    Raises HTTPException 429 if quota exceeded.
    Returns updated quota status dict (same shape as check_quota).
    """
    from fastapi import HTTPException

    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
        ent = TIER_ENTITLEMENTS[tier]
        limit = ent.get(f"{feature}_limit")
        period = ent.get(f"{feature}_period")

        if limit is _UNLIMITED or limit is None:
            return {"allowed": True, "limit": None, "used": 0, "remaining": None, "period": period}

        pk = _period_key(period)
        now_iso = _now_utc().isoformat()

        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT usage_count FROM usage_quotas WHERE user_id = ? AND feature = ? AND period_key = ?",
            (user_id, feature, pk),
        ).fetchone()
        current = int(row["usage_count"]) if row else 0

        if current >= limit:
            conn.rollback()
            _period_label = {"daily": "今日", "monthly": "本月", "total": "总计"}.get(period or "", "")
            raise HTTPException(
                status_code=429,
                detail=f"{_period_label}{feature} 用量已达上限（{limit}），请升级套餐以继续使用",
            )

        new_count = current + 1
        conn.execute(
            """
            INSERT INTO usage_quotas (user_id, feature, period_key, usage_count, last_used_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(user_id, feature, period_key) DO UPDATE SET
                usage_count  = usage_count + 1,
                last_used_at = excluded.last_used_at
            """,
            (user_id, feature, pk, now_iso),
        )
        conn.commit()

        remaining = max(0, limit - new_count)
        return {
            "allowed": True,
            "limit": limit,
            "used": new_count,
            "remaining": remaining,
            "period": period,
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def check_boolean_gate(user_id: int, gate: str) -> bool:
    """Return True if the user's tier has the boolean feature enabled."""
    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
        return bool(TIER_ENTITLEMENTS[tier].get(gate, False))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Compare helpers (per-session max items + engagement boost)
# ---------------------------------------------------------------------------

def get_compare_max_items(user_id: int, engagement_boost: dict[str, Any] | None = None) -> int:
    """
    Return effective max papers per compare session for this user, accounting
    for any active engagement boost.

    engagement_boost should be the dict returned by engagement_service.get_reward_boost().
    """
    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
    finally:
        conn.close()

    base = TIER_ENTITLEMENTS[tier]["compare_max_items"]
    if not engagement_boost:
        return base

    reward_code = engagement_boost.get("reward_code", "")
    delta = ENGAGEMENT_BOOST_DELTAS.get(reward_code, {}).get("compare_max_items_delta", 0)
    return base + delta


def get_effective_compare_max(user_id: int, reward_boost: dict[str, Any] | None = None) -> int:
    """Alias kept for callers that pass raw reward boost from engagement_service."""
    boost_code = (reward_boost or {}).get("reward_code", "")
    delta = ENGAGEMENT_BOOST_DELTAS.get(boost_code, {}).get("compare_max_items_delta", 0)

    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
    finally:
        conn.close()

    return TIER_ENTITLEMENTS[tier]["compare_max_items"] + delta


# ---------------------------------------------------------------------------
# KB storage helpers
# ---------------------------------------------------------------------------

def get_kb_paper_count(user_id: int, scope: str = "kb") -> int:
    """Return the number of papers the user currently has in their KB."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_papers WHERE user_id = ? AND scope = ?",
            (user_id, scope),
        ).fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def get_kb_folder_count(user_id: int, scope: str = "kb") -> int:
    """Return the number of folders the user currently has in their KB."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_folders WHERE user_id = ? AND scope = ?",
            (user_id, scope),
        ).fetchone()
        return int(row["cnt"]) if row else 0
    finally:
        conn.close()


def check_kb_paper_limit(user_id: int) -> dict[str, Any]:
    """
    Check whether the user can add more papers to their KB.
    Returns same shape as check_quota.
    """
    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
        limit = TIER_ENTITLEMENTS[tier]["kb_paper_limit"]
        if limit is _UNLIMITED or limit is None:
            return {"allowed": True, "limit": None, "used": 0, "remaining": None}
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_papers WHERE user_id = ? AND scope = 'kb'",
            (user_id,),
        ).fetchone()
        used = int(row["cnt"]) if row else 0
        remaining = max(0, limit - used)
        return {"allowed": used < limit, "limit": limit, "used": used, "remaining": remaining}
    finally:
        conn.close()


def check_kb_folder_limit(user_id: int) -> dict[str, Any]:
    """Check whether the user can create more KB folders."""
    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
        limit = TIER_ENTITLEMENTS[tier]["kb_folder_limit"]
        if limit is _UNLIMITED or limit is None:
            return {"allowed": True, "limit": None, "used": 0, "remaining": None}
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_folders WHERE user_id = ? AND scope = 'kb'",
            (user_id,),
        ).fetchone()
        used = int(row["cnt"]) if row else 0
        remaining = max(0, limit - used)
        return {"allowed": used < limit, "limit": limit, "used": used, "remaining": remaining}
    finally:
        conn.close()


def check_kb_note_limit(user_id: int) -> dict[str, Any]:
    """Check whether the user can create more KB notes (scope='kb' only)."""
    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
        limit = TIER_ENTITLEMENTS[tier]["kb_note_limit"]
        if limit is _UNLIMITED or limit is None:
            return {"allowed": True, "limit": None, "used": 0, "remaining": None}
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_notes WHERE user_id = ? AND scope = 'kb'",
            (user_id,),
        ).fetchone()
        used = int(row["cnt"]) if row else 0
        remaining = max(0, limit - used)
        return {"allowed": used < limit, "limit": limit, "used": used, "remaining": remaining}
    finally:
        conn.close()


def check_kb_compare_result_limit(user_id: int) -> dict[str, Any]:
    """Check whether the user can save more KB compare results."""
    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
        limit = TIER_ENTITLEMENTS[tier]["kb_compare_result_limit"]
        if limit is _UNLIMITED or limit is None:
            return {"allowed": True, "limit": None, "used": 0, "remaining": None}
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_compare_results WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        used = int(row["cnt"]) if row else 0
        remaining = max(0, limit - used)
        return {"allowed": used < limit, "limit": limit, "used": used, "remaining": remaining}
    finally:
        conn.close()


def get_browse_limit(user_id: Optional[int]) -> Optional[int]:
    """Return the daily visible paper count limit for the user (None = unlimited)."""
    if user_id is None:
        return TIER_ENTITLEMENTS["free"]["browse_limit"]
    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
        return TIER_ENTITLEMENTS[tier]["browse_limit"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Full entitlement snapshot (for /api/entitlements/me)
# ---------------------------------------------------------------------------

def get_user_entitlements(user_id: int) -> dict[str, Any]:
    """
    Return a complete entitlement snapshot for the user, including:
    - tier and its display label
    - per-feature quota status (limit / used / remaining / period)
    - boolean gates
    - KB storage status
    - per-session caps
    """
    conn = _connect()
    try:
        tier = _get_user_tier(user_id, conn)
        ent = TIER_ENTITLEMENTS[tier]

        def _quota_snapshot(feature: str) -> dict[str, Any]:
            limit = ent.get(f"{feature}_limit")
            period = ent.get(f"{feature}_period")
            if limit is _UNLIMITED or limit is None:
                return {"limit": None, "used": 0, "remaining": None, "period": period}
            used = _get_usage(conn, user_id, feature, period)
            remaining = max(0, limit - used)
            return {"limit": limit, "used": used, "remaining": remaining, "period": period}

        # KB counts
        kb_paper_limit = ent["kb_paper_limit"]
        kb_folder_limit = ent["kb_folder_limit"]
        kb_note_limit = ent["kb_note_limit"]
        kb_compare_result_limit = ent["kb_compare_result_limit"]

        kb_paper_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_papers WHERE user_id = ? AND scope = 'kb'",
            (user_id,),
        ).fetchone()
        kb_paper_used = int(kb_paper_row["cnt"]) if kb_paper_row else 0

        kb_folder_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_folders WHERE user_id = ? AND scope = 'kb'",
            (user_id,),
        ).fetchone()
        kb_folder_used = int(kb_folder_row["cnt"]) if kb_folder_row else 0

        kb_note_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_notes WHERE user_id = ? AND scope = 'kb'",
            (user_id,),
        ).fetchone()
        kb_note_used = int(kb_note_row["cnt"]) if kb_note_row else 0

        kb_compare_result_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM kb_compare_results WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        kb_compare_result_used = int(kb_compare_result_row["cnt"]) if kb_compare_result_row else 0

        # Build snapshot while conn is still open — _quota_snapshot uses conn.
        tier_label_map = {"free": "Free", "pro": "Pro", "pro_plus": "Pro+"}
        result = {
            "tier": tier,
            "tier_label": tier_label_map.get(tier, "Free"),
            "quotas": {
                "chat": _quota_snapshot("chat"),
                "compare": _quota_snapshot("compare"),
                "research": _quota_snapshot("research"),
                "idea_gen": _quota_snapshot("idea_gen"),
                "upload": _quota_snapshot("upload"),
                "translate": _quota_snapshot("translate"),
                "export": _quota_snapshot("export"),
            },
            "gates": {
                "general_chat": ent["general_chat"],
                "note_file_upload": ent["note_file_upload"],
                "llm_preset": ent["llm_preset"],
                "prompt_preset": ent["prompt_preset"],
                "export_docx_pdf": ent["export_docx_pdf"],
                "batch_export": ent["batch_export"],
                "translate": ent["translate"],
            },
            "storage": {
                "kb_papers": {
                    "limit": kb_paper_limit,
                    "used": kb_paper_used,
                    "remaining": None if kb_paper_limit is None else max(0, kb_paper_limit - kb_paper_used),
                },
                "kb_folders": {
                    "limit": kb_folder_limit,
                    "used": kb_folder_used,
                    "remaining": None if kb_folder_limit is None else max(0, kb_folder_limit - kb_folder_used),
                },
                "kb_notes": {
                    "limit": kb_note_limit,
                    "used": kb_note_used,
                    "remaining": None if kb_note_limit is None else max(0, kb_note_limit - kb_note_used),
                },
                "kb_compare_results": {
                    "limit": kb_compare_result_limit,
                    "used": kb_compare_result_used,
                    "remaining": None if kb_compare_result_limit is None else max(0, kb_compare_result_limit - kb_compare_result_used),
                },
            },
            "session_caps": {
                "compare_max_items": ent["compare_max_items"],
            },
            "retention": {
                "research_history_days": ent["research_history_days"],
            },
            "browse": {
                "limit": ent["browse_limit"],
            },
        }
    finally:
        conn.close()

    return result
