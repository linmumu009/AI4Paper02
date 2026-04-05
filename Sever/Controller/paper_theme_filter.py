from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

ROOT = Path(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, str(ROOT))

from config.config import DATA_ROOT  # noqa: E402


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("paper_theme_filter")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    log_root = ROOT / "logs" / datetime.now().strftime("%Y-%m-%d")
    log_root.mkdir(parents=True, exist_ok=True)
    log_file = log_root / (datetime.now().strftime("%H%M%S") + "_paper_theme_filter.log")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s " + fmt._fmt))
    logger.addHandler(fh)
    return logger


def find_latest_json(root: Path, explicit: Optional[str]) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise SystemExit(f"json not found: {p}")
        return p
    if not root.exists():
        raise SystemExit(f"json dir not found: {root}")
    files = sorted([p for p in root.glob("*.json") if p.is_file()])
    if not files:
        raise SystemExit(f"no json in {root}")
    return files[-1]


def load_json_papers(path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    try:
        obj = json.loads(text) if text else {}
    except json.JSONDecodeError:
        obj = {}
    if isinstance(obj, dict):
        papers = obj.get("papers") or []
    elif isinstance(obj, list):
        papers = obj
        obj = {"papers": papers}
    else:
        papers = []
        obj = {"papers": papers}
    papers = [p for p in papers if isinstance(p, dict)]
    return obj, papers


def run() -> None:
    logger = setup_logging()
    print("============开始主题相关性过滤==============", flush=True)
    ap = argparse.ArgumentParser("paper_theme_filter")
    ap.add_argument("--json", default=None, help="input json from llm_select_theme")
    ap.add_argument("--outdir", default=None, help="output dir (default data/paper_theme_filter)")
    ap.add_argument("--threshold", type=float, default=0.85, help="score threshold to keep (default 0.85)")
    ap.add_argument("--user-id", type=int, default=None,
                    help="user id; required when --output-mode db to key DB records")
    ap.add_argument("--output-mode", default=None, choices=["file", "db"],
                    help="output mode: 'file' (default) writes JSON; 'db' writes to pipeline_selected_papers table")
    args = ap.parse_args()

    output_mode = args.output_mode or os.environ.get("PIPELINE_OUTPUT_MODE", "file")
    run_date = os.environ.get("RUN_DATE") or datetime.utcnow().date().isoformat()

    if output_mode == "db":
        uid = args.user_id if args.user_id is not None else 0
        # Read scores from DB
        try:
            sys.path.insert(0, str(ROOT))
            from services import pipeline_db_service as _pdb
            date_str = run_date
            db_scores = _pdb.get_theme_scores(uid, date_str)
            if not db_scores:
                # In DB mode there is no valid fallback: reading the latest file
                # would silently inject data from a previous date's run.
                # Log clearly and exit cleanly so the pipeline shows a real warning
                # rather than appearing to succeed with stale data.
                logger.warning(
                    "[DB] No theme scores in DB for user=%s date=%s — skipping theme filter "
                    "(llm_select_theme may not have run yet for this date)",
                    uid, date_str,
                )
                # Write a date notice so the frontend can show an informational card
                try:
                    from services import pipeline_db_service as _pdb
                    _pdb.upsert_date_notice(
                        uid, date_str,
                        "no_matching_papers",
                        "今天没有符合您个性化筛选条件的论文。",
                    )
                except Exception as _ne:
                    logger.warning("Could not write date notice: %r", _ne)
                print(f"[INFO] Kept: 0, Filtered: 0 (no DB scores for {date_str})", flush=True)
                print("============结束主题相关性过滤==============", flush=True)
                return
            else:
                rows_to_write = []
                kept_count = 0
                for arxiv_id, score in db_scores.items():
                    passed = score >= args.threshold
                    rows_to_write.append({
                        "paper_arxiv_id": arxiv_id,
                        "theme_score": score,
                        "passed_theme_filter": int(passed),
                        # Initialize downstream flags for first insert so NOT NULL
                        # columns are always populated in DB mode.
                        "passed_institution_filter": 0,
                        "is_final_selected": 0,
                    })
                    if passed:
                        kept_count += 1
                _pdb.bulk_upsert_selected_papers(uid, date_str, rows_to_write)
                logger.info("[DB] Saved %d theme filter records (%d passed) for user=%s date=%s",
                            len(rows_to_write), kept_count, uid, date_str)
                print(f"[INFO] Kept: {kept_count}, Filtered: {len(rows_to_write) - kept_count}", flush=True)
                # If no papers passed the threshold, write a notice for the frontend
                if kept_count == 0:
                    try:
                        _pdb.upsert_date_notice(
                            uid, date_str,
                            "no_matching_papers",
                            "今天的论文均未达到您的相关性阈值，暂无推荐。",
                        )
                    except Exception as _ne:
                        logger.warning("Could not write date notice: %r", _ne)
                print("============结束主题相关性过滤==============", flush=True)
                return
        except Exception as exc:
            # Only fall back to file mode if the pipeline_db_service module itself
            # could not be imported (infrastructure failure). Any other DB error
            # (missing data, connection issue, etc.) should surface immediately
            # rather than silently reading a stale file from a previous date.
            import_failed = isinstance(exc, (ImportError, ModuleNotFoundError))
            if import_failed:
                logger.error("DB theme filter: pipeline_db_service unavailable: %r — falling back to file", exc)
                output_mode = "file"
            else:
                logger.error("DB theme filter failed: %r — aborting (not falling back to stale file)", exc)
                raise SystemExit(1)

    # ---- File mode (default / legacy) ----
    input_dir = ROOT / DATA_ROOT / "llm_select_theme"
    json_path = find_latest_json(input_dir, args.json)

    # Derive date_str from filename
    date_str = run_date
    stem = json_path.stem
    if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
        date_str = stem

    out_dir = Path(args.outdir) if args.outdir else ROOT / DATA_ROOT / "paper_theme_filter"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / Path(json_path.name).with_suffix(".json").name

    meta_obj, papers = load_json_papers(json_path)
    if not papers:
        out_path.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.warning("No paper records found; wrote original json to %s", out_path)
        return

    kept: List[Dict[str, Any]] = []
    total = len(papers)
    for idx, p in enumerate(papers, 1):
        score = float(p.get("theme_relevant_score", 0.0) or 0.0)
        if score >= float(args.threshold):
            kept.append(p)
        sys.stdout.write(f"\r[PROGRESS] filtering {idx}/{total}")
        sys.stdout.flush()
    print()

    kept_count = len(kept)
    filtered_count = total - kept_count
    meta_obj["papers"] = kept
    meta_obj["selected"] = kept_count
    meta_obj["generated_utc"] = datetime.utcnow().isoformat() + "Z"
    out_path.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved: %s", out_path)
    print(f"[INFO] Kept: {kept_count}, Filtered: {filtered_count}", flush=True)
    print("============结束主题相关性过滤==============", flush=True)


if __name__ == "__main__":
    run()
