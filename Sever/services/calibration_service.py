"""Calibration Service — per-user score-weight calibration infrastructure.

Manages the audit table ``weight_calibration_history`` and exposes helpers
used by both the weekly calibration script and the admin dashboard (Week 6).

Schema
------
  weight_calibration_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    calibrated_at  TEXT    NOT NULL,   -- UTC ISO8601
    old_weights    TEXT    NOT NULL,   -- JSON {"theme":…,"pref":…,"novel":…}
    new_weights    TEXT    NOT NULL,   -- JSON {"theme":…,"pref":…,"novel":…}
    ndcg_old       REAL    NOT NULL,
    ndcg_new       REAL    NOT NULL,
    n_impressions  INTEGER NOT NULL,
    n_saves        INTEGER NOT NULL,
    improved       INTEGER NOT NULL    -- boolean 0/1
  )
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")


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
    """Create calibration tables if they do not exist."""
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weight_calibration_history (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                calibrated_at  TEXT    NOT NULL,
                old_weights    TEXT    NOT NULL DEFAULT '{}',
                new_weights    TEXT    NOT NULL DEFAULT '{}',
                ndcg_old       REAL    NOT NULL DEFAULT 0.0,
                ndcg_new       REAL    NOT NULL DEFAULT 0.0,
                n_impressions  INTEGER NOT NULL DEFAULT 0,
                n_saves        INTEGER NOT NULL DEFAULT 0,
                improved       INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_wch_user
                ON weight_calibration_history(user_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_wch_calibrated_at
                ON weight_calibration_history(calibrated_at)
        """)
        conn.commit()
        logger.info("calibration_service: DB tables ready")
    except Exception as exc:
        logger.error("calibration_service.init_db: %r", exc)
    finally:
        conn.close()


# ── Audit log ──────────────────────────────────────────────────────────────────

def record_calibration(
    user_id: int,
    old_weights: dict,
    new_weights: dict,
    ndcg_old: float,
    ndcg_new: float,
    n_impressions: int,
    n_saves: int,
) -> int:
    """Persist one calibration event and return the new row id."""
    improved = 1 if ndcg_new > ndcg_old else 0
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO weight_calibration_history
                (user_id, calibrated_at, old_weights, new_weights,
                 ndcg_old, ndcg_new, n_impressions, n_saves, improved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                _now_iso(),
                json.dumps(old_weights, ensure_ascii=False),
                json.dumps(new_weights, ensure_ascii=False),
                round(ndcg_old, 6),
                round(ndcg_new, 6),
                n_impressions,
                n_saves,
                improved,
            ),
        )
        conn.commit()
        return cur.lastrowid or 0
    except Exception as exc:
        logger.warning("calibration_service.record_calibration: %r", exc)
        return 0
    finally:
        conn.close()


def get_last_calibration(user_id: int) -> Optional[dict]:
    """Return the most recent calibration record for a user, or None."""
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT * FROM weight_calibration_history
            WHERE user_id = ?
            ORDER BY calibrated_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "calibrated_at": row["calibrated_at"],
            "old_weights":   json.loads(row["old_weights"]),
            "new_weights":   json.loads(row["new_weights"]),
            "ndcg_old":      row["ndcg_old"],
            "ndcg_new":      row["ndcg_new"],
            "n_impressions": row["n_impressions"],
            "n_saves":       row["n_saves"],
            "improved":      bool(row["improved"]),
        }
    except Exception as exc:
        logger.warning("calibration_service.get_last_calibration: %r", exc)
        return None
    finally:
        conn.close()


def get_calibration_history(user_id: int, limit: int = 10) -> list[dict]:
    """Return up to *limit* most recent calibration records for a user."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM weight_calibration_history
            WHERE user_id = ?
            ORDER BY calibrated_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [
            {
                "calibrated_at": r["calibrated_at"],
                "old_weights":   json.loads(r["old_weights"]),
                "new_weights":   json.loads(r["new_weights"]),
                "ndcg_old":      r["ndcg_old"],
                "ndcg_new":      r["ndcg_new"],
                "n_impressions": r["n_impressions"],
                "n_saves":       r["n_saves"],
                "improved":      bool(r["improved"]),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("calibration_service.get_calibration_history: %r", exc)
        return []
    finally:
        conn.close()


def get_admin_calibration_stats(days: int = 30) -> dict:
    """Return system-wide calibration stats for the admin dashboard."""
    from datetime import timedelta
    conn = _connect()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        total = conn.execute(
            "SELECT COUNT(*) FROM weight_calibration_history WHERE calibrated_at >= ?",
            (cutoff,),
        ).fetchone()[0] or 0
        improved = conn.execute(
            "SELECT COUNT(*) FROM weight_calibration_history WHERE calibrated_at >= ? AND improved = 1",
            (cutoff,),
        ).fetchone()[0] or 0
        unique_users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM weight_calibration_history WHERE calibrated_at >= ?",
            (cutoff,),
        ).fetchone()[0] or 0
        avg_improvement_row = conn.execute(
            """
            SELECT AVG(ndcg_new - ndcg_old) AS avg_imp
            FROM weight_calibration_history
            WHERE calibrated_at >= ? AND improved = 1
            """,
            (cutoff,),
        ).fetchone()
        avg_improvement = float(avg_improvement_row["avg_imp"] or 0)
        return {
            "days": days,
            "total_calibrations": total,
            "improved_calibrations": improved,
            "unique_users": unique_users,
            "avg_ndcg_improvement": round(avg_improvement, 4),
        }
    except Exception as exc:
        logger.warning("calibration_service.get_admin_calibration_stats: %r", exc)
        return {"days": days, "total_calibrations": 0, "improved_calibrations": 0, "unique_users": 0, "avg_ndcg_improvement": 0.0}
    finally:
        conn.close()
