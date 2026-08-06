"""
Inspiration v2 — Layer B: Combination Pipeline Step.

Steps combined:
  11. question_generator — mine questions from limitation atoms
  12. idea_retrieve — retrieve relevant atoms for each question
  13. insight_generate — multi-strategy candidate generation
  14. Output structured IdeaCandidate records

Usage:
    python idea_combine.py --date 2025-06-15 --user-id 1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from openai import OpenAI
from services.llm_response_guard import (
    InvalidLlmResponseError,
    require_nonempty_text,
)
from services.llm_request_options import build_thinking_kwargs
import config.config as _config_module  # noqa: E402
from config.config import (  # noqa: E402
    DATA_ROOT,
    idea_generate_base_url,
    idea_generate_api_key,
    idea_generate_model,
    idea_generate_max_tokens,
    idea_generate_temperature,
    idea_generate_input_hard_limit,
    idea_generate_input_safety_margin,
)


# ---------------------------------------------------------------------------
# LLM config (system config first, user settings as fallback)
# ---------------------------------------------------------------------------

def _load_user_config(user_id: int) -> Dict[str, Any]:
    try:
        from services.user_settings_service import get_settings
        return get_settings(user_id, "idea_generate")
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
    """Resolve a user prompt preset to its content string."""
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


def _resolve_prompt(ucfg: Dict[str, Any], user_id: int,
                    module_preset_key: str, user_text_key: str,
                    config_var_name: str) -> str:
    """Resolve a prompt for a specific module with the standard priority chain.

    Priority:
      1. Module-specific prompt preset
      2. Global prompt preset
      3. User settings per-phase text override
      4. config.py variable
    """
    # 1. Module-specific prompt preset
    preset_id = ucfg.get(module_preset_key) or ucfg.get("prompt_preset_id")
    if preset_id:
        content = _resolve_prompt_preset(user_id, preset_id)
        if content:
            return content
    # 2. Per-phase text override in user settings
    user_text = (ucfg.get(user_text_key) or "").strip()
    if user_text:
        return user_text
    # 3. config.py variable
    return (getattr(_config_module, config_var_name, "") or "").strip()


def _make_client(user_id: Optional[int] = None,
                 module: str = "question") -> Tuple[Optional[OpenAI], Dict[str, Any]]:
    """Create OpenAI client for a specific idea_combine phase.

    module: "question" | "candidate"

    Priority for LLM credentials:
      1. System-level per-phase: idea_question_* / idea_candidate_*
      2. System-level global fallback: idea_generate_*
      3. Per-user settings (presets / manual)
    """
    # Map module → system config variable prefix
    _SYS_PREFIX = {
        "question":  "idea_question",
        "candidate": "idea_candidate",
    }
    sys_pfx = _SYS_PREFIX.get(module, "idea_question")

    cfg: Dict[str, Any] = {
        "model": "",
        "temperature": 0.7,
        "max_tokens": 8192,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
    }
    key = ""
    base = ""
    use_pool: bool = False

    # --- 1. Try system-level config (per-phase → global fallback) ---
    sys_base = (getattr(_config_module, f"{sys_pfx}_base_url", "") or "").strip()
    sys_key  = (getattr(_config_module, f"{sys_pfx}_api_key",  "") or "").strip()
    sys_model= (getattr(_config_module, f"{sys_pfx}_model",    "") or "").strip()
    sys_pool = bool(getattr(_config_module, f"{sys_pfx}_use_openrouter_free_pool", False))
    if not (sys_model and (sys_key or sys_pool)):
        sys_base = (getattr(_config_module, "idea_generate_base_url", "") or "").strip()
        sys_key  = (getattr(_config_module, "idea_generate_api_key",  "") or "").strip()
        sys_model= (getattr(_config_module, "idea_generate_model",    "") or "").strip()
        sys_pool = bool(getattr(_config_module, "idea_generate_use_openrouter_free_pool", False))
    if sys_model and (sys_key or sys_pool):
        base = sys_base
        key = sys_key
        cfg["model"] = sys_model
        cfg["max_tokens"] = getattr(_config_module, "idea_generate_max_tokens", 8192)
        cfg["temperature"] = getattr(_config_module, "idea_generate_temperature", 0.7)
        cfg["input_hard_limit"] = getattr(_config_module, "idea_generate_input_hard_limit", 129024)
        cfg["input_safety_margin"] = getattr(_config_module, "idea_generate_input_safety_margin", 4096)
        use_pool = sys_pool
        print(f"[IDEA_COMBINE] Using system-level {sys_pfx}/idea_generate config.", flush=True)
    elif user_id is not None:
        # --- 2. Fallback: per-user settings ---
        ucfg = _load_user_config(user_id)
        if ucfg:
            # Per-phase user preset key (matches ProfileSettings form keys)
            module_llm_key = f"{module}_llm_preset_id"  # "question_llm_preset_id" or "candidate_llm_preset_id"
            # Cascade: module-specific → global → ingest (first step) → system config
            preset_id = ucfg.get(module_llm_key) or ucfg.get("llm_preset_id") or ucfg.get("ingest_llm_preset_id")
            preset = _resolve_llm_preset(user_id, preset_id) if preset_id else {}
            if preset:
                key = (preset.get("api_key") or "").strip()
                base = (preset.get("base_url") or "").strip()
                cfg["model"] = (preset.get("model") or "").strip()
                cfg["enable_thinking"] = bool(preset.get("enable_thinking", False))
                if "use_openrouter_free_pool" in preset:
                    use_pool = bool(preset["use_openrouter_free_pool"])
                for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                    if preset.get(k) is not None:
                        cfg[k] = preset[k]
            else:
                key = (ucfg.get("llm_api_key") or "").strip()
                base = (ucfg.get("llm_base_url") or "").strip()
                cfg["model"] = (ucfg.get("llm_model") or "").strip()
                if "use_openrouter_free_pool" in ucfg:
                    use_pool = bool(ucfg["use_openrouter_free_pool"])
                for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                    if ucfg.get(k) is not None:
                        cfg[k] = ucfg[k]
            # Store ucfg for prompt resolution later
            cfg["_ucfg"] = ucfg
        if key or use_pool:
            print(f"[IDEA_COMBINE] Using per-user idea_generate config (user_id={user_id}).", flush=True)

    if (not key and not use_pool) or not cfg["model"]:
        return None, cfg
    cfg.setdefault("llm_base_url", base)
    cfg.setdefault("enable_thinking", False)
    cfg["use_openrouter_free_pool"] = use_pool
    from services.llm_client_factory import build_llm_client
    return build_llm_client({"api_key": key, "base_url": base, "use_openrouter_free_pool": use_pool}), cfg


def _approx_tokens(text: str) -> int:
    return len(text.encode("utf-8", errors="ignore")) if text else 0


def _crop(text: str, budget: int) -> str:
    b = text.encode("utf-8", errors="ignore")
    return text if len(b) <= budget else b[:budget].decode("utf-8", errors="ignore")


def _call_llm_json(
    client: OpenAI, cfg: Dict[str, Any], system_prompt: str, user_content: str,
) -> Dict[str, Any]:
    hard_limit = int(cfg.get("input_hard_limit", 129024))
    safety_margin = int(cfg.get("input_safety_margin", 4096))
    limit_total = hard_limit - safety_margin
    sys_tokens = _approx_tokens(system_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = _crop(user_content, user_budget)

    kwargs: Dict[str, Any] = {}
    if cfg.get("temperature") is not None:
        kwargs["temperature"] = float(cfg["temperature"])
    if cfg.get("max_tokens") is not None:
        kwargs["max_tokens"] = int(cfg["max_tokens"])
    kwargs.update(build_thinking_kwargs(cfg))

    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        **kwargs,
    )
    text = resp.choices[0].message.content if resp.choices else ""
    text = require_nonempty_text(text, operation="idea combination")
    return _parse_json(text)


def _parse_json(text: str) -> Dict[str, Any]:
    text = require_nonempty_text(text, operation="idea combination JSON parsing")
    s = text.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(s[start:end + 1])
        except json.JSONDecodeError:
            pass
    start = s.find("[")
    end = s.rfind("]")
    if start != -1 and end > start:
        try:
            return {"items": json.loads(s[start:end + 1])}
        except json.JSONDecodeError:
            pass
    raise InvalidLlmResponseError(
        "model returned invalid structured content during idea combination"
    )


# ---------------------------------------------------------------------------
# Step 11: Question generation
# ---------------------------------------------------------------------------

def generate_questions(
    client: OpenAI, cfg: Dict[str, Any], user_id: int,
) -> List[Dict[str, Any]]:
    from services import idea_service

    # Gather limitation and method atoms
    atoms = idea_service.list_atoms(user_id=user_id, atom_type="limitation", limit=30)
    atoms += idea_service.list_atoms(user_id=user_id, atom_type="method", limit=20)
    if not atoms:
        atoms = idea_service.list_atoms(user_id=user_id, limit=50)
    if not atoms:
        raise ValueError("no usable atoms are available for question generation")

    atoms_text = (
        "\n\n".join(
            f"[{a['atom_type'].upper()}] (paper: {a['paper_id']})\n{a['content']}"
            for a in atoms[:50]
        )
        + "\n\n## 语言要求\n请务必使用中文输出所有问题（question 字段），专有名词（模型名、数据集名、指标名）保留英文。"
    )

    # Resolve system prompt for question generation
    ucfg = cfg.get("_ucfg", {})
    question_prompt = _resolve_prompt(
        ucfg, user_id,
        module_preset_key="combine_question_prompt_preset_id",
        user_text_key="combine_question_prompt",
        config_var_name="idea_question_system_prompt",
    )
    result = _call_llm_json(client, cfg, question_prompt, atoms_text)
    questions_raw = result.get("questions") or result.get("items") or []
    if not isinstance(questions_raw, list) or not questions_raw:
        raise InvalidLlmResponseError(
            "model returned no research questions during idea combination"
        )

    question_specs = []
    source_atom_ids = [a["id"] for a in atoms[:5]]
    for index, q in enumerate(questions_raw):
        if isinstance(q, str):
            q = {"question": q, "strategy": "general"}
        if not isinstance(q, dict):
            raise InvalidLlmResponseError(
                f"research question {index} is not an object"
            )
        question_text = q.get("question")
        if not isinstance(question_text, str) or not question_text.strip():
            raise InvalidLlmResponseError(
                f"research question {index} has empty content"
            )
        context = q.get("context", {})
        if not isinstance(context, dict):
            context = {"raw_context": str(context)}
        question_specs.append({
            "question_text": question_text.strip(),
            "source_atom_ids": source_atom_ids,
            "strategy": q.get("strategy", "general"),
            "context": context,
        })

    return question_specs


# ---------------------------------------------------------------------------
# Step 12-14: Retrieve + generate candidates
# ---------------------------------------------------------------------------

def generate_candidates_for_question(
    client: OpenAI,
    cfg: Dict[str, Any],
    user_id: int,
    question: Dict[str, Any],
) -> List[Dict[str, Any]]:
    from services import idea_service

    q_text = question.get("question_text", "")
    # Retrieve relevant atoms (FTS first, fallback to recent)
    try:
        atoms = idea_service.search_atoms_fts(q_text, user_id=user_id, limit=20)
    except Exception:
        atoms = []
    if not atoms:
        atoms = idea_service.list_atoms(user_id=user_id, limit=20)
    if not atoms:
        raise ValueError("no usable atoms are available for candidate generation")

    atoms_context = "\n\n".join(
        f"[ATOM-{a['id']}] [{a['atom_type'].upper()}] (paper: {a['paper_id']})\n{a['content']}"
        for a in atoms
    )

    user_content = (
        f"## 研究问题\n{q_text}\n\n"
        f"## 可用灵感原子\n{atoms_context}\n\n"
        f"## 语言要求\n请务必使用中文输出所有字段（title、goal、mechanism、risks），专有名词（模型名、数据集名、指标名）保留英文。"
    )
    # Resolve system prompt for candidate generation
    ucfg = cfg.get("_ucfg", {})
    candidate_prompt = _resolve_prompt(
        ucfg, user_id,
        module_preset_key="combine_candidate_prompt_preset_id",
        user_text_key="combine_candidate_prompt",
        config_var_name="idea_candidate_system_prompt",
    )
    result = _call_llm_json(client, cfg, candidate_prompt, user_content)
    candidates_raw = result.get("candidates") or result.get("items") or []
    if not isinstance(candidates_raw, list) or not candidates_raw:
        raise InvalidLlmResponseError(
            "model returned no candidates during idea combination"
        )

    candidate_specs = []
    for index, c in enumerate(candidates_raw):
        if not isinstance(c, dict):
            raise InvalidLlmResponseError(
                f"idea candidate {index} is not an object"
            )
        required = {}
        for field in ("title", "goal", "mechanism", "risks"):
            value = c.get(field)
            if not isinstance(value, str) or not value.strip():
                raise InvalidLlmResponseError(
                    f"idea candidate {index} has empty {field}"
                )
            required[field] = value.strip()
        candidate_specs.append({
            **required,
            "strategy": c.get("strategy", ""),
            "tags": c.get("tags", []) if isinstance(c.get("tags", []), list) else [],
            "input_atom_ids": (
                c.get("input_atom_ids", [])
                if isinstance(c.get("input_atom_ids", []), list)
                else []
            ),
            "source_type": "question_pipeline",
        })

    return candidate_specs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _write_manifest(date_str: str, data: dict) -> None:
    """Write sentinel .jsonl file so app.py pipeline recognises this step as done."""
    root = os.path.dirname(os.path.dirname(__file__))
    from config.config import DATA_ROOT as _DATA_ROOT
    out_dir = os.path.join(root, _DATA_ROOT, "idea_combine")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{date_str}.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def run() -> None:
    ap = argparse.ArgumentParser("idea_combine")
    ap.add_argument("--date", default="")
    ap.add_argument("--user-id", type=int, default=None)
    args = ap.parse_args()

    date_str = args.date or os.environ.get("RUN_DATE", "") or datetime.now().date().isoformat()
    # Use 'is not None' so that explicit --user-id 0 (default/system user) is preserved.
    user_id = args.user_id if args.user_id is not None else int(os.environ.get("PIPELINE_USER_ID", "0") or "0")

    if user_id is None:
        print("[IDEA_COMBINE] No user_id; skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "no_user_id", "date": date_str})
        return

    # Each phase gets its own independent client (1:1 model+prompt)
    q_client, q_cfg = _make_client(user_id, module="question")
    c_client, c_cfg = _make_client(user_id, module="candidate")

    if not q_client:
        print("[IDEA_COMBINE] LLM not configured for question generation; skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "llm_not_configured", "date": date_str, "user_id": user_id})
        return
    if not c_client:
        print("[IDEA_COMBINE] LLM not configured for candidate generation; skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "llm_not_configured", "date": date_str, "user_id": user_id})
        return

    from services import idea_service

    # Check we have atoms ingested TODAY to work with.
    # Using count_atoms_for_date (not count_atoms) prevents reading historical atoms
    # on days where idea_ingest found 0 papers, which would produce spurious ideas.
    atom_count = idea_service.count_atoms_for_date(user_id, date_str)
    if atom_count == 0:
        print(
            f"[IDEA_COMBINE] No atoms for date={date_str}; "
            "idea_ingest produced nothing today — skipping.",
            flush=True,
        )
        _write_manifest(date_str, {"status": "skipped", "reason": "no_atoms_today", "date": date_str, "user_id": user_id})
        return

    print(f"============开始 灵感组合 (idea_combine) ============", flush=True)
    print(f"[IDEA_COMBINE] date={date_str} user_id={user_id} atoms={atom_count}", flush=True)

    try:
        # Generate and validate the complete replacement before mutating the DB.
        print("[IDEA_COMBINE] Generating research questions...", flush=True)
        question_batches = generate_questions(q_client, q_cfg, user_id)
        print(f"[IDEA_COMBINE] Validated {len(question_batches)} questions.", flush=True)

        for i, question in enumerate(question_batches):
            print(
                f"[IDEA_COMBINE] Q{i+1}/{len(question_batches)}: "
                f"{question.get('question_text', '')[:80]}...",
                flush=True,
            )
            candidates = generate_candidates_for_question(
                c_client, c_cfg, user_id, question
            )
            question["candidates"] = candidates
            print(f"[IDEA_COMBINE]   → validated {len(candidates)} candidates", flush=True)

        questions, total_candidates = (
            idea_service.replace_questions_and_candidates_for_date(
                user_id, date_str, question_batches
            )
        )
    except Exception as exc:
        error_type = type(exc).__name__
        print(f"[IDEA_COMBINE] generation failed: {error_type}", flush=True)
        _write_manifest(date_str, {
            "status": "failed",
            "date": date_str,
            "user_id": user_id,
            "error_type": error_type,
        })
        raise SystemExit(1) from exc

    print(f"[IDEA_COMBINE] Total: {len(questions)} questions, {total_candidates} candidates", flush=True)
    print(f"============结束 灵感组合 (idea_combine) ============", flush=True)

    _write_manifest(date_str, {
        "status": "done",
        "date": date_str,
        "user_id": user_id,
        "total_questions": len(questions),
        "total_candidates": total_candidates,
    })


if __name__ == "__main__":
    run()
