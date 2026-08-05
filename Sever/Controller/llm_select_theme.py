from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

ROOT = Path(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, str(ROOT))

from openai import OpenAI
from services.llm_request_options import build_thinking_kwargs
from services.llm_response_guard import (
    InvalidLlmResponseError,
    require_nonempty_text,
)

from config.config import (  # noqa: E402
    DATA_ROOT,
    qwen_api_key,
    theme_select_base_url,
    theme_select_model,
    theme_select_max_tokens,
    theme_select_temperature,
    theme_select_concurrency,
    theme_select_system_prompt,
    PAPER_DEDUP_DIR,
)


# ---------------------------------------------------------------------------
# User-config helpers (same pattern as paper_summary / summary_limit)
# ---------------------------------------------------------------------------

def _load_user_config(user_id: int) -> Dict[str, Any]:
    try:
        from services.user_settings_service import get_settings
        return get_settings(user_id, "paper_recommend")
    except Exception:
        return {}


def _resolve_llm_preset(user_id: int, preset_id: Any) -> Dict[str, Any]:
    try:
        pid = int(preset_id)
    except (TypeError, ValueError):
        return {}
    try:
        from services.user_presets_service import get_llm_preset
        return get_llm_preset(user_id, pid) or {}
    except Exception:
        return {}


def _resolve_prompt_preset(user_id: int, preset_id: Any) -> str:
    try:
        pid = int(preset_id)
    except (TypeError, ValueError):
        return ""
    try:
        from services.user_presets_service import get_prompt_preset
        p = get_prompt_preset(user_id, pid)
        return (p or {}).get("prompt_content", "")
    except Exception:
        return ""


def make_client_for_user(user_id: Optional[int] = None) -> Tuple[Any, Dict[str, Any]]:
    """Return (client, effective_cfg) honouring user overrides when *user_id* is given.

    effective_cfg keys: model, temperature, max_tokens, system_prompt.
    Falls back to config.py values when no user preset is found.
    """
    import config.config as _sys_cfg_ts
    # Global defaults
    key: str = (qwen_api_key or "").strip()
    base: str = (theme_select_base_url or "").strip() or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_name: str = theme_select_model or ""
    temperature = theme_select_temperature
    max_tokens = theme_select_max_tokens
    sys_prompt: str = theme_select_system_prompt or ""
    enable_thinking: bool = False
    use_pool: bool = bool(getattr(_sys_cfg_ts, "theme_select_use_openrouter_free_pool", False))

    if user_id is not None:
        ucfg = _load_user_config(user_id)
        if ucfg:
            # Module-specific preset first, then generic fallback
            preset_id = ucfg.get("theme_select_llm_preset_id") or ucfg.get("llm_preset_id")
            preset = _resolve_llm_preset(user_id, preset_id) if preset_id else {}
            if preset:
                key = (preset.get("api_key") or key).strip()
                base = (preset.get("base_url") or base).strip()
                model_name = (preset.get("model") or model_name).strip()
                enable_thinking = bool(preset.get("enable_thinking", False))
                if "use_openrouter_free_pool" in preset:
                    use_pool = bool(preset["use_openrouter_free_pool"])
                if preset.get("temperature") is not None:
                    temperature = preset["temperature"]
                if preset.get("max_tokens") is not None:
                    max_tokens = preset["max_tokens"]
            else:
                key = (ucfg.get("llm_api_key") or key).strip()
                base = (ucfg.get("llm_base_url") or base).strip()
                model_name = (ucfg.get("llm_model") or model_name).strip()
                if "use_openrouter_free_pool" in ucfg:
                    use_pool = bool(ucfg["use_openrouter_free_pool"])
                if ucfg.get("temperature") is not None:
                    temperature = ucfg["temperature"]
                if ucfg.get("max_tokens") is not None:
                    max_tokens = ucfg["max_tokens"]

            # Prompt override
            prompt_preset_id = ucfg.get("theme_select_prompt_preset_id")
            if prompt_preset_id:
                content = _resolve_prompt_preset(user_id, prompt_preset_id)
                if content:
                    sys_prompt = content
                else:
                    print(
                        f"[INFO] llm_select_theme: prompt preset id={prompt_preset_id} "
                        f"is empty for user {user_id}; using global default prompt.",
                        flush=True,
                    )
            else:
                print(
                    f"[INFO] llm_select_theme: no prompt preset configured for user {user_id}; "
                    "using global default prompt.",
                    flush=True,
                )

    if not key and not use_pool:
        raise SystemExit("theme_select: no api_key available (global config or user preset)")
    from services.llm_client_factory import build_llm_client
    effective_cfg = {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": sys_prompt,
        "llm_base_url": base,
        "enable_thinking": enable_thinking,
        "use_openrouter_free_pool": use_pool,
    }
    client = build_llm_client({"api_key": key, "base_url": base, "use_openrouter_free_pool": use_pool})
    return client, effective_cfg


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("llm_select_theme")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    log_root = ROOT / "logs" / datetime.now().strftime("%Y-%m-%d")
    log_root.mkdir(parents=True, exist_ok=True)
    log_file = log_root / (datetime.now().strftime("%H%M%S") + "_llm_select_theme.log")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s " + fmt._fmt))
    logger.addHandler(fh)
    return logger


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


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


@dataclass
class PaperRecord:
    title: str
    abstract: str
    arxiv_id: str


def make_client() -> OpenAI:
    """Legacy wrapper kept for compatibility; prefer make_client_for_user()."""
    client, _ = make_client_for_user(user_id=None)
    return client


def build_user_prompt(title: str, abstract: str) -> str:
    if abstract:
        return f"标题：{title}\n摘要：{abstract}"
    return f"标题：{title}\n摘要：无"


def parse_score(text: str) -> float:
    content = require_nonempty_text(text, operation="theme_relevance_scoring")
    m = re.search(
        r"(?<![\d.])(?:0(?:\.\d+)?|1(?:\.0+)?)(?![\d.])",
        content,
    )
    if not m:
        raise InvalidLlmResponseError(
            "model returned an unparseable theme relevance score"
        )
    try:
        val = float(m.group(0))
    except ValueError:
        raise InvalidLlmResponseError(
            "model returned an invalid theme relevance score"
        )
    return val


def score_one(client: OpenAI, block: PaperRecord, effective_cfg: Dict[str, Any]) -> float:
    user_content = build_user_prompt(block.title, block.abstract)
    kwargs: Dict[str, Any] = {}
    temp = effective_cfg.get("temperature")
    max_tok = effective_cfg.get("max_tokens")
    if temp is not None:
        kwargs["temperature"] = float(temp)
    if max_tok is not None:
        kwargs["max_tokens"] = int(max_tok)
    kwargs.update(build_thinking_kwargs(effective_cfg))
    resp = client.chat.completions.create(
        model=effective_cfg.get("model") or theme_select_model,
        messages=[
            {"role": "system", "content": effective_cfg.get("system_prompt") or theme_select_system_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        **kwargs,
    )
    content = resp.choices[0].message.content if resp.choices else ""
    return parse_score(content)


def run() -> None:
    logger = setup_logging()
    print("============开始主题相关性评分==============", flush=True)
    ap = argparse.ArgumentParser("llm_select_theme")
    ap.add_argument("--json", default=None, help="input json from paperList_remove_duplications")
    ap.add_argument("--outdir", default=None, help="output dir (default data/llm_select_theme)")
    ap.add_argument("--user-id", type=int, default=None, help="user id for per-user LLM/prompt preset override")
    ap.add_argument("--output-mode", default=None, choices=["file", "db"],
                    help="output mode: 'file' (default) writes JSON; 'db' writes to pipeline_theme_scores table")
    args = ap.parse_args()

    # --output-mode env fallback
    output_mode = args.output_mode or os.environ.get("PIPELINE_OUTPUT_MODE", "file")

    # Resolve run_date for DB keying
    run_date = os.environ.get("RUN_DATE") or datetime.utcnow().date().isoformat()

    input_dir = ROOT / PAPER_DEDUP_DIR
    date_str = run_date  # always key by RUN_DATE in DB mode

    if output_mode == "db" and not args.json:
        # DB mode: only process papers belonging to RUN_DATE.
        # Never fall back to the latest file from a different date – that would
        # silently re-score stale papers and write them under today's key.
        target_json = input_dir / f"{run_date}.json"
        if target_json.exists():
            json_path: Path = target_json
            meta_obj, papers = load_json_papers(json_path)
        else:
            # File for today doesn't exist yet; try loading directly from DB arxiv_list.
            try:
                sys.path.insert(0, str(ROOT))
                from services import pipeline_db_service as _pdb_init
                _arxiv_rows = _pdb_init.get_arxiv_list(run_date)
            except Exception as _db_init_err:
                logger.error("DB mode: cannot load arxiv_list for %s: %s", run_date, _db_init_err)
                _arxiv_rows = []
            if not _arxiv_rows:
                logger.warning(
                    "[DB] No papers in paperList_remove_duplications or pipeline_arxiv_list "
                    "for RUN_DATE=%s — skipping theme scoring. "
                    "Did the shared pipeline run successfully today?",
                    run_date,
                )
                print(f"[INFO] llm_select_theme: no papers for date={run_date}; skip", flush=True)
                print("============结束主题相关性评分==============", flush=True)
                return
            # Convert DB rows to the dict shape load_json_papers would produce
            papers = []
            for _r in _arxiv_rows:
                papers.append({
                    "arxiv_id": _r.get("paper_arxiv_id", ""),
                    "title": _r.get("title", ""),
                    "summary": _r.get("abstract_text", ""),
                    "categories": _r.get("paper_categories") or [],
                    "published": _r.get("published_utc", ""),
                })
            meta_obj: Dict[str, Any] = {"papers": papers}
            json_path = input_dir / f"{run_date}.json"  # used only for out_path name
        logger.info("[DB] Loaded %d papers for date=%s", len(papers), run_date)
    else:
        # File mode (or explicit --json): use find_latest_json as before
        json_path = find_latest_json(input_dir, args.json)
        meta_obj, papers = load_json_papers(json_path)
        # In file mode, derive date_str from the filename
        if output_mode != "db":
            stem = json_path.stem
            if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
                date_str = stem

    out_dir = Path(args.outdir) if args.outdir else ROOT / DATA_ROOT / "llm_select_theme"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}.json"

    # --- Per-user category filter ---
    # If the user has configured search_categories, only score papers whose arXiv
    # categories overlap with the user's selection. This avoids wasting LLM calls
    # on papers from categories the user never asked for.
    if args.user_id is not None:
        try:
            ucfg = _load_user_config(args.user_id)
            user_cats_raw = ucfg.get("search_categories")
            default_cats = ["cs.CL", "cs.LG", "cs.AI", "stat.ML"]
            try:
                from config import config as _cfg_mod
                default_cats = list(getattr(_cfg_mod, "SEARCH_CATEGORIES", default_cats) or default_cats)
            except Exception:
                pass
            user_cats: Optional[List[str]] = None
            if isinstance(user_cats_raw, list) and user_cats_raw:
                # Only apply filter when user has explicitly customised (differs from default)
                if sorted(user_cats_raw) != sorted(default_cats):
                    user_cats = [c.strip() for c in user_cats_raw if c.strip()]

            if user_cats:
                # Build paper_categories lookup from DB (DB mode) or from JSON field
                paper_cats_map: Dict[str, List[str]] = {}
                if output_mode == "db":
                    try:
                        sys.path.insert(0, str(ROOT))
                        from services import pipeline_db_service as _pdb
                        arxiv_rows = _pdb.get_arxiv_list(date_str)
                        for row in arxiv_rows:
                            pid = str(row.get("paper_arxiv_id", "")).strip()
                            if pid:
                                paper_cats_map[pid] = row.get("paper_categories") or []
                    except Exception as _pc_err:
                        logger.warning("Could not load paper_categories from DB: %s", _pc_err)
                else:
                    for p in papers:
                        pid = str(p.get("arxiv_id", "")).strip()
                        cats = p.get("categories") or []
                        if pid:
                            paper_cats_map[pid] = cats if isinstance(cats, list) else []

                user_cats_set = set(user_cats)
                before_count = len(papers)
                papers = [
                    p for p in papers
                    if not paper_cats_map.get(str(p.get("arxiv_id", "")).strip())
                    or bool(user_cats_set & set(paper_cats_map.get(str(p.get("arxiv_id", "")).strip(), [])))
                ]
                logger.info(
                    "Category filter [user=%s cats=%s]: %d → %d papers",
                    args.user_id, user_cats, before_count, len(papers),
                )
        except Exception as _filter_err:
            logger.warning("Category filter failed, scoring all papers: %s", _filter_err)

    records: List[PaperRecord] = []
    for p in papers:
        title = normalize_text(str(p.get("title", "")))
        abstract = normalize_text(str(p.get("summary", "")))
        arxiv_id = str(p.get("arxiv_id", "")).strip()
        records.append(PaperRecord(title=title, abstract=abstract, arxiv_id=arxiv_id))
    if not records:
        if output_mode != "db":
            out_path.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.warning("No paper records found; skip scoring")
        return

    client, effective_cfg = make_client_for_user(args.user_id)
    scores: Dict[str, float] = {}
    failed: set[str] = set()
    workers = max(1, int(theme_select_concurrency or 1))
    logger.info("Scoring %d paper(s) with %d worker(s) [user_id=%s output_mode=%s]",
                len(records), workers, args.user_id, output_mode)

    total = len(records)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(score_one, client, blk, effective_cfg): blk for blk in records}
        for future in as_completed(future_map):
            blk = future_map[future]
            key = blk.arxiv_id or blk.title
            try:
                score = future.result()
                scores[key] = score
            except Exception as exc:
                logger.warning("Score failed for %s: %r", blk.title, exc)
                failed.add(key)
            done += 1
            sys.stdout.write(f"\r[PROGRESS] scoring {done}/{total}")
            sys.stdout.flush()
            time.sleep(0.05)
    print()

    success_count = len(scores)
    fail_count = len(failed)
    if fail_count:
        logger.warning(
            "Theme scoring finished with %d success, %d failed (failed papers are not written as 0.0)",
            success_count, fail_count,
        )
    if success_count == 0 and total > 0:
        logger.error("All %d theme scores failed; aborting step", total)
        print("============结束主题相关性评分（全部失败）==============", flush=True)
        sys.exit(1)
    if total > 0 and fail_count / total > 0.5:
        logger.error(
            "Theme scoring failure rate %.0f%% exceeds 50%% (%d/%d); aborting step",
            100.0 * fail_count / total, fail_count, total,
        )
        print("============结束主题相关性评分（失败率过高）==============", flush=True)
        sys.exit(1)

    for p in papers:
        key = str(p.get("arxiv_id", "")).strip() or str(p.get("title", "")).strip()
        if key in scores:
            p["theme_relevant_score"] = round(float(scores[key]), 3)

    if output_mode == "db":
        # Write scores to DB
        uid = args.user_id if args.user_id is not None else 0
        try:
            sys.path.insert(0, str(ROOT))
            from services import pipeline_db_service as _pdb
            db_scores = {
                (str(p.get("arxiv_id", "")).strip() or str(p.get("title", "")).strip()):
                round(float(p.get("theme_relevant_score", 0.0) or 0.0), 3)
                for p in papers
                if (str(p.get("arxiv_id", "")).strip() or str(p.get("title", "")).strip())
                and "theme_relevant_score" in p
            }
            _pdb.bulk_upsert_theme_scores(uid, date_str, db_scores)
            logger.info("[DB] Saved %d theme scores for user=%s date=%s", len(db_scores), uid, date_str)
        except Exception as exc:
            logger.error("Failed to write theme scores to DB: %r — falling back to file", exc)
            output_mode = "file"

    if output_mode != "db":
        # File output (default / legacy / fallback)
        meta_obj["papers"] = papers
        meta_obj["selected"] = len(papers)
        meta_obj["generated_utc"] = datetime.utcnow().isoformat() + "Z"
        out_path.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved: %s", out_path)
    print("============结束主题相关性评分==============", flush=True)


if __name__ == "__main__":
    run()
