import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Institution tier lookup helpers
# ---------------------------------------------------------------------------

def _load_tier_mapping() -> Dict[str, int]:
    """Load institution name -> tier (1-4) mapping from institution_tiers.json.

    Returns a dict keyed by institution short name (as output by LLM).
    Returns an empty dict if the file is not found or malformed.
    """
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
    tiers_path = os.path.join(config_dir, "institution_tiers.json")
    try:
        with open(tiers_path, encoding="utf-8") as f:
            data = json.load(f)
        tiers = data.get("tiers", {})
        mapping: Dict[str, int] = {}
        for tier_label, names in tiers.items():
            try:
                tier_num = int(tier_label.lstrip("T"))
            except (ValueError, AttributeError):
                continue
            for name in names:
                if name:
                    mapping[name] = tier_num
        return mapping
    except Exception as e:
        print(f"[WARN] Could not load institution_tiers.json: {e!r}", flush=True)
        return {}


# Cache at module level to avoid reloading on every paper
_TIER_MAPPING: Optional[Dict[str, int]] = None


def _get_tier_mapping() -> Dict[str, int]:
    global _TIER_MAPPING
    if _TIER_MAPPING is None:
        _TIER_MAPPING = _load_tier_mapping()
    return _TIER_MAPPING


def resolve_institution_tier(institution: str, llm_tier: Any, is_large: bool) -> int:
    """Determine the final institution_tier value.

    Priority:
    1. Static mapping table (keyed by standardized institution name)
    2. LLM-provided tier (validated to be 1-4)
    3. Fallback from is_large: True -> 3, False -> 4
    """
    mapping = _get_tier_mapping()

    # Try static mapping first
    if institution:
        mapped = mapping.get(institution)
        if mapped is not None:
            return mapped

    # Use LLM tier if valid
    try:
        t = int(llm_tier)
        if 1 <= t <= 4:
            # Enforce consistency: is_large=false must be tier 4
            if not is_large and t < 4:
                return 4
            return t
    except (TypeError, ValueError):
        pass

    # Fallback
    return 3 if is_large else 4

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.config import qwen_api_key as CFG_QWEN_KEY  # noqa: E402
from config.config import org_base_url as CFG_BASE_URL  # noqa: E402
from config.config import org_model as CFG_MODEL  # noqa: E402
from config.config import org_temperature as CFG_TEMPERATURE  # noqa: E402
from config.config import org_max_tokens as CFG_MAX_TOKENS  # noqa: E402
from config.config import pdf_info_system_prompt as CFG_INFO_PROMPT  # noqa: E402
from config.config import DATA_ROOT, PAPER_THEME_FILTER_DIR  # noqa: E402
from config.config import pdf_info_concurrency  # noqa: E402
from services.llm_response_guard import (  # noqa: E402
    InvalidLlmResponseError,
    require_nonempty_text,
)


# ---------------------------------------------------------------------------
# User-config helpers
# ---------------------------------------------------------------------------

def _load_user_config(user_id: int, feature: str = "paper_recommend") -> Dict[str, Any]:
    try:
        from services.user_settings_service import get_settings
        return get_settings(user_id, feature)
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


def _resolve_llm_for_user(user_id: Optional[int], feature: str = "paper_recommend") -> Dict[str, Any]:
    """Return effective LLM connection + prompt config for *user_id*.

    Falls back to global config when *user_id* is None or has no preset.
    Includes ``use_openrouter_free_pool`` so callers can build a pool-aware
    client via ``build_llm_client()``.
    """
    import config.config as _sys_cfg
    sys_use_pool = bool(getattr(_sys_cfg, "org_use_openrouter_free_pool", False))
    cfg = {
        "api_key": (CFG_QWEN_KEY or "").strip(),
        "base_url": (CFG_BASE_URL or "https://dashscope.aliyuncs.com/compatible-mode/v1").strip(),
        "model": (CFG_MODEL or "qwen-plus").strip(),
        "temperature": CFG_TEMPERATURE if CFG_TEMPERATURE is not None else 1.0,
        "max_tokens": CFG_MAX_TOKENS if CFG_MAX_TOKENS is not None else 1024,
        "system_prompt": (CFG_INFO_PROMPT or "").strip(),
        "use_openrouter_free_pool": sys_use_pool,
    }
    if user_id is None:
        return cfg

    ucfg = _load_user_config(user_id, feature)
    if not ucfg:
        return cfg

    # Module-specific preset first, then generic fallback, then cascade from first step
    preset_id = ucfg.get("org_llm_preset_id") or ucfg.get("llm_preset_id") or ucfg.get("theme_select_llm_preset_id")
    preset = _resolve_llm_preset(user_id, preset_id) if preset_id else {}
    has_user_direct_llm = any(
        (ucfg.get(k) not in (None, ""))
        for k in ("llm_api_key", "llm_base_url", "llm_model", "use_openrouter_free_pool")
    )
    if preset:
        cfg["api_key"] = (preset.get("api_key") or cfg["api_key"]).strip()
        cfg["base_url"] = (preset.get("base_url") or cfg["base_url"]).strip()
        cfg["model"] = (preset.get("model") or cfg["model"]).strip()
        cfg["use_openrouter_free_pool"] = bool(preset.get("use_openrouter_free_pool", cfg["use_openrouter_free_pool"]))
        if preset.get("temperature") is not None:
            cfg["temperature"] = preset["temperature"]
        if preset.get("max_tokens") is not None:
            cfg["max_tokens"] = preset["max_tokens"]
    else:
        cfg["api_key"] = (ucfg.get("llm_api_key") or cfg["api_key"]).strip()
        cfg["base_url"] = (ucfg.get("llm_base_url") or cfg["base_url"]).strip()
        cfg["model"] = (ucfg.get("llm_model") or cfg["model"]).strip()
        if ucfg.get("use_openrouter_free_pool") is not None:
            cfg["use_openrouter_free_pool"] = bool(ucfg["use_openrouter_free_pool"])
        if ucfg.get("temperature") is not None:
            cfg["temperature"] = ucfg["temperature"]
        if ucfg.get("max_tokens") is not None:
            cfg["max_tokens"] = ucfg["max_tokens"]

    if not preset and not has_user_direct_llm:
        try:
            from services import user_settings_service as _uss
            admin_llm = _uss.resolve_admin_llm_for_feature(feature)
        except Exception:
            admin_llm = {}
        if admin_llm:
            cfg["api_key"] = (admin_llm.get("llm_api_key") or cfg["api_key"]).strip()
            cfg["base_url"] = (admin_llm.get("llm_base_url") or cfg["base_url"]).strip()
            cfg["model"] = (admin_llm.get("llm_model") or cfg["model"]).strip()
            cfg["use_openrouter_free_pool"] = bool(admin_llm.get("use_openrouter_free_pool", cfg["use_openrouter_free_pool"]))
            if admin_llm.get("temperature") is not None:
                cfg["temperature"] = admin_llm["temperature"]
            if admin_llm.get("max_tokens") is not None:
                cfg["max_tokens"] = admin_llm["max_tokens"]

    # Prompt override
    prompt_preset_id = ucfg.get("org_prompt_preset_id")
    if prompt_preset_id:
        content = _resolve_prompt_preset(user_id, prompt_preset_id)
        if content:
            cfg["system_prompt"] = content
        else:
            print(
                f"[INFO] pdf_info: prompt preset id={prompt_preset_id} "
                f"is empty for user {user_id}; using global default prompt.",
                flush=True,
            )
    else:
        print(
            f"[INFO] pdf_info: no prompt preset configured for user {user_id}; "
            "using global default prompt.",
            flush=True,
        )

    return cfg


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def find_latest_date_dir(root: Path) -> Tuple[Path, str]:
    cand: List[Tuple[Path, str]] = []
    if not root.exists():
        return root / today_str(), today_str()
    for d in root.iterdir():
        if not d.is_dir():
            continue
        m = re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)
        if not m:
            continue
        cand.append((d, d.name))
    if not cand:
        return root / today_str(), today_str()
    cand.sort(key=lambda x: x[1], reverse=True)
    return cand[0][0], cand[0][1]


def list_md_files(in_dir: Path) -> List[Path]:
    return sorted([p for p in in_dir.glob("*.md") if p.is_file()])


def read_text_clip(path: Path, max_chars: int = 120000) -> str:
    t = path.read_text(encoding="utf-8", errors="ignore")
    if len(t) > max_chars:
        return t[:max_chars]
    return t


def find_latest_json(root: Path) -> Path:
    if not root.exists():
        raise SystemExit(f"json dir not found: {root}")
    files = sorted([p for p in root.glob("*.json") if p.is_file()])
    if not files:
        raise SystemExit(f"no json in {root}")
    return files[-1]


def parse_arxiv_json(json_path: Path) -> Dict[str, Dict[str, str]]:
    text = json_path.read_text(encoding="utf-8", errors="ignore")
    try:
        obj = json.loads(text) if text.strip() else {}
    except Exception:
        obj = {}
    papers = obj.get("papers") if isinstance(obj, dict) else None
    papers = papers if isinstance(papers, list) else []
    meta: Dict[str, Dict[str, str]] = {}
    for p in papers:
        if not isinstance(p, dict):
            continue
        arxiv_id = str(p.get("arxiv_id") or "").strip()
        if not arxiv_id:
            continue
        title = str(p.get("title") or "").strip()
        published = str(p.get("published_utc") or p.get("published") or "").strip()
        abstract = str(p.get("abstract_text") or p.get("summary") or "").strip()
        meta[arxiv_id] = {
            "title": title,
            "abstract": abstract,
            "published": published,
            "source": f"arxiv, {arxiv_id}",
        }
    return meta


def call_qwen(api_key: str, base_url: str, model: str, system_prompt: str, user_content: str, temperature: float, max_tokens: int, use_openrouter_free_pool: bool = False) -> str:
    """Call LLM via build_llm_client (supports OpenRouter Key pool).

    The signature retains positional args for backward compatibility with
    callers that pass api_key/base_url directly (e.g. user_paper_pipeline_service).
    When use_openrouter_free_pool=True, api_key may be empty and a pool key is
    selected automatically.
    """
    from services.llm_client_factory import build_llm_client
    client = build_llm_client({
        "api_key": api_key,
        "base_url": base_url,
        "use_openrouter_free_pool": use_openrouter_free_pool,
    })
    kwargs: Dict[str, Any] = {}
    if temperature is not None:
        kwargs["temperature"] = float(temperature)
    if max_tokens is not None:
        kwargs["max_tokens"] = int(max_tokens)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        **kwargs,
    )
    return require_nonempty_text(
        resp.choices[0].message.content if resp.choices else None,
        operation="pdf_info_institution_extraction",
    )


def parse_json_or_fallback(text: str) -> Dict[str, Any]:
    content = require_nonempty_text(
        text,
        operation="pdf_info_institution_extraction",
    )
    try:
        obj = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            raise InvalidLlmResponseError(
                "model returned invalid JSON during pdf_info institution extraction"
            )
        try:
            obj = json.loads(content[start:end + 1])
        except (json.JSONDecodeError, TypeError) as exc:
            raise InvalidLlmResponseError(
                "model returned invalid JSON during pdf_info institution extraction"
            ) from exc
    if not isinstance(obj, dict) or "is_large" not in obj:
        raise InvalidLlmResponseError(
            "model returned an invalid pdf_info institution payload"
        )
    raw_is_large = obj.get("is_large")
    if isinstance(raw_is_large, bool):
        is_large = raw_is_large
    elif isinstance(raw_is_large, int) and raw_is_large in (0, 1):
        is_large = bool(raw_is_large)
    elif isinstance(raw_is_large, str) and raw_is_large.strip().lower() in {
        "true", "false", "yes", "no", "是", "否",
    }:
        is_large = raw_is_large.strip().lower() in {"true", "yes", "是"}
    else:
        raise InvalidLlmResponseError(
            "model returned an invalid is_large classification"
        )
    obj["is_large"] = is_large
    if "instution" not in obj and "institution" in obj:
        obj["instution"] = obj.get("institution")
    return obj


def run(args: argparse.Namespace) -> None:
    output_mode = getattr(args, "output_mode", None) or os.environ.get("PIPELINE_OUTPUT_MODE", "file")
    run_date = os.environ.get("RUN_DATE") or datetime.utcnow().date().isoformat()
    uid = getattr(args, "user_id", None)
    if uid is None:
        uid = 0

    _pdb = None
    if output_mode == "db":
        try:
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, _root)
            from services import pipeline_db_service as _pdb_mod
            _pdb = _pdb_mod
        except Exception as exc:
            print(f"[WARN] Could not import pipeline_db_service: {exc!r}; falling back to file", flush=True)
            output_mode = "file"

    preview_root = Path(args.in_md_root)

    if output_mode == "db":
        # DB mode: strictly use RUN_DATE as both the input directory key and the DB write key.
        # Never fall back to find_latest_date_dir – that picks the newest existing directory
        # which may be from a previous date, causing date drift in pipeline_paper_info.
        date_dir = run_date
        preview_dir = preview_root / run_date
        if not preview_dir.is_dir():
            has_expected_inputs = False
            if _pdb is not None:
                has_expected_inputs = any(
                    bool(row.get("passed_theme_filter", 0))
                    for row in _pdb.get_selected_papers(uid, run_date, final_only=False)
                )
            print(
                f"[pdf_info] DB mode: preview_pdf_to_mineru/{run_date} not found; "
                + (
                    "cannot process theme-passed papers"
                    if has_expected_inputs
                    else "skip (no theme-passed papers)"
                ),
                flush=True,
            )
            print("============结束机构识别与信息写入==============", flush=True)
            if has_expected_inputs:
                raise SystemExit(1)
            return
        print(f"[pdf_info] DB mode: input={preview_dir}  db_date={run_date}", flush=True)
    else:
        preview_dir, date_dir = find_latest_date_dir(preview_root)

    arxiv_json_path = Path(args.arxiv_json) if args.arxiv_json else None
    if arxiv_json_path and not arxiv_json_path.exists():
        raise SystemExit(f"missing arxiv json file: {arxiv_json_path}")
    if not arxiv_json_path:
        candidate = Path(PAPER_THEME_FILTER_DIR) / f"{date_dir}.json"
        if candidate.exists():
            arxiv_json_path = candidate
        elif output_mode != "db":
            # File mode: fall back to the most recent JSON for metadata enrichment
            arxiv_json_path = find_latest_json(Path(PAPER_THEME_FILTER_DIR))
        # DB mode reads authoritative metadata directly from pipeline_arxiv_list.
    if output_mode == "db" and _pdb is not None:
        meta_map = {
            str(row.get("paper_arxiv_id") or "").strip(): {
                "title": str(row.get("title") or "").strip(),
                "abstract": str(row.get("abstract_text") or "").strip(),
                "published": str(row.get("published_utc") or "").strip(),
                "source": f"arxiv, {str(row.get('paper_arxiv_id') or '').strip()}",
            }
            for row in _pdb.get_arxiv_list(date_dir)
            if str(row.get("paper_arxiv_id") or "").strip()
        }
    else:
        meta_map = parse_arxiv_json(arxiv_json_path) if arxiv_json_path else {}
    out_root = ensure_dir(Path(args.outdir))
    out_path = out_root / f"{date_dir}.json"
    md_files = list_md_files(preview_dir)

    expected_ids: set[str] = set()
    missing_input_count = 0
    if output_mode == "db" and _pdb is not None:
        selected_rows = _pdb.get_selected_papers(uid, date_dir, final_only=False)
        expected_ids = {
            str(row.get("paper_arxiv_id") or "").strip()
            for row in selected_rows
            if bool(row.get("passed_theme_filter", 0))
            and str(row.get("paper_arxiv_id") or "").strip()
        }
        if not expected_ids:
            print(
                f"[pdf_info] no theme-passed papers for user={uid} date={date_dir}; skip",
                flush=True,
            )
            print("============结束机构识别与信息写入==============", flush=True)
            return
        md_files = [path for path in md_files if path.stem in expected_ids]

    if not md_files:
        print(f"no md files in {preview_dir}, skip pdf_info", flush=True)
        if output_mode != "db":
            out_path.write_text("[]", encoding="utf-8")
        print("[process] 0/0")
        raise SystemExit(1 if expected_ids else 0)
    print("============开始调用大模型做机构识别==============", flush=True)
    user_id: Optional[int] = getattr(args, "user_id", None)
    llm_cfg = _resolve_llm_for_user(user_id)
    system_prompt = llm_cfg["system_prompt"]
    api_key = llm_cfg["api_key"]
    base_url = llm_cfg["base_url"]
    model = llm_cfg["model"]
    temperature = llm_cfg["temperature"]
    max_tokens = llm_cfg["max_tokens"]
    use_pool = bool(llm_cfg.get("use_openrouter_free_pool", False))
    if use_pool:
        print(f"[INFO] pdf_info: using OpenRouter Key pool (base_url={base_url or 'default'})", flush=True)
    else:
        print(f"[INFO] pdf_info: using base_url={base_url} model={model}", flush=True)
    agg: List[Dict[str, Any]] = []
    if output_mode != "db" and out_path.exists():
        try:
            agg_text = out_path.read_text(encoding="utf-8", errors="ignore")
            obj = json.loads(agg_text)
            if isinstance(obj, list):
                agg = obj
        except Exception:
            agg = []
    existing_ids: set[str] = set()
    if agg:
        for it in agg:
            src = str(it.get("source") or "")
            m = re.search(r"arxiv,\s*([0-9]+\.[0-9]+)", src)
            if m:
                existing_ids.add(m.group(1))
    if agg:
        dedup: Dict[str, Dict[str, Any]] = {}
        for it in agg:
            src = str(it.get("source") or "")
            m = re.search(r"arxiv,\s*([0-9]+\.[0-9]+)", src)
            if m:
                dedup[m.group(1)] = it
        agg = list(dedup.values())
        out_path.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
    if output_mode == "db" and _pdb is not None:
        existing_map = _pdb.get_paper_info_map(uid, date_dir)
        retry_ids = {
            paper_id
            for paper_id in expected_ids
            if paper_id not in existing_map
            or not str(existing_map[paper_id].get("title") or "").strip()
            or not str(existing_map[paper_id].get("abstract") or "").strip()
        }
        available_ids = {path.stem for path in md_files}
        missing_input_count = len(retry_ids - available_ids)
        remaining_files = [path for path in md_files if path.stem in retry_ids]
    else:
        remaining_files = [p for p in md_files if p.stem not in existing_ids]
    deferred_count = 0
    if args.limit and args.limit > 0:
        deferred_count = max(0, len(remaining_files) - args.limit)
        remaining_files = remaining_files[: args.limit]
    total = len(remaining_files)
    processed = 0
    errors = 0
    if total == 0:
        print(f"[process] 0/0")
        if missing_input_count:
            raise SystemExit(1)
        return

    workers = max(1, int(getattr(args, "concurrency", 1) or 1))
    print(f"[process] total={total} concurrency={workers}", flush=True)
    start = time.monotonic()

    def task(p: Path) -> Tuple[str, Dict[str, Any] | None, str]:
        arxiv_id = p.stem
        try:
            content = read_text_clip(p, max_chars=args.max_chars)
            content = require_nonempty_text(
                content,
                operation="pdf_info_source_text",
            )
            user_content = f"文件名：{p.name}\n文本：\n{content}"
            out_text = call_qwen(api_key, base_url, model, system_prompt, user_content, temperature, max_tokens, use_openrouter_free_pool=use_pool)
            obj_small = parse_json_or_fallback(out_text)
            meta = meta_map.get(
                arxiv_id,
                {
                    "title": "",
                    "abstract": "",
                    "source": f"arxiv, {arxiv_id}",
                    "published": "",
                },
            )
            title = require_nonempty_text(
                meta.get("title"),
                operation="pdf_info_title_metadata",
            )
            abstract = require_nonempty_text(
                meta.get("abstract") or obj_small.get("abstract"),
                operation="pdf_info_abstract_metadata",
            )
            institution_name = str(obj_small.get("instution", "") or "").strip()
            is_large = bool(obj_small.get("is_large", False))
            llm_tier = obj_small.get("institution_tier")
            institution_tier = resolve_institution_tier(institution_name, llm_tier, is_large)
            item = {
                "title": title,
                "source": meta.get("source", "") or f"arxiv, {arxiv_id}",
                "published": meta.get("published", ""),
                "instution": institution_name,
                "is_large": is_large,
                "institution_tier": institution_tier,
                "abstract": abstract,
            }
            return arxiv_id, item, ""
        except Exception as e:
            return arxiv_id, None, repr(e)

    _MAX_ERR_SAMPLES = 5

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(task, p) for p in remaining_files]
        for fut in concurrent.futures.as_completed(futures):
            try:
                arxiv_id, item, err = fut.result()
            except Exception as e:
                processed += 1
                errors += 1
                elapsed = time.monotonic() - start
                rate = processed / elapsed if elapsed > 0 else 0.0
                print(f"\r[process] {processed}/{total} err={errors} rate={rate:.2f}/s", end="", flush=True)
                if errors <= _MAX_ERR_SAMPLES:
                    print(f"\n[ERR sample] future exception: {e!r}", flush=True)
                continue

            processed += 1
            if item is None:
                errors += 1
                if errors <= _MAX_ERR_SAMPLES:
                    print(f"\n[ERR sample] {arxiv_id}: {err}", flush=True)
            else:
                if output_mode == "db" and _pdb is not None:
                    try:
                        _pdb.upsert_paper_info(
                            uid, date_dir, arxiv_id,
                            title=item.get("title") or "",
                            institution=item.get("instution") or "",
                            is_large=bool(item.get("is_large", False)),
                            institution_tier=int(item.get("institution_tier") or 4),
                            abstract=item.get("abstract") or "",
                            published=item.get("published") or "",
                            source=item.get("source") or "",
                        )
                        agg.append(item)
                    except Exception as db_exc:
                        errors += 1
                        print(f"\n[WARN] DB write failed for {arxiv_id}: {db_exc!r}", flush=True)
                else:
                    agg.append(item)
                    out_path.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
            elapsed = time.monotonic() - start
            rate = processed / elapsed if elapsed > 0 else 0.0
            print(f"\r[process] {processed}/{total} err={errors} rate={rate:.2f}/s", end="", flush=True)

    # Final file flush if in file mode
    if output_mode != "db" and agg:
        out_path.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    if output_mode == "db":
        print(f"[pdf_info] DB output: {len(agg)} records for user={uid} date={date_dir}", flush=True)
    print("============结束机构识别与信息写入==============", flush=True)
    if errors or missing_input_count or deferred_count:
        raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser("pdf_info")
    ap.add_argument("--in-md-root", default=str(Path(DATA_ROOT) / "preview_pdf_to_mineru"))
    ap.add_argument("--outdir", default=str(Path(DATA_ROOT) / "pdf_info"))
    ap.add_argument("--arxiv-json", default="")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=pdf_info_concurrency)
    ap.add_argument("--max-chars", type=int, default=120000)
    ap.add_argument("--user-id", type=int, default=None, help="user id for per-user LLM/prompt preset override")
    ap.add_argument("--output-mode", default=None, choices=["file", "db"],
                    help="output mode: 'file' (default) writes JSON; 'db' writes to pipeline_paper_info table")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
