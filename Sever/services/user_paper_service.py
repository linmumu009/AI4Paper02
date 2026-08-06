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


class ArxivMetadataError(ValueError):
    """A safe, user-facing arXiv lookup error with an HTTP status hint."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


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


def build_manual_source_ref(
    *,
    title: str,
    authors: list[str] | None,
    abstract: str,
    institution: str,
    year: int | None,
    external_url: str,
) -> str:
    import hashlib

    def normalize(value: Any) -> str:
        return " ".join(str(value or "").split()).casefold()

    payload = {
        "title": normalize(title),
        "authors": [normalize(author) for author in (authors or [])],
        "abstract": normalize(abstract),
        "institution": normalize(institution),
        "year": int(year) if year is not None else None,
        "external_url": normalize(external_url),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"manual-sha256:{hashlib.sha256(encoded).hexdigest()}"


def build_pdf_source_ref(pdf_bytes: bytes) -> str:
    import hashlib

    return f"pdf-sha256:{hashlib.sha256(pdf_bytes).hexdigest()}"


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
    deduplicate_source: bool = False,
) -> dict:
    """Create a new user-uploaded paper record.

    If pdf_bytes is provided the file is saved to disk and pdf_path is set.
    Returns the full paper dict.
    """
    paper_id = _new_paper_id()
    now = _now_iso()
    authors_json = json.dumps(authors or [], ensure_ascii=False)

    pdf_path: Optional[str] = None
    pdf_dir: Optional[str] = None
    abs_path: Optional[str] = None
    conn = None
    try:
        conn = _connect()
        if deduplicate_source and source_ref:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM user_uploaded_papers "
                "WHERE user_id = ? AND source_type = ? AND source_ref = ? "
                "ORDER BY id LIMIT 1",
                (user_id, source_type, source_ref),
            ).fetchone()
            if existing is not None:
                conn.rollback()
                paper = _row_to_dict(existing)
                paper["_created"] = False
                return paper

        if pdf_bytes:
            pdf_dir = _pdf_dir(user_id, paper_id)
            os.makedirs(pdf_dir, exist_ok=True)
            safe_name = _safe_filename(pdf_filename)
            abs_path = os.path.join(pdf_dir, safe_name)
            with open(abs_path, "wb") as f:
                f.write(pdf_bytes)
            pdf_path = _pdf_rel_path(user_id, paper_id, safe_name)

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
        row = conn.execute(
            "SELECT * FROM user_uploaded_papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("created paper record could not be reloaded")
        conn.commit()
        paper = _row_to_dict(row)
        if deduplicate_source:
            paper["_created"] = True
        return paper
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        if abs_path:
            try:
                if os.path.isfile(abs_path):
                    os.remove(abs_path)
            except OSError:
                pass
        if pdf_dir:
            try:
                os.rmdir(pdf_dir)
            except OSError:
                pass
        raise
    finally:
        if conn is not None:
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


def get_paper_by_source(
    user_id: int,
    source_type: str,
    source_ref: str,
) -> Optional[dict]:
    if not source_ref:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM user_uploaded_papers "
            "WHERE user_id = ? AND source_type = ? AND source_ref = ? "
            "ORDER BY id LIMIT 1",
            (user_id, source_type, source_ref),
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
    pending_path: Optional[str] = None
    new_abs_path: Optional[str] = None
    old_abs_path: Optional[str] = None
    new_materialized = False
    committed = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM user_uploaded_papers WHERE paper_id = ? AND user_id = ?",
            (paper_id, user_id),
        ).fetchone()
        if not row:
            conn.rollback()
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
            import hashlib
            import tempfile

            pdf_dir = _pdf_dir(user_id, paper_id)
            os.makedirs(pdf_dir, exist_ok=True)
            safe_name = _safe_filename(pdf_filename)
            stem, extension = os.path.splitext(safe_name)
            if extension.lower() != ".pdf":
                extension = ".pdf"
            digest = hashlib.sha256(pdf_bytes).hexdigest()[:16]
            versioned_name = f"{stem or 'paper'}.{digest}{extension}"
            new_abs_path = os.path.join(pdf_dir, versioned_name)

            pending = tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".pending-pdf-",
                suffix=".tmp",
                dir=pdf_dir,
                delete=False,
            )
            pending_path = pending.name
            try:
                pending.write(pdf_bytes)
                pending.flush()
                os.fsync(pending.fileno())
            finally:
                pending.close()
            os.replace(pending_path, new_abs_path)
            new_materialized = True
            pending_path = None

            stored_old_path = row["pdf_path"] if "pdf_path" in row.keys() else None
            if stored_old_path:
                candidate = os.path.realpath(os.path.join(_KB_FILES_DIR, stored_old_path))
                root = os.path.realpath(_USER_PAPERS_DIR)
                try:
                    if os.path.commonpath((root, candidate)) == root:
                        old_abs_path = candidate
                except ValueError:
                    old_abs_path = None
            fields["pdf_path"] = _pdf_rel_path(user_id, paper_id, versioned_name)

        if not fields:
            conn.rollback()
            return _row_to_dict(row)

        fields["updated_at"] = _now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [paper_id, user_id]
        conn.execute(
            f"UPDATE user_uploaded_papers SET {set_clause} WHERE paper_id = ? AND user_id = ?",
            values,
        )
        updated = conn.execute(
            "SELECT * FROM user_uploaded_papers WHERE paper_id = ? AND user_id = ?",
            (paper_id, user_id),
        ).fetchone()
        if updated is None:
            raise RuntimeError("updated paper record could not be reloaded")
        conn.commit()
        committed = True
        if (
            old_abs_path
            and new_abs_path
            and os.path.normcase(old_abs_path) != os.path.normcase(new_abs_path)
        ):
            try:
                if os.path.isfile(old_abs_path):
                    os.remove(old_abs_path)
            except OSError:
                pass
        return _row_to_dict(updated)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        if new_abs_path and new_materialized and not committed:
            if not old_abs_path or os.path.normcase(old_abs_path) != os.path.normcase(new_abs_path):
                try:
                    if os.path.isfile(new_abs_path):
                        os.remove(new_abs_path)
                except OSError:
                    pass
        raise
    finally:
        if pending_path:
            try:
                if os.path.isfile(pending_path):
                    os.remove(pending_path)
            except OSError:
                pass
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

def normalize_arxiv_id(arxiv_id: str) -> str:
    import re

    clean_id = str(arxiv_id or "").strip()
    clean_id = re.sub(r"^arxiv:\s*", "", clean_id, flags=re.IGNORECASE)
    clean_id = re.sub(
        r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/",
        "",
        clean_id,
        flags=re.IGNORECASE,
    )
    clean_id = clean_id.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if clean_id.lower().endswith(".pdf"):
        clean_id = clean_id[:-4]
    clean_id = clean_id.strip().lower()
    if not re.fullmatch(
        r"(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.\-]*/\d{7})(?:v\d+)?",
        clean_id,
        flags=re.IGNORECASE,
    ):
        raise ArxivMetadataError("arXiv ID 格式不正确，请输入论文 ID 或 arXiv 链接")
    return clean_id


def fetch_arxiv_metadata(arxiv_id: str) -> dict:
    """Fetch paper metadata from arXiv API. Returns a dict with title, authors, abstract, year."""
    import time
    import urllib.error
    import urllib.request

    from config.config import ARXIV_USER_AGENT
    from services.arxiv_rate_limit import (
        compute_429_wait,
        parse_retry_after,
        wait_before_request,
    )

    clean_id = normalize_arxiv_id(arxiv_id)

    url = f"https://export.arxiv.org/api/query?id_list={clean_id}&max_results=1"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": ARXIV_USER_AGENT},
    )

    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            wait_before_request()
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml = resp.read().decode("utf-8")
            break  # success
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                if attempt < max_attempts - 1:
                    retry_after = parse_retry_after(exc.headers.get("Retry-After"))
                    wait = compute_429_wait(attempt, retry_after)
                    time.sleep(wait)
                    continue
                raise ArxivMetadataError(
                    "arXiv 请求过于频繁，请稍等片刻后重试，或改用 PDF 上传方式导入。",
                    status_code=503,
                ) from exc
            raise ArxivMetadataError(
                f"arXiv 服务暂时不可用（HTTP {exc.code}），请稍后重试",
                status_code=502,
            ) from exc
        except Exception as exc:
            raise ArxivMetadataError(
                "arXiv 服务暂时不可用，请稍后重试",
                status_code=502,
            ) from exc

    # Parse with xml.etree (no extra deps)
    import xml.etree.ElementTree as ET
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(xml)
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise ArxivMetadataError(f"arXiv 未找到 ID: {clean_id}", status_code=404)

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
# Task-center helpers (read-only aggregation)
# ---------------------------------------------------------------------------

def list_papers_with_active_tasks(
    user_id: int,
    include_completed: bool = False,
) -> list[dict]:
    """Return user_uploaded_papers rows that have a non-trivial process or translate status.

    By default only pending/running/failed rows are returned.
    Pass include_completed=True to also include completed statuses.
    """
    if include_completed:
        proc_clause = "process_status != 'none'"
        trans_clause = "translate_status != 'none'"
    else:
        proc_clause = "process_status IN ('pending', 'processing', 'failed')"
        trans_clause = "translate_status IN ('processing', 'failed', 'cancelled')"

    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            SELECT * FROM user_uploaded_papers
            WHERE user_id = ? AND ({proc_clause} OR {trans_clause})
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (user_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module init
# ---------------------------------------------------------------------------

init_db()
