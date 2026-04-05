"""
Analytics service layer.

Aggregates statistics from existing data tables for the admin analytics dashboard.

Tables queried
--------------
paper_analysis.db:
    auth_users, auth_sessions, kb_papers, kb_notes, kb_annotations,
    kb_dismissed_papers, kb_compare_results, idea_candidates, idea_feedback,
    analytics_events (new)

idea.db:
    idea_atoms, idea_candidates, idea_questions
"""

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AUTH_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")
_IDEA_DB_PATH = os.path.join(_BASE_DIR, "database", "idea.db")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _connect_auth() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_AUTH_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_AUTH_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _connect_idea() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_IDEA_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_IDEA_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Schema: analytics_events table (in paper_analysis.db)
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create analytics_events table if not exists."""
    conn = _connect_auth()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS analytics_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                event_type  TEXT    NOT NULL,
                target_type TEXT,
                target_id   TEXT,
                value       REAL,
                meta_json   TEXT    NOT NULL DEFAULT '{}',
                created_at  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ae_user_id
                ON analytics_events(user_id);
            CREATE INDEX IF NOT EXISTS idx_ae_event_type
                ON analytics_events(event_type);
            CREATE INDEX IF NOT EXISTS idx_ae_created_at
                ON analytics_events(created_at);
            CREATE INDEX IF NOT EXISTS idx_ae_target
                ON analytics_events(target_type, target_id);
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Event recording
# ---------------------------------------------------------------------------

def record_event(
    user_id: int,
    event_type: str,
    target_type: str = None,
    target_id: str = None,
    value: float = None,
    meta: dict = None,
) -> int:
    """Record a single analytics event. Returns the new event id."""
    conn = _connect_auth()
    try:
        cur = conn.execute(
            """
            INSERT INTO analytics_events (user_id, event_type, target_type, target_id, value, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                event_type,
                target_type,
                target_id,
                value,
                json.dumps(meta or {}, ensure_ascii=False),
                _now_iso(),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def record_events_batch(events: list[dict]) -> int:
    """Record multiple events in a single transaction. Returns count inserted."""
    if not events:
        return 0
    now = _now_iso()
    conn = _connect_auth()
    try:
        rows = []
        for e in events:
            rows.append((
                e.get("user_id", 0),
                e["event_type"],
                e.get("target_type"),
                e.get("target_id"),
                e.get("value"),
                json.dumps(e.get("meta", {}), ensure_ascii=False),
                e.get("created_at", now),
            ))
        conn.executemany(
            """
            INSERT INTO analytics_events (user_id, event_type, target_type, target_id, value, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helper: check if a table exists
# ---------------------------------------------------------------------------

def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Overview statistics
# ---------------------------------------------------------------------------

def get_overview_stats() -> dict:
    """
    Returns high-level platform statistics:
      - total_users, active_today, active_7d, active_30d, new_today, new_7d, new_30d
      - tier_distribution: {free: N, pro: N}
      - content_stats: {papers_saved, notes_written, annotations, dismissed, compare_results, ideas_generated}
    """
    now = _now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    d7_start = (now - timedelta(days=7)).isoformat()
    d30_start = (now - timedelta(days=30)).isoformat()

    conn = _connect_auth()
    try:
        # --- User stats ---
        total_users = conn.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0]

        # Active users (based on last_login_at or session last_seen_at)
        active_today = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM auth_sessions WHERE last_seen_at >= ?",
            (today_start,),
        ).fetchone()[0]
        active_7d = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM auth_sessions WHERE last_seen_at >= ?",
            (d7_start,),
        ).fetchone()[0]
        active_30d = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM auth_sessions WHERE last_seen_at >= ?",
            (d30_start,),
        ).fetchone()[0]

        # New users
        new_today = conn.execute(
            "SELECT COUNT(*) FROM auth_users WHERE created_at >= ?",
            (today_start,),
        ).fetchone()[0]
        new_7d = conn.execute(
            "SELECT COUNT(*) FROM auth_users WHERE created_at >= ?",
            (d7_start,),
        ).fetchone()[0]
        new_30d = conn.execute(
            "SELECT COUNT(*) FROM auth_users WHERE created_at >= ?",
            (d30_start,),
        ).fetchone()[0]

        # Tier distribution
        tier_rows = conn.execute(
            "SELECT tier, COUNT(*) as cnt FROM auth_users GROUP BY tier"
        ).fetchall()
        tier_dist = {r["tier"]: r["cnt"] for r in tier_rows}

        # --- Content stats ---
        papers_saved = 0
        notes_written = 0
        annotations_count = 0
        dismissed_count = 0
        compare_count = 0

        if _table_exists(conn, "kb_papers"):
            papers_saved = conn.execute("SELECT COUNT(*) FROM kb_papers").fetchone()[0]
        if _table_exists(conn, "kb_notes"):
            notes_written = conn.execute("SELECT COUNT(*) FROM kb_notes").fetchone()[0]
        if _table_exists(conn, "kb_annotations"):
            annotations_count = conn.execute("SELECT COUNT(*) FROM kb_annotations").fetchone()[0]
        if _table_exists(conn, "kb_dismissed_papers"):
            dismissed_count = conn.execute("SELECT COUNT(*) FROM kb_dismissed_papers").fetchone()[0]
        if _table_exists(conn, "kb_compare_results"):
            compare_count = conn.execute("SELECT COUNT(*) FROM kb_compare_results").fetchone()[0]

        # Ideas from idea.db
        ideas_generated = 0
        try:
            iconn = _connect_idea()
            if _table_exists(iconn, "idea_candidates"):
                ideas_generated = iconn.execute("SELECT COUNT(*) FROM idea_candidates").fetchone()[0]
            iconn.close()
        except Exception:
            pass

        # --- Event-based stats (from analytics_events) ---
        page_views_today = 0
        paper_views_today = 0
        if _table_exists(conn, "analytics_events"):
            page_views_today = conn.execute(
                "SELECT COUNT(*) FROM analytics_events WHERE event_type='page_view' AND created_at >= ?",
                (today_start,),
            ).fetchone()[0]
            paper_views_today = conn.execute(
                "SELECT COUNT(*) FROM analytics_events WHERE event_type='paper_view' AND created_at >= ?",
                (today_start,),
            ).fetchone()[0]

        return {
            "total_users": total_users,
            "active_today": active_today,
            "active_7d": active_7d,
            "active_30d": active_30d,
            "new_today": new_today,
            "new_7d": new_7d,
            "new_30d": new_30d,
            "tier_distribution": tier_dist,
            "content_stats": {
                "papers_saved": papers_saved,
                "notes_written": notes_written,
                "annotations": annotations_count,
                "dismissed": dismissed_count,
                "compare_results": compare_count,
                "ideas_generated": ideas_generated,
            },
            "today_events": {
                "page_views": page_views_today,
                "paper_views": paper_views_today,
            },
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# User activity rankings
# ---------------------------------------------------------------------------

def get_user_activity_stats(limit: int = 50, offset: int = 0) -> dict:
    """
    Per-user activity breakdown.
    Returns users ranked by overall activity.
    """
    conn = _connect_auth()
    try:
        # Get all users basic info
        users = conn.execute(
            """
            SELECT id, username, role, tier, created_at, last_login_at
            FROM auth_users
            ORDER BY last_login_at DESC NULLS LAST
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

        total = conn.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0]

        result = []
        for u in users:
            uid = u["id"]
            stats = {"user_id": uid, "username": u["username"], "role": u["role"],
                     "tier": u["tier"], "created_at": u["created_at"],
                     "last_login_at": u["last_login_at"]}

            # Papers saved
            if _table_exists(conn, "kb_papers"):
                stats["papers_saved"] = conn.execute(
                    "SELECT COUNT(*) FROM kb_papers WHERE user_id=?", (uid,)
                ).fetchone()[0]
            else:
                stats["papers_saved"] = 0

            # Notes written
            if _table_exists(conn, "kb_notes"):
                stats["notes_written"] = conn.execute(
                    "SELECT COUNT(*) FROM kb_notes WHERE user_id=?", (uid,)
                ).fetchone()[0]
            else:
                stats["notes_written"] = 0

            # Annotations
            if _table_exists(conn, "kb_annotations"):
                stats["annotations"] = conn.execute(
                    "SELECT COUNT(*) FROM kb_annotations WHERE user_id=?", (uid,)
                ).fetchone()[0]
            else:
                stats["annotations"] = 0

            # Dismissed papers
            if _table_exists(conn, "kb_dismissed_papers"):
                stats["dismissed"] = conn.execute(
                    "SELECT COUNT(*) FROM kb_dismissed_papers WHERE user_id=?", (uid,)
                ).fetchone()[0]
            else:
                stats["dismissed"] = 0

            # Compare results
            if _table_exists(conn, "kb_compare_results"):
                stats["compare_results"] = conn.execute(
                    "SELECT COUNT(*) FROM kb_compare_results WHERE user_id=?", (uid,)
                ).fetchone()[0]
            else:
                stats["compare_results"] = 0

            # Event-based page views
            if _table_exists(conn, "analytics_events"):
                stats["total_page_views"] = conn.execute(
                    "SELECT COUNT(*) FROM analytics_events WHERE user_id=? AND event_type='page_view'",
                    (uid,),
                ).fetchone()[0]
                # Total time spent (sum of session_duration events, in seconds)
                row = conn.execute(
                    "SELECT COALESCE(SUM(value), 0) FROM analytics_events WHERE user_id=? AND event_type='session_duration'",
                    (uid,),
                ).fetchone()
                stats["total_time_spent_seconds"] = row[0] if row else 0
            else:
                stats["total_page_views"] = 0
                stats["total_time_spent_seconds"] = 0

            result.append(stats)

        return {"users": result, "total": total}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Paper popularity stats
# ---------------------------------------------------------------------------

def get_paper_popularity_stats(limit: int = 30) -> dict:
    """
    Returns the most popular papers by save count, annotation count, etc.
    """
    conn = _connect_auth()
    try:
        popular_papers = []

        if _table_exists(conn, "kb_papers"):
            # Most saved papers
            rows = conn.execute(
                """
                SELECT paper_id,
                       COUNT(DISTINCT user_id) as save_count,
                       MIN(created_at) as first_saved_at
                FROM kb_papers
                GROUP BY paper_id
                ORDER BY save_count DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            for r in rows:
                paper_id = r["paper_id"]
                entry = {
                    "paper_id": paper_id,
                    "save_count": r["save_count"],
                    "first_saved_at": r["first_saved_at"],
                    "note_count": 0,
                    "annotation_count": 0,
                    "dismiss_count": 0,
                    "view_count": 0,
                    "avg_view_duration": 0,
                }

                if _table_exists(conn, "kb_notes"):
                    entry["note_count"] = conn.execute(
                        "SELECT COUNT(*) FROM kb_notes WHERE paper_id=?", (paper_id,)
                    ).fetchone()[0]

                if _table_exists(conn, "kb_annotations"):
                    entry["annotation_count"] = conn.execute(
                        "SELECT COUNT(*) FROM kb_annotations WHERE paper_id=?", (paper_id,)
                    ).fetchone()[0]

                if _table_exists(conn, "kb_dismissed_papers"):
                    entry["dismiss_count"] = conn.execute(
                        "SELECT COUNT(*) FROM kb_dismissed_papers WHERE paper_id=?", (paper_id,)
                    ).fetchone()[0]

                if _table_exists(conn, "analytics_events"):
                    entry["view_count"] = conn.execute(
                        "SELECT COUNT(*) FROM analytics_events WHERE target_type='paper' AND target_id=? AND event_type='paper_view'",
                        (paper_id,),
                    ).fetchone()[0]
                    avg_row = conn.execute(
                        "SELECT AVG(value) FROM analytics_events WHERE target_type='paper' AND target_id=? AND event_type='paper_view_duration'",
                        (paper_id,),
                    ).fetchone()
                    entry["avg_view_duration"] = round(avg_row[0] or 0, 1)

                # Try to get paper title from paper_data JSON
                try:
                    pd_row = conn.execute(
                        "SELECT paper_data FROM kb_papers WHERE paper_id=? LIMIT 1",
                        (paper_id,),
                    ).fetchone()
                    if pd_row:
                        pd = json.loads(pd_row["paper_data"])
                        entry["title"] = pd.get("📖标题") or pd.get("short_title") or paper_id
                    else:
                        entry["title"] = paper_id
                except Exception:
                    entry["title"] = paper_id

                popular_papers.append(entry)

        return {"papers": popular_papers}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Time-series trend data
# ---------------------------------------------------------------------------

def get_trend_data(days: int = 30) -> dict:
    """
    Returns daily time-series data for the last N days.
    Series: new_users, active_users, papers_saved, notes_written, page_views
    """
    now = _now()
    start_date = now - timedelta(days=days)
    start_iso = start_date.isoformat()

    conn = _connect_auth()
    try:
        # Generate date labels
        dates = []
        for i in range(days):
            d = (start_date + timedelta(days=i + 1))
            dates.append(d.strftime("%Y-%m-%d"))

        # New users per day
        new_users_rows = conn.execute(
            """
            SELECT DATE(created_at) as day, COUNT(*) as cnt
            FROM auth_users
            WHERE created_at >= ?
            GROUP BY DATE(created_at)
            """,
            (start_iso,),
        ).fetchall()
        new_users_map = {r["day"]: r["cnt"] for r in new_users_rows}

        # Active users per day (from sessions)
        active_users_rows = conn.execute(
            """
            SELECT DATE(last_seen_at) as day, COUNT(DISTINCT user_id) as cnt
            FROM auth_sessions
            WHERE last_seen_at >= ?
            GROUP BY DATE(last_seen_at)
            """,
            (start_iso,),
        ).fetchall()
        active_users_map = {r["day"]: r["cnt"] for r in active_users_rows}

        # Papers saved per day
        papers_map = {}
        if _table_exists(conn, "kb_papers"):
            papers_rows = conn.execute(
                """
                SELECT DATE(created_at) as day, COUNT(*) as cnt
                FROM kb_papers
                WHERE created_at >= ?
                GROUP BY DATE(created_at)
                """,
                (start_iso,),
            ).fetchall()
            papers_map = {r["day"]: r["cnt"] for r in papers_rows}

        # Notes per day
        notes_map = {}
        if _table_exists(conn, "kb_notes"):
            notes_rows = conn.execute(
                """
                SELECT DATE(created_at) as day, COUNT(*) as cnt
                FROM kb_notes
                WHERE created_at >= ?
                GROUP BY DATE(created_at)
                """,
                (start_iso,),
            ).fetchall()
            notes_map = {r["day"]: r["cnt"] for r in notes_rows}

        # Page views per day (from analytics_events)
        page_views_map = {}
        if _table_exists(conn, "analytics_events"):
            pv_rows = conn.execute(
                """
                SELECT DATE(created_at) as day, COUNT(*) as cnt
                FROM analytics_events
                WHERE event_type='page_view' AND created_at >= ?
                GROUP BY DATE(created_at)
                """,
                (start_iso,),
            ).fetchall()
            page_views_map = {r["day"]: r["cnt"] for r in pv_rows}

        # Build series
        series = {
            "dates": dates,
            "new_users": [new_users_map.get(d, 0) for d in dates],
            "active_users": [active_users_map.get(d, 0) for d in dates],
            "papers_saved": [papers_map.get(d, 0) for d in dates],
            "notes_written": [notes_map.get(d, 0) for d in dates],
            "page_views": [page_views_map.get(d, 0) for d in dates],
        }

        return series
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Feature usage stats
# ---------------------------------------------------------------------------

def get_feature_usage_stats() -> dict:
    """
    Returns feature usage stats - how many users use each feature.
    """
    conn = _connect_auth()
    try:
        features = {}

        # Knowledge base usage (users who saved at least 1 paper)
        if _table_exists(conn, "kb_papers"):
            features["knowledge_base"] = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM kb_papers WHERE user_id > 0"
            ).fetchone()[0]
        else:
            features["knowledge_base"] = 0

        # Note-taking usage
        if _table_exists(conn, "kb_notes"):
            features["notes"] = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM kb_notes WHERE user_id > 0"
            ).fetchone()[0]
        else:
            features["notes"] = 0

        # Annotation usage
        if _table_exists(conn, "kb_annotations"):
            features["annotations"] = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM kb_annotations WHERE user_id > 0"
            ).fetchone()[0]
        else:
            features["annotations"] = 0

        # Paper comparison usage
        if _table_exists(conn, "kb_compare_results"):
            features["compare"] = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM kb_compare_results WHERE user_id > 0"
            ).fetchone()[0]
        else:
            features["compare"] = 0

        # Idea generation usage (from idea.db)
        try:
            iconn = _connect_idea()
            if _table_exists(iconn, "idea_candidates"):
                features["idea_generation"] = iconn.execute(
                    "SELECT COUNT(DISTINCT user_id) FROM idea_candidates WHERE user_id > 0"
                ).fetchone()[0]
            else:
                features["idea_generation"] = 0
            iconn.close()
        except Exception:
            features["idea_generation"] = 0

        # Dismissed (not interested) usage
        if _table_exists(conn, "kb_dismissed_papers"):
            features["dismiss"] = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM kb_dismissed_papers WHERE user_id > 0"
            ).fetchone()[0]
        else:
            features["dismiss"] = 0

        return {"features": features}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Retention & engagement
# ---------------------------------------------------------------------------

def get_retention_data(weeks: int = 8) -> dict:
    """
    Simple weekly retention: for each cohort (week of registration),
    how many users were active in subsequent weeks.
    """
    now = _now()
    start = now - timedelta(weeks=weeks)
    start_iso = start.isoformat()

    conn = _connect_auth()
    try:
        # Get registration cohorts (weekly)
        users = conn.execute(
            """
            SELECT id, created_at FROM auth_users
            WHERE created_at >= ?
            """,
            (start_iso,),
        ).fetchall()

        # Get all session activity
        sessions = conn.execute(
            """
            SELECT user_id, last_seen_at FROM auth_sessions
            WHERE last_seen_at >= ?
            """,
            (start_iso,),
        ).fetchall()

        # Build user activity map: user_id -> set of active week numbers
        user_active_weeks = defaultdict(set)
        for s in sessions:
            try:
                seen = datetime.fromisoformat(s["last_seen_at"])
                week_num = (seen - start).days // 7
                user_active_weeks[s["user_id"]].add(week_num)
            except Exception:
                pass

        # Build cohorts
        cohorts = []
        for w in range(weeks):
            week_start = start + timedelta(weeks=w)
            week_end = week_start + timedelta(weeks=1)

            cohort_users = [
                u["id"] for u in users
                if week_start.isoformat() <= u["created_at"] < week_end.isoformat()
            ]
            cohort_size = len(cohort_users)
            if cohort_size == 0:
                cohorts.append({
                    "week": week_start.strftime("%m/%d"),
                    "cohort_size": 0,
                    "retention": [],
                })
                continue

            retention = []
            for offset_week in range(w, weeks):
                active_in_week = sum(
                    1 for uid in cohort_users
                    if offset_week in user_active_weeks.get(uid, set())
                )
                retention.append(round(active_in_week / cohort_size * 100, 1))

            cohorts.append({
                "week": week_start.strftime("%m/%d"),
                "cohort_size": cohort_size,
                "retention": retention,
            })

        return {"cohorts": cohorts, "weeks": weeks}
    finally:
        conn.close()
