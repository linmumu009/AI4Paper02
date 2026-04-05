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

from openai import OpenAI

ROOT = Path(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, str(ROOT))

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


def make_client_for_user(user_id: Optional[int] = None) -> Tuple[OpenAI, Dict[str, Any]]:
    """Return (client, effective_cfg) honouring user overrides when *user_id* is given.

    effective_cfg keys: model, temperature, max_tokens, system_prompt.
    Falls back to config.py values when no user preset is found.
    """
    # Global defaults
    key: str = (qwen_api_key or "").strip()
    base: str = (theme_select_base_url or "").strip() or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_name: str = theme_select_model or ""
    temperature = theme_select_temperature
    max_tokens = theme_select_max_tokens
    sys_prompt: str = theme_select_system_prompt or ""

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
                if preset.get("temperature") is not None:
                    temperature = preset["temperature"]
                if preset.get("max_tokens") is not None:
                    max_tokens = preset["max_tokens"]
            else:
                key = (ucfg.get("llm_api_key") or key).strip()
                base = (ucfg.get("llm_base_url") or base).strip()
                model_name = (ucfg.get("llm_model") or model_name).strip()
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

    if not key:
        raise SystemExit("theme_select: no api_key available (global config or user preset)")
    client = OpenAI(api_key=key, base_url=base)
    return client, {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": sys_prompt,
    }


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
    if not text:
        return 0.0
    m = re.search(r"([0-1](?:\.\d+)?)", text)
    if not m:
        return 0.0
    try:
        val = float(m.group(1))
    except ValueError:
        return 0.0
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
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
    json_path = find_latest_json(input_dir, args.json)

    # Derive date_str from filename (e.g. 2025-01-15.json) — but ONLY in file mode.
    # In DB mode we must always key by RUN_DATE so that downstream steps
    # (paper_theme_filter, pdf_info, …) can find the scores by the same key.
    # Overwriting date_str with the input filename date causes silent key drift
    # (e.g. latest dedup file is 2026-03-07.json but RUN_DATE=2026-03-10).
    date_str = run_date
    if output_mode != "db":
        stem = json_path.stem
        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
            date_str = stem

    out_dir = Path(args.outdir) if args.outdir else ROOT / DATA_ROOT / "llm_select_theme"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / Path(json_path.name).with_suffix(".json").name

    meta_obj, papers = load_json_papers(json_path)
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
    workers = max(1, int(theme_select_concurrency or 1))
    logger.info("Scoring %d paper(s) with %d worker(s) [user_id=%s output_mode=%s]",
                len(records), workers, args.user_id, output_mode)

    total = len(records)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(score_one, client, blk, effective_cfg): blk for blk in records}
        for future in as_completed(future_map):
            blk = future_map[future]
            try:
                score = future.result()
            except Exception as exc:
                logger.warning("Score failed for %s: %r", blk.title, exc)
                score = 0.0
            scores[blk.arxiv_id or blk.title] = score
            done += 1
            sys.stdout.write(f"\r[PROGRESS] scoring {done}/{total}")
            sys.stdout.flush()
            time.sleep(0.05)
    print()

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
                if str(p.get("arxiv_id", "")).strip() or str(p.get("title", "")).strip()
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
