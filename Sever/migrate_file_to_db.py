"""
migrate_file_to_db.py
=====================
One-off migration script: reads legacy file-based pipeline outputs and
populates the pipeline DB tables (paper_analysis.db) as user_id=0 rows.

Only dates that do NOT already have DB rows are migrated (idempotent).

Migrated data sources (all under Sever/data/):
  llm_select_theme/{date}.json       → pipeline_theme_scores
  instutions_filter/{date}/{date}.json → pipeline_selected_papers (is_final=1)
  pdf_info/{date}.json               → pipeline_paper_info
  paper_summary/single/{date}/*.md   → pipeline_summaries.summary_raw
  summary_limit/single/{date}/*.md   → pipeline_summaries.summary_limit
  paper_assets/{date}.jsonl          → pipeline_paper_assets

A synthetic pipeline_runs row (run_type='user', user_id=0, status='completed')
is created for every migrated date.

Usage:
    cd Sever
    python migrate_file_to_db.py                 # migrate all dates
    python migrate_file_to_db.py --date 2026-01-21  # single date
    python migrate_file_to_db.py --dry-run       # preview only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# ── project root setup ────────────────────────────────────────────────────────
_SEVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SEVER_DIR))

from services import pipeline_db_service as _pdb  # noqa: E402

_DATA_ROOT = _SEVER_DIR / "data"

# ── helpers ───────────────────────────────────────────────────────────────────

def _read_json(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def _extract_arxiv_id(source: str) -> str:
    """Pull 'YYYY.NNNNN' from an arxiv source string."""
    m = re.search(r"(\d{4}\.\d{4,5})", source or "")
    return m.group(1) if m else ""


def _parse_headline(md_text: str) -> str:
    """Extract the first non-empty line of a summary-limit .md as headline."""
    for line in (md_text or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


# ── per-date migration ────────────────────────────────────────────────────────

def migrate_date(date_str: str, *, dry_run: bool = False) -> bool:
    """
    Migrate all file-based data for *date_str* to the DB as user_id=0.
    Returns True if anything was written (or would be written in dry_run).
    """
    USER_ID = 0

    # ── 1. Theme scores ───────────────────────────────────────────────────────
    theme_path = _DATA_ROOT / "llm_select_theme" / f"{date_str}.json"
    theme_data = _read_json(theme_path)
    scores: dict[str, float] = {}
    if theme_data:
        items = theme_data if isinstance(theme_data, list) else theme_data.get("papers", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            pid = _extract_arxiv_id(str(item.get("source") or item.get("arxiv_id") or ""))
            if not pid:
                pid = str(item.get("arxiv_id") or "")
            score = item.get("theme_relevant_score", item.get("score"))
            if pid and score is not None:
                try:
                    scores[pid] = float(score)
                except (ValueError, TypeError):
                    pass

    # ── 2. Selected papers (institutions_filter output) ──────────────────────
    inst_path = _DATA_ROOT / "instutions_filter" / date_str / f"{date_str}.json"
    inst_data = _read_json(inst_path)
    selected_arxiv_ids: set[str] = set()
    if isinstance(inst_data, list):
        for item in inst_data:
            if not isinstance(item, dict):
                continue
            pid = _extract_arxiv_id(str(item.get("source") or ""))
            if pid:
                selected_arxiv_ids.add(pid)

    # ── 3. PDF info ───────────────────────────────────────────────────────────
    pdf_info_path = _DATA_ROOT / "pdf_info" / f"{date_str}.json"
    pdf_info_raw = _read_json(pdf_info_path)
    pdf_info_map: dict[str, dict] = {}
    if isinstance(pdf_info_raw, list):
        for item in pdf_info_raw:
            if not isinstance(item, dict):
                continue
            pid = _extract_arxiv_id(str(item.get("source") or ""))
            if pid:
                pdf_info_map[pid] = item

    # ── 4. Summaries (raw) ────────────────────────────────────────────────────
    summary_dir = _DATA_ROOT / "paper_summary" / "single" / date_str
    summaries_raw: dict[str, str] = {}
    if summary_dir.is_dir():
        for md_file in summary_dir.glob("*.md"):
            pid = md_file.stem
            summaries_raw[pid] = md_file.read_text(encoding="utf-8", errors="ignore")

    # ── 5. Summaries (limit) ──────────────────────────────────────────────────
    limit_dir = _DATA_ROOT / "summary_limit" / "single" / date_str
    summaries_limit: dict[str, str] = {}
    if limit_dir.is_dir():
        for md_file in limit_dir.glob("*.md"):
            pid = md_file.stem
            summaries_limit[pid] = md_file.read_text(encoding="utf-8", errors="ignore")

    # ── 6. Paper assets ───────────────────────────────────────────────────────
    assets_path = _DATA_ROOT / "paper_assets" / f"{date_str}.jsonl"
    assets_raw = _read_jsonl(assets_path)
    assets_map: dict[str, dict] = {}
    for item in assets_raw:
        pid = item.get("paper_id") or item.get("arxiv_id") or ""
        if not pid:
            # try extracting from url
            pid = _extract_arxiv_id(str(item.get("url") or ""))
        if pid:
            assets_map[pid] = item

    # ── Collect all arxiv IDs ─────────────────────────────────────────────────
    all_ids: set[str] = (
        set(scores)
        | selected_arxiv_ids
        | set(pdf_info_map)
        | set(summaries_raw)
        | set(summaries_limit)
        | set(assets_map)
    )

    if not all_ids:
        print(f"  [{date_str}] No data found in any source – skipping.")
        return False

    print(
        f"  [{date_str}] Found: {len(scores)} scores, {len(selected_arxiv_ids)} selected, "
        f"{len(pdf_info_map)} pdf_info, {len(summaries_raw)} summaries_raw, "
        f"{len(summaries_limit)} summaries_limit, {len(assets_map)} assets  "
        f"(total unique papers: {len(all_ids)})"
    )

    if dry_run:
        print(f"  [{date_str}] DRY-RUN: would migrate {len(all_ids)} papers")
        return True

    # ── Already migrated? ─────────────────────────────────────────────────────
    if _pdb.has_theme_scores(USER_ID, date_str) or _pdb.has_final_selections(USER_ID, date_str):
        print(f"  [{date_str}] Already in DB – skipping (use --force to re-import)")
        return False

    # ── Write to DB ───────────────────────────────────────────────────────────

    # pipeline_runs record
    run_id = _pdb.create_run(
        run_type="user",
        user_id=USER_ID,
        date_str=date_str,
        pipeline="daily",
        config={"migrated_from": "file", "migration_script": "migrate_file_to_db.py"},
    )
    _pdb.update_run_status(run_id, "running")

    try:
        # Theme scores
        if scores:
            _pdb.bulk_upsert_theme_scores(USER_ID, date_str, scores)

        # Paper info
        if pdf_info_map:
            info_rows = []
            for pid, info in pdf_info_map.items():
                info_rows.append({
                    "paper_arxiv_id": pid,
                    "title": info.get("title", ""),
                    "institution": info.get("instution", info.get("institution", "")),
                    "is_large": bool(info.get("is_large", False)),
                    "abstract": info.get("abstract", ""),
                    "published": info.get("published", ""),
                    "source": info.get("source", ""),
                    "extra": {},
                })
            _pdb.bulk_upsert_paper_info(USER_ID, date_str, info_rows)

        # Selected papers
        if selected_arxiv_ids or scores:
            sel_rows = []
            for pid in all_ids:
                is_final = pid in selected_arxiv_ids
                sel_rows.append({
                    "paper_arxiv_id": pid,
                    "theme_score": scores.get(pid),
                    "passed_theme_filter": int(bool(scores.get(pid, 0) and scores[pid] > 0)),
                    "passed_institution_filter": int(is_final),
                    "is_final_selected": int(is_final),
                })
            _pdb.bulk_upsert_selected_papers(USER_ID, date_str, sel_rows)

        # Summaries
        if summaries_raw or summaries_limit:
            all_sum_ids = set(summaries_raw) | set(summaries_limit)
            sum_rows_raw = [
                {
                    "paper_arxiv_id": pid,
                    "summary_raw": summaries_raw.get(pid, ""),
                    "headline": _parse_headline(summaries_limit.get(pid, "")),
                }
                for pid in all_sum_ids
                if summaries_raw.get(pid)
            ]
            if sum_rows_raw:
                _pdb.bulk_upsert_summaries_raw(USER_ID, date_str, sum_rows_raw)

            for pid in all_sum_ids:
                lim = summaries_limit.get(pid, "")
                if lim:
                    _pdb.upsert_summary_limit(
                        USER_ID, date_str, pid,
                        summary_limit=lim,
                        headline=_parse_headline(lim),
                    )

        # Paper assets
        if assets_map:
            asset_rows = []
            for pid, item in assets_map.items():
                blocks = item.get("blocks", item.get("assets", []))
                if isinstance(blocks, str):
                    try:
                        blocks = json.loads(blocks)
                    except json.JSONDecodeError:
                        blocks = []
                asset_rows.append({
                    "paper_arxiv_id": pid,
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "year": item.get("year"),
                    "blocks": blocks if isinstance(blocks, list) else [],
                })
            _pdb.bulk_upsert_paper_assets(USER_ID, date_str, asset_rows)

        _pdb.update_run_status(run_id, "completed")
        print(f"  [{date_str}] Migration complete (run_id={run_id})")

    except Exception as exc:
        _pdb.update_run_status(run_id, "failed", error=str(exc))
        print(f"  [{date_str}] Migration FAILED: {exc!r}")
        return False

    return True


# ── date discovery ────────────────────────────────────────────────────────────

def discover_dates() -> list[str]:
    """
    Find all dates that have at least one of:
      - llm_select_theme/{date}.json
      - instutions_filter/{date}/{date}.json
      - pdf_info/{date}.json
      - paper_summary/single/{date}/
      - summary_limit/single/{date}/
      - paper_assets/{date}.jsonl
      - file_collect/{date}/
    """
    dates: set[str] = set()

    def _scan_json_dir(d: Path) -> None:
        if not d.is_dir():
            return
        for f in d.iterdir():
            m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.json", f.name)
            if m:
                dates.add(m.group(1))

    def _scan_date_subdirs(d: Path) -> None:
        if not d.is_dir():
            return
        for sd in d.iterdir():
            if sd.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", sd.name):
                dates.add(sd.name)

    _scan_json_dir(_DATA_ROOT / "llm_select_theme")
    _scan_json_dir(_DATA_ROOT / "pdf_info")
    _scan_json_dir(_DATA_ROOT / "paper_assets")
    _scan_date_subdirs(_DATA_ROOT / "instutions_filter")
    _scan_date_subdirs(_DATA_ROOT / "paper_summary" / "single")
    _scan_date_subdirs(_DATA_ROOT / "summary_limit" / "single")
    _scan_date_subdirs(_DATA_ROOT / "file_collect")

    return sorted(dates)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Migrate legacy file-based pipeline data into the pipeline DB (user_id=0)."
    )
    ap.add_argument("--date", default="", help="Migrate a single YYYY-MM-DD date only.")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing to DB.")
    ap.add_argument("--force", action="store_true",
                    help="Re-import even if DB already has data for a date (NOT IMPLEMENTED; "
                         "currently idempotent by skipping existing dates).")
    args = ap.parse_args()

    if args.date:
        dates = [args.date.strip()]
    else:
        dates = discover_dates()

    if not dates:
        print("No dated data found in data/ directories. Nothing to migrate.")
        return

    print(
        f"{'DRY-RUN: ' if args.dry_run else ''}Migrating {len(dates)} date(s) "
        f"to {_pdb._DB_PATH} …"
    )
    migrated = 0
    skipped = 0
    for date_str in dates:
        result = migrate_date(date_str, dry_run=args.dry_run)
        if result:
            migrated += 1
        else:
            skipped += 1

    print(
        f"\nDone. Migrated={migrated}  Skipped/empty={skipped}"
        + ("  (DRY-RUN – nothing written)" if args.dry_run else "")
    )


if __name__ == "__main__":
    main()
