"""
Pipeline DB service layer.

Stores per-user, per-date pipeline outputs in ``paper_analysis.db``.
Replaces the file-based intermediate outputs (llm_select_theme JSON,
paper_summary .md files, paper_assets .jsonl, etc.) with DB tables that are
keyed by (user_id, date_str, paper_arxiv_id).

user_id=0 is reserved for the default/system pipeline run.

Tables
------
    pipeline_runs           -- tracks each pipeline execution
    pipeline_theme_scores   -- replaces llm_select_theme/<date>.json
    pipeline_selected_papers-- replaces paper_theme_filter+instutions_filter+selectpaper outputs
    pipeline_paper_info     -- replaces pdf_info/<date>.json
    pipeline_summaries      -- replaces paper_summary + summary_limit .md files
    pipeline_paper_assets   -- replaces paper_assets/<date>.jsonl
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all pipeline_* tables if they do not exist."""
    conn = _connect()
    try:
        conn.executescript("""
            -- ----------------------------------------------------------------
            -- pipeline_runs: one row per (user, date, pipeline) execution
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_type     TEXT    NOT NULL DEFAULT 'user',   -- 'shared' | 'user'
                user_id      INTEGER NOT NULL DEFAULT 0,        -- 0 = default/system
                date_str     TEXT    NOT NULL,
                pipeline     TEXT    NOT NULL DEFAULT 'daily',
                status       TEXT    NOT NULL DEFAULT 'pending',-- pending/running/completed/failed
                config_json  TEXT    NOT NULL DEFAULT '{}',
                started_at   TEXT,
                finished_at  TEXT,
                error        TEXT,
                created_at   TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pipeline_runs_date
                ON pipeline_runs(date_str);
            CREATE INDEX IF NOT EXISTS idx_pipeline_runs_user_date
                ON pipeline_runs(user_id, date_str);

            -- ----------------------------------------------------------------
            -- pipeline_theme_scores: LLM relevance scores for each paper
            -- Replaces: data/llm_select_theme/<date>.json
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_theme_scores (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL DEFAULT 0,
                date_str       TEXT    NOT NULL,
                paper_arxiv_id TEXT    NOT NULL,
                score          REAL    NOT NULL DEFAULT 0.0,
                created_at     TEXT    NOT NULL,
                UNIQUE(user_id, date_str, paper_arxiv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_pts_user_date
                ON pipeline_theme_scores(user_id, date_str);

            -- ----------------------------------------------------------------
            -- pipeline_selected_papers: tracks which papers made it through
            -- each filter stage for a given user + date.
            -- Replaces: paper_theme_filter JSON + instutions_filter JSON + selectpaper manifest
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_selected_papers (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id               INTEGER NOT NULL DEFAULT 0,
                date_str              TEXT    NOT NULL,
                paper_arxiv_id        TEXT    NOT NULL,
                theme_score           REAL,
                passed_theme_filter   INTEGER NOT NULL DEFAULT 0,  -- 1=yes
                passed_institution_filter INTEGER NOT NULL DEFAULT 0,  -- 1=yes
                is_final_selected     INTEGER NOT NULL DEFAULT 0,  -- 1=final selection
                created_at            TEXT    NOT NULL,
                updated_at            TEXT    NOT NULL,
                UNIQUE(user_id, date_str, paper_arxiv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_psp_user_date
                ON pipeline_selected_papers(user_id, date_str);
            CREATE INDEX IF NOT EXISTS idx_psp_final
                ON pipeline_selected_papers(user_id, date_str, is_final_selected);

            -- ----------------------------------------------------------------
            -- pipeline_paper_info: LLM-extracted metadata per paper
            -- Replaces: data/pdf_info/<date>.json
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_paper_info (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           INTEGER NOT NULL DEFAULT 0,
                date_str          TEXT    NOT NULL,
                paper_arxiv_id    TEXT    NOT NULL,
                title             TEXT    NOT NULL DEFAULT '',
                institution       TEXT    NOT NULL DEFAULT '',
                is_large          INTEGER NOT NULL DEFAULT 0,
                institution_tier  INTEGER NOT NULL DEFAULT 0,
                abstract          TEXT    NOT NULL DEFAULT '',
                published         TEXT    NOT NULL DEFAULT '',
                source            TEXT    NOT NULL DEFAULT '',
                extra_json        TEXT    NOT NULL DEFAULT '{}',
                created_at        TEXT    NOT NULL,
                UNIQUE(user_id, date_str, paper_arxiv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_ppi_user_date
                ON pipeline_paper_info(user_id, date_str);

            -- ----------------------------------------------------------------
            -- pipeline_summaries: LLM-generated summaries (raw + compressed)
            -- Replaces: paper_summary/single/<date>/*.md
            --           summary_limit/single/<date>/*.md
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_summaries (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL DEFAULT 0,
                date_str       TEXT    NOT NULL,
                paper_arxiv_id TEXT    NOT NULL,
                summary_raw    TEXT    NOT NULL DEFAULT '',  -- paper_summary output
                summary_limit  TEXT    NOT NULL DEFAULT '',  -- summary_limit output
                headline       TEXT    NOT NULL DEFAULT '',  -- extracted headline
                created_at     TEXT    NOT NULL,
                updated_at     TEXT    NOT NULL,
                UNIQUE(user_id, date_str, paper_arxiv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_ps_user_date
                ON pipeline_summaries(user_id, date_str);

            -- ----------------------------------------------------------------
            -- pipeline_paper_assets: structured block analysis per paper
            -- Replaces: data/paper_assets/<date>.jsonl
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_paper_assets (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL DEFAULT 0,
                date_str       TEXT    NOT NULL,
                paper_arxiv_id TEXT    NOT NULL,
                title          TEXT    NOT NULL DEFAULT '',
                url            TEXT    NOT NULL DEFAULT '',
                year           INTEGER,
                blocks_json    TEXT    NOT NULL DEFAULT '[]',
                created_at     TEXT    NOT NULL,
                UNIQUE(user_id, date_str, paper_arxiv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_ppa_user_date
                ON pipeline_paper_assets(user_id, date_str);

            -- ----------------------------------------------------------------
            -- pipeline_date_notices: records why a date has 0 papers
            -- Used to show a helpful notice card on the frontend when
            -- the pipeline ran successfully but produced no results.
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_date_notices (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL DEFAULT 0,
                date_str     TEXT    NOT NULL,
                notice_type  TEXT    NOT NULL,   -- 'no_papers_weekend' | 'no_papers_empty' | 'no_matching_papers'
                message      TEXT    NOT NULL,
                created_at   TEXT    NOT NULL,
                UNIQUE(user_id, date_str)
            );
            CREATE INDEX IF NOT EXISTS idx_pdn_user_date
                ON pipeline_date_notices(user_id, date_str);

            -- ----------------------------------------------------------------
            -- pipeline_images: per-paper image filenames from select_image step
            -- Replaces: data/select_image/<date>/select_image_<date>.json lookup
            -- Shared across users (no user_id column)
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_images (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                date_str       TEXT    NOT NULL,
                paper_arxiv_id TEXT    NOT NULL,
                images_json    TEXT    NOT NULL DEFAULT '[]',
                created_at     TEXT    NOT NULL,
                UNIQUE(date_str, paper_arxiv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_pi_date ON pipeline_images(date_str);

            -- ----------------------------------------------------------------
            -- pipeline_arxiv_list: arxiv search results per date
            -- Replaces: data/arxivList/json/<date>.json
            --           data/arxivList/md/<date>.md
            -- Shared across users (no user_id column)
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_arxiv_list (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date_str        TEXT    NOT NULL,
                paper_arxiv_id  TEXT    NOT NULL,
                title           TEXT    NOT NULL DEFAULT '',
                abstract_text   TEXT    NOT NULL DEFAULT '',
                authors_json    TEXT    NOT NULL DEFAULT '[]',
                published_utc   TEXT    NOT NULL DEFAULT '',
                link            TEXT    NOT NULL DEFAULT '',
                categories_json TEXT    NOT NULL DEFAULT '[]',
                created_at      TEXT    NOT NULL,
                UNIQUE(date_str, paper_arxiv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_pal_date ON pipeline_arxiv_list(date_str);
        """)
        conn.commit()
    finally:
        conn.close()
    _migrate_pipeline_paper_info()
    _migrate_add_new_tables()


def _migrate_pipeline_paper_info() -> None:
    """Add institution_tier column to pipeline_paper_info if it does not exist."""
    conn = _connect()
    try:
        existing = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(pipeline_paper_info)"
            ).fetchall()
        }
        if "institution_tier" not in existing:
            conn.execute(
                "ALTER TABLE pipeline_paper_info ADD COLUMN institution_tier INTEGER NOT NULL DEFAULT 0"
            )
            conn.commit()
    finally:
        conn.close()


def _migrate_add_new_tables() -> None:
    """Create pipeline_images and pipeline_arxiv_list tables for existing installs."""
    conn = _connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS pipeline_images (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                date_str       TEXT    NOT NULL,
                paper_arxiv_id TEXT    NOT NULL,
                images_json    TEXT    NOT NULL DEFAULT '[]',
                created_at     TEXT    NOT NULL,
                UNIQUE(date_str, paper_arxiv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_pi_date ON pipeline_images(date_str);

            CREATE TABLE IF NOT EXISTS pipeline_arxiv_list (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date_str        TEXT    NOT NULL,
                paper_arxiv_id  TEXT    NOT NULL,
                title           TEXT    NOT NULL DEFAULT '',
                abstract_text   TEXT    NOT NULL DEFAULT '',
                authors_json    TEXT    NOT NULL DEFAULT '[]',
                published_utc   TEXT    NOT NULL DEFAULT '',
                link            TEXT    NOT NULL DEFAULT '',
                categories_json TEXT    NOT NULL DEFAULT '[]',
                created_at      TEXT    NOT NULL,
                UNIQUE(date_str, paper_arxiv_id)
            );
            CREATE INDEX IF NOT EXISTS idx_pal_date ON pipeline_arxiv_list(date_str);
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_runs CRUD
# ---------------------------------------------------------------------------

def create_run(
    run_type: str,
    user_id: int,
    date_str: str,
    pipeline: str = "daily",
    config: Optional[dict] = None,
) -> int:
    """Insert a new pipeline run record; return its id."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO pipeline_runs
                (run_type, user_id, date_str, pipeline, status, config_json, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (run_type, user_id, date_str, pipeline,
             json.dumps(config or {}, ensure_ascii=False), now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_run_status(
    run_id: int,
    status: str,
    error: Optional[str] = None,
) -> None:
    now = _now_iso()
    conn = _connect()
    try:
        if status == "running":
            conn.execute(
                "UPDATE pipeline_runs SET status=?, started_at=? WHERE id=?",
                (status, now, run_id),
            )
        else:
            conn.execute(
                "UPDATE pipeline_runs SET status=?, finished_at=?, error=? WHERE id=?",
                (status, now, error, run_id),
            )
        conn.commit()
    finally:
        conn.close()


def get_runs_for_date(date_str: str) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_runs WHERE date_str=? ORDER BY created_at DESC",
            (date_str,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_user_run_for_date(user_id: int, date_str: str) -> Optional[dict]:
    """Return the most-recent run for (user_id, date_str)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM pipeline_runs WHERE user_id=? AND date_str=? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, date_str),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_theme_scores CRUD
# ---------------------------------------------------------------------------

def upsert_theme_score(
    user_id: int,
    date_str: str,
    paper_arxiv_id: str,
    score: float,
) -> None:
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO pipeline_theme_scores
                (user_id, date_str, paper_arxiv_id, score, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                score=excluded.score,
                created_at=excluded.created_at
            """,
            (user_id, date_str, paper_arxiv_id, score, now),
        )
        conn.commit()
    finally:
        conn.close()


def bulk_upsert_theme_scores(
    user_id: int,
    date_str: str,
    scores: dict[str, float],
) -> None:
    """Upsert many scores at once. ``scores`` maps arxiv_id -> float."""
    now = _now_iso()
    conn = _connect()
    try:
        conn.executemany(
            """
            INSERT INTO pipeline_theme_scores
                (user_id, date_str, paper_arxiv_id, score, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                score=excluded.score,
                created_at=excluded.created_at
            """,
            [(user_id, date_str, arxiv_id, score, now)
             for arxiv_id, score in scores.items()],
        )
        conn.commit()
    finally:
        conn.close()


def get_theme_scores(user_id: int, date_str: str) -> dict[str, float]:
    """Return {arxiv_id: score} for the given user+date."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT paper_arxiv_id, score FROM pipeline_theme_scores "
            "WHERE user_id=? AND date_str=?",
            (user_id, date_str),
        ).fetchall()
        return {r["paper_arxiv_id"]: r["score"] for r in rows}
    finally:
        conn.close()


def has_theme_scores(user_id: int, date_str: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM pipeline_theme_scores WHERE user_id=? AND date_str=? LIMIT 1",
            (user_id, date_str),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_selected_papers CRUD
# ---------------------------------------------------------------------------

def upsert_selected_paper(
    user_id: int,
    date_str: str,
    paper_arxiv_id: str,
    *,
    theme_score: Optional[float] = None,
    passed_theme: Optional[bool] = None,
    passed_institution: Optional[bool] = None,
    is_final: Optional[bool] = None,
) -> None:
    now = _now_iso()
    conn = _connect()
    try:
        # Try insert first; if conflict, update only the fields that were provided.
        conn.execute(
            """
            INSERT INTO pipeline_selected_papers
                (user_id, date_str, paper_arxiv_id,
                 theme_score, passed_theme_filter, passed_institution_filter,
                 is_final_selected, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                theme_score             = COALESCE(excluded.theme_score, theme_score),
                passed_theme_filter     = COALESCE(excluded.passed_theme_filter, passed_theme_filter),
                passed_institution_filter = COALESCE(excluded.passed_institution_filter, passed_institution_filter),
                is_final_selected       = COALESCE(excluded.is_final_selected, is_final_selected),
                updated_at              = excluded.updated_at
            """,
            (
                user_id, date_str, paper_arxiv_id,
                theme_score,
                int(passed_theme) if passed_theme is not None else None,
                int(passed_institution) if passed_institution is not None else None,
                int(is_final) if is_final is not None else None,
                now, now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def bulk_upsert_selected_papers(
    user_id: int,
    date_str: str,
    papers: list[dict[str, Any]],
) -> None:
    """
    Bulk upsert. Each dict in ``papers`` may contain:
      paper_arxiv_id (required), theme_score, passed_theme_filter,
      passed_institution_filter, is_final_selected
    """
    now = _now_iso()
    conn = _connect()
    try:
        conn.executemany(
            """
            INSERT INTO pipeline_selected_papers
                (user_id, date_str, paper_arxiv_id,
                 theme_score, passed_theme_filter, passed_institution_filter,
                 is_final_selected, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                theme_score               = COALESCE(excluded.theme_score, theme_score),
                passed_theme_filter       = COALESCE(excluded.passed_theme_filter, passed_theme_filter),
                passed_institution_filter = COALESCE(excluded.passed_institution_filter, passed_institution_filter),
                is_final_selected         = COALESCE(excluded.is_final_selected, is_final_selected),
                updated_at                = excluded.updated_at
            """,
            [
                (
                    user_id, date_str, p["paper_arxiv_id"],
                    # theme_score may legitimately be None (unknown); keep as NULL
                    p.get("theme_score"),
                    # Integer flags: coerce None -> 0 so NOT NULL constraint is always satisfied.
                    # COALESCE in DO UPDATE still preserves the existing value when the
                    # caller intentionally passes 0 as a safe placeholder.
                    0 if p.get("passed_theme_filter") is None else int(p["passed_theme_filter"]),
                    0 if p.get("passed_institution_filter") is None else int(p["passed_institution_filter"]),
                    0 if p.get("is_final_selected") is None else int(p["is_final_selected"]),
                    now, now,
                )
                for p in papers
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_selected_papers(
    user_id: int,
    date_str: str,
    final_only: bool = True,
) -> list[dict]:
    """Return list of selected paper rows for user+date."""
    conn = _connect()
    try:
        query = (
            "SELECT * FROM pipeline_selected_papers WHERE user_id=? AND date_str=?"
        )
        params: list[Any] = [user_id, date_str]
        if final_only:
            query += " AND is_final_selected=1"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_final_arxiv_ids(user_id: int, date_str: str) -> list[str]:
    """Return arxiv_ids of finally selected papers for user+date."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT paper_arxiv_id FROM pipeline_selected_papers "
            "WHERE user_id=? AND date_str=? AND is_final_selected=1",
            (user_id, date_str),
        ).fetchall()
        return [r["paper_arxiv_id"] for r in rows]
    finally:
        conn.close()


def has_final_selections(user_id: int, date_str: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM pipeline_selected_papers "
            "WHERE user_id=? AND date_str=? AND is_final_selected=1 LIMIT 1",
            (user_id, date_str),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_paper_info CRUD
# ---------------------------------------------------------------------------

def upsert_paper_info(
    user_id: int,
    date_str: str,
    paper_arxiv_id: str,
    *,
    title: str = "",
    institution: str = "",
    is_large: bool = False,
    institution_tier: int = 0,
    abstract: str = "",
    published: str = "",
    source: str = "",
    extra: Optional[dict] = None,
) -> None:
    # Coerce any None values that callers may pass for text columns
    title = title or ""
    institution = institution or ""
    abstract = abstract or ""
    published = published or ""
    source = source or ""
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO pipeline_paper_info
                (user_id, date_str, paper_arxiv_id,
                 title, institution, is_large, institution_tier,
                 abstract, published, source, extra_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                title            = excluded.title,
                institution      = excluded.institution,
                is_large         = excluded.is_large,
                institution_tier = excluded.institution_tier,
                abstract         = excluded.abstract,
                published        = excluded.published,
                source           = excluded.source,
                extra_json       = excluded.extra_json,
                created_at       = excluded.created_at
            """,
            (
                user_id, date_str, paper_arxiv_id,
                title, institution, int(is_large), institution_tier,
                abstract, published, source,
                json.dumps(extra or {}, ensure_ascii=False), now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def bulk_upsert_paper_info(
    user_id: int,
    date_str: str,
    papers: list[dict[str, Any]],
) -> None:
    now = _now_iso()
    conn = _connect()
    try:
        conn.executemany(
            """
            INSERT INTO pipeline_paper_info
                (user_id, date_str, paper_arxiv_id,
                 title, institution, is_large, institution_tier,
                 abstract, published, source, extra_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                title            = excluded.title,
                institution      = excluded.institution,
                is_large         = excluded.is_large,
                institution_tier = excluded.institution_tier,
                abstract         = excluded.abstract,
                published        = excluded.published,
                source           = excluded.source,
                extra_json       = excluded.extra_json,
                created_at       = excluded.created_at
            """,
            [
                (
                    user_id, date_str, p["paper_arxiv_id"],
                    p.get("title") or "",
                    p.get("institution") or "",
                    int(bool(p.get("is_large", False))),
                    int(p.get("institution_tier") or 0),
                    p.get("abstract") or "",
                    p.get("published") or "",
                    p.get("source") or "",
                    json.dumps(p.get("extra") or {}, ensure_ascii=False),
                    now,
                )
                for p in papers
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_paper_info(
    user_id: int,
    date_str: str,
    paper_arxiv_id: Optional[str] = None,
) -> list[dict]:
    """Return all paper_info rows for user+date, or a single paper if specified."""
    conn = _connect()
    try:
        if paper_arxiv_id:
            rows = conn.execute(
                "SELECT * FROM pipeline_paper_info "
                "WHERE user_id=? AND date_str=? AND paper_arxiv_id=?",
                (user_id, date_str, paper_arxiv_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pipeline_paper_info WHERE user_id=? AND date_str=?",
                (user_id, date_str),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_paper_info_map(user_id: int, date_str: str) -> dict[str, dict]:
    """Return {arxiv_id: info_dict} for all papers in user+date."""
    rows = get_paper_info(user_id, date_str)
    return {r["paper_arxiv_id"]: r for r in rows}


def has_paper_info(user_id: int, date_str: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM pipeline_paper_info WHERE user_id=? AND date_str=? LIMIT 1",
            (user_id, date_str),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_summaries CRUD
# ---------------------------------------------------------------------------

def upsert_summary_raw(
    user_id: int,
    date_str: str,
    paper_arxiv_id: str,
    summary_raw: str,
    headline: str = "",
) -> None:
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO pipeline_summaries
                (user_id, date_str, paper_arxiv_id, summary_raw, headline,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                summary_raw = excluded.summary_raw,
                headline    = CASE WHEN excluded.headline != ''
                                   THEN excluded.headline
                                   ELSE headline END,
                updated_at  = excluded.updated_at
            """,
            (user_id, date_str, paper_arxiv_id, summary_raw, headline, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_summary_limit(
    user_id: int,
    date_str: str,
    paper_arxiv_id: str,
    summary_limit: str,
    headline: str = "",
) -> None:
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO pipeline_summaries
                (user_id, date_str, paper_arxiv_id, summary_limit, headline,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                summary_limit = excluded.summary_limit,
                headline      = CASE WHEN excluded.headline != ''
                                     THEN excluded.headline
                                     ELSE headline END,
                updated_at    = excluded.updated_at
            """,
            (user_id, date_str, paper_arxiv_id, summary_limit, headline, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def bulk_upsert_summaries_raw(
    user_id: int,
    date_str: str,
    summaries: list[dict[str, str]],
) -> None:
    """Each dict: {paper_arxiv_id, summary_raw, headline(opt)}."""
    now = _now_iso()
    conn = _connect()
    try:
        conn.executemany(
            """
            INSERT INTO pipeline_summaries
                (user_id, date_str, paper_arxiv_id, summary_raw, headline,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                summary_raw = excluded.summary_raw,
                headline    = CASE WHEN excluded.headline != ''
                                   THEN excluded.headline
                                   ELSE headline END,
                updated_at  = excluded.updated_at
            """,
            [
                (user_id, date_str, s["paper_arxiv_id"],
                 s.get("summary_raw", ""), s.get("headline", ""),
                 now, now)
                for s in summaries
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_summaries(
    user_id: int,
    date_str: str,
    paper_arxiv_id: Optional[str] = None,
) -> list[dict]:
    conn = _connect()
    try:
        if paper_arxiv_id:
            rows = conn.execute(
                "SELECT * FROM pipeline_summaries "
                "WHERE user_id=? AND date_str=? AND paper_arxiv_id=?",
                (user_id, date_str, paper_arxiv_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pipeline_summaries WHERE user_id=? AND date_str=?",
                (user_id, date_str),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_summaries_map(user_id: int, date_str: str) -> dict[str, dict]:
    """Return {arxiv_id: summary_dict}."""
    return {r["paper_arxiv_id"]: r for r in get_summaries(user_id, date_str)}


def has_summaries_raw(user_id: int, date_str: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM pipeline_summaries "
            "WHERE user_id=? AND date_str=? AND summary_raw!='' LIMIT 1",
            (user_id, date_str),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def has_summaries_limit(user_id: int, date_str: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM pipeline_summaries "
            "WHERE user_id=? AND date_str=? AND summary_limit!='' LIMIT 1",
            (user_id, date_str),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_paper_assets CRUD
# ---------------------------------------------------------------------------

def upsert_paper_assets(
    user_id: int,
    date_str: str,
    paper_arxiv_id: str,
    *,
    title: str = "",
    url: str = "",
    year: Optional[int] = None,
    blocks: Optional[list] = None,
) -> None:
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO pipeline_paper_assets
                (user_id, date_str, paper_arxiv_id, title, url, year,
                 blocks_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                title       = excluded.title,
                url         = excluded.url,
                year        = excluded.year,
                blocks_json = excluded.blocks_json,
                created_at  = excluded.created_at
            """,
            (
                user_id, date_str, paper_arxiv_id, title, url, year,
                json.dumps(blocks or [], ensure_ascii=False), now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def bulk_upsert_paper_assets(
    user_id: int,
    date_str: str,
    assets: list[dict[str, Any]],
) -> None:
    now = _now_iso()
    conn = _connect()
    try:
        conn.executemany(
            """
            INSERT INTO pipeline_paper_assets
                (user_id, date_str, paper_arxiv_id, title, url, year,
                 blocks_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str, paper_arxiv_id) DO UPDATE SET
                title       = excluded.title,
                url         = excluded.url,
                year        = excluded.year,
                blocks_json = excluded.blocks_json,
                created_at  = excluded.created_at
            """,
            [
                (
                    user_id, date_str, a["paper_arxiv_id"],
                    a.get("title", ""), a.get("url", ""), a.get("year"),
                    json.dumps(a.get("blocks", []), ensure_ascii=False), now,
                )
                for a in assets
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_paper_assets(
    user_id: int,
    date_str: str,
    paper_arxiv_id: Optional[str] = None,
) -> list[dict]:
    conn = _connect()
    try:
        if paper_arxiv_id:
            rows = conn.execute(
                "SELECT * FROM pipeline_paper_assets "
                "WHERE user_id=? AND date_str=? AND paper_arxiv_id=?",
                (user_id, date_str, paper_arxiv_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pipeline_paper_assets WHERE user_id=? AND date_str=?",
                (user_id, date_str),
            ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["blocks"] = json.loads(d.get("blocks_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["blocks"] = []
            results.append(d)
        return results
    finally:
        conn.close()


def get_paper_assets_map(user_id: int, date_str: str) -> dict[str, dict]:
    """Return {arxiv_id: assets_dict}."""
    return {r["paper_arxiv_id"]: r for r in get_paper_assets(user_id, date_str)}


def has_paper_assets(user_id: int, date_str: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM pipeline_paper_assets WHERE user_id=? AND date_str=? LIMIT 1",
            (user_id, date_str),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Cross-table query: build the full paper digest for one user+date
# ---------------------------------------------------------------------------

def get_digest_papers(
    user_id: int,
    date_str: str,
    fallback_user_id: int = 0,
) -> list[dict]:
    """
    Build a list of fully assembled paper dicts for user+date.

    Falls back to ``fallback_user_id`` (default=0) for any user-level data
    that does not exist for ``user_id`` yet.

    Returns a list ordered by theme_score descending.
    """
    effective_uid = user_id if has_final_selections(user_id, date_str) else fallback_user_id

    # Load selections
    selected_ids = get_final_arxiv_ids(effective_uid, date_str)
    if not selected_ids:
        return []

    # Load info, summaries, assets (fall back per-table)
    info_uid = user_id if has_paper_info(user_id, date_str) else fallback_user_id
    sum_uid  = user_id if has_summaries_limit(user_id, date_str) else fallback_user_id
    asset_uid = user_id if has_paper_assets(user_id, date_str) else fallback_user_id

    info_map   = get_paper_info_map(info_uid, date_str)
    sum_map    = get_summaries_map(sum_uid, date_str)
    asset_map  = get_paper_assets_map(asset_uid, date_str)

    # Load theme scores for ordering
    score_uid = user_id if has_theme_scores(user_id, date_str) else fallback_user_id
    scores = get_theme_scores(score_uid, date_str)

    conn = _connect()
    try:
        placeholders = ",".join("?" for _ in selected_ids)
        sel_rows = conn.execute(
            f"SELECT * FROM pipeline_selected_papers "
            f"WHERE user_id=? AND date_str=? AND paper_arxiv_id IN ({placeholders})",
            [effective_uid, date_str] + selected_ids,
        ).fetchall()
    finally:
        conn.close()

    papers = []
    for row in sel_rows:
        arxiv_id = row["paper_arxiv_id"]
        info   = info_map.get(arxiv_id, {})
        summ   = sum_map.get(arxiv_id, {})
        assets = asset_map.get(arxiv_id, {})

        raw_tier = int(info.get("institution_tier") or 0)
        is_large = bool(info.get("is_large", 0))
        # 0 or out-of-range: same fallback as data_service.get_paper_detail (DB path)
        effective_tier = (
            raw_tier if 1 <= raw_tier <= 4 else (3 if is_large else 4)
        )
        paper = {
            "paper_id": arxiv_id,
            "institution": info.get("institution", ""),
            "is_large_institution": is_large,
            "institution_tier": effective_tier,
            "abstract": info.get("abstract", ""),
            "title": info.get("title", ""),
            "summary_raw": summ.get("summary_raw", ""),
            "summary_limit": summ.get("summary_limit", ""),
            "headline": summ.get("headline", ""),
            "relevance_score": scores.get(arxiv_id),
            "paper_assets": assets.get("blocks") if assets else None,
            # Indicate whether this came from the user's personalised pipeline
            "is_personalized": (effective_uid != 0 and effective_uid == user_id),
            "pipeline_user_id": effective_uid,
        }
        papers.append(paper)

    # Sort: institution tier ascending (T1=1 first), then relevance_score descending within same tier
    papers.sort(
        key=lambda p: (
            p.get("institution_tier") or 4,
            -(p.get("relevance_score") or 0.0),
        )
    )
    return papers


# ---------------------------------------------------------------------------
# Utility: list dates that have pipeline data
# ---------------------------------------------------------------------------

def list_dates_with_data(user_id: int = 0) -> list[str]:
    """Return distinct date_str values for which user_id has final selections
    OR has a date notice (pipeline ran but produced 0 results)."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT date_str FROM pipeline_selected_papers
            WHERE user_id=? AND is_final_selected=1
            UNION
            SELECT DISTINCT date_str FROM pipeline_date_notices
            WHERE user_id=?
            ORDER BY date_str DESC
            """,
            (user_id, user_id),
        ).fetchall()
        return [r["date_str"] for r in rows]
    finally:
        conn.close()


def list_all_dates_with_data() -> list[str]:
    """Return all distinct dates across all users (default run only)."""
    return list_dates_with_data(user_id=0)


# ---------------------------------------------------------------------------
# pipeline_date_notices CRUD
# ---------------------------------------------------------------------------

def upsert_date_notice(
    user_id: int,
    date_str: str,
    notice_type: str,
    message: str,
) -> None:
    """Insert or replace a date notice for (user_id, date_str)."""
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO pipeline_date_notices
                (user_id, date_str, notice_type, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date_str) DO UPDATE SET
                notice_type = excluded.notice_type,
                message     = excluded.message,
                created_at  = excluded.created_at
            """,
            (user_id, date_str, notice_type, message, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_date_notice(user_id: int, date_str: str) -> Optional[dict]:
    """Return the notice dict for (user_id, date_str), or None if no notice exists."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT notice_type, message FROM pipeline_date_notices "
            "WHERE user_id=? AND date_str=?",
            (user_id, date_str),
        ).fetchone()
        if row:
            return {"type": row["notice_type"], "message": row["message"]}
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_images CRUD
# ---------------------------------------------------------------------------

def upsert_paper_images(date_str: str, paper_arxiv_id: str, images: list) -> None:
    """Store image filenames for a paper on a given date."""
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO pipeline_images (date_str, paper_arxiv_id, images_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date_str, paper_arxiv_id) DO UPDATE SET
                images_json = excluded.images_json,
                created_at  = excluded.created_at
            """,
            (date_str, paper_arxiv_id, json.dumps(images or [], ensure_ascii=False), now),
        )
        conn.commit()
    finally:
        conn.close()


def bulk_upsert_paper_images(date_str: str, images_map: dict) -> None:
    """Bulk-store image filenames. images_map: {arxiv_id: [filename, ...]}"""
    now = _now_iso()
    conn = _connect()
    try:
        conn.executemany(
            """
            INSERT INTO pipeline_images (date_str, paper_arxiv_id, images_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date_str, paper_arxiv_id) DO UPDATE SET
                images_json = excluded.images_json,
                created_at  = excluded.created_at
            """,
            [
                (date_str, arxiv_id, json.dumps(imgs or [], ensure_ascii=False), now)
                for arxiv_id, imgs in images_map.items()
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_paper_images(date_str: str, paper_arxiv_id: Optional[str] = None) -> dict:
    """Return {arxiv_id: [filename, ...]} for the given date (and optionally paper)."""
    conn = _connect()
    try:
        if paper_arxiv_id:
            rows = conn.execute(
                "SELECT paper_arxiv_id, images_json FROM pipeline_images "
                "WHERE date_str=? AND paper_arxiv_id=?",
                (date_str, paper_arxiv_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT paper_arxiv_id, images_json FROM pipeline_images WHERE date_str=?",
                (date_str,),
            ).fetchall()
        result = {}
        for r in rows:
            try:
                imgs = json.loads(r["images_json"] or "[]")
            except (json.JSONDecodeError, TypeError):
                imgs = []
            result[r["paper_arxiv_id"]] = imgs
        return result
    finally:
        conn.close()


def has_images(date_str: str) -> bool:
    """Return True if any image records exist for the given date."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM pipeline_images WHERE date_str=? LIMIT 1",
            (date_str,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_arxiv_list CRUD
# ---------------------------------------------------------------------------

def bulk_upsert_arxiv_list(date_str: str, papers: list) -> None:
    """
    Store arxiv search results for a date.
    Each paper dict should have: paper_arxiv_id, title, abstract_text,
    authors (list), published_utc, link, categories (list).
    """
    now = _now_iso()
    conn = _connect()
    try:
        conn.executemany(
            """
            INSERT INTO pipeline_arxiv_list
                (date_str, paper_arxiv_id, title, abstract_text,
                 authors_json, published_utc, link, categories_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date_str, paper_arxiv_id) DO UPDATE SET
                title           = excluded.title,
                abstract_text   = excluded.abstract_text,
                authors_json    = excluded.authors_json,
                published_utc   = excluded.published_utc,
                link            = excluded.link,
                categories_json = excluded.categories_json,
                created_at      = excluded.created_at
            """,
            [
                (
                    date_str,
                    p["paper_arxiv_id"],
                    p.get("title", ""),
                    p.get("abstract_text", ""),
                    json.dumps(p.get("authors", []), ensure_ascii=False),
                    p.get("published_utc", ""),
                    p.get("link", ""),
                    json.dumps(p.get("categories", []), ensure_ascii=False),
                    now,
                )
                for p in papers
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_arxiv_list(date_str: str) -> list:
    """Return all papers from the arxiv search for the given date."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_arxiv_list WHERE date_str=? ORDER BY id",
            (date_str,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["authors"] = json.loads(d.get("authors_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["authors"] = []
            try:
                d["categories"] = json.loads(d.get("categories_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["categories"] = []
            result.append(d)
        return result
    finally:
        conn.close()


def has_arxiv_list(date_str: str) -> bool:
    """Return True if arxiv search results exist in DB for the given date."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM pipeline_arxiv_list WHERE date_str=? LIMIT 1",
            (date_str,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_arxiv_list_ids(date_str: str) -> list:
    """Return a list of arxiv IDs for the given date (lightweight query)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT paper_arxiv_id FROM pipeline_arxiv_list WHERE date_str=?",
            (date_str,),
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pipeline data tracking: per-date paper counts for each pipeline step
# ---------------------------------------------------------------------------

def get_pipeline_data_tracking(user_id: int, date_str: str) -> dict:
    """
    Return a dict of paper counts at each pipeline step for the given user+date.
    Counts are None if the step has not run yet (no data in DB).
    """
    conn = _connect()
    try:
        def _count(query: str, params: tuple) -> Optional[int]:
            row = conn.execute(query, params).fetchone()
            if row is None:
                return None
            val = row[0]
            return val if val is not None else None

        arxiv_search = _count(
            "SELECT COUNT(*) FROM pipeline_arxiv_list WHERE date_str=?",
            (date_str,),
        )
        # 0 means the table exists but no rows → step hasn't run, treat as None
        if arxiv_search == 0:
            arxiv_search = None

        theme_scored = _count(
            "SELECT COUNT(*) FROM pipeline_theme_scores WHERE user_id=? AND date_str=?",
            (user_id, date_str),
        )
        if theme_scored == 0:
            theme_scored = None

        theme_passed = _count(
            "SELECT COUNT(*) FROM pipeline_selected_papers "
            "WHERE user_id=? AND date_str=? AND passed_theme_filter=1",
            (user_id, date_str),
        )
        if theme_passed == 0:
            theme_passed = None

        institution_info = _count(
            "SELECT COUNT(*) FROM pipeline_paper_info WHERE user_id=? AND date_str=?",
            (user_id, date_str),
        )
        if institution_info == 0:
            institution_info = None

        final_selected = _count(
            "SELECT COUNT(*) FROM pipeline_selected_papers "
            "WHERE user_id=? AND date_str=? AND is_final_selected=1",
            (user_id, date_str),
        )
        if final_selected == 0:
            final_selected = None

        summary_raw = _count(
            "SELECT COUNT(*) FROM pipeline_summaries "
            "WHERE user_id=? AND date_str=? AND summary_raw != ''",
            (user_id, date_str),
        )
        if summary_raw == 0:
            summary_raw = None

        summary_limit = _count(
            "SELECT COUNT(*) FROM pipeline_summaries "
            "WHERE user_id=? AND date_str=? AND summary_limit != ''",
            (user_id, date_str),
        )
        if summary_limit == 0:
            summary_limit = None

        paper_assets = _count(
            "SELECT COUNT(*) FROM pipeline_paper_assets WHERE user_id=? AND date_str=?",
            (user_id, date_str),
        )
        if paper_assets == 0:
            paper_assets = None

    finally:
        conn.close()

    # Dedup count comes from the file system (step writes a JSON file, not DB)
    dedup: Optional[int] = None
    try:
        import json as _json
        dedup_path = os.path.join(
            _BASE_DIR, "data", "paperList_remove_duplications", f"{date_str}.json"
        )
        if os.path.isfile(dedup_path):
            with open(dedup_path, "r", encoding="utf-8") as _f:
                dedup_obj = _json.load(_f)
            if isinstance(dedup_obj, list):
                dedup = len(dedup_obj)
            elif isinstance(dedup_obj, dict) and "papers" in dedup_obj:
                dedup = len(dedup_obj["papers"])
    except Exception:
        dedup = None

    return {
        "date": date_str,
        "arxiv_search": arxiv_search,
        "dedup": dedup,
        "theme_scored": theme_scored,
        "theme_passed": theme_passed,
        "institution_info": institution_info,
        "final_selected": final_selected,
        "summary_raw": summary_raw,
        "summary_limit": summary_limit,
        "paper_assets": paper_assets,
    }


def get_pipeline_data_tracking_range(user_id: int, days: int = 30) -> list[dict]:
    """
    Return tracking data for the most recent *days* calendar days that have
    any data in the DB (pipeline_arxiv_list).  Sorted newest-first.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT date_str
            FROM pipeline_arxiv_list
            ORDER BY date_str DESC
            LIMIT ?
            """,
            (days,),
        ).fetchall()
        date_strs = [r[0] for r in rows]
    finally:
        conn.close()

    return [get_pipeline_data_tracking(user_id, d) for d in date_strs]


# Ensure tables exist on first import
init_db()
