"""Search published analyses alongside the current user's research assets."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from typing import Any
from urllib.parse import quote


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
    terms = _terms(query_l)
    if terms and all(term in title_l for term in terms):
        return 70
    if terms and all(term in text_l for term in terms):
        return 30
    return 0


def _normalize_query(query: str) -> str:
    value = " ".join(unicodedata.normalize("NFKC", query).split())
    match = re.fullmatch(
        r"(?:(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf|html)/)|arxiv\s*:\s*)?"
        r"(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?/?(?:[?#].*)?", value, re.I,
    )
    return match.group(1) if match else value


def _terms(query: str) -> list[str]:
    if re.fullmatch(r"\d{4}\.\d{4,5}", query):
        return [query]
    return list(dict.fromkeys(re.findall(r"[^\W_]+", query.casefold())))[:24]


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _matches_sql(columns: list[str], query: str) -> tuple[str, list[str]]:
    clauses = []
    values = []
    for term in _terms(query):
        clauses.append("(" + " OR ".join(f"{column} LIKE ? ESCAPE '\\'" for column in columns) + ")")
        values.extend([_like(term)] * len(columns))
    return " AND ".join(clauses) or "0", values


def _has_text(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_text(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_text(item) for item in value)
    return False


def _visible_paper_ids(conn: sqlite3.Connection, user_id: int, date: str) -> set[str]:
    """Mirror publication guards using one connection and no pipeline input files."""
    rows = conn.execute(
        """SELECT p.paper_arxiv_id, s.summary_raw, s.summary_limit, a.blocks_json
           FROM pipeline_selected_papers p
           LEFT JOIN pipeline_summaries s ON s.user_id=p.user_id AND s.date_str=p.date_str
             AND s.paper_arxiv_id=p.paper_arxiv_id
           LEFT JOIN pipeline_paper_assets a ON a.user_id=p.user_id AND a.date_str=p.date_str
             AND a.paper_arxiv_id=p.paper_arxiv_id
           WHERE p.user_id=? AND p.date_str=? AND p.is_final_selected=1""", (user_id, date),
    )
    selected, ready = set(), set()
    for row in rows:
        paper_id = row["paper_arxiv_id"]
        selected.add(paper_id)
        if not (row["summary_raw"] or "").strip() or not (row["summary_limit"] or "").strip():
            continue
        try:
            blocks = json.loads(row["blocks_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if _has_text(blocks):
            ready.add(paper_id)
    # User-owned analysis is accessible independently of the public batch.
    if user_id != 0:
        return ready
    if _table_exists(conn, "pipeline_digest_publications"):
        publication = conn.execute(
            "SELECT paper_ids_json FROM pipeline_digest_publications WHERE user_id=0 AND date_str=?", (date,),
        ).fetchone()
        if publication is not None:
            return ready & set(json.loads(publication["paper_ids_json"]))
    return ready if selected == ready else set()


def _search_analyses(conn: sqlite3.Connection, user_id: int | None, q: str, limit: int, scope: str) -> list[dict]:
    required = ("pipeline_selected_papers", "pipeline_summaries", "pipeline_paper_assets",
                "pipeline_paper_info", "pipeline_arxiv_list")
    if not all(_table_exists(conn, table) for table in required):
        return []
    owned = {}
    if user_id is not None and _table_exists(conn, "kb_papers"):
        owned = {row["paper_id"]: row["created_at"] for row in conn.execute(
            "SELECT paper_id, created_at FROM kb_papers WHERE user_id=? AND scope='kb'", (user_id,),
        )}
    where, params = _matches_sql(
        ["p.paper_arxiv_id", "m.title", "m.authors_json", "m.abstract_text", "i.title", "a.title", "i.abstract", "i.institution",
         "s.headline", "s.summary_raw", "s.summary_limit"], q,
    )
    rows = conn.execute(
        f"""SELECT p.user_id, p.date_str, p.paper_arxiv_id, p.updated_at,
                   COALESCE(NULLIF(m.title, ''), NULLIF(i.title, ''), NULLIF(a.title, '')) AS title,
                   m.authors_json, m.abstract_text AS source_abstract, i.institution, i.abstract,
                   s.headline, s.summary_raw, s.summary_limit
            FROM pipeline_selected_papers p
            JOIN pipeline_summaries s ON s.user_id=p.user_id AND s.date_str=p.date_str
              AND s.paper_arxiv_id=p.paper_arxiv_id
            LEFT JOIN pipeline_arxiv_list m ON m.date_str=p.date_str AND m.paper_arxiv_id=p.paper_arxiv_id
            LEFT JOIN pipeline_paper_info i ON i.user_id=p.user_id AND i.date_str=p.date_str
              AND i.paper_arxiv_id=p.paper_arxiv_id
            LEFT JOIN pipeline_paper_assets a ON a.user_id=p.user_id AND a.date_str=p.date_str
              AND a.paper_arxiv_id=p.paper_arxiv_id
            WHERE p.user_id IN (0, ?) AND p.is_final_selected=1 AND ({where})
            ORDER BY CASE WHEN p.paper_arxiv_id=? THEN 0
                          WHEN lower(m.title)=lower(?) OR lower(i.title)=lower(?) THEN 1
                          WHEN m.title LIKE ? ESCAPE '\\' OR i.title LIKE ? ESCAPE '\\' THEN 2
                          ELSE 3 END, p.date_str DESC, p.user_id DESC""",
        [user_id or 0, *params, q, q, q, _like(q), _like(q)],
    )
    visible = {}
    results = []
    seen = set()
    for row in rows:
        paper_id = row["paper_arxiv_id"]
        if paper_id in seen:
            continue
        collected = paper_id in owned
        if (scope == "mine" and not collected) or (scope == "uncollected" and collected):
            continue
        key = (row["user_id"], row["date_str"])
        if key not in visible:
            visible[key] = _visible_paper_ids(conn, *key)
        if paper_id not in visible[key]:
            continue
        try:
            authors = json.loads(row["authors_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            authors = []
        if not isinstance(authors, list):
            authors = []
        author_text = ", ".join(str(a) for a in authors)
        title = row["title"]
        if not title:
            text = f"{row['summary_limit'] or ''}\n{row['summary_raw'] or ''}"
            heading = re.search(r"(?m)^\s*(?:📖\s*)?(?:标题|title)\s*[:：]\s*(.+)$", text, re.I)
            if heading is None:
                heading = re.search(r"(?m)^\s*笔记标题\s*[:：]\s*(.+)$", text)
            title = heading.group(1).strip() if heading else paper_id
        searchable = " ".join(str(v or "") for v in (
            paper_id, title, row["institution"], row["abstract"], row["source_abstract"], row["headline"],
            row["summary_raw"], row["summary_limit"], author_text,
        ))
        results.append({
            "type": "paper", "id": paper_id, "title": title,
            "subtitle": " · ".join(v for v in (f"arXiv:{paper_id}", author_text, row["date_str"]) if v),
            "route": f"/papers/{quote(paper_id, safe='')}",
            "updated_at": row["updated_at"],
            "score": 180 if q == paper_id else _score(title, searchable, q),
            "collection_status": "collected" if collected else "uncollected",
        })
        seen.add(paper_id)
        if len(results) >= limit:
            break
    return results


def _paper_title(data: dict[str, Any], paper_id: str) -> str:
    return str(
        data.get("short_title")
        or data.get("📖标题")
        or data.get("title")
        or paper_id
    )


def _search_owned_assets(user_id: int, query: str, limit: int = 30) -> dict:
    """Return ranked results from all durable research-asset stores."""
    q = query.strip()
    if not q:
        return {"query": "", "results": [], "total": 0}

    per_type_limit = max(8, min(limit, 51))
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
                    author_text = ", ".join(str(a) for a in authors) if isinstance(authors, list) else str(authors)
                    searchable = " ".join(
                        str(v) for v in (
                            row["paper_id"],
                            data.get("📖标题", ""),
                            data.get("title", ""),
                            data.get("abstract", ""),
                            data.get("🛎️文章简介", ""),
                            author_text,
                        )
                    )
                    results.append({
                        "type": "paper",
                        "id": row["paper_id"],
                        "title": title,
                        "subtitle": " · ".join(v for v in (f"arXiv:{row['paper_id']}", str(data.get("📖标题") or data.get("title") or ""), author_text) if v),
                        "route": f"/papers/{row['paper_id']}",
                        "updated_at": row["created_at"],
                        "score": 180 if row["paper_id"] == q else _score(title, searchable, q),
                        "collection_status": "collected",
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
                columns = {row["name"] for row in conn.execute("PRAGMA table_info(user_uploaded_papers)")}
                authors_column = "authors_json" if "authors_json" in columns else "'[]'"
                source_column = "source_ref" if "source_ref" in columns else "''"
                where, params = _matches_sql(
                    ["paper_id", "title", "abstract", "institution", authors_column, source_column], q,
                )
                rows = conn.execute(
                    f"SELECT paper_id, title, abstract, institution, updated_at, {authors_column} AS authors_json, {source_column} AS source_ref "
                    "FROM user_uploaded_papers WHERE user_id=? "
                    f"AND ({where}) "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (user_id, *params, per_type_limit),
                ).fetchall()
                for row in rows:
                    title = row["title"] or row["paper_id"]
                    searchable = " ".join((row["paper_id"], row["abstract"] or "", row["institution"] or "", row["authors_json"] or "", row["source_ref"] or ""))
                    results.append({
                        "type": "user_paper",
                        "id": row["paper_id"],
                        "title": title,
                        "subtitle": f"我的论文 · {row['institution'] or '未标注机构'}",
                        "route": f"/?tab=mypapers&paper={row['paper_id']}",
                        "updated_at": row["updated_at"],
                        "score": _score(title, searchable, q),
                        "collection_status": "uploaded",
                    })
        finally:
            conn.close()

    results = [item for item in results if item["score"] > 0]
    results.sort(key=lambda item: (item["score"], item.get("updated_at") or ""), reverse=True)
    total = len(results)
    return {"query": q, "results": results[:limit], "total": total}


def search_assets(user_id: int | None, query: str, limit: int = 30, scope: str = "all") -> dict:
    """Search every accessible analysis plus personal assets, deduplicated by ID."""
    q = _normalize_query(query.strip())
    if not q or not _terms(q):
        return {"query": query.strip(), "results": [], "total": 0}
    limit = max(1, min(limit, 50))
    if scope not in {"all", "mine", "uncollected"}:
        raise ValueError("Unknown search scope")
    results = []
    if user_id is not None and scope != "uncollected":
        results.extend(_search_owned_assets(user_id, q, 6 * (limit + 1))["results"])
    if os.path.isfile(_PAPER_DB_PATH):
        conn = _connect(_PAPER_DB_PATH)
        try:
            results.extend(_search_analyses(conn, user_id, q, limit + 1, scope))
        finally:
            conn.close()
    unique = {}
    for item in results:
        key = (item["type"], item["id"])
        if key not in unique or item["score"] > unique[key]["score"]:
            unique[key] = item
    results = sorted(unique.values(), key=lambda item: (item["score"], item.get("updated_at") or ""), reverse=True)
    return {"query": query.strip(), "results": results[:limit], "total": len(results), "has_more": len(results) > limit}
