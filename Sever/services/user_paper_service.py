"""
User-uploaded papers service.

Manages papers that users manually import (PDF upload, arXiv import, manual entry).
These papers are completely independent of the daily arXiv pipeline.

Database: Sever/database/user_papers.db
Table:    user_uploaded_papers

Internal paper_id format: "up_<uuid4>" — never conflicts with arXiv IDs.
PDF files are stored under: data/kb_files/user_papers/{user_id}/{paper_id}/paper.pdf
"""

import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "user_papers.db")
_KB_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")
_KB_FILES_DIR = os.path.join(_BASE_DIR, "data", "kb_files")
_USER_PAPERS_DIR = os.path.join(_KB_FILES_DIR, "user_papers")

_MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
_MY_PAPERS_SCOPE = "mypapers"


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _connect_kb() -> sqlite3.Connection:
    """Connect to the shared KB database (paper_analysis.db) for folder access."""
    os.makedirs(os.path.dirname(_KB_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_KB_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_paper_id() -> str:
    return f"up_{uuid.uuid4().hex}"


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("authors", "tags"):
        if d.get(f"{field}_json"):
            try:
                d[field] = json.loads(d[f"{field}_json"])
            except Exception:
                d[field] = []
        else:
            d[field] = []
    return d


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_uploaded_papers (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id        TEXT    NOT NULL UNIQUE,
                user_id         INTEGER NOT NULL,
                source_type     TEXT    NOT NULL DEFAULT 'manual',
                source_ref      TEXT    NOT NULL DEFAULT '',
                title           TEXT    NOT NULL DEFAULT '',
                authors_json    TEXT    NOT NULL DEFAULT '[]',
                abstract        TEXT    NOT NULL DEFAULT '',
                institution     TEXT    NOT NULL DEFAULT '',
                year            INTEGER,
                pdf_path        TEXT,
                external_url    TEXT    NOT NULL DEFAULT '',
                summary_json    TEXT,
                paper_assets_json TEXT,
                process_status  TEXT    NOT NULL DEFAULT 'none',
                process_step    TEXT    NOT NULL DEFAULT '',
                process_error   TEXT    NOT NULL DEFAULT '',
                process_started_at  TEXT,
                process_finished_at TEXT,
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_uup_user_id
                ON user_uploaded_papers(user_id);

            CREATE INDEX IF NOT EXISTS idx_uup_source_type
                ON user_uploaded_papers(user_id, source_type);
            """
        )
        # Migrate existing tables that may lack the new columns
        for col, definition in [
            ("process_status",      "TEXT NOT NULL DEFAULT 'none'"),
            ("process_step",        "TEXT NOT NULL DEFAULT ''"),
            ("process_error",       "TEXT NOT NULL DEFAULT ''"),
            ("process_started_at",  "TEXT"),
            ("process_finished_at", "TEXT"),
            ("folder_id",           "INTEGER DEFAULT NULL"),
            ("translate_status",    "TEXT NOT NULL DEFAULT 'none'"),
            ("translate_error",     "TEXT NOT NULL DEFAULT ''"),
            ("translate_started_at", "TEXT"),
            ("translate_finished_at", "TEXT"),
            ("translate_progress", "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                conn.execute(
                    f"ALTER TABLE user_uploaded_papers ADD COLUMN {col} {definition}"
                )
            except Exception:
                pass  # Column already exists
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def _pdf_dir(user_id: int, paper_id: str) -> str:
    return os.path.join(_USER_PAPERS_DIR, str(user_id), paper_id)


def _pdf_rel_path(user_id: int, paper_id: str, filename: str = "paper.pdf") -> str:
    """Relative path stored in DB (relative to _KB_FILES_DIR)."""
    return os.path.join("user_papers", str(user_id), paper_id, filename)


def create_paper(
    user_id: int,
    *,
    source_type: str,
    source_ref: str = "",
    title: str = "",
    authors: list[str] | None = None,
    abstract: str = "",
    institution: str = "",
    year: int | None = None,
    external_url: str = "",
    pdf_bytes: bytes | None = None,
    pdf_filename: str = "paper.pdf",
) -> dict:
    """Create a new user-uploaded paper record.

    If pdf_bytes is provided the file is saved to disk and pdf_path is set.
    Returns the full paper dict.
    """
    paper_id = _new_paper_id()
    now = _now_iso()
    authors_json = json.dumps(authors or [], ensure_ascii=False)

    pdf_path: Optional[str] = None
    if pdf_bytes:
        pdf_dir = _pdf_dir(user_id, paper_id)
        os.makedirs(pdf_dir, exist_ok=True)
        safe_name = _safe_filename(pdf_filename)
        abs_path = os.path.join(pdf_dir, safe_name)
        with open(abs_path, "wb") as f:
            f.write(pdf_bytes)
        pdf_path = _pdf_rel_path(user_id, paper_id, safe_name)

    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO user_uploaded_papers
                (paper_id, user_id, source_type, source_ref, title,
                 authors_json, abstract, institution, year,
                 pdf_path, external_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper_id, user_id, source_type, source_ref, title,
                authors_json, abstract, institution, year,
                pdf_path, external_url, now, now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_uploaded_papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_papers(
    user_id: int,
    *,
    source_type: Optional[str] = None,
    search: Optional[str] = None,
    institution: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    conn = _connect()
    try:
        clauses = ["user_id = ?"]
        params: list[Any] = [user_id]

        if source_type:
            clauses.append("source_type = ?")
            params.append(source_type)

        if search:
            clauses.append("(title LIKE ? OR abstract LIKE ? OR institution LIKE ?)")
            q = f"%{search}%"
            params.extend([q, q, q])

        if institution:
            clauses.append("institution = ?")
            params.append(institution)

        where = " AND ".join(clauses)
        params.extend([limit, offset])
        rows = conn.execute(
            f"SELECT * FROM user_uploaded_papers WHERE {where} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def list_institutions(user_id: int) -> list[str]:
    """Return distinct non-empty institution names for a user, sorted alphabetically."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT institution FROM user_uploaded_papers "
            "WHERE user_id = ? AND institution != '' ORDER BY institution",
            (user_id,),
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def get_paper(user_id: int, paper_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM user_uploaded_papers WHERE paper_id = ? AND user_id = ?",
            (paper_id, user_id),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def update_paper(
    user_id: int,
    paper_id: str,
    *,
    title: Optional[str] = None,
    authors: Optional[list[str]] = None,
    abstract: Optional[str] = None,
    institution: Optional[str] = None,
    year: Optional[int] = None,
    external_url: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    pdf_filename: str = "paper.pdf",
) -> Optional[dict]:
    """Partial update for a user's paper. Returns updated dict or None if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM user_uploaded_papers WHERE paper_id = ? AND user_id = ?",
            (paper_id, user_id),
        ).fetchone()
        if not row:
            return None

        fields: dict[str, Any] = {}
        if title is not None:
            fields["title"] = title
        if authors is not None:
            fields["authors_json"] = json.dumps(authors, ensure_ascii=False)
        if abstract is not None:
            fields["abstract"] = abstract
        if institution is not None:
            fields["institution"] = institution
        if year is not None:
            fields["year"] = year
        if external_url is not None:
            fields["external_url"] = external_url

        if pdf_bytes is not None:
            pdf_dir = _pdf_dir(user_id, paper_id)
            os.makedirs(pdf_dir, exist_ok=True)
            safe_name = _safe_filename(pdf_filename)
            abs_path = os.path.join(pdf_dir, safe_name)
            with open(abs_path, "wb") as f:
                f.write(pdf_bytes)
            fields["pdf_path"] = _pdf_rel_path(user_id, paper_id, safe_name)

        if not fields:
            return _row_to_dict(row)

        fields["updated_at"] = _now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [paper_id, user_id]
        conn.execute(
            f"UPDATE user_uploaded_papers SET {set_clause} WHERE paper_id = ? AND user_id = ?",
            values,
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM user_uploaded_papers WHERE paper_id = ? AND user_id = ?",
            (paper_id, user_id),
        ).fetchone()
        return _row_to_dict(updated)
    finally:
        conn.close()


def delete_paper(user_id: int, paper_id: str) -> bool:
    """Delete paper record and any associated files on disk."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT pdf_path FROM user_uploaded_papers WHERE paper_id = ? AND user_id = ?",
            (paper_id, user_id),
        ).fetchone()
        if not row:
            return False

        # Remove directory with all uploaded files
        pdf_dir = _pdf_dir(user_id, paper_id)
        if os.path.isdir(pdf_dir):
            shutil.rmtree(pdf_dir, ignore_errors=True)

        conn.execute(
            "DELETE FROM user_uploaded_papers WHERE paper_id = ? AND user_id = ?",
            (paper_id, user_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def count_papers(user_id: int) -> int:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM user_uploaded_papers WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# arXiv metadata fetch helper
# ---------------------------------------------------------------------------

def fetch_arxiv_metadata(arxiv_id: str) -> dict:
    """Fetch paper metadata from arXiv API. Returns a dict with title, authors, abstract, year."""
    import re
    import urllib.request

    clean_id = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", arxiv_id.strip())
    clean_id = clean_id.rstrip("/").replace(".pdf", "")

    url = f"https://export.arxiv.org/api/query?id_list={clean_id}&max_results=1"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            xml = resp.read().decode("utf-8")
    except Exception as exc:
        raise ValueError(f"无法连接 arXiv API: {exc}") from exc

    # Parse with xml.etree (no extra deps)
    import xml.etree.ElementTree as ET
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(xml)
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise ValueError(f"arXiv 未找到 ID: {clean_id}")

    title_el = entry.find("atom:title", ns)
    summary_el = entry.find("atom:summary", ns)
    published_el = entry.find("atom:published", ns)
    authors_els = entry.findall("atom:author/atom:name", ns)
    affil_el = entry.find("atom:author/arxiv:affiliation", ns)

    title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
    abstract = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""
    year = None
    if published_el is not None and published_el.text:
        try:
            year = int(published_el.text[:4])
        except ValueError:
            pass
    authors = [a.text.strip() for a in authors_els if a.text]
    institution = (affil_el.text or "").strip() if affil_el is not None else ""

    return {
        "arxiv_id": clean_id,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "institution": institution,
        "year": year,
        "external_url": f"https://arxiv.org/abs/{clean_id}",
        "pdf_url": f"https://arxiv.org/pdf/{clean_id}",
    }


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

def _safe_filename(name: str) -> str:
    """Strip path separators and null bytes from an uploaded filename."""
    name = os.path.basename(name)
    name = name.replace("\x00", "").strip()
    return name or "upload.pdf"


# ---------------------------------------------------------------------------
# Pipeline processing status helpers
# ---------------------------------------------------------------------------

def set_translate_progress(paper_id: str, progress: int) -> None:
    """Update translation progress 0–100 (does not change status)."""
    p = max(0, min(100, int(progress)))
    conn = _connect()
    try:
        conn.execute(
            "UPDATE user_uploaded_papers SET translate_progress = ?, updated_at = ? WHERE paper_id = ?",
            (p, _now_iso(), paper_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_translate_status(
    paper_id: str,
    *,
    status: str,
    error: str = "",
    started: bool = False,
    finished: bool = False,
    progress: int | None = None,
) -> None:
    """Update translation job status for a user paper."""
    conn = _connect()
    try:
        fields: dict[str, Any] = {
            "translate_status": status,
            "translate_error": error,
            "updated_at": _now_iso(),
        }
        if started:
            fields["translate_started_at"] = _now_iso()
            fields["translate_progress"] = 0
        if finished:
            fields["translate_finished_at"] = _now_iso()
        if progress is not None:
            fields["translate_progress"] = max(0, min(100, int(progress)))
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [paper_id]
        conn.execute(
            f"UPDATE user_uploaded_papers SET {set_clause} WHERE paper_id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def set_process_status(
    paper_id: str,
    *,
    status: str,
    step: str = "",
    error: str = "",
    started: bool = False,
    finished: bool = False,
) -> None:
    """Update pipeline processing status for a user paper."""
    conn = _connect()
    try:
        fields: dict[str, Any] = {
            "process_status": status,
            "process_step": step,
            "process_error": error,
            "updated_at": _now_iso(),
        }
        if started:
            fields["process_started_at"] = _now_iso()
        if finished:
            fields["process_finished_at"] = _now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [paper_id]
        conn.execute(
            f"UPDATE user_uploaded_papers SET {set_clause} WHERE paper_id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def update_summary_and_assets(
    paper_id: str,
    *,
    summary_json: Optional[str] = None,
    paper_assets_json: Optional[str] = None,
    institution: Optional[str] = None,
    abstract: Optional[str] = None,
) -> None:
    """Persist pipeline results (summary_json, paper_assets_json) for a user paper."""
    conn = _connect()
    try:
        fields: dict[str, Any] = {"updated_at": _now_iso()}
        if summary_json is not None:
            fields["summary_json"] = summary_json
        if paper_assets_json is not None:
            fields["paper_assets_json"] = paper_assets_json
        if institution is not None:
            fields["institution"] = institution
        if abstract is not None:
            fields["abstract"] = abstract
        if len(fields) == 1:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [paper_id]
        conn.execute(
            f"UPDATE user_uploaded_papers SET {set_clause} WHERE paper_id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Folder-based tree (for "我的论文" sidebar)
# ---------------------------------------------------------------------------

def get_tree(user_id: int) -> dict:
    """
    Return the full "我的论文" tree for a user:
    {
      "folders": [ ... nested folders, each with "children" and "papers" ... ],
      "papers":  [ ... root-level papers (no folder) ... ]
    }
    Folders are stored in kb_folders (scope='mypapers') in paper_analysis.db.
    Papers come from user_uploaded_papers in user_papers.db.
    """
    # Get folders from kb DB
    kb_conn = _connect_kb()
    try:
        folder_rows = kb_conn.execute(
            "SELECT * FROM kb_folders WHERE user_id = ? AND scope = ? ORDER BY created_at",
            (user_id, _MY_PAPERS_SCOPE),
        ).fetchall()
    finally:
        kb_conn.close()

    # Get papers from user DB
    conn = _connect()
    try:
        paper_rows = conn.execute(
            "SELECT * FROM user_uploaded_papers WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    # Build folder lookup
    folders_by_id: dict[int, dict] = {}
    for row in folder_rows:
        d = dict(row)
        d["children"] = []
        d["papers"] = []
        folders_by_id[d["id"]] = d

    # Attach papers to their folders (or collect root papers)
    root_papers: list[dict] = []
    for row in paper_rows:
        p = _row_to_dict(row)
        fid = p.get("folder_id")
        if fid and fid in folders_by_id:
            folders_by_id[fid]["papers"].append(p)
        else:
            root_papers.append(p)

    # Build nested tree from flat folder list
    root_folders: list[dict] = []
    for fid, folder in folders_by_id.items():
        pid = folder.get("parent_id")
        if pid and pid in folders_by_id:
            folders_by_id[pid]["children"].append(folder)
        else:
            root_folders.append(folder)

    return {"folders": root_folders, "papers": root_papers}


def move_papers(user_id: int, paper_ids: list[str], target_folder_id: int | None) -> int:
    """
    Batch-move user papers to a target folder (None = root).
    Validates that the target folder belongs to the user and has scope='mypapers'.
    Returns the number of updated rows.
    """
    if target_folder_id is not None:
        kb_conn = _connect_kb()
        try:
            owner = kb_conn.execute(
                "SELECT user_id, scope FROM kb_folders WHERE id = ?",
                (target_folder_id,),
            ).fetchone()
            if owner is None or owner["user_id"] != user_id or owner["scope"] != _MY_PAPERS_SCOPE:
                target_folder_id = None
        finally:
            kb_conn.close()

    if not paper_ids:
        return 0

    conn = _connect()
    try:
        placeholders = ",".join("?" for _ in paper_ids)
        cur = conn.execute(
            f"UPDATE user_uploaded_papers SET folder_id = ?, updated_at = ? "
            f"WHERE user_id = ? AND paper_id IN ({placeholders})",
            [target_folder_id, _now_iso(), user_id, *paper_ids],
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module init
# ---------------------------------------------------------------------------

init_db()
