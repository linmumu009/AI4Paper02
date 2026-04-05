"""
Announcement service layer.

Provides CRUD operations for the announcements table stored in paper_analysis.db.
Tags: 'important' | 'general' | 'update' | 'maintenance'
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

VALID_TAGS = {"important", "general", "update", "maintenance"}


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "tag": row["tag"],
        "is_pinned": bool(row["is_pinned"]),
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_announcements(limit: int = 50, offset: int = 0) -> list:
    """Return announcements ordered by pinned first, then by created_at desc."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, title, content, tag, is_pinned, created_by, created_at, updated_at
            FROM announcements
            ORDER BY is_pinned DESC, created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def count_announcements() -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM announcements").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def get_announcement(announcement_id: int) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ?", (announcement_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def create_announcement(
    title: str,
    content: str,
    tag: str = "general",
    is_pinned: bool = False,
    created_by: Optional[int] = None,
) -> dict:
    if tag not in VALID_TAGS:
        tag = "general"
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO announcements (title, content, tag, is_pinned, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title.strip(), content.strip(), tag, int(is_pinned), created_by, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_announcement(
    announcement_id: int,
    title: Optional[str] = None,
    content: Optional[str] = None,
    tag: Optional[str] = None,
    is_pinned: Optional[bool] = None,
) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM announcements WHERE id = ?", (announcement_id,)
        ).fetchone()
        if row is None:
            return None

        new_title = title.strip() if title is not None else row["title"]
        new_content = content.strip() if content is not None else row["content"]
        new_tag = tag if tag in VALID_TAGS else row["tag"]
        new_pinned = int(is_pinned) if is_pinned is not None else row["is_pinned"]
        now = _now_iso()

        conn.execute(
            """
            UPDATE announcements
            SET title = ?, content = ?, tag = ?, is_pinned = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_title, new_content, new_tag, new_pinned, now, announcement_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM announcements WHERE id = ?", (announcement_id,)
        ).fetchone()
        return _row_to_dict(updated)
    finally:
        conn.close()


def delete_announcement(announcement_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM announcements WHERE id = ?", (announcement_id,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Unread tracking
# ---------------------------------------------------------------------------


def count_unread(user_id: int) -> int:
    """Return number of announcements not yet read by user_id."""
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM announcements a
            WHERE NOT EXISTS (
                SELECT 1 FROM announcement_reads r
                WHERE r.user_id = ? AND r.announcement_id = a.id
            )
            """,
            (user_id,),
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def list_announcements_with_read(user_id: int, limit: int = 50, offset: int = 0) -> list:
    """Return announcements with an is_read field for the given user."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT a.id, a.title, a.content, a.tag, a.is_pinned,
                   a.created_by, a.created_at, a.updated_at,
                   CASE WHEN r.user_id IS NOT NULL THEN 1 ELSE 0 END AS is_read
            FROM announcements a
            LEFT JOIN announcement_reads r
                   ON r.announcement_id = a.id AND r.user_id = ?
            ORDER BY a.is_pinned DESC, a.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        ).fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            d["is_read"] = bool(row["is_read"])
            result.append(d)
        return result
    finally:
        conn.close()


def mark_read(user_id: int, announcement_ids: list) -> None:
    """Mark specific announcements as read for user_id (upsert)."""
    if not announcement_ids:
        return
    now = _now_iso()
    conn = _connect()
    try:
        conn.executemany(
            """
            INSERT OR IGNORE INTO announcement_reads (user_id, announcement_id, read_at)
            VALUES (?, ?, ?)
            """,
            [(user_id, aid, now) for aid in announcement_ids],
        )
        conn.commit()
    finally:
        conn.close()


def mark_all_read(user_id: int) -> None:
    """Mark all current announcements as read for user_id."""
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO announcement_reads (user_id, announcement_id, read_at)
            SELECT ?, id, ? FROM announcements
            """,
            (user_id, now),
        )
        conn.commit()
    finally:
        conn.close()
