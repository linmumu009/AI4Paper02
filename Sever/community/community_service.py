"""
Community service layer.

Provides CRUD operations for community_posts, community_replies, and community_likes
tables stored in paper_analysis.db.

Categories: 'question' | 'discussion' | 'sharing' | 'help'
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

VALID_CATEGORIES = {"question", "discussion", "sharing", "help"}


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Create community tables if they don't exist."""
    conn = _connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS community_posts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                category     TEXT    NOT NULL DEFAULT 'discussion',
                title        TEXT    NOT NULL,
                content      TEXT    NOT NULL,
                view_count   INTEGER NOT NULL DEFAULT 0,
                reply_count  INTEGER NOT NULL DEFAULT 0,
                like_count   INTEGER NOT NULL DEFAULT 0,
                is_pinned    INTEGER NOT NULL DEFAULT 0,
                is_closed    INTEGER NOT NULL DEFAULT 0,
                last_reply_at TEXT,
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_community_posts_user_id
                ON community_posts(user_id);
            CREATE INDEX IF NOT EXISTS idx_community_posts_category
                ON community_posts(category);
            CREATE INDEX IF NOT EXISTS idx_community_posts_list
                ON community_posts(is_pinned DESC, last_reply_at DESC, created_at DESC);

            CREATE TABLE IF NOT EXISTS community_replies (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id          INTEGER NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
                user_id          INTEGER NOT NULL,
                parent_reply_id  INTEGER REFERENCES community_replies(id) ON DELETE SET NULL,
                content          TEXT    NOT NULL,
                like_count       INTEGER NOT NULL DEFAULT 0,
                created_at       TEXT    NOT NULL,
                updated_at       TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_community_replies_post
                ON community_replies(post_id, created_at);

            CREATE TABLE IF NOT EXISTS community_likes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                target_type TEXT    NOT NULL,
                target_id   INTEGER NOT NULL,
                created_at  TEXT    NOT NULL,
                UNIQUE(user_id, target_type, target_id)
            );

            CREATE INDEX IF NOT EXISTS idx_community_likes_target
                ON community_likes(target_type, target_id);
        """)
        conn.commit()
        # Migration: add parent_reply_id to existing tables that lack it
        try:
            conn.execute(
                "ALTER TABLE community_replies ADD COLUMN parent_reply_id INTEGER REFERENCES community_replies(id) ON DELETE SET NULL"
            )
            conn.commit()
        except Exception:
            pass  # column already exists
        print("[community_service] Tables initialized.", flush=True)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helper: row → dict
# ---------------------------------------------------------------------------

def _post_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "username": row["username"] if "username" in row.keys() else None,
        "category": row["category"],
        "title": row["title"],
        "content": row["content"],
        "view_count": row["view_count"],
        "reply_count": row["reply_count"],
        "like_count": row["like_count"],
        "is_pinned": bool(row["is_pinned"]),
        "is_closed": bool(row["is_closed"]),
        "last_reply_at": row["last_reply_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _reply_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "post_id": row["post_id"],
        "user_id": row["user_id"],
        "username": row["username"] if "username" in row.keys() else None,
        "content": row["content"],
        "like_count": row["like_count"],
        "parent_reply_id": row["parent_reply_id"] if "parent_reply_id" in row.keys() else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

def list_posts(
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "latest",
) -> dict:
    """
    Return paginated post list.
    sort: 'latest' (by last_reply_at/created_at desc) | 'hot' (by reply_count desc)
    """
    offset = (page - 1) * page_size
    where_clause = ""
    params: list = []

    if category and category in VALID_CATEGORIES:
        where_clause = "WHERE p.category = ?"
        params.append(category)

    if sort == "hot":
        order_clause = "ORDER BY p.is_pinned DESC, p.reply_count DESC, p.created_at DESC"
    else:
        order_clause = "ORDER BY p.is_pinned DESC, COALESCE(p.last_reply_at, p.created_at) DESC"

    sql = f"""
        SELECT p.*, u.username
        FROM community_posts p
        LEFT JOIN auth_users u ON u.id = p.user_id
        {where_clause}
        {order_clause}
        LIMIT ? OFFSET ?
    """
    count_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM community_posts p
        {where_clause}
    """
    params_with_page = params + [page_size, offset]

    conn = _connect()
    try:
        total = conn.execute(count_sql, params).fetchone()["cnt"]
        rows = conn.execute(sql, params_with_page).fetchall()
        posts = []
        for r in rows:
            d = _post_row_to_dict(r)
            d.pop("content", None)  # omit full content in list view
            posts.append(d)
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "posts": posts,
        }
    finally:
        conn.close()


def get_post(post_id: int) -> Optional[dict]:
    """Get a single post with its replies."""
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT p.*, u.username
            FROM community_posts p
            LEFT JOIN auth_users u ON u.id = p.user_id
            WHERE p.id = ?
            """,
            (post_id,),
        ).fetchone()
        if row is None:
            return None
        post = _post_row_to_dict(row)

        reply_rows = conn.execute(
            """
            SELECT r.*, u.username
            FROM community_replies r
            LEFT JOIN auth_users u ON u.id = r.user_id
            WHERE r.post_id = ?
            ORDER BY r.created_at ASC
            """,
            (post_id,),
        ).fetchall()
        post["replies"] = [_reply_row_to_dict(r) for r in reply_rows]
        return post
    finally:
        conn.close()


def create_post(user_id: int, category: str, title: str, content: str) -> dict:
    if category not in VALID_CATEGORIES:
        category = "discussion"
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO community_posts
                (user_id, category, title, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, category, title.strip(), content.strip(), now, now),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT p.*, u.username
            FROM community_posts p
            LEFT JOIN auth_users u ON u.id = p.user_id
            WHERE p.id = ?
            """,
            (cur.lastrowid,),
        ).fetchone()
        post = _post_row_to_dict(row)
        post["replies"] = []
        return post
    finally:
        conn.close()


def update_post(
    post_id: int,
    title: Optional[str] = None,
    content: Optional[str] = None,
    category: Optional[str] = None,
) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM community_posts WHERE id = ?", (post_id,)
        ).fetchone()
        if row is None:
            return None

        new_title = title.strip() if title is not None else row["title"]
        new_content = content.strip() if content is not None else row["content"]
        new_category = category if category in VALID_CATEGORIES else row["category"]
        now = _now_iso()

        conn.execute(
            """
            UPDATE community_posts
            SET title = ?, content = ?, category = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_title, new_content, new_category, now, post_id),
        )
        conn.commit()
        return get_post(post_id)
    finally:
        conn.close()


def delete_post(post_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM community_posts WHERE id = ?", (post_id,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def increment_view_count(post_id: int) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE community_posts SET view_count = view_count + 1 WHERE id = ?",
            (post_id,),
        )
        conn.commit()
    finally:
        conn.close()


def set_pinned(post_id: int, pinned: bool) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE community_posts SET is_pinned = ? WHERE id = ?",
            (int(pinned), post_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_closed(post_id: int, closed: bool) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE community_posts SET is_closed = ? WHERE id = ?",
            (int(closed), post_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Replies
# ---------------------------------------------------------------------------

def create_reply(post_id: int, user_id: int, content: str, parent_reply_id: Optional[int] = None) -> Optional[dict]:
    """Create a reply, increment post reply_count and update last_reply_at."""
    conn = _connect()
    try:
        post = conn.execute(
            "SELECT id, is_closed FROM community_posts WHERE id = ?", (post_id,)
        ).fetchone()
        if post is None:
            return None

        now = _now_iso()
        cur = conn.execute(
            """
            INSERT INTO community_replies (post_id, user_id, parent_reply_id, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (post_id, user_id, parent_reply_id, content.strip(), now, now),
        )
        reply_id = cur.lastrowid

        conn.execute(
            """
            UPDATE community_posts
            SET reply_count = reply_count + 1, last_reply_at = ?
            WHERE id = ?
            """,
            (now, post_id),
        )
        conn.commit()

        row = conn.execute(
            """
            SELECT r.*, u.username
            FROM community_replies r
            LEFT JOIN auth_users u ON u.id = r.user_id
            WHERE r.id = ?
            """,
            (reply_id,),
        ).fetchone()
        return _reply_row_to_dict(row)
    finally:
        conn.close()


def update_reply(reply_id: int, content: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM community_replies WHERE id = ?", (reply_id,)
        ).fetchone()
        if row is None:
            return None
        now = _now_iso()
        conn.execute(
            "UPDATE community_replies SET content = ?, updated_at = ? WHERE id = ?",
            (content.strip(), now, reply_id),
        )
        conn.commit()
        updated = conn.execute(
            """
            SELECT r.*, u.username
            FROM community_replies r
            LEFT JOIN auth_users u ON u.id = r.user_id
            WHERE r.id = ?
            """,
            (reply_id,),
        ).fetchone()
        return _reply_row_to_dict(updated)
    finally:
        conn.close()


def delete_reply(reply_id: int) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT post_id FROM community_replies WHERE id = ?", (reply_id,)
        ).fetchone()
        if row is None:
            return False
        post_id = row["post_id"]

        conn.execute("DELETE FROM community_replies WHERE id = ?", (reply_id,))
        conn.execute(
            "UPDATE community_posts SET reply_count = MAX(0, reply_count - 1) WHERE id = ?",
            (post_id,),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_reply(reply_id: int) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM community_replies WHERE id = ?", (reply_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Likes
# ---------------------------------------------------------------------------

def toggle_like(user_id: int, target_type: str, target_id: int) -> dict:
    """
    Toggle like for a post or reply.
    Returns {"liked": bool, "like_count": int}
    """
    if target_type not in ("post", "reply"):
        raise ValueError(f"Invalid target_type: {target_type}")

    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT id FROM community_likes WHERE user_id = ? AND target_type = ? AND target_id = ?",
            (user_id, target_type, target_id),
        ).fetchone()

        if existing:
            conn.execute(
                "DELETE FROM community_likes WHERE user_id = ? AND target_type = ? AND target_id = ?",
                (user_id, target_type, target_id),
            )
            if target_type == "post":
                conn.execute(
                    "UPDATE community_posts SET like_count = MAX(0, like_count - 1) WHERE id = ?",
                    (target_id,),
                )
                new_count_row = conn.execute(
                    "SELECT like_count FROM community_posts WHERE id = ?", (target_id,)
                ).fetchone()
            else:
                conn.execute(
                    "UPDATE community_replies SET like_count = MAX(0, like_count - 1) WHERE id = ?",
                    (target_id,),
                )
                new_count_row = conn.execute(
                    "SELECT like_count FROM community_replies WHERE id = ?", (target_id,)
                ).fetchone()
            conn.commit()
            return {"liked": False, "like_count": new_count_row["like_count"] if new_count_row else 0}
        else:
            conn.execute(
                "INSERT INTO community_likes (user_id, target_type, target_id, created_at) VALUES (?, ?, ?, ?)",
                (user_id, target_type, target_id, _now_iso()),
            )
            if target_type == "post":
                conn.execute(
                    "UPDATE community_posts SET like_count = like_count + 1 WHERE id = ?",
                    (target_id,),
                )
                new_count_row = conn.execute(
                    "SELECT like_count FROM community_posts WHERE id = ?", (target_id,)
                ).fetchone()
            else:
                conn.execute(
                    "UPDATE community_replies SET like_count = like_count + 1 WHERE id = ?",
                    (target_id,),
                )
                new_count_row = conn.execute(
                    "SELECT like_count FROM community_replies WHERE id = ?", (target_id,)
                ).fetchone()
            conn.commit()
            return {"liked": True, "like_count": new_count_row["like_count"] if new_count_row else 0}
    finally:
        conn.close()


def get_user_liked_targets(user_id: int, target_type: str, target_ids: list[int]) -> set[int]:
    """Return the subset of target_ids that user_id has liked."""
    if not target_ids:
        return set()
    placeholders = ",".join("?" * len(target_ids))
    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            SELECT target_id FROM community_likes
            WHERE user_id = ? AND target_type = ? AND target_id IN ({placeholders})
            """,
            [user_id, target_type] + list(target_ids),
        ).fetchall()
        return {r["target_id"] for r in rows}
    finally:
        conn.close()
