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


def get_engagement_signin_stats(days: int = 14) -> dict:
    """
    Engagement funnel metrics for task-signin rollout.

    Returns:
      - daily series for task recorded / day completed / milestone granted
      - completion_rate = completed / recorded
      - grant_rate = granted / completed
      - unique users for each stage in the selected window
    """
    days = max(1, min(days, 90))
    now = _now()
    start_dt = now - timedelta(days=days - 1)
    start_iso = start_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    conn = _connect_auth()
    try:
        if not _table_exists(conn, "analytics_events"):
            return {
                "days": days,
                "dates": [],
                "task_recorded": [],
                "day_completed": [],
                "milestone_granted": [],
                "completion_rate": [],
                "grant_rate": [],
                "unique_users": {"task_recorded": 0, "day_completed": 0, "milestone_granted": 0},
            }

        rows = conn.execute(
            """
            SELECT DATE(created_at) as day, event_type, COUNT(*) as cnt
            FROM analytics_events
            WHERE created_at >= ?
              AND event_type IN ('signin_task_recorded', 'signin_day_completed', 'signin_milestone_granted')
            GROUP BY DATE(created_at), event_type
            """,
            (start_iso,),
        ).fetchall()

        user_rows = conn.execute(
            """
            SELECT event_type, COUNT(DISTINCT user_id) as cnt
            FROM analytics_events
            WHERE created_at >= ?
              AND user_id > 0
              AND event_type IN ('signin_task_recorded', 'signin_day_completed', 'signin_milestone_granted')
            GROUP BY event_type
            """,
            (start_iso,),
        ).fetchall()

        day_map = defaultdict(lambda: {"signin_task_recorded": 0, "signin_day_completed": 0, "signin_milestone_granted": 0})
        for r in rows:
            day_map[r["day"]][r["event_type"]] = int(r["cnt"])

        dates: list[str] = []
        task_recorded: list[int] = []
        day_completed: list[int] = []
        milestone_granted: list[int] = []
        completion_rate: list[float] = []
        grant_rate: list[float] = []

        for i in range(days):
            d = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            bucket = day_map[d]
            rec = int(bucket["signin_task_recorded"])
            comp = int(bucket["signin_day_completed"])
            grant = int(bucket["signin_milestone_granted"])
            dates.append(d)
            task_recorded.append(rec)
            day_completed.append(comp)
            milestone_granted.append(grant)
            completion_rate.append(round((comp / rec) * 100, 2) if rec > 0 else 0.0)
            grant_rate.append(round((grant / comp) * 100, 2) if comp > 0 else 0.0)

        uniq = {"signin_task_recorded": 0, "signin_day_completed": 0, "signin_milestone_granted": 0}
        for r in user_rows:
            uniq[r["event_type"]] = int(r["cnt"])

        return {
            "days": days,
            "dates": dates,
            "task_recorded": task_recorded,
            "day_completed": day_completed,
            "milestone_granted": milestone_granted,
            "completion_rate": completion_rate,
            "grant_rate": grant_rate,
            "unique_users": {
                "task_recorded": uniq["signin_task_recorded"],
                "day_completed": uniq["signin_day_completed"],
                "milestone_granted": uniq["signin_milestone_granted"],
            },
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module A: New User Activation (7-day activation funnel)
# ---------------------------------------------------------------------------

def get_activation_stats(days: int = 30, activation_window_days: int = 7, tier: str = None) -> dict:
    """
    Answers: "Are new users completing their first valuable action?"

    Activation = user performed at least one key action (save paper, create note,
    make annotation, dismiss paper, run compare) within `activation_window_days`
    of their registration date.

    Returns:
      - activation_rate_overall: % of users registered in [days] who activated
      - daily_registrations: list of new users per day
      - daily_activations: list of users who activated (per registration day)
      - activation_funnel: { registered, activated, pending, not_activated }
      - recent_unactivated: list of up to 20 recently registered but not yet activated users
    """
    now = _now()
    start_dt = now - timedelta(days=days)
    start_iso = start_dt.isoformat()

    conn = _connect_auth()
    try:
        # Fetch all users registered in the window (optionally filtered by tier)
        _uq = (
            "SELECT id, username, created_at, last_login_at, tier"
            " FROM auth_users WHERE created_at >= ?"
        )
        _up: list = [start_iso]
        if tier:
            _uq += " AND tier = ?"
            _up.append(tier)
        _uq += " ORDER BY created_at ASC"
        users = conn.execute(_uq, _up).fetchall()

        if not users:
            return {
                "activation_rate_overall": 0.0,
                "daily_registrations": [],
                "daily_activations": [],
                "dates": [],
                "activation_funnel": {"registered": 0, "activated": 0, "pending": 0, "not_activated": 0},
                "recent_unactivated": [],
                "tier_breakdown": {},
                "activation_definition": "save_note_annotation_compare",
            }

        # Build a set of user_ids that have performed at least one key action
        user_ids = [u["id"] for u in users]
        placeholders = ",".join("?" * len(user_ids))

        activated_ids = set()

        # Check kb_papers (save paper)
        if _table_exists(conn, "kb_papers"):
            rows = conn.execute(
                f"""
                SELECT DISTINCT kp.user_id
                FROM kb_papers kp
                JOIN auth_users au ON au.id = kp.user_id
                WHERE kp.user_id IN ({placeholders})
                  AND (julianday(kp.created_at) - julianday(au.created_at)) BETWEEN 0 AND ?
                """,
                (*user_ids, activation_window_days),
            ).fetchall()
            activated_ids.update(r["user_id"] for r in rows)

        # Check kb_notes (create note)
        if _table_exists(conn, "kb_notes"):
            rows = conn.execute(
                f"""
                SELECT DISTINCT kn.user_id
                FROM kb_notes kn
                JOIN auth_users au ON au.id = kn.user_id
                WHERE kn.user_id IN ({placeholders})
                  AND (julianday(kn.created_at) - julianday(au.created_at)) BETWEEN 0 AND ?
                """,
                (*user_ids, activation_window_days),
            ).fetchall()
            activated_ids.update(r["user_id"] for r in rows)

        # Check kb_annotations
        if _table_exists(conn, "kb_annotations"):
            rows = conn.execute(
                f"""
                SELECT DISTINCT ka.user_id
                FROM kb_annotations ka
                JOIN auth_users au ON au.id = ka.user_id
                WHERE ka.user_id IN ({placeholders})
                  AND (julianday(ka.created_at) - julianday(au.created_at)) BETWEEN 0 AND ?
                """,
                (*user_ids, activation_window_days),
            ).fetchall()
            activated_ids.update(r["user_id"] for r in rows)

        # Check kb_compare_results
        if _table_exists(conn, "kb_compare_results"):
            rows = conn.execute(
                f"""
                SELECT DISTINCT kcr.user_id
                FROM kb_compare_results kcr
                JOIN auth_users au ON au.id = kcr.user_id
                WHERE kcr.user_id IN ({placeholders})
                  AND (julianday(kcr.created_at) - julianday(au.created_at)) BETWEEN 0 AND ?
                """,
                (*user_ids, activation_window_days),
            ).fetchall()
            activated_ids.update(r["user_id"] for r in rows)

        # Build daily series
        date_labels = []
        for i in range(days):
            d = (start_dt + timedelta(days=i + 1))
            date_labels.append(d.strftime("%Y-%m-%d"))

        daily_reg: dict[str, int] = {}
        daily_act: dict[str, int] = {}
        for u in users:
            day = u["created_at"][:10]
            daily_reg[day] = daily_reg.get(day, 0) + 1
            if u["id"] in activated_ids:
                daily_act[day] = daily_act.get(day, 0) + 1

        # Classify users: activated / pending (registered within window) / not_activated
        pending_cutoff = (now - timedelta(days=activation_window_days)).isoformat()
        activated_count = len(activated_ids)
        pending_users = [u for u in users if u["id"] not in activated_ids and u["created_at"] >= pending_cutoff]
        not_activated = [u for u in users if u["id"] not in activated_ids and u["created_at"] < pending_cutoff]

        registered_count = len(users)
        activation_rate = round(activated_count / registered_count * 100, 1) if registered_count > 0 else 0.0

        recent_unactivated = sorted(
            not_activated + pending_users,
            key=lambda x: x["created_at"],
            reverse=True,
        )[:20]

        # Tier breakdown of activation (only for the current tier filter scope)
        tier_breakdown: dict[str, dict] = {}
        for u in users:
            t = u["tier"] or "free"
            if t not in tier_breakdown:
                tier_breakdown[t] = {"registered": 0, "activated": 0, "rate": 0.0}
            tier_breakdown[t]["registered"] += 1
            if u["id"] in activated_ids:
                tier_breakdown[t]["activated"] += 1
        for t, td in tier_breakdown.items():
            td["rate"] = round(td["activated"] / td["registered"] * 100, 1) if td["registered"] > 0 else 0.0

        return {
            "activation_rate_overall": activation_rate,
            "dates": date_labels,
            "daily_registrations": [daily_reg.get(d, 0) for d in date_labels],
            "daily_activations": [daily_act.get(d, 0) for d in date_labels],
            "activation_funnel": {
                "registered": registered_count,
                "activated": activated_count,
                "pending": len(pending_users),
                "not_activated": len(not_activated),
            },
            "recent_unactivated": [
                {
                    "user_id": u["id"],
                    "username": u["username"],
                    "created_at": u["created_at"],
                    "last_login_at": u["last_login_at"],
                    "tier": u["tier"],
                    "is_pending": u["created_at"] >= pending_cutoff,
                }
                for u in recent_unactivated
            ],
            "tier_breakdown": tier_breakdown,
            "activation_definition": "save_note_annotation_compare",
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module B: Activated User Retention
# ---------------------------------------------------------------------------

def get_activated_retention(weeks: int = 8) -> dict:
    """
    Answers: "Are activated users coming back?"

    Retention is computed only for users who were "activated" (performed at
    least one key action). This gives a more honest signal than retention for
    all registered users (many of whom may have just poked around).

    Returns same cohort format as get_retention_data but scoped to activated users.
    """
    now = _now()
    start = now - timedelta(weeks=weeks)
    start_iso = start.isoformat()

    conn = _connect_auth()
    try:
        # Step 1: find all activated user_ids — dismiss is excluded from activation definition
        activated_ids: set[int] = set()
        for table in ["kb_papers", "kb_notes", "kb_annotations", "kb_compare_results"]:
            if _table_exists(conn, table):
                rows = conn.execute(f"SELECT DISTINCT user_id FROM {table} WHERE user_id > 0").fetchall()
                activated_ids.update(r["user_id"] for r in rows)

        if not activated_ids:
            return {"cohorts": [], "weeks": weeks, "total_activated": 0}

        placeholders = ",".join("?" * len(activated_ids))
        activated_list = list(activated_ids)

        # Step 2: get these users' registration dates
        users = conn.execute(
            f"""
            SELECT id, created_at FROM auth_users
            WHERE id IN ({placeholders}) AND created_at >= ?
            """,
            (*activated_list, start_iso),
        ).fetchall()

        # Step 3: get session activity for these users
        sessions = conn.execute(
            f"""
            SELECT user_id, last_seen_at FROM auth_sessions
            WHERE user_id IN ({placeholders}) AND last_seen_at >= ?
            """,
            (*activated_list, start_iso),
        ).fetchall()

        # Build activity map
        user_active_weeks: dict[int, set[int]] = defaultdict(set)
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

        return {
            "cohorts": cohorts,
            "weeks": weeks,
            "total_activated": len(activated_ids),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module C: Content & Feature Value (conversion funnel)
# ---------------------------------------------------------------------------

def get_content_funnel_stats(days: int = 30) -> dict:
    """
    Answers: "What content/features are actually driving value?"

    Tracks:
      - paper_views: from analytics_events
      - key_actions: saves + notes + annotations + compares (from structural tables)
      - overall conversion rate: key_actions / paper_views
      - daily series for views vs actions
      - top papers by save count with view-to-save ratio
      - feature breakdown: which features are being used
    """
    now = _now()
    start_dt = now - timedelta(days=days)
    start_iso = start_dt.isoformat()

    conn = _connect_auth()
    try:
        date_labels = []
        for i in range(days):
            d = (start_dt + timedelta(days=i + 1))
            date_labels.append(d.strftime("%Y-%m-%d"))

        # Paper views from analytics_events
        daily_views: dict[str, int] = {}
        total_paper_views = 0
        if _table_exists(conn, "analytics_events"):
            rows = conn.execute(
                """
                SELECT DATE(created_at) as day, COUNT(*) as cnt
                FROM analytics_events
                WHERE event_type = 'paper_view' AND created_at >= ?
                GROUP BY DATE(created_at)
                """,
                (start_iso,),
            ).fetchall()
            for r in rows:
                daily_views[r["day"]] = r["cnt"]
                total_paper_views += r["cnt"]

        # Key actions from structural tables
        daily_saves: dict[str, int] = {}
        daily_notes: dict[str, int] = {}
        total_saves = 0
        total_notes = 0
        total_annotations = 0
        total_compares = 0

        if _table_exists(conn, "kb_papers"):
            rows = conn.execute(
                """
                SELECT DATE(created_at) as day, COUNT(*) as cnt
                FROM kb_papers WHERE created_at >= ?
                GROUP BY DATE(created_at)
                """,
                (start_iso,),
            ).fetchall()
            for r in rows:
                daily_saves[r["day"]] = r["cnt"]
                total_saves += r["cnt"]

        if _table_exists(conn, "kb_notes"):
            rows = conn.execute(
                """
                SELECT DATE(created_at) as day, COUNT(*) as cnt
                FROM kb_notes WHERE created_at >= ?
                GROUP BY DATE(created_at)
                """,
                (start_iso,),
            ).fetchall()
            for r in rows:
                daily_notes[r["day"]] = r["cnt"]
                total_notes += r["cnt"]

        if _table_exists(conn, "kb_annotations"):
            total_annotations = conn.execute(
                "SELECT COUNT(*) FROM kb_annotations WHERE created_at >= ?", (start_iso,)
            ).fetchone()[0]

        if _table_exists(conn, "kb_compare_results"):
            total_compares = conn.execute(
                "SELECT COUNT(*) FROM kb_compare_results WHERE created_at >= ?", (start_iso,)
            ).fetchone()[0]

        total_key_actions = total_saves + total_notes + total_annotations + total_compares
        conversion_rate = round(total_key_actions / total_paper_views * 100, 1) if total_paper_views > 0 else 0.0

        # Top papers by save count with view data
        top_papers = []
        if _table_exists(conn, "kb_papers"):
            rows = conn.execute(
                """
                SELECT paper_id, COUNT(DISTINCT user_id) as save_count, MIN(paper_data) as paper_data
                FROM kb_papers
                WHERE created_at >= ?
                GROUP BY paper_id
                ORDER BY save_count DESC
                LIMIT 15
                """,
                (start_iso,),
            ).fetchall()
            for r in rows:
                paper_id = r["paper_id"]
                view_count = 0
                if _table_exists(conn, "analytics_events"):
                    vc = conn.execute(
                        "SELECT COUNT(*) FROM analytics_events WHERE target_type='paper' AND target_id=? AND event_type='paper_view' AND created_at >= ?",
                        (paper_id, start_iso),
                    ).fetchone()[0]
                    view_count = vc
                try:
                    pd_data = json.loads(r["paper_data"])
                    title = pd_data.get("📖标题") or pd_data.get("short_title") or paper_id
                except Exception:
                    title = paper_id
                view_to_save = round(r["save_count"] / view_count * 100, 1) if view_count > 0 else None
                top_papers.append({
                    "paper_id": paper_id,
                    "title": title,
                    "save_count": r["save_count"],
                    "view_count": view_count,
                    "view_to_save_rate": view_to_save,
                })

        return {
            "days": days,
            "dates": date_labels,
            "daily_paper_views": [daily_views.get(d, 0) for d in date_labels],
            "daily_saves": [daily_saves.get(d, 0) for d in date_labels],
            "daily_notes": [daily_notes.get(d, 0) for d in date_labels],
            "totals": {
                "paper_views": total_paper_views,
                "saves": total_saves,
                "notes": total_notes,
                "annotations": total_annotations,
                "compares": total_compares,
                "key_actions": total_key_actions,
            },
            "conversion_rate": conversion_rate,
            "top_papers": top_papers,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module B (extended): Value-action weekly retention
# ---------------------------------------------------------------------------

def get_value_action_retention(weeks: int = 8) -> dict:
    """
    Answers: "Are activated users coming back to do value actions?"

    Unlike get_activated_retention (which uses session presence = 'logged in'),
    this measures whether activated users performed a structural value action
    (save / note / annotation / compare) in each weekly cohort window.
    More honest signal for product engagement.
    """
    now = _now()
    start = now - timedelta(weeks=weeks)
    start_iso = start.isoformat()

    conn = _connect_auth()
    try:
        # Step 1: all activated users (same definition as get_activated_retention)
        activated_ids: set[int] = set()
        for table in ["kb_papers", "kb_notes", "kb_annotations", "kb_compare_results"]:
            if _table_exists(conn, table):
                rows = conn.execute(
                    f"SELECT DISTINCT user_id FROM {table} WHERE user_id > 0"
                ).fetchall()
                activated_ids.update(r["user_id"] for r in rows)

        if not activated_ids:
            return {"cohorts": [], "weeks": weeks, "total_activated": 0, "definition": "value_action"}

        placeholders = ",".join("?" * len(activated_ids))
        activated_list = list(activated_ids)

        # Step 2: registration dates of recently-registered activated users
        users = conn.execute(
            f"""
            SELECT id, created_at FROM auth_users
            WHERE id IN ({placeholders}) AND created_at >= ?
            """,
            (*activated_list, start_iso),
        ).fetchall()

        # Step 3: collect value-action timestamps per user -> week number
        user_value_weeks: dict[int, set[int]] = defaultdict(set)
        for table in ["kb_papers", "kb_notes", "kb_annotations", "kb_compare_results"]:
            if _table_exists(conn, table):
                rows = conn.execute(
                    f"""
                    SELECT user_id, created_at FROM {table}
                    WHERE user_id IN ({placeholders}) AND created_at >= ?
                    """,
                    (*activated_list, start_iso),
                ).fetchall()
                for r in rows:
                    try:
                        dt = datetime.fromisoformat(r["created_at"])
                        week_num = (dt - start).days // 7
                        if 0 <= week_num < weeks:
                            user_value_weeks[r["user_id"]].add(week_num)
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
                    if offset_week in user_value_weeks.get(uid, set())
                )
                retention.append(round(active_in_week / cohort_size * 100, 1))

            cohorts.append({
                "week": week_start.strftime("%m/%d"),
                "cohort_size": cohort_size,
                "retention": retention,
            })

        return {
            "cohorts": cohorts,
            "weeks": weeks,
            "total_activated": len(activated_ids),
            "definition": "value_action",
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module C (step funnel): card_view -> paper_view -> save -> deep_action
# ---------------------------------------------------------------------------

def get_content_step_funnel(days: int = 30) -> dict:
    """
    Answers: "Where in the discovery-to-engagement funnel are users dropping off?"

    Returns distinct-user counts at each step:
      Step 1: paper_card_view  – saw a paper card in the recommendation list
      Step 2: paper_view       – opened paper detail page
      Step 3: save             – saved paper to knowledge base
      Step 4: deep_action      – note / annotation / compare

    Also surfaces high-view-low-save anomaly papers for drill-down.
    NOTE: card_view events require frontend tracking to accumulate; until then
          step 1 will show 0 and a note is included in the response.
    """
    now = _now()
    start_dt = now - timedelta(days=days)
    start_iso = start_dt.isoformat()

    conn = _connect_auth()
    try:
        # Step 1: distinct users who viewed a paper card
        s1_users = 0
        if _table_exists(conn, "analytics_events"):
            s1_users = conn.execute(
                """
                SELECT COUNT(DISTINCT user_id) FROM analytics_events
                WHERE event_type = 'paper_card_view' AND created_at >= ? AND user_id > 0
                """,
                (start_iso,),
            ).fetchone()[0]

        # Step 2: distinct users who opened a paper detail
        s2_users = 0
        if _table_exists(conn, "analytics_events"):
            s2_users = conn.execute(
                """
                SELECT COUNT(DISTINCT user_id) FROM analytics_events
                WHERE event_type = 'paper_view' AND created_at >= ? AND user_id > 0
                """,
                (start_iso,),
            ).fetchone()[0]

        # Step 3: distinct users who saved a paper (structural table — always reliable)
        s3_users = 0
        if _table_exists(conn, "kb_papers"):
            s3_users = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM kb_papers WHERE created_at >= ? AND user_id > 0",
                (start_iso,),
            ).fetchone()[0]

        # Step 4: distinct users who did deep actions
        s4_ids: set[int] = set()
        for tbl in ["kb_notes", "kb_annotations", "kb_compare_results"]:
            if _table_exists(conn, tbl):
                rows = conn.execute(
                    f"SELECT DISTINCT user_id FROM {tbl} WHERE created_at >= ? AND user_id > 0",
                    (start_iso,),
                ).fetchall()
                s4_ids.update(r["user_id"] for r in rows)
        s4_users = len(s4_ids)

        # Anomaly: papers with high views but low save rate (drill-down)
        anomaly_papers = []
        if _table_exists(conn, "analytics_events"):
            view_rows = conn.execute(
                """
                SELECT target_id AS paper_id, COUNT(DISTINCT user_id) AS view_users
                FROM analytics_events
                WHERE event_type = 'paper_view' AND created_at >= ?
                  AND target_id IS NOT NULL AND user_id > 0
                GROUP BY target_id
                HAVING view_users >= 2
                ORDER BY view_users DESC
                LIMIT 30
                """,
                (start_iso,),
            ).fetchall()

            for r in view_rows:
                pid = r["paper_id"]
                save_users = 0
                if _table_exists(conn, "kb_papers"):
                    save_users = conn.execute(
                        "SELECT COUNT(DISTINCT user_id) FROM kb_papers"
                        " WHERE paper_id = ? AND created_at >= ? AND user_id > 0",
                        (pid, start_iso),
                    ).fetchone()[0]
                vu = r["view_users"]
                save_rate = round(save_users / vu * 100, 1) if vu > 0 else 0.0
                title = pid
                if _table_exists(conn, "kb_papers"):
                    pd_row = conn.execute(
                        "SELECT paper_data FROM kb_papers WHERE paper_id = ? LIMIT 1",
                        (pid,),
                    ).fetchone()
                    if pd_row:
                        try:
                            pd_data = json.loads(pd_row["paper_data"])
                            title = pd_data.get("📖标题") or pd_data.get("short_title") or pid
                        except Exception:
                            pass
                anomaly_papers.append({
                    "paper_id": pid,
                    "title": title,
                    "view_users": vu,
                    "save_users": save_users,
                    "save_rate": save_rate,
                })

        # Keep only low-save-rate papers, sorted by most viewed
        anomaly_papers = sorted(
            [p for p in anomaly_papers if p["save_rate"] < 30],
            key=lambda x: x["view_users"],
            reverse=True,
        )[:10]

        return {
            "days": days,
            "funnel": [
                {
                    "step": "card_view",
                    "label": "浏览推荐列表（论文卡片）",
                    "users": s1_users,
                    "note": "需前端埋点积累后才有数据" if s1_users == 0 else "",
                },
                {"step": "paper_view", "label": "打开论文详情", "users": s2_users, "note": ""},
                {"step": "save", "label": "收藏论文", "users": s3_users, "note": "来自结构表，始终准确"},
                {"step": "deep_action", "label": "深度行为（笔记/批注/对比）", "users": s4_users, "note": ""},
            ],
            "high_view_low_save": anomaly_papers,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module D: AI Feature Adoption
# ---------------------------------------------------------------------------

def get_ai_feature_stats(days: int = 30) -> dict:
    """
    Answers: "Are users adopting AI features? Which ones?"

    Covers three high-value AI surfaces:
      - Deep Research   → research_sessions table (paper_analysis.db)
      - Paper Chat      → paper_chat_sessions + paper_chat_messages (paper_analysis.db)
      - Idea Generation → idea_candidates (idea.db)

    Returns:
      - penetration_rate: % of activated users who used any AI feature in [days]
      - per-feature: distinct users, total sessions/items, daily trend
      - combined daily trend (any AI feature usage)
    """
    days = max(1, min(days, 180))
    now = _now()
    start_dt = now - timedelta(days=days)
    start_iso = start_dt.isoformat()

    date_labels = []
    for i in range(days):
        d = (start_dt + timedelta(days=i + 1))
        date_labels.append(d.strftime("%Y-%m-%d"))

    conn = _connect_auth()
    try:
        # --- Deep Research ---
        research_users = 0
        research_sessions_count = 0
        research_daily: dict[str, int] = {}

        if _table_exists(conn, "research_sessions"):
            research_users = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM research_sessions"
                " WHERE created_at >= ? AND user_id > 0",
                (start_iso,),
            ).fetchone()[0]
            research_sessions_count = conn.execute(
                "SELECT COUNT(*) FROM research_sessions WHERE created_at >= ? AND user_id > 0",
                (start_iso,),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT DATE(created_at) as day, COUNT(DISTINCT user_id) as cnt"
                " FROM research_sessions WHERE created_at >= ? AND user_id > 0"
                " GROUP BY DATE(created_at)",
                (start_iso,),
            ).fetchall()
            research_daily = {r["day"]: r["cnt"] for r in rows}

        # --- Paper Chat ---
        chat_users = 0
        chat_sessions_count = 0
        chat_messages_count = 0
        chat_daily: dict[str, int] = {}

        if _table_exists(conn, "paper_chat_sessions"):
            chat_users = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM paper_chat_sessions"
                " WHERE created_at >= ? AND user_id > 0",
                (start_iso,),
            ).fetchone()[0]
            chat_sessions_count = conn.execute(
                "SELECT COUNT(*) FROM paper_chat_sessions WHERE created_at >= ? AND user_id > 0",
                (start_iso,),
            ).fetchone()[0]
            if _table_exists(conn, "paper_chat_messages"):
                chat_messages_count = conn.execute(
                    "SELECT COUNT(*) FROM paper_chat_messages WHERE created_at >= ?",
                    (start_iso,),
                ).fetchone()[0]
            rows = conn.execute(
                "SELECT DATE(created_at) as day, COUNT(DISTINCT user_id) as cnt"
                " FROM paper_chat_sessions WHERE created_at >= ? AND user_id > 0"
                " GROUP BY DATE(created_at)",
                (start_iso,),
            ).fetchall()
            chat_daily = {r["day"]: r["cnt"] for r in rows}

        # --- Total activated users (for penetration rate) ---
        total_activated = 0
        activated_ids: set[int] = set()
        for table in ["kb_papers", "kb_notes", "kb_annotations", "kb_compare_results"]:
            if _table_exists(conn, table):
                rows2 = conn.execute(
                    f"SELECT DISTINCT user_id FROM {table} WHERE user_id > 0"
                ).fetchall()
                activated_ids.update(r["user_id"] for r in rows2)
        total_activated = len(activated_ids)

    finally:
        conn.close()

    # --- Idea Generation (from idea.db) ---
    idea_users = 0
    idea_count = 0
    idea_daily: dict[str, int] = {}

    try:
        iconn = _connect_idea()
        if _table_exists(iconn, "idea_candidates"):
            idea_users = iconn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM idea_candidates"
                " WHERE created_at >= ? AND user_id > 0",
                (start_iso,),
            ).fetchone()[0]
            idea_count = iconn.execute(
                "SELECT COUNT(*) FROM idea_candidates WHERE created_at >= ? AND user_id > 0",
                (start_iso,),
            ).fetchone()[0]
            rows3 = iconn.execute(
                "SELECT DATE(created_at) as day, COUNT(DISTINCT user_id) as cnt"
                " FROM idea_candidates WHERE created_at >= ? AND user_id > 0"
                " GROUP BY DATE(created_at)",
                (start_iso,),
            ).fetchall()
            idea_daily = {r["day"]: r["cnt"] for r in rows3}
        iconn.close()
    except Exception:
        pass

    # --- Combined any-AI-feature daily users (union via max per day) ---
    all_ai_daily: dict[str, set] = defaultdict(set)
    # For simplicity: per-day count = max of the three (rough upper bound union)
    # We track by summing distinct users across features per day (may overcount, noted)
    combined_daily = []
    for d in date_labels:
        combined_daily.append(max(
            research_daily.get(d, 0),
            chat_daily.get(d, 0),
            idea_daily.get(d, 0),
        ))

    # Penetration rate = users who used any AI feature / total activated users
    ai_users_set_approx = max(research_users, chat_users, idea_users)
    penetration_rate = round(ai_users_set_approx / total_activated * 100, 1) if total_activated > 0 else 0.0

    return {
        "days": days,
        "dates": date_labels,
        "total_activated": total_activated,
        "penetration_rate": penetration_rate,
        "features": {
            "research": {
                "label": "深度研究",
                "users": research_users,
                "sessions": research_sessions_count,
                "daily": [research_daily.get(d, 0) for d in date_labels],
            },
            "chat": {
                "label": "论文聊天",
                "users": chat_users,
                "sessions": chat_sessions_count,
                "messages": chat_messages_count,
                "daily": [chat_daily.get(d, 0) for d in date_labels],
            },
            "idea": {
                "label": "灵感生成",
                "users": idea_users,
                "generated": idea_count,
                "daily": [idea_daily.get(d, 0) for d in date_labels],
            },
        },
        "combined_daily": combined_daily,
        "note": "penetration_rate = max(研究/聊天/灵感用户数) / 已激活用户总数，为保守估算（可能低估真实去重值）",
    }


# ---------------------------------------------------------------------------
# Engagement Depth: session duration + reading duration signals
# ---------------------------------------------------------------------------

def get_engagement_depth(days: int = 30) -> dict:
    """
    Answers: "How deeply are users engaging, not just how often?"

    Uses analytics_events to compute:
      - Daily avg session duration (session_duration events, in seconds)
      - Daily avg paper reading duration (paper_view_duration events, in seconds)
      - Distribution buckets for session duration (<30s / 30-120s / 2-10min / >10min)
      - Window aggregate: overall avg + median approx for the period
    """
    days = max(1, min(days, 90))
    now = _now()
    start_dt = now - timedelta(days=days)
    start_iso = start_dt.isoformat()

    date_labels = []
    for i in range(days):
        d = (start_dt + timedelta(days=i + 1))
        date_labels.append(d.strftime("%Y-%m-%d"))

    conn = _connect_auth()
    try:
        if not _table_exists(conn, "analytics_events"):
            return {
                "days": days,
                "dates": date_labels,
                "avg_session_duration_by_day": [None] * days,
                "avg_paper_read_duration_by_day": [None] * days,
                "window_avg_session_seconds": None,
                "window_avg_paper_read_seconds": None,
                "session_duration_distribution": {
                    "lt30s": 0, "s30_120": 0, "m2_10": 0, "gt10m": 0,
                },
                "data_available": False,
            }

        # Daily avg session duration
        session_rows = conn.execute(
            """
            SELECT DATE(created_at) as day, AVG(value) as avg_val, COUNT(*) as cnt
            FROM analytics_events
            WHERE event_type = 'session_duration' AND value > 0 AND created_at >= ?
            GROUP BY DATE(created_at)
            """,
            (start_iso,),
        ).fetchall()
        session_by_day = {r["day"]: round(r["avg_val"] or 0, 1) for r in session_rows}
        session_daily = [session_by_day.get(d) for d in date_labels]

        # Daily avg paper reading duration
        read_rows = conn.execute(
            """
            SELECT DATE(created_at) as day, AVG(value) as avg_val
            FROM analytics_events
            WHERE event_type = 'paper_view_duration' AND value > 0 AND created_at >= ?
            GROUP BY DATE(created_at)
            """,
            (start_iso,),
        ).fetchall()
        read_by_day = {r["day"]: round(r["avg_val"] or 0, 1) for r in read_rows}
        read_daily = [read_by_day.get(d) for d in date_labels]

        # Window aggregates
        window_session = conn.execute(
            "SELECT AVG(value) FROM analytics_events"
            " WHERE event_type='session_duration' AND value > 0 AND created_at >= ?",
            (start_iso,),
        ).fetchone()[0]
        window_read = conn.execute(
            "SELECT AVG(value) FROM analytics_events"
            " WHERE event_type='paper_view_duration' AND value > 0 AND created_at >= ?",
            (start_iso,),
        ).fetchone()[0]

        # Session duration distribution (counts)
        def _bucket(min_v, max_v):
            if max_v is None:
                return conn.execute(
                    "SELECT COUNT(*) FROM analytics_events"
                    " WHERE event_type='session_duration' AND value >= ? AND created_at >= ?",
                    (min_v, start_iso),
                ).fetchone()[0]
            return conn.execute(
                "SELECT COUNT(*) FROM analytics_events"
                " WHERE event_type='session_duration' AND value >= ? AND value < ? AND created_at >= ?",
                (min_v, max_v, start_iso),
            ).fetchone()[0]

        dist = {
            "lt30s": _bucket(0, 30),
            "s30_120": _bucket(30, 120),
            "m2_10": _bucket(120, 600),
            "gt10m": _bucket(600, None),
        }

        return {
            "days": days,
            "dates": date_labels,
            "avg_session_duration_by_day": session_daily,
            "avg_paper_read_duration_by_day": read_daily,
            "window_avg_session_seconds": round(window_session, 1) if window_session else None,
            "window_avg_paper_read_seconds": round(window_read, 1) if window_read else None,
            "session_duration_distribution": dist,
            "data_available": True,
            "note": "session_duration/paper_view_duration 来自前端埋点；avg 为算术平均值",
        }
    finally:
        conn.close()
