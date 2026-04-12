"""
Web engagement service: task-based signin and streak rewards.

Rules:
- A valid study day requires three tasks: view / collect / analyze.
- Completing 3/3 tasks marks the day as completed.
- Continuous completed days unlock milestones: 1 / 2 / 3 / 4 / 5 / 7 / 14 / 30 / 60 / 100.
- Milestones grant real entitlement rewards that can be consumed to enhance features.

Streak freeze rules:
- A streak freeze protects a missed day: if today's streak would break because yesterday was
  not completed, spending a freeze counts yesterday as "frozen" and preserves the streak.
- Freezes are per-calendar-month.  Free users: 1 freeze/month.  Pro/Pro+ users: 3 freezes/month.
- Only one missed day can be frozen at a time (no stacking to cover multi-day gaps).
- A freeze can only be used on the day immediately following the missed day (grace window = same
  calendar day as the break is detected).

Reward entitlements:
- day1_focus_badge              : Honorary badge (no entitlement, permanent)
- day2_chat_boost_ticket        : Paper/general chat input context +50% for one session
- day3_fast_track_ticket        : Upload priority boost (priority=1 in pipeline)
- day4_idea_boost_ticket        : Idea generation atom pool +50% for one session (richer candidates)
- day5_compare_plus_ticket      : Compare limit +2 papers per session
- day7_research_accelerator     : Research input_hard_limit +50% boost, top_n up to 30
- day14_researcher_badge        : Honorary badge (no entitlement, permanent) + 3-day Pro trial (free users)
- day30_compare_premium_ticket  : Compare limit +4 papers per session
- day60_research_premium_ticket : Research input_hard_limit +100% boost + compare limit +4
- day100_legend_badge           : Honorary badge (no entitlement, permanent)
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

_CHINA_TZ = timezone(timedelta(hours=8))
_VALID_ACTIONS = {"view", "collect", "analyze"}
_MILESTONES = (1, 2, 3, 4, 5, 7, 14, 30, 60, 100)

# Reward codes that are purely honorary (no entitlement side effects)
_HONORARY_CODES = {"day1_focus_badge", "day14_researcher_badge", "day100_legend_badge"}

# Feature → reward_codes that apply to it
_FEATURE_REWARD_CODES: dict[str, set[str]] = {
    "chat": {"day2_chat_boost_ticket"},
    "idea_gen": {"day4_idea_boost_ticket"},
    "compare": {"day5_compare_plus_ticket", "day30_compare_premium_ticket", "day60_research_premium_ticket"},
    "research": {"day7_research_accelerator", "day60_research_premium_ticket"},
    "upload": {"day3_fast_track_ticket"},
}

# Boost parameters per reward_code.
# Compare limits are expressed as *deltas* added on top of the tier baseline.
# Research and chat limits are multipliers on the service's input_hard_limit.
# idea_gen uses an atoms_limit_multiplier on the atom retrieval pool size.
_REWARD_BOOSTS: dict[str, dict[str, Any]] = {
    "day2_chat_boost_ticket": {
        # +50% input context for one chat session (more paper content in prompt)
        "input_hard_limit_multiplier": 1.5,
        "reward_code": "day2_chat_boost_ticket",
    },
    "day3_fast_track_ticket": {
        "upload_priority": 1,
        "reward_code": "day3_fast_track_ticket",
    },
    "day4_idea_boost_ticket": {
        # +50% atom pool for one generation session (richer, more diverse candidates)
        "atoms_limit_multiplier": 1.5,
        "reward_code": "day4_idea_boost_ticket",
    },
    "day5_compare_plus_ticket": {
        # +2 on top of tier baseline: Free 2→4, Pro 5→7, Pro+ 8→10
        "compare_items_delta": 2,
        "reward_code": "day5_compare_plus_ticket",
    },
    "day7_research_accelerator": {
        "input_hard_limit_multiplier": 1.5,
        "max_top_n": 30,
        "reward_code": "day7_research_accelerator",
    },
    "day30_compare_premium_ticket": {
        # +4 on top of tier baseline: Free 2→6, Pro 5→9, Pro+ 8→12
        "compare_items_delta": 4,
        "reward_code": "day30_compare_premium_ticket",
    },
    "day60_research_premium_ticket": {
        "input_hard_limit_multiplier": 2.0,
        "max_top_n": 30,
        # +4 on top of tier baseline for compare as well
        "compare_items_delta": 4,
        "reward_code": "day60_research_premium_ticket",
    },
}


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _today_key() -> str:
    # Keep business day aligned with CN timezone used by most product copy.
    return _now_utc().astimezone(_CHINA_TZ).date().isoformat()


def _yesterday_key(day_key: str) -> str:
    d = datetime.fromisoformat(f"{day_key}T00:00:00+08:00").date()
    return (d - timedelta(days=1)).isoformat()


def _reward_pool(streak_day: int) -> dict[str, Any]:
    mapping = {
        1: {
            "reward_code": "day1_focus_badge",
            "reward_name": "研究启动徽章",
            "description": "你迈出了第一步。持续研究的习惯从今天开始——这枚永久徽章记录了你的起点。",
            "expires_days": None,  # Honorary — never expires
        },
        2: {
            "reward_code": "day2_chat_boost_ticket",
            "reward_name": "对话增强券",
            "description": "连续 2 天研究奖励。在 AI 对话界面开启此券，下次对话 AI 可读取 1.5 倍的论文上下文，理解更全面、回答更深入。7 天内有效。",
            "expires_days": 7,
        },
        3: {
            "reward_code": "day3_fast_track_ticket",
            "reward_name": "快速处理加速券",
            "description": "连续 3 天研究奖励。下次上传论文时，在上传对话框中开启此券——论文将跳过普通队列优先处理，无需等待。14 天内有效。",
            "expires_days": 14,
        },
        4: {
            "reward_code": "day4_idea_boost_ticket",
            "reward_name": "灵感增强券",
            "description": "连续 4 天研究奖励。在灵感生成时开启此券，AI 将从更大的知识原子池（1.5 倍）中提取灵感，生成更多元、更有深度的研究方向。7 天内有效。",
            "expires_days": 7,
        },
        5: {
            "reward_code": "day5_compare_plus_ticket",
            "reward_name": "扩展对比券",
            "description": "连续 5 天研究奖励。在对比面板中使用此券，单次对比篇数在你当前套餐基础上额外 +2 篇（免费 2→4，Pro 5→7，Pro+ 8→10）。14 天内有效。",
            "expires_days": 14,
        },
        7: {
            "reward_code": "day7_research_accelerator",
            "reward_name": "深度研究加速券",
            "description": "连续 7 天研究奖励。在深度研究面板中开启此券，AI 获得 1.5 倍上下文额度与最多 30 篇精选范围，让分析更完整深入。14 天内有效。",
            "expires_days": 14,
        },
        14: {
            "reward_code": "day14_researcher_badge",
            "reward_name": "研究达人徽章",
            "description": "连续 14 天坚持研究，你已建立稳定的研究习惯。这枚永久徽章见证了你的坚持。",
            "expires_days": None,  # Honorary — never expires
        },
        30: {
            "reward_code": "day30_compare_premium_ticket",
            "reward_name": "高级对比券",
            "description": "连续 30 天研究奖励。在对比面板中使用此券，单次对比篇数在你当前套餐基础上额外 +4 篇（免费 2→6，Pro 5→9，Pro+ 8→12），一次性把握整个领域研究脉络。21 天内有效。",
            "expires_days": 21,
        },
        60: {
            "reward_code": "day60_research_premium_ticket",
            "reward_name": "全能研究券",
            "description": "连续 60 天研究奖励。一张券全面增强：2 倍上下文额度 + 最多 30 篇精选范围 + 对比名额在套餐基础上 +4 篇，深度研究与对比分析均可使用。30 天内有效。",
            "expires_days": 30,
        },
        100: {
            "reward_code": "day100_legend_badge",
            "reward_name": "传奇研究者徽章",
            "description": "连续 100 天坚持研究，你已是真正的研究者。这枚永久徽章是对你百日研究精神的见证。",
            "expires_days": None,  # Honorary — never expires
        },
    }
    return mapping[streak_day]


# ---------------------------------------------------------------------------
# Streak freeze configuration
# ---------------------------------------------------------------------------

# Freezes allowed per calendar month by tier
_FREEZE_QUOTA: dict[str, int] = {
    "free": 1,
    "pro": 3,
    "pro_plus": 3,
}


def _month_key() -> str:
    """Return current month key (YYYY-MM) in China timezone."""
    return _now_utc().astimezone(_CHINA_TZ).strftime("%Y-%m")


def _get_user_tier_for_freeze(user_id: int, conn: sqlite3.Connection) -> str:
    """Read tier from auth_users for freeze quota calculation."""
    from datetime import timezone as tz_module
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
    if tier not in _FREEZE_QUOTA:
        return "free"
    if tier in ("pro", "pro_plus"):
        expires_at = row["tier_expires_at"]
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=tz_module.utc)
                if exp <= _now_utc():
                    return "free"
            except ValueError:
                pass
    return tier


def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS engagement_daily_tasks (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                day_key       TEXT    NOT NULL,
                viewed        INTEGER NOT NULL DEFAULT 0,
                collected     INTEGER NOT NULL DEFAULT 0,
                analyzed      INTEGER NOT NULL DEFAULT 0,
                completed_at  TEXT,
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL,
                UNIQUE(user_id, day_key)
            );

            CREATE INDEX IF NOT EXISTS idx_engagement_daily_tasks_user_day
                ON engagement_daily_tasks(user_id, day_key);

            CREATE TABLE IF NOT EXISTS engagement_streaks (
                user_id             INTEGER PRIMARY KEY,
                current_streak      INTEGER NOT NULL DEFAULT 0,
                longest_streak      INTEGER NOT NULL DEFAULT 0,
                last_completed_day  TEXT,
                updated_at          TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS engagement_reward_grants (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                day_key       TEXT    NOT NULL,
                streak_day    INTEGER NOT NULL,
                reward_code   TEXT    NOT NULL,
                reward_name   TEXT    NOT NULL,
                description   TEXT    NOT NULL,
                payload_json  TEXT    NOT NULL DEFAULT '{}',
                status        TEXT    NOT NULL DEFAULT 'active',
                expires_at    TEXT,
                used_at       TEXT,
                used_context  TEXT,
                created_at    TEXT    NOT NULL,
                UNIQUE(user_id, day_key, streak_day)
            );

            CREATE INDEX IF NOT EXISTS idx_engagement_reward_user_created
                ON engagement_reward_grants(user_id, created_at DESC);
            """
        )
        # Migrate existing tables that may lack the new columns
        for col, definition in [
            ("used_at",      "TEXT"),
            ("used_context", "TEXT"),
        ]:
            try:
                conn.execute(
                    f"ALTER TABLE engagement_reward_grants ADD COLUMN {col} {definition}"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Streak freeze columns on engagement_streaks
        for col, definition in [
            ("freeze_used_this_month", "INTEGER NOT NULL DEFAULT 0"),
            ("freeze_month_key",       "TEXT"),
        ]:
            try:
                conn.execute(
                    f"ALTER TABLE engagement_streaks ADD COLUMN {col} {definition}"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Engagement trial flag on auth_users (added here to avoid needing auth_service migration)
        try:
            conn.execute(
                "ALTER TABLE auth_users ADD COLUMN engagement_trial_granted INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # Column already exists

        conn.commit()
    finally:
        conn.close()


def _get_today_task_row(conn: sqlite3.Connection, user_id: int, day_key: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM engagement_daily_tasks WHERE user_id = ? AND day_key = ?",
        (user_id, day_key),
    ).fetchone()
    if row is not None:
        return row

    now = _now_iso()
    conn.execute(
        """
        INSERT INTO engagement_daily_tasks (user_id, day_key, viewed, collected, analyzed, created_at, updated_at)
        VALUES (?, ?, 0, 0, 0, ?, ?)
        """,
        (user_id, day_key, now, now),
    )
    return conn.execute(
        "SELECT * FROM engagement_daily_tasks WHERE user_id = ? AND day_key = ?",
        (user_id, day_key),
    ).fetchone()


def _task_progress_payload(row: sqlite3.Row) -> dict[str, Any]:
    tasks = {
        "view": bool(row["viewed"]),
        "collect": bool(row["collected"]),
        "analyze": bool(row["analyzed"]),
    }
    progress = sum(1 for ok in tasks.values() if ok)
    return {
        "tasks": tasks,
        "progress_count": progress,
        "target_count": 3,
        "completed": progress >= 3,
    }


def _get_streak_row(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM engagement_streaks WHERE user_id = ?",
        (user_id,),
    ).fetchone()


def _upsert_streak(
    conn: sqlite3.Connection,
    user_id: int,
    current_streak: int,
    longest_streak: int,
    last_completed_day: str,
) -> None:
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO engagement_streaks (user_id, current_streak, longest_streak, last_completed_day, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            current_streak = excluded.current_streak,
            longest_streak = excluded.longest_streak,
            last_completed_day = excluded.last_completed_day,
            updated_at = excluded.updated_at
        """,
        (user_id, current_streak, longest_streak, last_completed_day, now),
    )


def _expire_stale_rewards(conn: sqlite3.Connection, user_id: int) -> None:
    """Lazily mark active rewards whose expires_at has passed as expired."""
    conn.execute(
        """
        UPDATE engagement_reward_grants
        SET status = 'expired'
        WHERE user_id = ?
          AND status = 'active'
          AND expires_at IS NOT NULL
          AND expires_at < ?
        """,
        (user_id, _now_iso()),
    )


def _grant_reward_if_needed(
    conn: sqlite3.Connection,
    user_id: int,
    day_key: str,
    streak_day: int,
) -> dict[str, Any] | None:
    if streak_day not in _MILESTONES:
        return None

    existing = conn.execute(
        """
        SELECT id
        FROM engagement_reward_grants
        WHERE user_id = ? AND day_key = ? AND streak_day = ?
        """,
        (user_id, day_key, streak_day),
    ).fetchone()
    if existing is not None:
        return None

    reward = _reward_pool(streak_day)
    now = _now_utc()
    expires_days = reward.get("expires_days")
    expires_at = (now + timedelta(days=int(expires_days))).isoformat() if expires_days else None
    payload = {"streak_day": streak_day, "milestone": f"{streak_day}d"}

    conn.execute(
        """
        INSERT INTO engagement_reward_grants
          (user_id, day_key, streak_day, reward_code, reward_name, description, payload_json, status, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (
            user_id,
            day_key,
            streak_day,
            reward["reward_code"],
            reward["reward_name"],
            reward["description"],
            json.dumps(payload, ensure_ascii=False),
            expires_at,
            now.isoformat(),
        ),
    )

    # Bridge: try to grant a Pro trial when the day14 milestone is hit
    pro_trial = _maybe_grant_pro_trial(conn, user_id, streak_day)

    result: dict[str, Any] = {
        "streak_day": streak_day,
        "reward_code": reward["reward_code"],
        "reward_name": reward["reward_name"],
        "description": reward["description"],
        "expires_at": expires_at,
    }
    if pro_trial:
        result["pro_trial"] = pro_trial
    return result


# ---------------------------------------------------------------------------
# Engagement → entitlement bridge: Pro trial grant at day14 milestone
# ---------------------------------------------------------------------------

# Number of trial days granted at the day14 milestone (free users only, once ever)
_DAY14_TRIAL_DAYS = 3
_DAY14_TRIAL_TIER = "pro"


def _maybe_grant_pro_trial(conn: sqlite3.Connection, user_id: int, streak_day: int) -> dict[str, Any] | None:
    """
    When the day14 milestone is reached for a free-tier user who has never received
    a trial, grant _DAY14_TRIAL_DAYS days of Pro access.

    Returns a dict describing the trial if granted, None otherwise.
    Must be called inside an open transaction (the caller manages commit/rollback).
    """
    if streak_day != 14:
        return None

    # Read user tier and trial flag
    row = conn.execute(
        "SELECT tier, tier_expires_at, engagement_trial_granted FROM auth_users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None

    # Only for free users; already paid users don't need a trial
    current_tier = (row["tier"] or "free").strip()
    if current_tier != "free":
        return None

    # Check if trial already granted (migration adds this column as default 0)
    trial_granted = int(row["engagement_trial_granted"] or 0)
    if trial_granted:
        return None

    # Apply the subscription via auth_service helper (needs a new independent connection
    # since auth_service opens its own conn — but we just write directly here to avoid
    # circular imports and to stay within the current transaction)
    from datetime import timezone as tz_module
    now = _now_utc()
    trial_expires = (now + timedelta(days=_DAY14_TRIAL_DAYS)).replace(tzinfo=tz_module.utc)
    now_iso = now.isoformat()
    trial_expires_iso = trial_expires.isoformat()

    conn.execute(
        """
        UPDATE auth_users
        SET tier = ?, tier_expires_at = ?, updated_at = ?, engagement_trial_granted = 1
        WHERE id = ?
        """,
        (_DAY14_TRIAL_TIER, trial_expires_iso, now_iso, user_id),
    )
    conn.execute(
        """
        INSERT INTO auth_entitlements
          (user_id, source, source_ref, from_tier, to_tier, start_at, end_at, created_at, operator_user_id, note)
        VALUES (?, 'engagement_milestone', 'day14', ?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            user_id,
            current_tier,
            _DAY14_TRIAL_TIER,
            now_iso,
            trial_expires_iso,
            now_iso,
            f"连续研究 14 天里程碑奖励：{_DAY14_TRIAL_DAYS} 天 Pro 试用",
        ),
    )

    return {
        "trial_granted": True,
        "trial_tier": _DAY14_TRIAL_TIER,
        "trial_days": _DAY14_TRIAL_DAYS,
        "trial_expires_at": trial_expires_iso,
        "message": f"恭喜！连续研究 14 天里程碑解锁 {_DAY14_TRIAL_DAYS} 天 Pro 试用，所有 Pro 功能即刻可用",
    }


def _row_to_reward_dict(r: sqlite3.Row) -> dict[str, Any]:
    item = dict(r)
    payload_json = item.pop("payload_json", None)
    try:
        item["payload"] = json.loads(payload_json or "{}")
    except Exception:
        item["payload"] = {}
    return item


def get_signin_status(user_id: int) -> dict[str, Any]:
    day_key = _today_key()
    conn = _connect()
    try:
        _expire_stale_rewards(conn, user_id)
        row = _get_today_task_row(conn, user_id, day_key)
        streak_row = _get_streak_row(conn, user_id)
        rewards = conn.execute(
            """
            SELECT id, day_key, streak_day, reward_code, reward_name, description,
                   payload_json, status, expires_at, used_at, used_context, created_at
            FROM engagement_reward_grants
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (user_id,),
        ).fetchall()
        # Read whether the user has already received the day-14 Pro trial
        user_row = conn.execute(
            "SELECT tier, engagement_trial_granted FROM auth_users WHERE id = ?",
            (user_id,),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()

    progress = _task_progress_payload(row)
    current_streak = int(streak_row["current_streak"]) if streak_row else 0
    longest_streak = int(streak_row["longest_streak"]) if streak_row else 0
    next_milestones = [m for m in _MILESTONES if m > current_streak][:2]

    tier = (user_row["tier"] or "free").strip() if user_row else "free"
    trial_granted = bool(int(user_row["engagement_trial_granted"] or 0)) if user_row else False

    # Include freeze status inline so the frontend gets it in one call
    freeze_status = get_freeze_status(user_id)

    return {
        "day_key": day_key,
        "progress": progress,
        "streak": {
            "current": current_streak,
            "longest": longest_streak,
            "milestones": list(_MILESTONES),
            "next_milestones": next_milestones,
        },
        "rewards": [_row_to_reward_dict(r) for r in rewards],
        "freeze": freeze_status,
        "tier": tier,
        "trial_granted": trial_granted,
    }


def list_rewards(user_id: int, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    conn = _connect()
    try:
        _expire_stale_rewards(conn, user_id)
        conn.commit()
        if status:
            rows = conn.execute(
                """
                SELECT id, day_key, streak_day, reward_code, reward_name, description,
                       payload_json, status, expires_at, used_at, used_context, created_at
                FROM engagement_reward_grants
                WHERE user_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, day_key, streak_day, reward_code, reward_name, description,
                       payload_json, status, expires_at, used_at, used_context, created_at
                FROM engagement_reward_grants
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
    finally:
        conn.close()

    return [_row_to_reward_dict(r) for r in rows]


def get_active_rewards_for_feature(user_id: int, feature: str) -> list[dict[str, Any]]:
    """Return active, non-expired rewards applicable to the given feature."""
    applicable_codes = _FEATURE_REWARD_CODES.get(feature, set())
    if not applicable_codes:
        return []

    conn = _connect()
    try:
        _expire_stale_rewards(conn, user_id)
        conn.commit()
        placeholders = ",".join("?" * len(applicable_codes))
        rows = conn.execute(
            f"""
            SELECT id, day_key, streak_day, reward_code, reward_name, description,
                   payload_json, status, expires_at, used_at, used_context, created_at
            FROM engagement_reward_grants
            WHERE user_id = ?
              AND status = 'active'
              AND reward_code IN ({placeholders})
            ORDER BY streak_day DESC
            """,
            (user_id, *applicable_codes),
        ).fetchall()
    finally:
        conn.close()

    result = []
    for r in rows:
        item = _row_to_reward_dict(r)
        item["boost"] = _REWARD_BOOSTS.get(item["reward_code"], {})
        result.append(item)
    return result


def has_active_reward(user_id: int, reward_code: str) -> bool:
    """Return True if user has at least one active (non-expired) reward of the given code."""
    conn = _connect()
    try:
        _expire_stale_rewards(conn, user_id)
        conn.commit()
        row = conn.execute(
            """
            SELECT id FROM engagement_reward_grants
            WHERE user_id = ? AND reward_code = ? AND status = 'active'
            LIMIT 1
            """,
            (user_id, reward_code),
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def get_reward_boost(user_id: int, feature: str, reward_id: int | None) -> dict[str, Any]:
    """
    Validate that reward_id belongs to user, is active and applies to feature.
    Returns the boost dict if valid, otherwise empty dict.
    """
    if reward_id is None:
        return {}

    conn = _connect()
    try:
        _expire_stale_rewards(conn, user_id)
        conn.commit()
        row = conn.execute(
            """
            SELECT id, reward_code, status
            FROM engagement_reward_grants
            WHERE id = ? AND user_id = ? AND status = 'active'
            """,
            (reward_id, user_id),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {}

    reward_code = row["reward_code"]
    applicable_codes = _FEATURE_REWARD_CODES.get(feature, set())
    if reward_code not in applicable_codes:
        return {}

    return _REWARD_BOOSTS.get(reward_code, {})


def use_reward(user_id: int, reward_id: int, context: str) -> dict[str, Any]:
    """
    Consume a reward: mark it as used. Returns the reward dict after update.
    Raises ValueError if reward is not valid/applicable.
    Honorary badges (_HONORARY_CODES) are permanent and cannot be consumed.
    """
    now = _now_iso()
    conn = _connect()
    try:
        _expire_stale_rewards(conn, user_id)
        row = conn.execute(
            """
            SELECT id, reward_code, reward_name, description, status, expires_at, streak_day
            FROM engagement_reward_grants
            WHERE id = ? AND user_id = ?
            """,
            (reward_id, user_id),
        ).fetchone()

        if row is None:
            raise ValueError("奖励不存在或不属于当前用户")
        if row["reward_code"] in _HONORARY_CODES:
            raise ValueError("荣誉徽章为永久纪念，不可消耗")
        if row["status"] != "active":
            raise ValueError(f"奖励状态为 {row['status']}，无法使用")

        conn.execute(
            """
            UPDATE engagement_reward_grants
            SET status = 'used', used_at = ?, used_context = ?
            WHERE id = ?
            """,
            (now, context[:500] if context else "", reward_id),
        )
        conn.commit()

        return {
            "id": reward_id,
            "reward_code": row["reward_code"],
            "reward_name": row["reward_name"],
            "description": row["description"],
            "status": "used",
            "used_at": now,
            "used_context": context,
            "boost": _REWARD_BOOSTS.get(row["reward_code"], {}),
        }
    finally:
        conn.close()


def get_freeze_status(user_id: int) -> dict[str, Any]:
    """
    Return the current streak freeze status for the user.

    Response shape:
    {
        "freeze_allowed": bool,         # True if user CAN use a freeze right now
        "freeze_quota": int,            # Total freezes available this month
        "freeze_used": int,             # Freezes used this month
        "freeze_remaining": int,        # Remaining freezes this month
        "streak_would_break": bool,     # True if today's streak is already broken
        "missed_day": str | None,       # The day that would be frozen (day before today)
    }
    """
    day_key = _today_key()
    conn = _connect()
    try:
        tier = _get_user_tier_for_freeze(user_id, conn)
        quota = _FREEZE_QUOTA.get(tier, 1)
        month_key = _month_key()

        streak_row = _get_streak_row(conn, user_id)
        if streak_row is None:
            freeze_used = 0
        else:
            row_month = streak_row["freeze_month_key"] if "freeze_month_key" in streak_row.keys() else None
            if row_month == month_key:
                freeze_used = int(streak_row["freeze_used_this_month"] or 0)
            else:
                freeze_used = 0

        freeze_remaining = max(0, quota - freeze_used)

        # Determine if streak would break: prev completed day was two days ago (not yesterday)
        yesterday = _yesterday_key(day_key)
        streak_would_break = False
        missed_day: str | None = None
        if streak_row is not None:
            prev_day = streak_row["last_completed_day"]
            current_streak = int(streak_row["current_streak"] or 0)
            if current_streak > 0 and prev_day not in (None, day_key, yesterday):
                # Check if prev_day is exactly 2 days ago (one missed day)
                try:
                    prev_date = datetime.fromisoformat(f"{prev_day}T00:00:00+08:00").date()
                    today_date = datetime.fromisoformat(f"{day_key}T00:00:00+08:00").date()
                    gap = (today_date - prev_date).days
                    if gap == 2:
                        streak_would_break = True
                        missed_day = yesterday
                except (ValueError, AttributeError):
                    pass
    finally:
        conn.close()

    freeze_allowed = freeze_remaining > 0 and streak_would_break

    return {
        "freeze_allowed": freeze_allowed,
        "freeze_quota": quota,
        "freeze_used": freeze_used,
        "freeze_remaining": freeze_remaining,
        "streak_would_break": streak_would_break,
        "missed_day": missed_day,
    }


def use_streak_freeze(user_id: int) -> dict[str, Any]:
    """
    Spend one streak freeze to cover the missed day.

    Returns:
    {
        "success": bool,
        "message": str,
        "new_streak": int,
        "freeze_remaining": int,
    }
    Raises ValueError with a user-facing message if the freeze cannot be applied.
    """
    day_key = _today_key()
    yesterday = _yesterday_key(day_key)
    month_key = _month_key()
    now = _now_iso()

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        tier = _get_user_tier_for_freeze(user_id, conn)
        quota = _FREEZE_QUOTA.get(tier, 1)

        streak_row = _get_streak_row(conn, user_id)
        if streak_row is None:
            conn.rollback()
            raise ValueError("暂无连续记录，无需使用冻结")

        row_month = streak_row["freeze_month_key"] if "freeze_month_key" in streak_row.keys() else None
        if row_month == month_key:
            freeze_used = int(streak_row["freeze_used_this_month"] or 0)
        else:
            freeze_used = 0

        if freeze_used >= quota:
            conn.rollback()
            raise ValueError(f"本月连续保护次数已用完（{quota} 次）")

        prev_day = streak_row["last_completed_day"]
        current_streak = int(streak_row["current_streak"] or 0)

        if current_streak == 0:
            conn.rollback()
            raise ValueError("当前没有连续研究记录，无需使用保护")

        # Validate: missed day is exactly yesterday
        try:
            prev_date = datetime.fromisoformat(f"{prev_day}T00:00:00+08:00").date()
            today_date = datetime.fromisoformat(f"{day_key}T00:00:00+08:00").date()
            gap = (today_date - prev_date).days
        except (ValueError, AttributeError):
            gap = 999

        if gap != 2:
            conn.rollback()
            if gap <= 1:
                raise ValueError("连续记录尚未中断，无需使用保护")
            raise ValueError("中断超过 1 天，无法使用保护（仅可弥补昨天一天的缺失）")

        # Insert a synthetic "frozen" completed task row for yesterday
        conn.execute(
            """
            INSERT OR IGNORE INTO engagement_daily_tasks
              (user_id, day_key, viewed, collected, analyzed, completed_at, created_at, updated_at)
            VALUES (?, ?, 1, 1, 1, ?, ?, ?)
            """,
            (user_id, yesterday, now, now, now),
        )
        # Update the streak: yesterday now counts as completed, so today is consecutive
        new_streak = current_streak + 1
        longest_streak = max(int(streak_row["longest_streak"] or 0), new_streak)
        # Update last_completed_day to yesterday (not today — user still needs to complete today)
        _upsert_streak(conn, user_id, new_streak, longest_streak, yesterday)

        # Record freeze usage (reset counter if month changed)
        new_freeze_used = freeze_used + 1
        conn.execute(
            """
            UPDATE engagement_streaks
            SET freeze_used_this_month = ?, freeze_month_key = ?
            WHERE user_id = ?
            """,
            (new_freeze_used, month_key, user_id),
        )

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    freeze_remaining = max(0, quota - new_freeze_used)
    return {
        "success": True,
        "message": f"已使用连续保护，昨天（{yesterday}）的缺失已弥补，连续天数恢复为 {new_streak} 天",
        "new_streak": new_streak,
        "frozen_day": yesterday,
        "freeze_remaining": freeze_remaining,
    }


def get_activity_calendar(user_id: int, days: int = 60) -> dict[str, Any]:
    """
    Return a calendar of the user's daily task completion for the past `days` days.
    Each entry is {day_key, completed, partial} where:
      - completed: all 3 tasks done on that day
      - partial: some tasks done but not all 3
    Days with no record are included as {completed: false, partial: false}.
    """
    days = min(max(days, 7), 180)
    today = _now_utc().astimezone(_CHINA_TZ).date()
    start_date = today - timedelta(days=days - 1)

    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT day_key, viewed, collected, analyzed, completed_at
            FROM engagement_daily_tasks
            WHERE user_id = ? AND day_key >= ?
            ORDER BY day_key ASC
            """,
            (user_id, start_date.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    record_map: dict[str, dict] = {}
    for r in rows:
        tasks_done = int(r["viewed"] or 0) + int(r["collected"] or 0) + int(r["analyzed"] or 0)
        record_map[r["day_key"]] = {
            "completed": bool(r["completed_at"]),
            "partial": tasks_done > 0 and not r["completed_at"],
            "tasks_done": tasks_done,
        }

    calendar = []
    current = start_date
    while current <= today:
        dk = current.isoformat()
        entry = record_map.get(dk, {"completed": False, "partial": False, "tasks_done": 0})
        calendar.append({"day_key": dk, **entry})
        current += timedelta(days=1)

    return {
        "days": days,
        "today": today.isoformat(),
        "calendar": calendar,
    }


def record_task_action(
    user_id: int,
    action: str,
    source: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    action = (action or "").strip().lower()
    if action not in _VALID_ACTIONS:
        raise ValueError("invalid action")

    day_key = _today_key()
    now = _now_iso()
    just_completed = False
    just_granted_reward: dict[str, Any] | None = None

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = _get_today_task_row(conn, user_id, day_key)

        field_name = {
            "view": "viewed",
            "collect": "collected",
            "analyze": "analyzed",
        }[action]

        if not row[field_name]:
            conn.execute(
                f"UPDATE engagement_daily_tasks SET {field_name} = 1, updated_at = ? WHERE user_id = ? AND day_key = ?",
                (now, user_id, day_key),
            )
            row = _get_today_task_row(conn, user_id, day_key)

        progress = _task_progress_payload(row)
        if progress["completed"] and not row["completed_at"]:
            just_completed = True
            conn.execute(
                "UPDATE engagement_daily_tasks SET completed_at = ?, updated_at = ? WHERE user_id = ? AND day_key = ?",
                (now, now, user_id, day_key),
            )
            streak_row = _get_streak_row(conn, user_id)
            if streak_row is None:
                current = 1
                longest = 1
            else:
                prev_day = streak_row["last_completed_day"]
                if prev_day == day_key:
                    current = int(streak_row["current_streak"])
                elif prev_day == _yesterday_key(day_key):
                    current = int(streak_row["current_streak"]) + 1
                else:
                    current = 1
                longest = max(int(streak_row["longest_streak"]), current)
            _upsert_streak(conn, user_id, current, longest, day_key)
            just_granted_reward = _grant_reward_if_needed(conn, user_id, day_key, current)

        conn.commit()
    finally:
        conn.close()

    status = get_signin_status(user_id)
    status["action"] = action
    status["source"] = source or ""
    status["target_id"] = target_id or ""
    status["just_completed"] = just_completed
    status["just_granted_reward"] = just_granted_reward
    # Surface pro_trial if it was included in the reward grant
    if just_granted_reward and just_granted_reward.get("pro_trial"):
        status["just_granted_pro_trial"] = just_granted_reward["pro_trial"]
    return status
