"""
cleanup.py — Pipeline output cleanup script.

Deletes intermediate files, deprecated directories, and files already stored
in the database, safely verifying DB data exists before any deletion.

Usage (standalone):
    python cleanup.py --date 2026-04-01 [--dry-run]
    python cleanup.py --all-dates [--dry-run]
    python cleanup.py --date 2026-04-01 --mode intermediate,deprecated [--dry-run]

Usage (via app.py pipeline):
    Invoked automatically as the last step of the 'shared' pipeline.

Modes (comma-separated, or 'all'):
    intermediate   Delete pipeline intermediate files for date:
                   preview_pdf/<date>/ and preview_pdf_to_mineru/<date>/
    deprecated     Delete legacy deprecated directories for date:
                   file_collect/<date>/, selectedpaper/<date>/,
                   selectedpaper_to_mineru/<date>/
    db-replaced    Delete small JSON/MD files now stored in DB:
                   llm_select_theme, paper_theme_filter, pdf_info,
                   instutions_filter, paper_summary, summary_limit,
                   paper_assets, paperList_remove_duplications
                   (only if DB has confirmed data for that date)
    slim-mineru    Remove non-.md files inside full_mineru_cache/<date>/
                   keeping only <arxiv_id>.md per paper.
                   (only if DB has summaries for that date)
    post-idea      Delete full_mineru_cache/<date>/ entirely.
                   (only if idea steps are completed in DB)
    raw-pdf        Delete raw_pdf/<date>/<arxiv_id>.pdf for papers NOT
                   selected by any user. Keep selected papers' PDFs.
                   (only if DB has final selections for that date)
    select-image   Delete select_image/<date>/select_image_<date>.json
                   summary file (images_json already in DB).
                   Keeps the per-paper PNG directories.
    all            Run all modes above.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Allow importing from Sever root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.config import DATA_ROOT

_DATA_ROOT = Path(DATA_ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str, dry_run: bool = False) -> None:
    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"[CLEANUP] {prefix}{msg}", flush=True)


def _remove_path(path: Path, dry_run: bool) -> int:
    """Remove a file or directory. Returns bytes freed (approximate)."""
    if not path.exists():
        return 0
    try:
        if path.is_file() or path.is_symlink():
            size = path.stat().st_size
            if not dry_run:
                path.unlink()
            _log(f"Deleted file: {path}  ({size / 1024 / 1024:.2f} MB)", dry_run)
            return size
        elif path.is_dir():
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            if not dry_run:
                shutil.rmtree(path)
            _log(f"Deleted dir:  {path}  ({size / 1024 / 1024:.2f} MB)", dry_run)
            return size
    except OSError as exc:
        _log(f"ERROR removing {path}: {exc}", dry_run=False)
    return 0


def _remove_non_md_files(paper_dir: Path, dry_run: bool) -> int:
    """Remove all non-.md files (and subdirectories) within a paper directory."""
    if not paper_dir.is_dir():
        return 0
    freed = 0
    for item in list(paper_dir.iterdir()):
        if item.is_file() and item.suffix.lower() != ".md":
            freed += _remove_path(item, dry_run)
        elif item.is_dir():
            freed += _remove_path(item, dry_run)
    return freed


def _list_dates(data_root: Path, subdir: str) -> list[str]:
    """List date-named subdirectories inside data_root/subdir."""
    target = data_root / subdir
    if not target.is_dir():
        return []
    return sorted(
        d.name for d in target.iterdir()
        if d.is_dir() and len(d.name) == 10 and d.name[4] == "-"
    )


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------

def cleanup_intermediate(date_str: str, dry_run: bool = False) -> int:
    """Delete preview_pdf for the given date.

    IMPORTANT: preview_pdf_to_mineru is intentionally NOT deleted here.
    Although it is produced by the shared pipeline step pdfsplite_to_minerU,
    it is consumed by the per_user pipeline step pdf_info.  Deleting it during
    shared-pipeline cleanup causes pdf_info to fall back to an older date's
    directory, writing wrong-date records into the DB.

    Use the 'preview-mineru' mode instead, which only deletes
    preview_pdf_to_mineru after confirming that pdf_info data is in the DB.
    """
    freed = 0
    freed += _remove_path(_DATA_ROOT / "preview_pdf" / date_str, dry_run)
    return freed


def cleanup_preview_mineru(date_str: str, dry_run: bool = False) -> int:
    """
    Delete preview_pdf_to_mineru/<date>/ after confirming pdf_info data is in DB.

    This must NOT run during the shared pipeline phase.  It is safe only when
    ALL users' per_user pdf_info steps have completed for the given date.
    Run this via migrate_and_cleanup.py after all pipelines have finished.
    """
    try:
        from services.pipeline_db_service import has_paper_info
        if not has_paper_info(0, date_str):
            _log(
                f"SKIP preview-mineru for {date_str}: pdf_info not yet in DB "
                f"(run after all users' pdf_info steps complete)",
                dry_run=False,
            )
            return 0
    except Exception as exc:
        _log(f"SKIP preview-mineru for {date_str}: DB check failed: {exc}", dry_run=False)
        return 0

    return _remove_path(_DATA_ROOT / "preview_pdf_to_mineru" / date_str, dry_run)


def cleanup_deprecated(date_str: str, dry_run: bool = False) -> int:
    """Delete deprecated directories for the given date."""
    freed = 0
    freed += _remove_path(_DATA_ROOT / "file_collect" / date_str, dry_run)
    freed += _remove_path(_DATA_ROOT / "selectedpaper" / date_str, dry_run)
    freed += _remove_path(_DATA_ROOT / "selectedpaper_to_mineru" / date_str, dry_run)
    return freed


def cleanup_db_replaced(date_str: str, dry_run: bool = False) -> int:
    """
    Delete small JSON/MD files that have been replaced by DB entries.
    Skips deletion if DB does not have confirmed data for that date.
    """
    try:
        from services.pipeline_db_service import has_final_selections, has_paper_assets
        if not has_final_selections(0, date_str) and not has_paper_assets(0, date_str):
            _log(
                f"SKIP db-replaced for {date_str}: no DB data found "
                f"(pipeline may not have run in DB mode yet)",
                dry_run=False,
            )
            return 0
    except Exception as exc:
        _log(f"SKIP db-replaced for {date_str}: DB check failed: {exc}", dry_run=False)
        return 0

    freed = 0
    # Per-date JSON files
    freed += _remove_path(_DATA_ROOT / "llm_select_theme" / f"{date_str}.json", dry_run)
    freed += _remove_path(_DATA_ROOT / "paper_theme_filter" / f"{date_str}.json", dry_run)
    freed += _remove_path(_DATA_ROOT / "pdf_info" / f"{date_str}.json", dry_run)
    freed += _remove_path(_DATA_ROOT / "paper_assets" / f"{date_str}.jsonl", dry_run)
    freed += _remove_path(_DATA_ROOT / "paperList_remove_duplications" / f"{date_str}.json", dry_run)
    # Per-date directories
    freed += _remove_path(_DATA_ROOT / "instutions_filter" / date_str, dry_run)
    freed += _remove_path(_DATA_ROOT / "paper_summary" / "single" / date_str, dry_run)
    freed += _remove_path(_DATA_ROOT / "summary_limit" / "single" / date_str, dry_run)
    return freed


def cleanup_select_image_json(date_str: str, dry_run: bool = False) -> int:
    """
    Delete the select_image summary JSON file for a date (image filenames stored in DB).
    Keeps the per-paper PNG directories.
    """
    try:
        from services.pipeline_db_service import has_images
        if not has_images(date_str):
            _log(
                f"SKIP select-image for {date_str}: no image data found in DB",
                dry_run=False,
            )
            return 0
    except Exception as exc:
        _log(f"SKIP select-image for {date_str}: DB check failed: {exc}", dry_run=False)
        return 0

    summary_json = _DATA_ROOT / "select_image" / date_str / f"select_image_{date_str}.json"
    return _remove_path(summary_json, dry_run)


def cleanup_slim_mineru(date_str: str, dry_run: bool = False) -> int:
    """
    Remove non-.md files and subdirs within full_mineru_cache/<date>/<arxiv_id>/.
    Keeps the <arxiv_id>.md file which is needed by paper_summary and idea_ingest.
    Only runs if DB has summaries for that date.
    """
    try:
        from services.pipeline_db_service import has_summaries_limit
        if not has_summaries_limit(0, date_str):
            _log(
                f"SKIP slim-mineru for {date_str}: DB has no summaries yet",
                dry_run=False,
            )
            return 0
    except Exception as exc:
        _log(f"SKIP slim-mineru for {date_str}: DB check failed: {exc}", dry_run=False)
        return 0

    cache_date_dir = _DATA_ROOT / "full_mineru_cache" / date_str
    if not cache_date_dir.is_dir():
        return 0

    freed = 0
    for paper_dir in cache_date_dir.iterdir():
        if paper_dir.is_dir():
            freed += _remove_non_md_files(paper_dir, dry_run)
    return freed


def cleanup_post_idea(date_str: str, dry_run: bool = False) -> int:
    """
    Delete the entire full_mineru_cache/<date>/ directory.
    Only runs if the idea pipeline has completed (sentinel jsonl files exist).

    IMPORTANT: also deletes the selectedpaper_to_mineru/<date>/_manifest.json
    sentinel so that on the next pipeline execution, selectedpaper_to_mineru
    re-runs and regenerates full_mineru_cache.  Without this reset the step
    would be skipped (sentinel exists) but full_mineru_cache would be empty,
    causing paper_summary and idea_ingest to fail on any re-run.
    """
    # Check idea sentinel files (these are always file-based sentinels)
    idea_done = all(
        (_DATA_ROOT / d / f"{date_str}.jsonl").exists()
        for d in ("idea_ingest", "idea_combine", "idea_review", "idea_compound")
    )
    if not idea_done:
        _log(
            f"SKIP post-idea for {date_str}: idea pipeline not fully complete yet",
            dry_run=False,
        )
        return 0

    freed = _remove_path(_DATA_ROOT / "full_mineru_cache" / date_str, dry_run)

    # Reset the selectedpaper_to_mineru sentinel so the next run regenerates the cache
    sentinel = _DATA_ROOT / "selectedpaper_to_mineru" / date_str / "_manifest.json"
    if sentinel.exists():
        _log(
            f"Resetting sentinel {sentinel.name} in selectedpaper_to_mineru/{date_str}/ "
            f"so next run regenerates full_mineru_cache",
            dry_run,
        )
        freed += _remove_path(sentinel, dry_run)

    return freed


def cleanup_raw_pdf(date_str: str, dry_run: bool = False) -> int:
    """
    Delete PDFs from raw_pdf/<date>/ that are NOT selected by any user.
    Keeps PDFs for selected papers and the _manifest.json.
    Only runs if DB has final selections for that date.
    """
    try:
        from services.pipeline_db_service import has_final_selections, get_final_arxiv_ids
        if not has_final_selections(0, date_str):
            _log(
                f"SKIP raw-pdf for {date_str}: no final selections in DB",
                dry_run=False,
            )
            return 0
        selected_ids = set(get_final_arxiv_ids(0, date_str))
    except Exception as exc:
        _log(f"SKIP raw-pdf for {date_str}: DB check failed: {exc}", dry_run=False)
        return 0

    raw_pdf_dir = _DATA_ROOT / "raw_pdf" / date_str
    if not raw_pdf_dir.is_dir():
        return 0

    freed = 0
    for pdf_file in raw_pdf_dir.iterdir():
        if pdf_file.name == "_manifest.json":
            continue
        if not pdf_file.suffix.lower() == ".pdf":
            continue
        arxiv_id = pdf_file.stem
        if arxiv_id not in selected_ids:
            freed += _remove_path(pdf_file, dry_run)
    return freed


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

ALL_MODES = [
    "intermediate",
    "deprecated",
    "db-replaced",
    "preview-mineru",
    "select-image",
    "slim-mineru",
    "post-idea",
    "raw-pdf",
]

_MODE_FN = {
    "intermediate":  cleanup_intermediate,
    "deprecated":    cleanup_deprecated,
    "db-replaced":   cleanup_db_replaced,
    "preview-mineru": cleanup_preview_mineru,
    "select-image":  cleanup_select_image_json,
    "slim-mineru":   cleanup_slim_mineru,
    "post-idea":     cleanup_post_idea,
    "raw-pdf":       cleanup_raw_pdf,
}


def run_cleanup(
    date_str: str,
    modes: list[str],
    dry_run: bool = False,
) -> int:
    """Run the specified cleanup modes for a single date. Returns total bytes freed."""
    total_freed = 0
    _log(f"=== Cleanup date={date_str} modes={modes} dry_run={dry_run} ===", dry_run)
    for mode in modes:
        fn = _MODE_FN.get(mode)
        if fn is None:
            _log(f"WARNING: unknown mode '{mode}', skipping", dry_run=False)
            continue
        freed = fn(date_str, dry_run)
        total_freed += freed
    _log(f"=== Done date={date_str} freed={total_freed / 1024 / 1024:.2f} MB ===", dry_run)
    return total_freed


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Cleanup pipeline output files to save disk space"
    )
    ap.add_argument("--date", default="", help="Target date (YYYY-MM-DD)")
    ap.add_argument("--all-dates", action="store_true", help="Clean all available dates")
    ap.add_argument(
        "--mode",
        default="intermediate,deprecated",
        help=(
            "Comma-separated modes: "
            + ", ".join(ALL_MODES)
            + ". Use 'all' to run every mode."
        ),
    )
    ap.add_argument("--dry-run", action="store_true", help="Preview only, no actual deletion")
    args = ap.parse_args()

    # Resolve date(s)
    if args.all_dates:
        # Collect all dates from all relevant directories
        date_set: set[str] = set()
        for subdir in (
            "preview_pdf", "preview_pdf_to_mineru",
            "file_collect", "selectedpaper", "selectedpaper_to_mineru",
            "full_mineru_cache", "raw_pdf", "select_image",
        ):
            date_set.update(_list_dates(_DATA_ROOT, subdir))
        dates = sorted(date_set)
    else:
        date_str = (args.date or "").strip()
        if not date_str:
            date_str = os.environ.get("RUN_DATE", datetime.now().date().isoformat())
        dates = [date_str]

    # Resolve modes
    mode_str = args.mode.strip().lower()
    if mode_str == "all":
        modes = list(ALL_MODES)
    else:
        modes = [m.strip() for m in mode_str.split(",") if m.strip()]

    # Validate modes
    invalid = [m for m in modes if m not in _MODE_FN]
    if invalid:
        print(f"[CLEANUP] ERROR: unknown mode(s): {invalid}", flush=True)
        print(f"[CLEANUP] Valid modes: {ALL_MODES}", flush=True)
        sys.exit(1)

    grand_total = 0
    for date_str in dates:
        grand_total += run_cleanup(date_str, modes, dry_run=args.dry_run)

    print(
        f"[CLEANUP] Grand total freed: {grand_total / 1024 / 1024:.2f} MB "
        f"({'dry-run' if args.dry_run else 'actual'})",
        flush=True,
    )


if __name__ == "__main__":
    main()
