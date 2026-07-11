"""Unified, user-scoped search across research assets."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PAPER_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")
_USER_PAPERS_DB_PATH = os.path.join(_BASE_DIR, "database", "user_papers.db")


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _score(title: str, searchable: str, query: str) -> int:
    title_l = title.casefold()
    text_l = searchable.casefold()
    query_l = query.casefold()
    if title_l == query_l:
        return 120
    if title_l.startswith(query_l):
        return 100
    if query_l in title_l:
        return 80
    if query_l in text_l:
        return 40
    return 0


def _paper_title(data: dict[str, Any], paper_id: str) -> str:
    return str(
        data.get("short_title")
        or data.get("📖标题")
        or data.get("title")
        or paper_id
    )


def search_assets(user_id: int, query: str, limit: int = 30) -> dict:
    """Return ranked results from all durable research-asset stores."""
    q = query.strip()
    if not q:
        return {"query": "", "results": [], "total": 0}

    per_type_limit = max(8, min(limit, 30))
    like = f"%{q}%"
    results: list[dict[str, Any]] = []

    if os.path.isfile(_PAPER_DB_PATH):
        conn = _connect(_PAPER_DB_PATH)
        try:
            if _table_exists(conn, "kb_papers"):
                rows = conn.execute(
                    "SELECT paper_id, paper_data, created_at FROM kb_papers "
                    "WHERE user_id=? AND scope='kb' AND (paper_id LIKE ? OR paper_data LIKE ?) "
                    "ORDER BY created_at DESC LIMIT ?",
                    (user_id, like, like, per_type_limit),
                ).fetchall()
                for row in rows:
                    try:
                        data = json.loads(row["paper_data"] or "{}")
                    except (TypeError, json.JSONDecodeError):
                        data = {}
                    title = _paper_title(data, row["paper_id"])
                    authors = data.get("authors") or []
                    author_text = ", ".join(str(a) for a in authors[:3]) if isinstance(authors, list) else str(authors)
                    searchable = " ".join(
                        str(v) for v in (
                            row["paper_id"],
                            data.get("abstract", ""),
                            data.get("🛎️文章简介", ""),
                            author_text,
                        )
                    )
                    results.append({
                        "type": "paper",
                        "id": row["paper_id"],
                        "title": title,
                        "subtitle": f"知识库论文 · {row['paper_id']}",
                        "route": f"/papers/{row['paper_id']}",
                        "updated_at": row["created_at"],
                        "score": _score(title, searchable, q),
                    })

            if _table_exists(conn, "kb_notes"):
                rows = conn.execute(
                    "SELECT id, paper_id, title, content, type, updated_at FROM kb_notes "
                    "WHERE user_id=? AND scope='kb' AND (title LIKE ? OR content LIKE ?) "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (user_id, like, like, per_type_limit),
                ).fetchall()
                for row in rows:
                    title = row["title"] or "未命名笔记"
                    results.append({
                        "type": "note",
                        "id": str(row["id"]),
                        "title": title,
                        "subtitle": f"笔记 · {row['paper_id']}",
                        "route": f"/notes/{row['id']}",
                        "updated_at": row["updated_at"],
                        "score": _score(title, row["content"] or "", q),
                    })

            if _table_exists(conn, "kb_compare_results"):
                rows = conn.execute(
                    "SELECT id, title, markdown, updated_at FROM kb_compare_results "
                    "WHERE user_id=? AND (title LIKE ? OR markdown LIKE ?) "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (user_id, like, like, per_type_limit),
                ).fetchall()
                for row in rows:
                    title = row["title"] or "未命名对比"
                    results.append({
                        "type": "compare",
                        "id": str(row["id"]),
                        "title": title,
                        "subtitle": "论文对比报告",
                        "route": f"/?tool=compare-library&result={row['id']}",
                        "updated_at": row["updated_at"],
                        "score": _score(title, row["markdown"] or "", q),
                    })

            if _table_exists(conn, "research_sessions"):
                rows = conn.execute(
                    "SELECT id, question, status, updated_at FROM research_sessions "
                    "WHERE user_id=? AND question LIKE ? ORDER BY updated_at DESC LIMIT ?",
                    (user_id, like, per_type_limit),
                ).fetchall()
                for row in rows:
                    title = row["question"] or "未命名研究"
                    results.append({
                        "type": "research",
                        "id": str(row["id"]),
                        "title": title,
                        "subtitle": f"深度研究 · {row['status']}",
                        "route": f"/?tool=research-library&session={row['id']}",
                        "updated_at": row["updated_at"],
                        "score": _score(title, title, q),
                    })

            if _table_exists(conn, "research_projects"):
                rows = conn.execute(
                    "SELECT id, name, objective, description, updated_at FROM research_projects "
                    "WHERE user_id=? AND status!='deleted' "
                    "AND (name LIKE ? OR objective LIKE ? OR description LIKE ?) "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (user_id, like, like, like, per_type_limit),
                ).fetchall()
                for row in rows:
                    title = row["name"] or "未命名课题"
                    searchable = " ".join((row["objective"] or "", row["description"] or ""))
                    results.append({
                        "type": "project",
                        "id": str(row["id"]),
                        "title": title,
                        "subtitle": "课题空间",
                        "route": f"/projects/{row['id']}",
                        "updated_at": row["updated_at"],
                        "score": _score(title, searchable, q),
                    })
        finally:
            conn.close()

    if os.path.isfile(_USER_PAPERS_DB_PATH):
        conn = _connect(_USER_PAPERS_DB_PATH)
        try:
            if _table_exists(conn, "user_uploaded_papers"):
                rows = conn.execute(
                    "SELECT paper_id, title, abstract, institution, updated_at "
                    "FROM user_uploaded_papers WHERE user_id=? "
                    "AND (paper_id LIKE ? OR title LIKE ? OR abstract LIKE ? OR institution LIKE ?) "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (user_id, like, like, like, like, per_type_limit),
                ).fetchall()
                for row in rows:
                    title = row["title"] or row["paper_id"]
                    searchable = " ".join((row["paper_id"], row["abstract"] or "", row["institution"] or ""))
                    results.append({
                        "type": "user_paper",
                        "id": row["paper_id"],
                        "title": title,
                        "subtitle": f"我的论文 · {row['institution'] or '未标注机构'}",
                        "route": f"/?tab=mypapers&paper={row['paper_id']}",
                        "updated_at": row["updated_at"],
                        "score": _score(title, searchable, q),
                    })
        finally:
            conn.close()

    results = [item for item in results if item["score"] > 0]
    results.sort(key=lambda item: (item["score"], item.get("updated_at") or ""), reverse=True)
    total = len(results)
    return {"query": q, "results": results[:limit], "total": total}
