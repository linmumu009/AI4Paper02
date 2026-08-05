"""Recommendation Impression Logging Service.

Every time a personalized slate is served to a user, this service records
one row per paper in `recommendation_impression`.  This log is the single
source of truth for:

  - Week 3 offline calibrator  (NDCG@10 grid-search for per-user weights)
  - Week 2 Why-NOT API         (which high-theme papers were suppressed)
  - Week 5 exploration bandit  (which impressions were marked is_exploration)
  - Week 6 admin dashboard     (global system health metrics)

Schema
------
  recommendation_impression (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER  NOT NULL,
    date_str       TEXT     NOT NULL,   -- YYYY-MM-DD of the content date, not serve date
    served_at      TEXT     NOT NULL,   -- UTC ISO8601 timestamp
    paper_id       TEXT     NOT NULL,
    position       INTEGER  NOT NULL,   -- 0-based rank in the served slate
    theme_score    REAL     NOT NULL,
    pref_score     REAL     NOT NULL,
    novel_score    REAL     NOT NULL,
    final_score    REAL     NOT NULL,
    is_exploration INTEGER  NOT NULL DEFAULT 0,  -- boolean 0/1
    weights_json   TEXT     NOT NULL DEFAULT '{}',
    profile_version TEXT    NOT NULL DEFAULT ''
  )

Indexes
-------
  (user_id, date_str)  -- calibrator, Why-NOT
  (paper_id)           -- bandit reward lookup
  (served_at)          -- TTL archival
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Path resolution ────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

# Number of days of impression history to retain (older rows are archived/deleted)
IMPRESSION_RETENTION_DAYS: int = 90


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── DB initialisation ──────────────────────────────────────────────────────────

def init_db() -> None:
    """Create impression tables and indexes if they do not exist.

    Called from api.py startup hook so tables are ready before first request.
    """
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recommendation_impression (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                date_str       TEXT    NOT NULL,
                served_at      TEXT    NOT NULL,
                paper_id       TEXT    NOT NULL,
                position       INTEGER NOT NULL,
                theme_score    REAL    NOT NULL DEFAULT 0.0,
                pref_score     REAL    NOT NULL DEFAULT 0.0,
                novel_score    REAL    NOT NULL DEFAULT 0.0,
                final_score    REAL    NOT NULL DEFAULT 0.0,
                is_exploration INTEGER NOT NULL DEFAULT 0,
                weights_json   TEXT    NOT NULL DEFAULT '{}',
                profile_version TEXT   NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ri_user_date
                ON recommendation_impression(user_id, date_str)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ri_paper
                ON recommendation_impression(paper_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ri_served_at
                ON recommendation_impression(served_at)
        """)
        conn.commit()
        logger.info("impression_service: DB tables ready")
    except Exception as exc:
        logger.error("impression_service.init_db: %r", exc)
    finally:
        conn.close()


# ── Slate logging ──────────────────────────────────────────────────────────────

def log_slate(
    user_id: int,
    date_str: str,
    scored_papers: list[dict],
    weights: dict | None = None,
    profile_version: str = "",
) -> int:
    """Persist one row per paper in the served slate.

    Parameters
    ----------
    user_id:
        The authenticated user.  0 means anonymous; impressions for
        anonymous users are not logged (no profile to calibrate).
    date_str:
        Content date (YYYY-MM-DD) — the date the papers belong to,
        NOT today's date.
    scored_papers:
        Output of ``preference_service.rerank_papers_detailed()``.
        Each element must have at minimum:
          paper_id, theme_score, pref_score, novel_score, final_score,
          is_exploration.
    weights:
        The score-blend weights actually used, e.g.
        {"theme": 0.55, "pref": 0.30, "novel": 0.15}.
    profile_version:
        Opaque string identifying the profile snapshot (e.g. "built_at" ISO string).

    Returns
    -------
    int
        Number of rows written (0 on any error).
    """
    if user_id <= 0 or not scored_papers:
        return 0

    served_at = _now_iso()
    weights_str = json.dumps(weights or {}, ensure_ascii=False)

    rows: list[tuple] = []
    for pos, sp in enumerate(scored_papers):
        paper_id = sp.get("paper_id", "")
        if not paper_id:
            continue
        rows.append((
            user_id,
            date_str,
            served_at,
            paper_id,
            pos,
            float(sp.get("theme_score", 0.0)),
            float(sp.get("pref_score", 0.5)),
            float(sp.get("novel_score", 0.5)),
            float(sp.get("final_score", 0.0)),
            1 if sp.get("is_exploration") else 0,
            weights_str,
            profile_version,
        ))

    if not rows:
        return 0

    conn = _connect()
    try:
        conn.executemany(
            """
            INSERT INTO recommendation_impression
                (user_id, date_str, served_at, paper_id, position,
                 theme_score, pref_score, novel_score, final_score,
                 is_exploration, weights_json, profile_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    except Exception as exc:
        logger.warning("impression_service.log_slate: %r", exc)
        return 0
    finally:
        conn.close()


# ── Query helpers (used by calibrator, Why-NOT, bandit) ───────────────────────

def get_impressions_for_user(
    user_id: int,
    days: int = 30,
    date_str: str | None = None,
) -> list[dict]:
    """Return impression rows for a user, newest first.

    If *date_str* is given, filter to that content date only.
    If *days* is given without *date_str*, return all rows from the last
    *days* days by ``served_at``.
    """
    conn = _connect()
    try:
        if date_str:
            rows = conn.execute(
                """
                SELECT * FROM recommendation_impression
                WHERE user_id = ? AND date_str = ?
                ORDER BY position ASC
                """,
                (user_id, date_str),
            ).fetchall()
        else:
            cutoff = _cutoff_iso(days)
            rows = conn.execute(
                """
                SELECT * FROM recommendation_impression
                WHERE user_id = ? AND served_at >= ?
                ORDER BY served_at DESC, position ASC
                """,
                (user_id, cutoff),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("impression_service.get_impressions_for_user: %r", exc)
        return []
    finally:
        conn.close()


def get_impression_paper_ids_for_date(user_id: int, date_str: str) -> set[str]:
    """Return the set of paper_ids that were served to *user_id* for *date_str*."""
    rows = get_impressions_for_user(user_id, date_str=date_str)
    return {r["paper_id"] for r in rows}


def get_unique_users_with_impressions(min_impressions: int = 30, days: int = 30) -> list[int]:
    """Return user IDs that have at least *min_impressions* in the last *days* days."""
    conn = _connect()
    try:
        cutoff = _cutoff_iso(days)
        rows = conn.execute(
            """
            SELECT user_id, COUNT(*) as cnt
            FROM recommendation_impression
            WHERE served_at >= ?
            GROUP BY user_id
            HAVING cnt >= ?
            """,
            (cutoff, min_impressions),
        ).fetchall()
        return [r["user_id"] for r in rows]
    except Exception as exc:
        logger.warning("impression_service.get_unique_users_with_impressions: %r", exc)
        return []
    finally:
        conn.close()


def get_exploration_impressions(
    user_id: int,
    days: int = 7,
) -> list[dict]:
    """Return exploration-flagged impressions for bandit reward calculation."""
    conn = _connect()
    try:
        cutoff = _cutoff_iso(days)
        rows = conn.execute(
            """
            SELECT * FROM recommendation_impression
            WHERE user_id = ? AND is_exploration = 1 AND served_at >= ?
            ORDER BY served_at DESC
            """,
            (user_id, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("impression_service.get_exploration_impressions: %r", exc)
        return []
    finally:
        conn.close()


def get_admin_stats(days: int = 30) -> dict:
    """Return system-wide impression stats for the admin dashboard."""
    conn = _connect()
    try:
        cutoff = _cutoff_iso(days)
        total = conn.execute(
            "SELECT COUNT(*) as n FROM recommendation_impression WHERE served_at >= ?",
            (cutoff,),
        ).fetchone()["n"]
        users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) as n FROM recommendation_impression WHERE served_at >= ?",
            (cutoff,),
        ).fetchone()["n"]
        exploration_pct_row = conn.execute(
            """
            SELECT
                ROUND(100.0 * SUM(is_exploration) / MAX(COUNT(*), 1), 1) AS pct
            FROM recommendation_impression
            WHERE served_at >= ?
            """,
            (cutoff,),
        ).fetchone()
        exploration_pct = exploration_pct_row["pct"] if exploration_pct_row else 0.0
        return {
            "days": days,
            "total_impressions": total,
            "unique_users": users,
            "exploration_pct": exploration_pct,
        }
    except Exception as exc:
        logger.warning("impression_service.get_admin_stats: %r", exc)
        return {"days": days, "total_impressions": 0, "unique_users": 0, "exploration_pct": 0.0}
    finally:
        conn.close()


# ── TTL archival ───────────────────────────────────────────────────────────────

def archive_old_impressions(retention_days: int = IMPRESSION_RETENTION_DAYS) -> int:
    """Delete impression rows older than *retention_days* days.

    Returns the number of rows deleted.  Safe to call periodically.
    """
    conn = _connect()
    try:
        cutoff = _cutoff_iso(retention_days)
        cur = conn.execute(
            "DELETE FROM recommendation_impression WHERE served_at < ?",
            (cutoff,),
        )
        conn.commit()
        deleted = cur.rowcount
        if deleted:
            logger.info("impression_service.archive_old_impressions: deleted %d rows older than %d days", deleted, retention_days)
        return deleted
    except Exception as exc:
        logger.warning("impression_service.archive_old_impressions: %r", exc)
        return 0
    finally:
        conn.close()


# ── Internal helpers ───────────────────────────────────────────────────────────

def _cutoff_iso(days: int) -> str:
    from datetime import timedelta
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff_dt.isoformat()
