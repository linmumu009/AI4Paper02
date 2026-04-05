import os
import sys
import shutil
import subprocess
from datetime import datetime

ROOT = os.path.dirname(__file__)
DATA_ROOT = "data"

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
#   - slim-mineru:   remove non-.md files from full_mineru_cache to save space
#   - post-idea:     delete full_mineru_cache entirely (only if idea pipeline is done)
#   - select-image:  delete summary JSON now that image list is in DB
#
# per_user pipeline (non-zero uid):
#   - db-replaced only (lightweight, data check before deletion)
_CLEANUP_MODES = {
    "shared":          "intermediate,deprecated",
    "per_user_uid0":   "db-replaced,preview-mineru,raw-pdf,slim-mineru,post-idea,select-image",
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


def run_step(name, extra_args=None, env=None):
    if name not in STEPS:
        raise SystemExit(f"Unknown step: {name}")
    cmd = STEPS[name] + (extra_args or [])
    r = subprocess.run(cmd, check=True, env=env)
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


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    pipeline = "default"
    extra = []
    if argv:
        pipeline = argv[0]
        extra = list(argv[1:])

    # Parse --date
    run_date = os.environ.get("RUN_DATE") or datetime.now().date().isoformat()
    if "--date" in extra:
        idx = extra.index("--date")
        if idx + 1 < len(extra):
            run_date = extra[idx + 1]
            extra = extra[:idx] + extra[idx + 2:]

    # Parse --SLLM
    sllm_value = os.environ.get("SLLM")
    if "--SLLM" in extra:
        idx = extra.index("--SLLM")
        if idx + 1 < len(extra):
            raw = extra[idx + 1]
            try:
                iv = int(raw)
            except ValueError:
                iv = None
            if iv in (1, 2, 3):
                sllm_value = str(iv)
        extra = extra[:idx] + extra[idx + 2:]

    # Parse --user-id
    user_id_value = os.environ.get("PIPELINE_USER_ID")
    if "--user-id" in extra:
        idx = extra.index("--user-id")
        if idx + 1 < len(extra):
            user_id_value = extra[idx + 1]
        extra = extra[:idx] + extra[idx + 2:]

    # Parse --output-mode (file|db)
    output_mode = os.environ.get("PIPELINE_OUTPUT_MODE", "file")
    if "--output-mode" in extra:
        idx = extra.index("--output-mode")
        if idx + 1 < len(extra):
            output_mode = extra[idx + 1]
        extra = extra[:idx] + extra[idx + 2:]

    # Parse --Zo
    zo_value = os.environ.get("ZO", "F")
    if "--Zo" in extra:
        idx = extra.index("--Zo")
        if idx + 1 < len(extra):
            raw = (extra[idx + 1] or "").strip().upper()
            if raw in ("T", "F"):
                zo_value = raw
        extra = extra[:idx] + extra[idx + 2:]

    # Parse --force
    force = False
    if "--force" in extra:
        idx = extra.index("--force")
        force = True
        extra = extra[:idx] + extra[idx + 1:]

    zo_value = (zo_value or "F").strip().upper()
    if zo_value not in ("T", "F"):
        zo_value = "F"

    env = {**os.environ, "RUN_DATE": run_date, "PYTHONIOENCODING": "utf-8"}
    if sllm_value is not None:
        env["SLLM"] = sllm_value
    if user_id_value is not None:
        env["PIPELINE_USER_ID"] = str(user_id_value)
    if output_mode:
        env["PIPELINE_OUTPUT_MODE"] = output_mode

    steps = PIPELINES.get(pipeline)
    if not steps:
        raise SystemExit(f"Unknown pipeline: {pipeline}")

    # Remove zotero_push unless explicitly enabled
    if zo_value != "T":
        steps = [s for s in steps if s != "zotero_push"]
    else:
        steps = list(steps)

    print(
        f"START pipeline '{pipeline}' with {len(steps)} step(s) "
        f"RUN_DATE={run_date} Zo={zo_value} force={force} "
        f"output_mode={output_mode} user_id={user_id_value}",
        flush=True,
    )

    # Resolve user_id integer for DB checks
    try:
        uid_int = int(user_id_value) if user_id_value else 0
    except (ValueError, TypeError):
        uid_int = 0

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
        # preview_pdf_to_mineru is only deleted for uid=0 in per_user (after all
        # users' pdf_info has completed) to prevent parallel-user race conditions.
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
        if output_mode == "db" and step in _DB_OUTPUT_STEPS:
            # DB-based check: output already in DB for this user/date → skip
            if not force and _db_step_done(step, uid_int, run_date):
                print(f"SKIP step: {step} (DB output exists for user={uid_int} date={run_date})", flush=True)
                continue
        elif output_mode == "db" and step in _IDEA_STEPS:
            # Idea steps in DB mode: no file-sentinel check.
            # The controllers handle per-user idempotency internally via idea_service DB.
            pass
        else:
            # File-based check (shared steps and legacy / non-DB mode)
            if step_output_exists(step, run_date):
                if force:
                    step_output_remove(step, run_date)
                    print(f"FORCE step: {step} (removed old output for {run_date})", flush=True)
                else:
                    print(f"SKIP step: {step} (output exists for {run_date})", flush=True)
                    continue

        print(f"RUN step: {step}", flush=True)
        run_step(step, step_args, env=env)

        if step == "arxiv_search":
            selected = detect_selected_count()
            if selected == 0:
                print("[PIPELINE] No papers selected in current window; stop after arxiv_search.", flush=True)
                # Write a date notice so the frontend can show a helpful card
                # explaining why there are no papers for this date.
                try:
                    sys.path.insert(0, ROOT)
                    from services import pipeline_db_service as _pdb
                    _run_date_dt = datetime.strptime(run_date, "%Y-%m-%d")
                    weekday = _run_date_dt.weekday()  # 0=Mon … 6=Sun
                    if weekday in (5, 6):
                        _notice_type = "no_papers_weekend"
                        _notice_msg = "今天是周末，ArXiv 不发布新论文。"
                    else:
                        _notice_type = "no_papers_empty"
                        _notice_msg = "今天 ArXiv 在您关注的领域暂无新论文（搜索窗口内无结果）。"
                    _pdb.upsert_date_notice(uid_int, run_date, _notice_type, _notice_msg)
                    print(f"[PIPELINE] Wrote date notice: {_notice_type} for {run_date}", flush=True)
                except Exception as _ne:
                    print(f"[PIPELINE] Could not write date notice: {_ne!r}", flush=True)
                return


if __name__ == "__main__":
    main()
