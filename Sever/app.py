import os
import sys
import shutil
import subprocess
import time
import traceback
from datetime import datetime
from typing import Optional

ROOT = os.path.dirname(__file__)
DATA_ROOT = "data"

# ---------------------------------------------------------------------------
# PipelineRecorder – lightweight observability layer.
# All DB writes are wrapped in try/except so a DB failure never crashes the
# pipeline. Import errors (e.g. cold start without DB) are also silently
# ignored so legacy CLI usage keeps working.
# ---------------------------------------------------------------------------

class PipelineRecorder:
    """Wraps pipeline_db_service calls to record step lifecycle, events and artifacts."""

    def __init__(
        self,
        run_id: int = 0,
        phase: str = "",
        user_id: int = 0,
        date_str: str = "",
        log_file: str = "",
    ):
        self.run_id = run_id
        self.phase = phase
        self.user_id = user_id
        self.date_str = date_str
        self.log_file = log_file
        self._current_step_run_id: int = 0
        self._step_start_ts: float = 0.0

    # ------------------------------------------------------------------
    # Run-level helpers (called from pipeline_router when it creates the run)
    # ------------------------------------------------------------------

    @staticmethod
    def start_run(
        pipeline: str,
        user_id: int,
        date_str: str,
        phase: str = "",
        trigger: str = "cli",
        parent_run_id: int = 0,
        requested_by: Optional[int] = None,
        config: Optional[dict] = None,
    ) -> int:
        """Create a pipeline_run row and return its id (0 on error)."""
        try:
            sys.path.insert(0, ROOT)
            from services import pipeline_db_service as _pdb
            run_type = phase or "shared"
            run_id = _pdb.create_run(
                run_type=run_type,
                user_id=user_id,
                date_str=date_str,
                pipeline=pipeline,
                config=config,
                parent_run_id=parent_run_id or None,
                trigger=trigger,
                phase=phase,
                requested_by=requested_by,
            )
            _pdb.update_run_status(run_id, "running")
            return run_id
        except Exception:
            return 0

    @staticmethod
    def end_run(run_id: int, success: bool, error: str = "") -> None:
        if not run_id:
            return
        try:
            from services import pipeline_db_service as _pdb
            _pdb.update_run_status(run_id, "completed" if success else "failed", error=error or None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Step-level helpers
    # ------------------------------------------------------------------

    def begin_step(self, step_name: str, input_params: Optional[dict] = None) -> None:
        self._step_start_ts = time.monotonic()
        self._current_step_run_id = 0
        if not self.run_id:
            return
        try:
            from services import pipeline_db_service as _pdb
            self._current_step_run_id = _pdb.create_step_run(
                self.run_id,
                step_name,
                phase=self.phase,
                user_id=self.user_id,
                date_str=self.date_str,
                input_params=input_params or {},
                log_file=self.log_file,
            )
        except Exception:
            pass

    def finish_step(
        self,
        step_name: str,
        *,
        status: str,
        exit_code: Optional[int] = None,
        error_type: str = "",
        error_message: str = "",
        skip_reason: str = "",
        metrics: Optional[dict] = None,
    ) -> None:
        if not self._current_step_run_id:
            return
        try:
            from services import pipeline_db_service as _pdb
            _pdb.finish_step_run(
                self._current_step_run_id,
                status,
                exit_code=exit_code,
                error_type=error_type,
                error_message=error_message,
                skip_reason=skip_reason,
                metrics=metrics,
            )
            # Record artifact footprint for known steps
            if status == "completed":
                self._auto_record_artifact(step_name)
        except Exception:
            pass

    def _auto_record_artifact(self, step_name: str) -> None:
        """Auto-detect and log artifacts for known step patterns."""
        if not (self.run_id and self._current_step_run_id and self.date_str):
            return
        try:
            from services import pipeline_db_service as _pdb

            # DB-output steps
            db_steps = {
                "llm_select_theme": ("pipeline_theme_scores", "user_id=? AND date_str=?"),
                "paper_theme_filter": ("pipeline_selected_papers", "user_id=? AND date_str=? AND passed_theme_filter=1"),
                "instutions_filter":  ("pipeline_selected_papers", "user_id=? AND date_str=? AND is_final_selected=1"),
                "pdf_info":           ("pipeline_paper_info", "user_id=? AND date_str=?"),
                "paper_summary":      ("pipeline_summaries", "user_id=? AND date_str=? AND summary_raw != ''"),
                "summary_limit":      ("pipeline_summaries", "user_id=? AND date_str=? AND summary_limit != ''"),
                "paper_assets":       ("pipeline_paper_assets", "user_id=? AND date_str=?"),
                "arxiv_search":       ("pipeline_arxiv_list", "date_str=?"),
            }
            if step_name in db_steps:
                table, where_clause = db_steps[step_name]
                try:
                    import sqlite3 as _sq
                    db_path = os.path.join(ROOT, "database", "paper_analysis.db")
                    con = _sq.connect(db_path)
                    con.row_factory = _sq.Row
                    if "user_id=?" in where_clause:
                        count = con.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE {where_clause}",
                            (self.user_id, self.date_str),
                        ).fetchone()[0]
                    else:
                        count = con.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE {where_clause}",
                            (self.date_str,),
                        ).fetchone()[0]
                    con.close()
                    _pdb.record_artifact(
                        self.run_id,
                        self._current_step_run_id,
                        artifact_type="db_rows",
                        storage="sqlite",
                        path_or_table=table,
                        record_count=count,
                    )
                except Exception:
                    pass

            # File-output steps
            if step_name in STEP_OUTPUT_PATHS:
                path = STEP_OUTPUT_PATHS[step_name](self.date_str)
                try:
                    if os.path.isfile(path):
                        byte_size = os.path.getsize(path)
                        _pdb.record_artifact(
                            self.run_id,
                            self._current_step_run_id,
                            artifact_type="file",
                            storage="file",
                            path_or_table=path,
                            byte_size=byte_size,
                        )
                    elif os.path.isdir(path):
                        byte_size = sum(
                            os.path.getsize(os.path.join(dp, f))
                            for dp, _, files in os.walk(path)
                            for f in files
                        )
                        _pdb.record_artifact(
                            self.run_id,
                            self._current_step_run_id,
                            artifact_type="directory",
                            storage="file",
                            path_or_table=path,
                            byte_size=byte_size,
                        )
                except Exception:
                    pass
        except Exception:
            pass

    def emit(
        self,
        message: str,
        *,
        level: str = "info",
        event_type: str = "custom",
        payload: Optional[dict] = None,
    ) -> None:
        if not self.run_id:
            return
        try:
            from services import pipeline_db_service as _pdb
            _pdb.emit_event(
                self.run_id,
                message,
                step_run_id=self._current_step_run_id,
                level=level,
                event_type=event_type,
                payload=payload,
            )
        except Exception:
            pass

    def skip_step(self, step_name: str, reason: str) -> None:
        self.begin_step(step_name)
        self.finish_step(step_name, status="skipped", skip_reason=reason)
        self.emit(f"SKIP {step_name}: {reason}", event_type="skip")

    @property
    def current_step_run_id(self) -> int:
        return self._current_step_run_id


# ---------------------------------------------------------------------------
# Step output paths – used for idempotency checks.
# Per-user DB-based steps use a DB check instead of a file check;
# they are NOT listed here so that step_output_exists() always returns False
# (forcing the scheduler to check the DB via _db_step_done()).
# ---------------------------------------------------------------------------
STEP_OUTPUT_PATHS = {
    # ---- Shared phase (file-based, user-independent) ----
    "arxiv_search":                  lambda d: os.path.join(ROOT, DATA_ROOT, "arxivList", "md", f"{d}.md"),
    "paperList_remove_duplications": lambda d: os.path.join(ROOT, DATA_ROOT, "paperList_remove_duplications", f"{d}.json"),
    "pdf_download":                  lambda d: os.path.join(ROOT, DATA_ROOT, "raw_pdf", d, "_manifest.json"),
    "pdf_split":                     lambda d: os.path.join(ROOT, DATA_ROOT, "preview_pdf", d, "_manifest.json"),
    "pdfsplite_to_minerU":           lambda d: os.path.join(ROOT, DATA_ROOT, "preview_pdf_to_mineru", d, "_manifest.json"),
    # ---- Legacy file-based paths (kept for backward-compat single-user mode) ----
    "llm_select_theme":     lambda d: os.path.join(ROOT, DATA_ROOT, "llm_select_theme", f"{d}.json"),
    "paper_theme_filter":   lambda d: os.path.join(ROOT, DATA_ROOT, "paper_theme_filter", f"{d}.json"),
    "pdf_info":             lambda d: os.path.join(ROOT, DATA_ROOT, "pdf_info", f"{d}.json"),
    "instutions_filter":    lambda d: os.path.join(ROOT, DATA_ROOT, "instutions_filter", d, f"{d}.json"),
    "selectpaper":          lambda d: os.path.join(ROOT, DATA_ROOT, "selectedpaper", d, "_manifest.json"),
    "selectedpaper_to_mineru": lambda d: os.path.join(ROOT, DATA_ROOT, "selectedpaper_to_mineru", d, "_manifest.json"),
    "paper_summary":        lambda d: os.path.join(ROOT, DATA_ROOT, "paper_summary", "single", d),
    "summary_limit":        lambda d: os.path.join(ROOT, DATA_ROOT, "summary_limit", "single", d),
    "select_image":         lambda d: os.path.join(ROOT, DATA_ROOT, "select_image", d, f"select_image_{d}.json"),
    "file_collect":         lambda d: os.path.join(ROOT, DATA_ROOT, "file_collect", d),
    "paper_assets":         lambda d: os.path.join(ROOT, DATA_ROOT, "paper_assets", f"{d}.jsonl"),
    # ---- Inspiration pipeline sentinels ----
    "idea_ingest":   lambda d: os.path.join(ROOT, DATA_ROOT, "idea_ingest",   f"{d}.jsonl"),
    "idea_combine":  lambda d: os.path.join(ROOT, DATA_ROOT, "idea_combine",  f"{d}.jsonl"),
    "idea_review":   lambda d: os.path.join(ROOT, DATA_ROOT, "idea_review",   f"{d}.jsonl"),
    "idea_compound": lambda d: os.path.join(ROOT, DATA_ROOT, "idea_compound", f"{d}.jsonl"),
}

# ---------------------------------------------------------------------------
# DB-mode idempotency check for per-user steps
# ---------------------------------------------------------------------------

def _db_step_done(step: str, user_id: int, date_str: str) -> bool:
    """
    Return True when the DB already contains output for *step* / *user_id* / *date_str*.
    Only used when --output-mode db is active.
    """
    try:
        import sys as _sys
        _sys.path.insert(0, ROOT)
        from services import pipeline_db_service as _pdb
        if step == "llm_select_theme":
            return _pdb.has_theme_scores(user_id, date_str)
        if step in ("paper_theme_filter", "instutions_filter", "selectpaper"):
            return _pdb.has_final_selections(user_id, date_str)
        if step == "pdf_info":
            return _pdb.has_paper_info(user_id, date_str)
        if step in ("paper_summary",):
            return _pdb.has_summaries_raw(user_id, date_str)
        if step in ("summary_limit",):
            return _pdb.has_summaries_limit(user_id, date_str)
        if step == "paper_assets":
            return _pdb.has_paper_assets(user_id, date_str)
    except Exception:
        pass
    return False


STEPS = {
    "arxiv_search":                  [sys.executable, "-u", os.path.join(ROOT, "Controller", "arxiv_search04.py")],
    "paperList_remove_duplications": [sys.executable, "-u", os.path.join(ROOT, "Controller", "paperList_remove_duplications.py")],
    "llm_select_theme":              [sys.executable, "-u", os.path.join(ROOT, "Controller", "llm_select_theme.py")],
    "paper_theme_filter":            [sys.executable, "-u", os.path.join(ROOT, "Controller", "paper_theme_filter.py")],
    "pdf_download":                  [sys.executable, "-u", os.path.join(ROOT, "Controller", "pdf_download.py")],
    "pdf_split":                     [sys.executable, "-u", os.path.join(ROOT, "Controller", "pdf_split.py")],
    "pdfsplite_to_minerU":           [sys.executable, "-u", os.path.join(ROOT, "Controller", "pdfsplite_to_minerU.py")],
    "pdf_info":                      [sys.executable, "-u", os.path.join(ROOT, "Controller", "pdf_info.py")],
    "instutions_filter":             [sys.executable, "-u", os.path.join(ROOT, "Controller", "instutions_filter.py")],
    "selectpaper":                   [sys.executable, "-u", os.path.join(ROOT, "Controller", "selectpaper.py")],
    "selectedpaper_to_mineru":       [sys.executable, "-u", os.path.join(ROOT, "Controller", "selectedpaper_to_mineru.py")],
    "paper_summary":                 [sys.executable, "-u", os.path.join(ROOT, "Controller", "paper_summary.py")],
    "summary_limit":                 [sys.executable, "-u", os.path.join(ROOT, "Controller", "summary_limit.py")],
    "select_image":                  [sys.executable, "-u", os.path.join(ROOT, "Controller", "select_image.py")],
    "file_collect":                  [sys.executable, "-u", os.path.join(ROOT, "Controller", "file_collect.py")],
    "paper_assets":                  [sys.executable, "-u", os.path.join(ROOT, "Controller", "paper_assets.py")],
    "zotero_push":                   [sys.executable, "-u", os.path.join(ROOT, "Controller", "zotero_push.py")],
    # Inspiration v2 pipeline steps
    "idea_ingest":   [sys.executable, "-u", os.path.join(ROOT, "Controller", "idea_ingest.py")],
    "idea_combine":  [sys.executable, "-u", os.path.join(ROOT, "Controller", "idea_combine.py")],
    "idea_review":   [sys.executable, "-u", os.path.join(ROOT, "Controller", "idea_review.py")],
    "idea_compound": [sys.executable, "-u", os.path.join(ROOT, "Controller", "idea_compound.py")],
    # Cleanup: deletes intermediate / deprecated / DB-replaced files to save disk space
    "cleanup":       [sys.executable, "-u", os.path.join(ROOT, "Controller", "cleanup.py")],
}

# ---------------------------------------------------------------------------
# Pipeline definitions
# ---------------------------------------------------------------------------

# Shared phase: user-independent data acquisition.
# pdf_download now reads ALL deduped papers (not just theme-filtered ones).
SHARED_STEPS = [
    "arxiv_search",
    "paperList_remove_duplications",
    "pdf_download",
    "pdf_split",
    "pdfsplite_to_minerU",
    # Full MinerU conversion for ALL downloaded PDFs (shared-cache mode).
    # Must run ONCE before per-user phases to avoid parallel MinerU API calls
    # and concurrent writes to full_mineru_cache/<date>/.
    "selectedpaper_to_mineru",
    # Cleanup: delete intermediate files (preview_pdf, preview_pdf_to_mineru)
    # and deprecated directories (file_collect, selectedpaper, selectedpaper_to_mineru old dates).
    # Runs at the end of the shared phase when all per-user-independent cleanup is safe.
    "cleanup",
]

# Per-user phase: LLM-dependent steps that vary by user config.
# Outputs are written to DB (--output-mode db).
# selectpaper / file_collect are intentionally OMITTED – replaced by DB queries.
# selectedpaper_to_mineru is intentionally OMITTED – runs in shared phase.
PER_USER_STEPS = [
    "llm_select_theme",
    "paper_theme_filter",
    "pdf_info",
    "instutions_filter",
    "paper_summary",
    "summary_limit",
    "paper_assets",
    # Inspiration pipeline
    "idea_ingest",
    "idea_combine",
    "idea_review",
    "idea_compound",
    # Deep cleanup: remove files now in DB, slim mineru cache, delete unselected PDFs,
    # and (if idea is done) remove full_mineru_cache entirely.
    "cleanup",
]

PIPELINES = {
    # ---- New multi-user pipeline ----
    # "shared" phase: run once per day to fetch/download raw data.
    "shared": SHARED_STEPS,
    # "per_user" phase: run for each user with output-mode=db.
    "per_user": PER_USER_STEPS,

    # ---- Legacy single-user pipelines (kept for manual runs / backward compat) ----
    # NOTE: "selectpaper" and "file_collect" are DEPRECATED.
    #   - selectpaper: paper selection is now handled by paper_theme_filter +
    #     instutions_filter writing directly to pipeline_db (--output-mode db).
    #   - file_collect: the file_collect directory tree is no longer the primary
    #     data source; data_service.py reads from pipeline_db first, then falls
    #     back to file_collect for pre-migration dates.
    # These steps remain here only so that existing deployments that run the
    # legacy "default" or "daily" pipeline continue to work unchanged.
    "default": [
        "arxiv_search",
        "paperList_remove_duplications",
        "llm_select_theme",
        "paper_theme_filter",
        "pdf_download",
        "pdf_split",
        "pdfsplite_to_minerU",
        "pdf_info",
        "instutions_filter",
        "selectpaper",            # DEPRECATED – use DB pipeline instead
        "selectedpaper_to_mineru",
        "paper_summary",
        "summary_limit",
        "select_image",
        "file_collect",           # DEPRECATED – use DB pipeline instead
        "paper_assets",
        "zotero_push",
        "idea_ingest",
        "idea_combine",
        "idea_review",
        "idea_compound",
    ],
    "daily": [
        "arxiv_search",
        "paperList_remove_duplications",
        "llm_select_theme",
        "paper_theme_filter",
        "pdf_download",
        "pdf_split",
        "pdfsplite_to_minerU",
        "pdf_info",
        "instutions_filter",
        "selectpaper",            # DEPRECATED – use DB pipeline instead
        "selectedpaper_to_mineru",
        "paper_summary",
        "summary_limit",
        "select_image",
        "file_collect",           # DEPRECATED – use DB pipeline instead
        "paper_assets",
        "zotero_push",
        "idea_ingest",
        "idea_combine",
        "idea_review",
        "idea_compound",
    ],
    # Standalone idea pipeline (can be run independently)
    "idea": [
        "idea_ingest",
        "idea_combine",
        "idea_review",
        "idea_compound",
    ],
}

# Steps that accept --user-id for per-user config overrides
_USER_ID_STEPS = {
    "llm_select_theme", "paper_theme_filter", "pdf_info", "instutions_filter",
    "paper_assets", "paper_summary", "summary_limit",
    "idea_ingest", "idea_combine", "idea_review", "idea_compound",
}

# Steps that accept --output-mode db
_DB_OUTPUT_STEPS = {
    "llm_select_theme", "paper_theme_filter", "pdf_info", "instutions_filter",
    "paper_summary", "summary_limit", "paper_assets",
}

# Idea pipeline steps: these already write to idea_service DB regardless of --output-mode.
# In per-user DB mode, skip the file-based sentinel check and let the controllers
# handle per-user idempotency themselves via the idea_service DB.
_IDEA_STEPS = {"idea_ingest", "idea_combine", "idea_review", "idea_compound"}

# Steps where a non-zero exit code should NOT abort the entire pipeline.
# These steps handle partial success internally (write a manifest with per-item
# statuses) so downstream steps can skip missing items gracefully.
# MinerU controllers return zero when they produced at least one usable result.
# A non-zero exit therefore means there is no safe downstream input and must
# abort the shared phase so the scheduler can retry instead of recording a
# false-success day.
SOFT_FAIL_STEPS: set = set()

# arxiv_search exit code when partial pages were saved after rate limit (see arxiv_rate_limit.py)
ARXIV_EXIT_RATE_LIMIT_PARTIAL = 3

# Cleanup modes to pass depending on which pipeline is running.
#
# shared pipeline:
#   - intermediate: delete preview_pdf/{date}/ (no longer needed after pdfsplite_to_minerU)
#   - deprecated:   delete file_collect, selectedpaper, selectedpaper_to_mineru (legacy)
#   NOTE: preview_pdf_to_mineru is intentionally NOT deleted here because the
#   per_user pdf_info step still needs it.  Use 'preview-mineru' in per_user (uid=0).
#
# per_user pipeline (uid=0 only — runs last, after all users' pdf_info is done):
#   - db-replaced:   delete small JSON files now stored in DB
#   - preview-mineru: delete preview_pdf_to_mineru now that all pdf_info is done in DB
#   - raw-pdf:       delete unselected PDFs from raw_pdf
#   - slim-mineru:   disabled for now to preserve MinerU bundles for KB reuse
#   - post-idea:     disabled for now to preserve full_mineru_cache for KB reuse
#   - select-image:  delete summary JSON now that image list is in DB
#
# per_user pipeline (non-zero uid):
#   - db-replaced only (lightweight, data check before deletion)
_CLEANUP_MODES = {
    "shared":          "intermediate,deprecated",
    "per_user_uid0":   "db-replaced,preview-mineru,raw-pdf,select-image",
    "per_user_nonzero": "db-replaced",
}


def step_output_exists(step: str, date_str: str) -> bool:
    if step not in STEP_OUTPUT_PATHS:
        return False
    path = STEP_OUTPUT_PATHS[step](date_str)
    if os.path.isfile(path):
        return True
    if os.path.isdir(path):
        return True
    return False


def step_output_remove(step: str, date_str: str) -> bool:
    """Delete the output file/directory for *step* on *date_str*.
    Returns True if something was actually removed."""
    if step not in STEP_OUTPUT_PATHS:
        return False
    path = STEP_OUTPUT_PATHS[step](date_str)
    try:
        if os.path.isfile(path):
            os.remove(path)
            return True
        if os.path.isdir(path):
            shutil.rmtree(path)
            return True
    except OSError as exc:
        print(f"WARN: failed to remove output for {step}: {exc}", flush=True)
    return False


def run_step(name, extra_args=None, env=None, recorder: Optional["PipelineRecorder"] = None):
    if name not in STEPS:
        raise SystemExit(f"Unknown step: {name}")
    cmd = STEPS[name] + (extra_args or [])

    if recorder:
        recorder.begin_step(name)

    is_soft = name in SOFT_FAIL_STEPS
    try:
        if is_soft:
            r = subprocess.run(cmd, env=env)
            if r.returncode != 0:
                print(
                    f"[WARN] step '{name}' exited with code {r.returncode}；"
                    f"该步骤支持部分成功，流水线继续执行",
                    flush=True,
                )
                if recorder:
                    recorder.finish_step(
                        name,
                        status="soft_failed",
                        exit_code=r.returncode,
                        error_type="soft_fail",
                        error_message=f"exit code {r.returncode}",
                    )
            else:
                if recorder:
                    recorder.finish_step(name, status="completed", exit_code=0)
        else:
            r = subprocess.run(cmd, env=env)
            if name == "arxiv_search" and r.returncode == ARXIV_EXIT_RATE_LIMIT_PARTIAL:
                print(
                    "[WARN] arxiv_search 因 arXiv 限流(429) 仅部分拉取成功；"
                    "已保存已获取的论文列表。建议冷却 15–30 分钟后再重跑 arxiv_search，"
                    "流水线将继续后续步骤。",
                    flush=True,
                )
                if recorder:
                    recorder.finish_step(
                        name,
                        status="partial",
                        exit_code=r.returncode,
                        error_type="rate_limit_partial",
                        error_message="partial fetch after 429",
                    )
            elif r.returncode != 0:
                raise subprocess.CalledProcessError(r.returncode, cmd)
            else:
                if recorder:
                    recorder.finish_step(name, status="completed", exit_code=0)
    except subprocess.CalledProcessError as exc:
        if recorder:
            recorder.finish_step(
                name,
                status="failed",
                exit_code=exc.returncode,
                error_type="subprocess_error",
                error_message=f"step '{name}' exited with code {exc.returncode}",
            )
            recorder.emit(
                f"FAIL {name}: exit code {exc.returncode}",
                level="error",
                event_type="custom",
            )
        raise
    except Exception as exc:
        if recorder:
            recorder.finish_step(
                name,
                status="failed",
                exit_code=-1,
                error_type="exception",
                error_message=str(exc)[:500],
            )
            recorder.emit(
                f"FAIL {name}: {exc}",
                level="error",
                event_type="custom",
            )
        raise
    return r.returncode


def detect_selected_count():
    data_root = os.path.join(ROOT, "data", "arxivList", "md")
    if not os.path.isdir(data_root):
        return None
    files = [os.path.join(data_root, f) for f in os.listdir(data_root) if f.endswith(".md")]
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    latest = files[0]
    try:
        with open(latest, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("- Selected"):
                    parts = line.split("**")
                    if len(parts) >= 2:
                        try:
                            return int(parts[1])
                        except ValueError:
                            return None
    except OSError:
        return None
    return None


def _parse_flag(extra: list, flag: str, has_value: bool = True):
    """Pop a flag (and its optional value) from extra. Returns (value_or_True, new_extra)."""
    if flag not in extra:
        return None, extra
    idx = extra.index(flag)
    if has_value and idx + 1 < len(extra):
        value = extra[idx + 1]
        return value, extra[:idx] + extra[idx + 2:]
    return True, extra[:idx] + extra[idx + 1:]


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    pipeline = "default"
    extra = []
    if argv:
        pipeline = argv[0]
        extra = list(argv[1:])

    # Parse --date
    run_date = os.environ.get("RUN_DATE") or datetime.now().date().isoformat()
    v, extra = _parse_flag(extra, "--date")
    if v:
        run_date = v

    # Parse --SLLM
    sllm_value = os.environ.get("SLLM")
    v, extra = _parse_flag(extra, "--SLLM")
    if v:
        try:
            iv = int(v)
        except (ValueError, TypeError):
            iv = None
        if iv in (1, 2, 3):
            sllm_value = str(iv)

    # Parse --user-id
    user_id_value = os.environ.get("PIPELINE_USER_ID")
    v, extra = _parse_flag(extra, "--user-id")
    if v:
        user_id_value = v

    # Parse --output-mode (file|db)
    output_mode = os.environ.get("PIPELINE_OUTPUT_MODE", "file")
    v, extra = _parse_flag(extra, "--output-mode")
    if v:
        output_mode = v

    # Parse --Zo
    zo_value = os.environ.get("ZO", "F")
    v, extra = _parse_flag(extra, "--Zo")
    if v:
        raw = (v or "").strip().upper()
        if raw in ("T", "F"):
            zo_value = raw

    # Parse --force
    force = False
    v, extra = _parse_flag(extra, "--force", has_value=False)
    if v:
        force = True

    # Parse --run-id (DB run id supplied by pipeline_router for observability)
    run_id_str = os.environ.get("PIPELINE_RUN_ID", "0")
    v, extra = _parse_flag(extra, "--run-id")
    if v:
        run_id_str = v

    # Parse --phase (shared|per_user|legacy)
    phase_value = os.environ.get("PIPELINE_PHASE", "")
    v, extra = _parse_flag(extra, "--phase")
    if v:
        phase_value = v

    # Parse --trigger (manual|scheduled|cli)
    trigger_value = os.environ.get("PIPELINE_TRIGGER", "cli")
    v, extra = _parse_flag(extra, "--trigger")
    if v:
        trigger_value = v

    # Parse --from-step (resume from a specific step name)
    from_step_value = os.environ.get("PIPELINE_FROM_STEP", "")
    v, extra = _parse_flag(extra, "--from-step")
    if v:
        from_step_value = v

    # Parse --only-step (run a single step then stop)
    only_step_value = os.environ.get("PIPELINE_ONLY_STEP", "")
    v, extra = _parse_flag(extra, "--only-step")
    if v:
        only_step_value = v

    zo_value = (zo_value or "F").strip().upper()
    if zo_value not in ("T", "F"):
        zo_value = "F"

    _sever_root = os.path.abspath(ROOT)
    _existing_pp = os.environ.get("PYTHONPATH", "")
    _new_pp = _sever_root if _sever_root not in _existing_pp.split(os.pathsep) else _existing_pp
    if _existing_pp and _sever_root not in _existing_pp.split(os.pathsep):
        _new_pp = _sever_root + os.pathsep + _existing_pp
    env = {**os.environ, "RUN_DATE": run_date, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": _new_pp}
    if sllm_value is not None:
        env["SLLM"] = sllm_value
    if user_id_value is not None:
        env["PIPELINE_USER_ID"] = str(user_id_value)
    if output_mode:
        env["PIPELINE_OUTPUT_MODE"] = output_mode

    # Resolve identifiers before --from-step dependency checks. Targeted CLI
    # reruns commonly omit --run-id; they must still work with observability
    # disabled instead of referencing an uninitialized local variable.
    try:
        uid_int = int(user_id_value) if user_id_value else 0
    except (ValueError, TypeError):
        uid_int = 0
    try:
        run_id_int = int(run_id_str) if run_id_str else 0
    except (ValueError, TypeError):
        run_id_int = 0
    recorder = PipelineRecorder(
        run_id=run_id_int,
        phase=phase_value,
        user_id=uid_int,
        date_str=run_date,
    )

    steps = PIPELINES.get(pipeline)
    if not steps:
        raise SystemExit(f"Unknown pipeline: {pipeline}")

    # Remove zotero_push unless explicitly enabled
    if zo_value != "T":
        steps = [s for s in steps if s != "zotero_push"]
    else:
        steps = list(steps)

    # Apply --from-step: skip everything before (and including the skipped prefix)
    if from_step_value and from_step_value in steps:
        start_idx = steps.index(from_step_value)
        # Dependency check: warn if any file-output step before from_step is missing
        _missing_deps = []
        for dep_step in steps[:start_idx]:
            if dep_step in STEP_OUTPUT_PATHS:
                dep_path = STEP_OUTPUT_PATHS[dep_step](run_date)
                if not os.path.exists(dep_path):
                    print(
                        f"[PIPELINE][WARN] --from-step dependency check: output of '{dep_step}' "
                        f"not found at {dep_path}. Step may fail if it requires this input.",
                        flush=True,
                    )
                    _missing_deps.append(dep_step)
        if _missing_deps and run_id_int:
            recorder.emit(
                f"dependency warning: {_missing_deps}",
                level="warning",
                event_type="custom",
                payload={"missing_deps": _missing_deps, "from_step": from_step_value},
            )
        steps = steps[start_idx:]
        print(f"[PIPELINE] --from-step: resuming from '{from_step_value}' ({len(steps)} step(s) remain)", flush=True)

    # Apply --only-step: run a single step
    if only_step_value and only_step_value in steps:
        steps = [only_step_value]
        print(f"[PIPELINE] --only-step: running only '{only_step_value}'", flush=True)

    print(
        f"START pipeline '{pipeline}' with {len(steps)} step(s) "
        f"RUN_DATE={run_date} Zo={zo_value} force={force} "
        f"output_mode={output_mode} user_id={user_id_value}",
        flush=True,
    )

    # Apply step config filter.
    # Skipped for --from-step / --only-step reruns so manual step reruns
    # are never blocked by the admin step config.
    disabled_by_config: set = set()
    if not from_step_value and not only_step_value:
        try:
            from services.pipeline_step_config_service import get_enabled_steps as _gec
            steps, disabled_by_config = _gec(pipeline, steps)
            if disabled_by_config:
                print(
                    f"[PIPELINE] Step config: skipping disabled steps: {sorted(disabled_by_config)}",
                    flush=True,
                )
                for _ds in disabled_by_config:
                    recorder.skip_step(_ds, "disabled_by_step_config")
        except Exception as _sce:
            print(
                f"[PIPELINE] Warning: step config unavailable, running all steps: {_sce!r}",
                flush=True,
            )

    pipeline_error: Optional[str] = None
    try:
        for i, step in enumerate(steps):
            if i == 0:
                step_args = list(extra)
            else:
                step_args = []

            # Forward --user-id to supported steps
            if user_id_value and step in _USER_ID_STEPS:
                step_args.extend(["--user-id", str(user_id_value)])

            # Forward --output-mode db to supported steps
            if output_mode == "db" and step in _DB_OUTPUT_STEPS:
                step_args.extend(["--output-mode", "db"])

            # For cleanup step: pass the appropriate --mode based on pipeline and user.
            if step == "cleanup":
                if pipeline == "shared":
                    cleanup_mode = _CLEANUP_MODES["shared"]
                elif pipeline == "per_user":
                    if uid_int == 0:
                        cleanup_mode = _CLEANUP_MODES["per_user_uid0"]
                    else:
                        cleanup_mode = _CLEANUP_MODES["per_user_nonzero"]
                else:
                    cleanup_mode = "intermediate,deprecated"
                step_args.extend(["--mode", cleanup_mode])

            # Idempotency check
            skipped = False
            if output_mode == "db" and step in _DB_OUTPUT_STEPS:
                if not force and _db_step_done(step, uid_int, run_date):
                    print(f"SKIP step: {step} (DB output exists for user={uid_int} date={run_date})", flush=True)
                    recorder.skip_step(step, f"DB output exists for user={uid_int} date={run_date}")
                    skipped = True
            elif output_mode == "db" and step in _IDEA_STEPS:
                pass  # idea controllers handle idempotency themselves
            else:
                if step_output_exists(step, run_date):
                    if force:
                        step_output_remove(step, run_date)
                        print(f"FORCE step: {step} (removed old output for {run_date})", flush=True)
                        recorder.emit(f"FORCE {step}: removed old output", event_type="custom")
                    else:
                        print(f"SKIP step: {step} (output exists for {run_date})", flush=True)
                        recorder.skip_step(step, f"output exists for {run_date}")
                        skipped = True

            if skipped:
                continue

            print(f"RUN step: {step}", flush=True)
            recorder.emit(f"RUN step: {step}", event_type="custom")
            run_step(step, step_args, env=env, recorder=recorder)

            if step == "arxiv_search":
                selected = detect_selected_count()
                if selected == 0:
                    print("[PIPELINE] No papers selected in current window; stop after arxiv_search.", flush=True)
                    try:
                        sys.path.insert(0, ROOT)
                        from services import pipeline_db_service as _pdb
                        _run_date_dt = datetime.strptime(run_date, "%Y-%m-%d")
                        weekday = _run_date_dt.weekday()
                        if weekday in (5, 6):
                            _notice_type = "no_papers_weekend"
                            _notice_msg = "今天是周末，ArXiv 不发布新论文。"
                        else:
                            _notice_type = "no_papers_empty"
                            _notice_msg = "今天 ArXiv 在您关注的领域暂无新论文（搜索窗口内无结果）。"
                        _pdb.upsert_date_notice(uid_int, run_date, _notice_type, _notice_msg)
                        print(f"[PIPELINE] Wrote date notice: {_notice_type} for {run_date}", flush=True)
                        recorder.emit(
                            f"no papers: {_notice_type}",
                            level="warning",
                            event_type="paper_count",
                            payload={"notice_type": _notice_type},
                        )
                    except Exception as _ne:
                        print(f"[PIPELINE] Could not write date notice: {_ne!r}", flush=True)
                    return

    except Exception as exc:
        pipeline_error = str(exc)
        raise
    finally:
        if run_id_int:
            PipelineRecorder.end_run(
                run_id_int,
                success=(pipeline_error is None),
                error=pipeline_error or "",
            )


if __name__ == "__main__":
    main()
