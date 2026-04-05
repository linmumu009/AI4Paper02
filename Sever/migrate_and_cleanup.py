"""
migrate_and_cleanup.py — One-time historical data migration and cleanup tool.

This script:
1. Migrates existing file-based select_image data to the DB (pipeline_images)
2. Migrates existing arxivList JSON data to the DB (pipeline_arxiv_list)
3. Cleans up all historical dates using cleanup.py logic

Usage:
    # Preview what would be done (safe, no changes)
    python migrate_and_cleanup.py --dry-run

    # Migrate data to DB and clean up deprecated/intermediate files
    python migrate_and_cleanup.py --migrate --cleanup

    # Migrate only (no deletion)
    python migrate_and_cleanup.py --migrate

    # Cleanup only (requires data already in DB)
    python migrate_and_cleanup.py --cleanup --mode all

    # Specific date
    python migrate_and_cleanup.py --date 2026-04-01 --migrate --cleanup
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Sever root
_SEVER_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SEVER_ROOT)

from config.config import DATA_ROOT
from Controller.cleanup import (
    ALL_MODES,
    _DATA_ROOT,
    _list_dates,
    run_cleanup,
)

_DATA_PATH = Path(DATA_ROOT)


# ---------------------------------------------------------------------------
# Migration: select_image → pipeline_images
# ---------------------------------------------------------------------------

def migrate_select_image_to_db(date_str: str, dry_run: bool = False) -> int:
    """
    Read per-paper image directories from select_image/<date>/<arxiv_id>/ and
    insert filenames into pipeline_images DB table.
    Returns number of papers migrated.
    """
    try:
        from services.pipeline_db_service import bulk_upsert_paper_images, has_images
    except Exception as exc:
        print(f"[MIGRATE] ERROR: could not import pipeline_db_service: {exc}", flush=True)
        return 0

    if has_images(date_str):
        print(f"[MIGRATE] select_image DB already has data for {date_str}, skipping", flush=True)
        return 0

    date_dir = _DATA_PATH / "select_image" / date_str
    if not date_dir.is_dir():
        return 0

    images_map: dict[str, list[str]] = {}

    # First try reading the summary JSON for metadata
    summary_json = date_dir / f"select_image_{date_str}.json"
    if summary_json.is_file():
        try:
            with open(summary_json, encoding="utf-8") as f:
                summary = json.load(f)
            for report in summary.get("reports", []):
                stem = report.get("stem")
                if not stem or report.get("error"):
                    continue
                out_dir = Path(report.get("output_dir", ""))
                if out_dir.is_dir():
                    imgs = sorted(
                        p.name for p in out_dir.iterdir()
                        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif")
                    )
                    if imgs:
                        images_map[stem] = imgs
        except Exception as exc:
            print(f"[MIGRATE] WARNING: failed to parse {summary_json}: {exc}", flush=True)

    # Also scan per-paper directories directly (catches cases where summary is missing)
    for paper_dir in date_dir.iterdir():
        if not paper_dir.is_dir():
            continue
        arxiv_id = paper_dir.name
        if arxiv_id in images_map:
            continue
        imgs = sorted(
            p.name for p in paper_dir.iterdir()
            if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif")
        )
        if imgs:
            images_map[arxiv_id] = imgs

    if not images_map:
        print(f"[MIGRATE] No image data found for {date_str}", flush=True)
        return 0

    print(
        f"[MIGRATE] select_image→DB: {date_str}: {len(images_map)} papers "
        f"({'dry-run' if dry_run else 'writing'})",
        flush=True,
    )
    if not dry_run:
        bulk_upsert_paper_images(date_str, images_map)
    return len(images_map)


# ---------------------------------------------------------------------------
# Migration: arxivList JSON → pipeline_arxiv_list
# ---------------------------------------------------------------------------

def migrate_arxiv_list_to_db(date_str: str, dry_run: bool = False) -> int:
    """
    Read arxivList/json/<date>.json and insert papers into pipeline_arxiv_list DB table.
    Returns number of papers migrated.
    """
    try:
        from services.pipeline_db_service import bulk_upsert_arxiv_list, has_arxiv_list
    except Exception as exc:
        print(f"[MIGRATE] ERROR: could not import pipeline_db_service: {exc}", flush=True)
        return 0

    if has_arxiv_list(date_str):
        print(f"[MIGRATE] arxiv_list DB already has data for {date_str}, skipping", flush=True)
        return 0

    json_path = _DATA_PATH / "arxivList" / "json" / f"{date_str}.json"
    if not json_path.is_file():
        return 0

    try:
        with open(json_path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        print(f"[MIGRATE] WARNING: failed to parse {json_path}: {exc}", flush=True)
        return 0

    papers_raw = payload.get("papers", [])
    if not papers_raw:
        return 0

    db_papers = []
    categories_str = payload.get("search_query", "")
    for p in papers_raw:
        db_papers.append({
            "paper_arxiv_id": p.get("arxiv_id", ""),
            "title": p.get("title", ""),
            "abstract_text": p.get("summary", ""),
            "authors": p.get("authors", []),
            "published_utc": p.get("published_utc", ""),
            "link": p.get("link", ""),
            "categories": [],  # not stored per-paper in the JSON file
        })

    db_papers = [p for p in db_papers if p["paper_arxiv_id"]]

    print(
        f"[MIGRATE] arxiv_list→DB: {date_str}: {len(db_papers)} papers "
        f"({'dry-run' if dry_run else 'writing'})",
        flush=True,
    )
    if not dry_run:
        bulk_upsert_arxiv_list(date_str, db_papers)
    return len(db_papers)


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def print_disk_usage() -> None:
    """Print disk usage of each data subdirectory."""
    print("\n[DISK USAGE] Sever/data/ subdirectories:", flush=True)
    total = 0
    rows = []
    for d in sorted(_DATA_PATH.iterdir()):
        if not d.is_dir():
            continue
        size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        total += size
        rows.append((size, d.name))
    rows.sort(reverse=True)
    for size, name in rows:
        print(f"  {name:<40} {size / 1024 / 1024:>8.2f} MB", flush=True)
    print(f"  {'TOTAL':<40} {total / 1024 / 1024:>8.2f} MB", flush=True)
    print(flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "One-time migration and cleanup tool for ArxivPaper4.\n"
            "Migrates file-based data to DB and removes redundant files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--date", default="", help="Target date (YYYY-MM-DD). Default: all dates.")
    ap.add_argument("--migrate", action="store_true", help="Migrate file data to DB")
    ap.add_argument("--cleanup", action="store_true", help="Run cleanup after migration")
    ap.add_argument(
        "--mode",
        default="intermediate,deprecated,db-replaced,select-image",
        help=(
            f"Cleanup modes (comma-separated or 'all'). Valid: {ALL_MODES}. "
            "Default: intermediate,deprecated,db-replaced,select-image"
        ),
    )
    ap.add_argument("--dry-run", action="store_true", help="Preview only, no actual changes")
    ap.add_argument("--disk-usage", action="store_true", help="Print disk usage and exit")
    args = ap.parse_args()

    if args.disk_usage:
        print_disk_usage()
        return

    if not args.migrate and not args.cleanup:
        print(
            "[ERROR] Specify at least one action: --migrate and/or --cleanup\n"
            "Use --dry-run to preview changes safely.\n"
            "Use --disk-usage to see current disk usage.",
            flush=True,
        )
        ap.print_help()
        sys.exit(1)

    # Resolve dates
    if args.date:
        dates = [args.date.strip()]
    else:
        date_set: set[str] = set()
        for subdir in (
            "arxivList/json", "select_image",
            "preview_pdf", "preview_pdf_to_mineru",
            "file_collect", "selectedpaper", "selectedpaper_to_mineru",
            "full_mineru_cache", "raw_pdf",
        ):
            target = _DATA_PATH / subdir
            if target.is_dir():
                for d in target.iterdir():
                    if d.is_dir() and len(d.name) == 10 and d.name[4] == "-":
                        date_set.add(d.name)
            # Also handle flat JSON files like arxivList/json/2026-04-01.json
            elif target.parent.is_dir():
                for f in target.parent.glob(f"{target.name}/*.json"):
                    name = f.stem
                    if len(name) == 10 and name[4] == "-":
                        date_set.add(name)
        # Scan for json files in arxivList/json/
        arxiv_json_dir = _DATA_PATH / "arxivList" / "json"
        if arxiv_json_dir.is_dir():
            for f in arxiv_json_dir.glob("*.json"):
                name = f.stem
                if len(name) == 10 and name[4] == "-":
                    date_set.add(name)
        dates = sorted(date_set)

    if not dates:
        print("[INFO] No dates found to process.", flush=True)
        return

    print(f"[INFO] Processing {len(dates)} date(s): {dates[0]} … {dates[-1]}", flush=True)
    if args.dry_run:
        print("[INFO] DRY-RUN mode: no files will be modified.", flush=True)

    # Resolve cleanup modes
    mode_str = args.mode.strip().lower()
    if mode_str == "all":
        modes = list(ALL_MODES)
    else:
        modes = [m.strip() for m in mode_str.split(",") if m.strip()]
    invalid = [m for m in modes if m not in ALL_MODES]
    if invalid:
        print(f"[ERROR] Unknown cleanup mode(s): {invalid}", flush=True)
        sys.exit(1)

    total_migrated_imgs = 0
    total_migrated_arxiv = 0
    total_freed = 0

    for date_str in dates:
        print(f"\n{'='*60}", flush=True)
        print(f"[INFO] Processing date: {date_str}", flush=True)

        if args.migrate:
            total_migrated_imgs += migrate_select_image_to_db(date_str, dry_run=args.dry_run)
            total_migrated_arxiv += migrate_arxiv_list_to_db(date_str, dry_run=args.dry_run)

        if args.cleanup:
            total_freed += run_cleanup(date_str, modes, dry_run=args.dry_run)

    print(f"\n{'='*60}", flush=True)
    print("[SUMMARY]", flush=True)
    if args.migrate:
        print(f"  Papers migrated (images): {total_migrated_imgs}", flush=True)
        print(f"  Papers migrated (arxiv):  {total_migrated_arxiv}", flush=True)
    if args.cleanup:
        print(f"  Total freed:              {total_freed / 1024 / 1024:.2f} MB", flush=True)
    if args.dry_run:
        print("  (dry-run: no files were actually modified)", flush=True)

    if args.cleanup and not args.dry_run:
        print("\n[DISK USAGE AFTER CLEANUP]", flush=True)
        print_disk_usage()


if __name__ == "__main__":
    main()
