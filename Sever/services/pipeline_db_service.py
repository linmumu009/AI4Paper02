"""
Pipeline DB service layer.

Stores per-user, per-date pipeline outputs in ``paper_analysis.db``.
Replaces the file-based intermediate outputs (llm_select_theme JSON,
paper_summary .md files, paper_assets .jsonl, etc.) with DB tables that are
keyed by (user_id, date_str, paper_arxiv_id).

user_id=0 is reserved for the default/system pipeline run.

Tables
------
Output / data tables:
    pipeline_runs           -- tracks each pipeline execution
    pipeline_theme_scores   -- replaces llm_select_theme/<date>.json
    pipeline_selected_papers-- replaces paper_theme_filter+instutions_filter+selectpaper outputs
    pipeline_paper_info     -- replaces pdf_info/<date>.json
    pipeline_summaries      -- replaces paper_summary + summary_limit .md files
    pipeline_paper_assets   -- replaces paper_assets/<date>.jsonl

Observability tables (作业账本):
    pipeline_step_runs      -- step-level lifecycle: status, timing, errors
    pipeline_artifacts      -- artifact registry: files and DB records produced per step
    pipeline_events         -- structured event stream: progress, warnings, diagnostics
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
                created_at   TEXT    NOT NULL,
                log_file     TEXT    NOT NULL DEFAULT ''
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
                blocks_json    TEXT    NOT NULL DEFAULT '{}',
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
    _migrate_add_observability_tables()
    _migrate_pipeline_runs_extend()
    _migrate_pipeline_runs_add_log_file()


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
    _migrate_arxiv_list_paper_categories()


def _migrate_arxiv_list_paper_categories() -> None:
    """Add paper_categories_json column to pipeline_arxiv_list if it does not exist."""
    conn = _connect()
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_arxiv_list)").fetchall()}
        if "paper_categories_json" not in existing:
            conn.execute(
                "ALTER TABLE pipeline_arxiv_list ADD COLUMN paper_categories_json TEXT NOT NULL DEFAULT '[]'"
            )
            conn.commit()
    finally:
        conn.close()


def _migrate_add_observability_tables() -> None:
    """Create pipeline_step_runs, pipeline_artifacts, pipeline_events tables (observability layer)."""
    conn = _connect()
    try:
        conn.executescript("""
            -- ----------------------------------------------------------------
            -- pipeline_step_runs: one row per step execution attempt
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_step_runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id       INTEGER NOT NULL DEFAULT 0,  -- FK to pipeline_runs.id (0 = no parent)
                step_name    TEXT    NOT NULL,
                phase        TEXT    NOT NULL DEFAULT '',  -- 'shared' | 'per_user' | 'legacy' | ''
                user_id      INTEGER NOT NULL DEFAULT 0,
                date_str     TEXT    NOT NULL DEFAULT '',
                status       TEXT    NOT NULL DEFAULT 'running',
                -- pending / running / skipped / soft_failed / failed / completed / cancelled
                attempt      INTEGER NOT NULL DEFAULT 1,
                skip_reason  TEXT    NOT NULL DEFAULT '',
                error_type   TEXT    NOT NULL DEFAULT '',
                error_message TEXT   NOT NULL DEFAULT '',
                log_file     TEXT    NOT NULL DEFAULT '',
                input_json   TEXT    NOT NULL DEFAULT '{}',
                metrics_json TEXT    NOT NULL DEFAULT '{}',
                started_at   TEXT,
                finished_at  TEXT,
                duration_ms  INTEGER,
                exit_code    INTEGER,
                created_at   TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_psr_run_id ON pipeline_step_runs(run_id);
            CREATE INDEX IF NOT EXISTS idx_psr_user_date ON pipeline_step_runs(user_id, date_str);
            CREATE INDEX IF NOT EXISTS idx_psr_step_status ON pipeline_step_runs(step_name, status);

            -- ----------------------------------------------------------------
            -- pipeline_artifacts: files and DB records produced by each step
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_artifacts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id        INTEGER NOT NULL DEFAULT 0,
                step_run_id   INTEGER NOT NULL DEFAULT 0,
                artifact_type TEXT    NOT NULL DEFAULT '',
                -- 'file' | 'db_table' | 'db_rows' | 'directory'
                storage       TEXT    NOT NULL DEFAULT '',
                -- 'file' | 'sqlite'
                path_or_table TEXT    NOT NULL DEFAULT '',
                record_count  INTEGER,
                byte_size     INTEGER,
                created_at    TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pa_run_id ON pipeline_artifacts(run_id);
            CREATE INDEX IF NOT EXISTS idx_pa_step_run ON pipeline_artifacts(step_run_id);

            -- ----------------------------------------------------------------
            -- pipeline_events: structured event stream per run / step
            -- ----------------------------------------------------------------
            CREATE TABLE IF NOT EXISTS pipeline_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id       INTEGER NOT NULL DEFAULT 0,
                step_run_id  INTEGER NOT NULL DEFAULT 0,
                level        TEXT    NOT NULL DEFAULT 'info',
                -- 'debug' | 'info' | 'warning' | 'error'
                event_type   TEXT    NOT NULL DEFAULT '',
                -- 'progress' | 'skip' | 'soft_fail' | 'retry' | 'cleanup' | 'paper_count' | 'llm_call' | 'custom'
                message      TEXT    NOT NULL DEFAULT '',
                payload_json TEXT    NOT NULL DEFAULT '{}',
                created_at   TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pe_run_id ON pipeline_events(run_id);
            CREATE INDEX IF NOT EXISTS idx_pe_step_run ON pipeline_events(step_run_id);
            CREATE INDEX IF NOT EXISTS idx_pe_created ON pipeline_events(created_at);
        """)
        conn.commit()
    finally:
        conn.close()


def _migrate_pipeline_runs_extend() -> None:
    """Add observability columns to pipeline_runs if they don't exist yet."""
    conn = _connect()
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)").fetchall()}
        additions = [
            ("parent_run_id", "INTEGER"),
            ("trigger",       "TEXT NOT NULL DEFAULT ''"),
            ("phase",         "TEXT NOT NULL DEFAULT ''"),
            ("requested_by",  "INTEGER"),
            ("cancelled_at",  "TEXT"),
        ]
        for col_name, col_def in additions:
            if col_name not in existing:
                conn.execute(f"ALTER TABLE pipeline_runs ADD COLUMN {col_name} {col_def}")
        conn.commit()
    finally:
        conn.close()


def _migrate_pipeline_runs_add_log_file() -> None:
    """Add log_file column to pipeline_runs if it does not exist."""
    conn = _connect()
    try:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)").fetchall()}
        if "log_file" not in existing:
            conn.execute("ALTER TABLE pipeline_runs ADD COLUMN log_file TEXT NOT NULL DEFAULT ''")
            conn.commit()
    finally:
        conn.close()


def update_run_log_file(run_id: int, log_file: str) -> None:
    """Store the log file path for a pipeline run."""
    if not run_id:
        return
    conn = _connect()
    try:
        conn.execute(
            "UPDATE pipeline_runs SET log_file=? WHERE id=?",
            (log_file or "", run_id),
        )
        conn.commit()
    finally:
        conn.close()


def _get_user_display_map(user_ids: list) -> dict:
    """Return {user_id: {'username': ..., 'nickname': ...}} for the given non-zero IDs."""
    ids = [uid for uid in user_ids if uid]
    if not ids:
        return {}
    conn = _connect()
    try:
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT id, username, COALESCE(nickname, '') AS nickname "
            f"FROM auth_users WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        return {r["id"]: {"username": r["username"], "nickname": r["nickname"]} for r in rows}
    except Exception:
        return {}
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
    parent_run_id: Optional[int] = None,
    trigger: str = "",
    phase: str = "",
    requested_by: Optional[int] = None,
) -> int:
    """Insert a new pipeline run record; return its id."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO pipeline_runs
                (run_type, user_id, date_str, pipeline, status, config_json,
                 parent_run_id, trigger, phase, requested_by, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
            """,
            (run_type, user_id, date_str, pipeline,
             json.dumps(config or {}, ensure_ascii=False),
             parent_run_id, trigger, phase, requested_by, now),
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
    blocks: Optional[dict] = None,
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
                json.dumps(blocks or {}, ensure_ascii=False), now,
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
                    json.dumps(a.get("blocks", {}), ensure_ascii=False), now,
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
                d["blocks"] = json.loads(d.get("blocks_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                d["blocks"] = {}
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

        # Load authors and categories from shared arxiv list table
        arxiv_meta: dict[str, dict] = {}
        try:
            meta_rows = conn.execute(
                f"SELECT paper_arxiv_id, title, abstract_text, authors_json, categories_json "
                f"FROM pipeline_arxiv_list "
                f"WHERE date_str=? AND paper_arxiv_id IN ({placeholders})",
                [date_str] + selected_ids,
            ).fetchall()
            for mr in meta_rows:
                try:
                    authors = json.loads(mr["authors_json"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    authors = []
                try:
                    categories = json.loads(mr["categories_json"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    categories = []
                arxiv_meta[mr["paper_arxiv_id"]] = {
                    "title": mr["title"] or "",
                    "abstract": mr["abstract_text"] or "",
                    "authors": authors,
                    "categories": categories,
                }
        except Exception:
            pass
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
        meta = arxiv_meta.get(arxiv_id, {})
        paper = {
            "paper_id": arxiv_id,
            "institution": info.get("institution", ""),
            "is_large_institution": is_large,
            "institution_tier": effective_tier,
            "abstract": info.get("abstract") or meta.get("abstract", ""),
            "title": info.get("title") or meta.get("title") or arxiv_id,
            "summary_raw": summ.get("summary_raw", ""),
            "summary_limit": summ.get("summary_limit", ""),
            "headline": summ.get("headline", ""),
            "relevance_score": scores.get(arxiv_id),
            "authors": meta.get("authors", []),
            "categories": meta.get("categories", []),
            "paper_assets": {
                "paper_id": arxiv_id,
                "title": assets.get("title", ""),
                "url": assets.get("url", ""),
                "year": assets.get("year"),
                "blocks": assets.get("blocks"),
            } if assets and assets.get("blocks") else None,
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
    authors (list), published_utc, link, categories (list), paper_categories (list).
    """
    now = _now_iso()
    conn = _connect()
    try:
        conn.executemany(
            """
            INSERT INTO pipeline_arxiv_list
                (date_str, paper_arxiv_id, title, abstract_text,
                 authors_json, published_utc, link, categories_json, paper_categories_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date_str, paper_arxiv_id) DO UPDATE SET
                title                  = excluded.title,
                abstract_text          = excluded.abstract_text,
                authors_json           = excluded.authors_json,
                published_utc          = excluded.published_utc,
                link                   = excluded.link,
                categories_json        = excluded.categories_json,
                paper_categories_json  = excluded.paper_categories_json,
                created_at             = excluded.created_at
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
                    json.dumps(p.get("paper_categories", []), ensure_ascii=False),
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
            try:
                d["paper_categories"] = json.loads(d.get("paper_categories_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                d["paper_categories"] = []
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


def _blocks_have_meaningful_text(value: Any) -> bool:
    """Return True when a paper-assets payload contains real textual content."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_blocks_have_meaningful_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_blocks_have_meaningful_text(item) for item in value)
    return False


def _get_theme_candidate_ids(
    conn: sqlite3.Connection,
    user_id: int,
    date_str: str,
) -> set[str]:
    """Mirror llm_select_theme's dedup-file and per-user category inputs."""
    papers: list[dict[str, Any]] = []
    dedup_path = os.path.join(
        _BASE_DIR, "data", "paperList_remove_duplications", f"{date_str}.json"
    )
    try:
        with open(dedup_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, dict):
            raw = raw.get("papers") or []
        if isinstance(raw, list):
            papers = [item for item in raw if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError, TypeError):
        papers = []

    if papers:
        candidate_ids = {
            str(item.get("arxiv_id") or item.get("paper_arxiv_id") or "").strip()
            for item in papers
        }
        candidate_ids.discard("")
    else:
        # Older successful runs may already have removed the deduplicated
        # input file.  Their stored score set is the only authoritative record
        # of the user-specific model candidates; do not expand those runs back
        # to the much larger acquisition table during a recovery check.
        candidate_ids = {
            str(row[0])
            for row in conn.execute(
                "SELECT paper_arxiv_id FROM pipeline_theme_scores "
                "WHERE user_id=? AND date_str=?",
                (user_id, date_str),
            ).fetchall()
            if row[0]
        }
    if not candidate_ids:
        candidate_ids = {
            str(row[0])
            for row in conn.execute(
                "SELECT paper_arxiv_id FROM pipeline_arxiv_list WHERE date_str=?",
                (date_str,),
            ).fetchall()
            if row[0]
        }

    try:
        from services.user_settings_service import get_settings
        from config import config as config_module

        settings = get_settings(user_id, "paper_recommend")
        configured = settings.get("search_categories")
        defaults = list(
            getattr(
                config_module,
                "SEARCH_CATEGORIES",
                ["cs.CL", "cs.LG", "cs.AI", "stat.ML"],
            )
            or []
        )
        user_categories = (
            {str(item).strip() for item in configured if str(item).strip()}
            if isinstance(configured, list)
            and configured
            and sorted(configured) != sorted(defaults)
            else set()
        )
        if user_categories and candidate_ids:
            rows = conn.execute(
                "SELECT paper_arxiv_id, paper_categories_json "
                "FROM pipeline_arxiv_list WHERE date_str=?",
                (date_str,),
            ).fetchall()
            categories_by_id: dict[str, set[str]] = {}
            for row in rows:
                try:
                    categories = json.loads(row["paper_categories_json"] or "[]")
                except (json.JSONDecodeError, TypeError):
                    categories = []
                categories_by_id[str(row["paper_arxiv_id"])] = {
                    str(item) for item in categories if item
                }
            candidate_ids = {
                paper_id
                for paper_id in candidate_ids
                if not categories_by_id.get(paper_id)
                or bool(user_categories & categories_by_id[paper_id])
            }
    except Exception:
        # Match the controller's safe fallback: score the unfiltered candidate set.
        pass

    return candidate_ids


def get_db_step_coverage(step: str, user_id: int, date_str: str) -> dict:
    """Return the expected/valid output coverage for one DB pipeline step.

    Completion is deliberately based on the full expected paper-id set, not on
    whether the table happens to contain at least one row.  Extra rows are
    reported for diagnostics but do not block recovery of older runs yet.
    """
    conn = _connect()
    try:
        def _ids(query: str, params: tuple) -> set[str]:
            rows = conn.execute(query, params).fetchall()
            return {str(row[0]) for row in rows if row[0]}

        theme_candidate_ids = _get_theme_candidate_ids(conn, user_id, date_str)
        score_ids = _ids(
            "SELECT paper_arxiv_id FROM pipeline_theme_scores WHERE user_id=? AND date_str=?",
            (user_id, date_str),
        )
        selected_row_ids = _ids(
            "SELECT paper_arxiv_id FROM pipeline_selected_papers "
            "WHERE user_id=? AND date_str=?",
            (user_id, date_str),
        )
        final_ids = _ids(
            "SELECT paper_arxiv_id FROM pipeline_selected_papers "
            "WHERE user_id=? AND date_str=? AND is_final_selected=1",
            (user_id, date_str),
        )
        theme_passed_ids = _ids(
            "SELECT paper_arxiv_id FROM pipeline_selected_papers "
            "WHERE user_id=? AND date_str=? AND passed_theme_filter=1",
            (user_id, date_str),
        )

        invalid_ids: set[str] = set()
        if step == "llm_select_theme":
            expected_ids = theme_candidate_ids
            valid_ids = score_ids
        elif step == "paper_theme_filter":
            expected_ids = score_ids
            valid_ids = _ids(
                "SELECT paper_arxiv_id FROM pipeline_selected_papers "
                "WHERE user_id=? AND date_str=? AND theme_score IS NOT NULL",
                (user_id, date_str),
            )
        elif step == "pdf_info":
            # Institution extraction runs only for papers that passed this
            # user's relevance threshold. Shared preview files must not widen
            # this per-user input set.
            expected_ids = theme_passed_ids
            all_output_ids = _ids(
                "SELECT paper_arxiv_id FROM pipeline_paper_info "
                "WHERE user_id=? AND date_str=?",
                (user_id, date_str),
            )
            valid_ids = _ids(
                "SELECT paper_arxiv_id FROM pipeline_paper_info "
                "WHERE user_id=? AND date_str=? "
                "AND TRIM(title) != '' AND TRIM(abstract) != ''",
                (user_id, date_str),
            )
            invalid_ids = all_output_ids - valid_ids
        elif step == "instutions_filter":
            expected_ids = theme_passed_ids
            paper_info_valid_ids = _ids(
                "SELECT paper_arxiv_id FROM pipeline_paper_info "
                "WHERE user_id=? AND date_str=? "
                "AND TRIM(title) != '' AND TRIM(abstract) != ''",
                (user_id, date_str),
            )
            valid_ids = selected_row_ids & paper_info_valid_ids
        elif step == "paper_summary":
            expected_ids = final_ids
            valid_ids = _ids(
                "SELECT paper_arxiv_id FROM pipeline_summaries "
                "WHERE user_id=? AND date_str=? AND TRIM(summary_raw) != ''",
                (user_id, date_str),
            )
        elif step == "summary_limit":
            expected_ids = final_ids
            valid_ids = _ids(
                "SELECT paper_arxiv_id FROM pipeline_summaries "
                "WHERE user_id=? AND date_str=? AND TRIM(summary_limit) != ''",
                (user_id, date_str),
            )
        elif step == "paper_assets":
            expected_ids = final_ids
            rows = conn.execute(
                "SELECT paper_arxiv_id, blocks_json FROM pipeline_paper_assets "
                "WHERE user_id=? AND date_str=?",
                (user_id, date_str),
            ).fetchall()
            all_output_ids = {str(row["paper_arxiv_id"]) for row in rows if row["paper_arxiv_id"]}
            valid_ids: set[str] = set()
            for row in rows:
                paper_id = str(row["paper_arxiv_id"] or "")
                try:
                    blocks = json.loads(row["blocks_json"] or "{}")
                except (json.JSONDecodeError, TypeError):
                    blocks = {}
                if paper_id and _blocks_have_meaningful_text(blocks):
                    valid_ids.add(paper_id)
            invalid_ids = all_output_ids - valid_ids
        else:
            return {
                "step": step,
                "complete": False,
                "reason": "unsupported_step",
                "expected_count": 0,
                "valid_count": 0,
                "missing_ids": [],
                "invalid_ids": [],
                "unexpected_ids": [],
            }

        missing_ids = expected_ids - valid_ids
        relevant_invalid_ids = invalid_ids & expected_ids
        return {
            "step": step,
            "complete": not missing_ids and not relevant_invalid_ids,
            "reason": "complete" if not missing_ids and not relevant_invalid_ids else "incomplete_coverage",
            "expected_count": len(expected_ids),
            "valid_count": len(expected_ids & valid_ids),
            "missing_ids": sorted(missing_ids),
            "invalid_ids": sorted(relevant_invalid_ids),
            "unexpected_ids": sorted(valid_ids - expected_ids),
        }
    finally:
        conn.close()


def get_digest_publication_readiness(user_id: int, date_str: str) -> dict:
    """Return whether one user's digest is safe to expose as a complete batch."""
    if not has_final_selections(user_id, date_str):
        notice = get_date_notice(user_id, date_str)
        return {
            "ready": notice is not None,
            "user_id": user_id,
            "date_str": date_str,
            "reason": "empty_result_notice" if notice is not None else "no_result",
            "coverage": {},
        }

    coverage = {
        step: get_db_step_coverage(step, user_id, date_str)
        for step in ("paper_summary", "summary_limit", "paper_assets")
    }
    ready = all(item.get("complete") for item in coverage.values())
    return {
        "ready": ready,
        "user_id": user_id,
        "date_str": date_str,
        "reason": "complete" if ready else "incomplete_coverage",
        "coverage": coverage,
    }


def is_digest_ready_for_publication(user_id: int, date_str: str) -> bool:
    return bool(get_digest_publication_readiness(user_id, date_str).get("ready"))


def get_all_final_arxiv_ids(date_str: str) -> list[str]:
    """Return the union of final paper selections across every user for a date."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT paper_arxiv_id FROM pipeline_selected_papers "
            "WHERE date_str=? AND is_final_selected=1 ORDER BY paper_arxiv_id",
            (date_str,),
        ).fetchall()
        return [str(row[0]) for row in rows if row[0]]
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


# ===========================================================================
# Observability layer — pipeline_step_runs / pipeline_artifacts / pipeline_events
# ===========================================================================

# ---------------------------------------------------------------------------
# pipeline_step_runs CRUD
# ---------------------------------------------------------------------------

def create_step_run(
    run_id: int,
    step_name: str,
    *,
    phase: str = "",
    user_id: int = 0,
    date_str: str = "",
    input_params: Optional[dict] = None,
    log_file: str = "",
    attempt: int = 1,
) -> int:
    """Insert a step-run record with status=running; return its id."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO pipeline_step_runs
                (run_id, step_name, phase, user_id, date_str, status, attempt,
                 input_json, log_file, started_at, created_at)
            VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?)
            """,
            (run_id, step_name, phase, user_id, date_str, attempt,
             json.dumps(input_params or {}, ensure_ascii=False),
             log_file, now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def finish_step_run(
    step_run_id: int,
    status: str,
    *,
    exit_code: Optional[int] = None,
    error_type: str = "",
    error_message: str = "",
    skip_reason: str = "",
    metrics: Optional[dict] = None,
) -> None:
    """Mark a step-run as finished with the given status and metadata."""
    now = _now_iso()
    conn = _connect()
    try:
        started_row = conn.execute(
            "SELECT started_at FROM pipeline_step_runs WHERE id=?", (step_run_id,)
        ).fetchone()
        duration_ms: Optional[int] = None
        if started_row and started_row["started_at"]:
            try:
                from datetime import datetime as _dt
                started = _dt.fromisoformat(started_row["started_at"])
                finished = _dt.fromisoformat(now)
                duration_ms = int((finished - started).total_seconds() * 1000)
            except Exception:
                pass

        conn.execute(
            """
            UPDATE pipeline_step_runs SET
                status=?, finished_at=?, duration_ms=?, exit_code=?,
                error_type=?, error_message=?, skip_reason=?, metrics_json=?
            WHERE id=?
            """,
            (status, now, duration_ms, exit_code,
             error_type, error_message, skip_reason,
             json.dumps(metrics or {}, ensure_ascii=False),
             step_run_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_step_runs_for_run(run_id: int) -> list[dict]:
    """Return all step-run rows for a given run, ordered by creation time."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_step_runs WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["input_params"] = json.loads(d.get("input_json") or "{}")
            except Exception:
                d["input_params"] = {}
            try:
                d["metrics"] = json.loads(d.get("metrics_json") or "{}")
            except Exception:
                d["metrics"] = {}
            result.append(d)
        return result
    finally:
        conn.close()


def get_step_run_by_id(step_run_id: int) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM pipeline_step_runs WHERE id=?", (step_run_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_artifacts CRUD
# ---------------------------------------------------------------------------

def record_artifact(
    run_id: int,
    step_run_id: int,
    *,
    artifact_type: str,
    storage: str,
    path_or_table: str,
    record_count: Optional[int] = None,
    byte_size: Optional[int] = None,
) -> int:
    """Log a produced artifact; return its id."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO pipeline_artifacts
                (run_id, step_run_id, artifact_type, storage,
                 path_or_table, record_count, byte_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, step_run_id, artifact_type, storage,
             path_or_table, record_count, byte_size, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_artifacts_for_run(run_id: int) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_artifacts WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_artifacts_for_step(step_run_id: int) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_artifacts WHERE step_run_id=? ORDER BY id",
            (step_run_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_events CRUD
# ---------------------------------------------------------------------------

def emit_event(
    run_id: int,
    message: str,
    *,
    step_run_id: int = 0,
    level: str = "info",
    event_type: str = "custom",
    payload: Optional[dict] = None,
) -> None:
    """Append a structured event to the pipeline event log (non-blocking; swallows errors)."""
    try:
        now = _now_iso()
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO pipeline_events
                    (run_id, step_run_id, level, event_type, message, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, step_run_id, level, event_type, message,
                 json.dumps(payload or {}, ensure_ascii=False), now),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # Never let observability writes crash the pipeline


def get_events_for_run(
    run_id: int,
    step_run_id: Optional[int] = None,
    limit: int = 500,
) -> list[dict]:
    conn = _connect()
    try:
        if step_run_id is not None:
            rows = conn.execute(
                "SELECT * FROM pipeline_events WHERE run_id=? AND step_run_id=? ORDER BY id DESC LIMIT ?",
                (run_id, step_run_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pipeline_events WHERE run_id=? ORDER BY id DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.get("payload_json") or "{}")
            except Exception:
                d["payload"] = {}
            result.append(d)
        return list(reversed(result))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Run summary helpers (for the status API)
# ---------------------------------------------------------------------------

def get_run_with_steps(run_id: int) -> Optional[dict]:
    """Return a run dict with its steps embedded (used by status API)."""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM pipeline_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        try:
            run["config"] = json.loads(run.get("config_json") or "{}")
        except Exception:
            run["config"] = {}
    finally:
        conn.close()

    run["steps"] = get_step_runs_for_run(run_id)
    return run


def get_runs_recent(
    limit: int = 20,
    date_str: Optional[str] = None,
    user_id: Optional[int] = None,
) -> list[dict]:
    """Return recent pipeline runs, newest first."""
    conn = _connect()
    try:
        conditions = []
        params: list = []
        if date_str:
            conditions.append("date_str=?")
            params.append(date_str)
        if user_id is not None:
            conditions.append("user_id=?")
            params.append(user_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM pipeline_runs {where} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["config"] = json.loads(d.get("config_json") or "{}")
            except Exception:
                d["config"] = {}
            result.append(d)
        return result
    finally:
        conn.close()


def get_runs_recent_with_summary(
    limit: int = 20,
    date_str: Optional[str] = None,
    user_id: Optional[int] = None,
) -> list[dict]:
    """Like get_runs_recent but enriches each run with step counts and child runs in two bulk queries."""
    runs = get_runs_recent(limit=limit, date_str=date_str, user_id=user_id)
    if not runs:
        return runs

    run_ids = [r["id"] for r in runs]
    placeholders = ",".join("?" for _ in run_ids)

    conn = _connect()
    try:
        # Bulk step counts grouped by (run_id, status)
        step_rows = conn.execute(
            f"SELECT run_id, status, COUNT(*) as cnt FROM pipeline_step_runs "
            f"WHERE run_id IN ({placeholders}) GROUP BY run_id, status",
            run_ids,
        ).fetchall()
        counts_by_run: dict[int, dict[str, int]] = {}
        for r in step_rows:
            rid = r["run_id"]
            if rid not in counts_by_run:
                counts_by_run[rid] = {}
            counts_by_run[rid][r["status"]] = r["cnt"]

        # Bulk child runs
        child_rows = conn.execute(
            f"SELECT id, parent_run_id, user_id, phase, status "
            f"FROM pipeline_runs WHERE parent_run_id IN ({placeholders}) ORDER BY id",
            run_ids,
        ).fetchall()
        children_by_parent: dict[int, list[dict]] = {}
        for r in child_rows:
            pid = r["parent_run_id"]
            if pid not in children_by_parent:
                children_by_parent[pid] = []
            children_by_parent[pid].append(
                {"id": r["id"], "user_id": r["user_id"], "phase": r["phase"], "status": r["status"]}
            )

        # Bulk user display info (username / nickname)
        all_user_ids = list(
            {r.get("user_id", 0) for r in runs} | {r["user_id"] for r in child_rows}
        )
        user_display: dict[int, dict] = {}
        uid_non_zero = [uid for uid in all_user_ids if uid]
        if uid_non_zero:
            uid_ph = ",".join("?" for _ in uid_non_zero)
            try:
                u_rows = conn.execute(
                    f"SELECT id, username, COALESCE(nickname, '') AS nickname "
                    f"FROM auth_users WHERE id IN ({uid_ph})",
                    uid_non_zero,
                ).fetchall()
                user_display = {r["id"]: {"username": r["username"], "nickname": r["nickname"]} for r in u_rows}
            except Exception:
                pass
    finally:
        conn.close()

    for run in runs:
        rid = run["id"]
        counts = counts_by_run.get(rid, {})
        run["step_counts"] = counts
        run["step_total"] = sum(counts.values())
        run["step_failed"] = counts.get("failed", 0)
        run["step_completed"] = counts.get("completed", 0)
        run["step_skipped"] = counts.get("skipped", 0)
        run["step_soft_failed"] = counts.get("soft_failed", 0)
        # Enrich child_runs with user display info
        children = []
        for child in children_by_parent.get(rid, []):
            cuid = child.get("user_id", 0)
            cinfo = user_display.get(cuid, {})
            children.append({**child, "username": cinfo.get("username", ""), "nickname": cinfo.get("nickname", "")})
        run["child_runs"] = children
        # Enrich run with user display info
        uid = run.get("user_id", 0)
        uinfo = user_display.get(uid, {})
        run["username"] = uinfo.get("username", "")
        run["nickname"] = uinfo.get("nickname", "")

    return runs


def get_run_summary(run_id: int) -> Optional[dict]:
    """Return a run with step counts and health indicators (lightweight summary)."""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM pipeline_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        try:
            run["config"] = json.loads(run.get("config_json") or "{}")
        except Exception:
            run["config"] = {}

        step_rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM pipeline_step_runs WHERE run_id=? GROUP BY status",
            (run_id,),
        ).fetchall()
        counts = {r["status"]: r["cnt"] for r in step_rows}
        run["step_counts"] = counts
        run["step_total"] = sum(counts.values())
        run["step_failed"] = counts.get("failed", 0)
        run["step_completed"] = counts.get("completed", 0)
        run["step_skipped"] = counts.get("skipped", 0)
        run["step_soft_failed"] = counts.get("soft_failed", 0)

        child_rows = conn.execute(
            "SELECT id, user_id, phase, status FROM pipeline_runs WHERE parent_run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        run["child_runs"] = [dict(r) for r in child_rows]
        return run
    finally:
        conn.close()


# Ensure tables exist on first import
init_db()
