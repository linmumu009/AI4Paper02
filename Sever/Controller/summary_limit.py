from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, List, Tuple, Optional, Dict

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from openai import OpenAI
from services.llm_request_options import build_thinking_kwargs
from services.llm_response_guard import (
    EmptyLlmResponseError,
    InvalidLlmResponseError,
    require_nonempty_text,
)
from services.safe_logging_service import redact_sensitive_text
from config.config import (  # noqa: E402
    qwen_api_key,
    summary_limit_base_url,
    summary_limit_model,
    summary_limit_max_tokens,
    summary_limit_temperature,
    summary_limit_input_hard_limit,
    summary_limit_input_safety_margin,
    summary_limit_concurrency,
    summary_limit_section_limit_intro,
    summary_limit_section_limit_method,
    summary_limit_section_limit_findings,
    summary_limit_section_limit_opinion,
    summary_limit_headline_limit,
    summary_limit_prompt_card,
    summary_limit_prompt_intro,
    summary_limit_prompt_method,
    summary_limit_prompt_findings,
    summary_limit_prompt_opinion,
    summary_limit_prompt_structure_check,
    summary_limit_prompt_structure_rewrite,
    summary_limit_prompt_headline,
    summary_limit_url_2,
    summary_limit_gptgod_apikey,
    summary_limit_model_2,
    summary_limit_url_3,
    summary_limit_apikey_3,
    summary_limit_model_3,
    DATA_ROOT,
    SLLM,
)
from config.recommend_card_prompts import CARD_FIELD_LIMITS
from services.recommend_card_prompt_eval import (
    FIELD_ORDER as CARD_FIELD_ORDER,
    deterministic_report as card_deterministic_report,
    parse_card,
)


SECTION_LABELS = {
    "intro": ("🛎️文章简介", "文章简介"),
    "method": ("📝重点思路", "重点思路"),
    "findings": ("🔎分析总结", "分析总结"),
    "opinion": ("💡个人观点", "个人观点"),
    "memory": ("一句话记忆版", "一句话记忆版"),
}

# Default section limits / prompts from config.py  (may be overridden per-user)
SECTION_LIMITS_DEFAULT: Dict[str, int] = {
    "intro": summary_limit_section_limit_intro,
    "method": summary_limit_section_limit_method,
    "findings": summary_limit_section_limit_findings,
    "opinion": summary_limit_section_limit_opinion,
}

SECTION_PROMPTS_DEFAULT: Dict[str, str] = {
    "intro": summary_limit_prompt_intro,
    "method": summary_limit_prompt_method,
    "findings": summary_limit_prompt_findings,
    "opinion": summary_limit_prompt_opinion,
}

# Module-level aliases kept for backward-compat (used by functions that
# don't receive an explicit effective_cfg).
SECTION_LIMITS = dict(SECTION_LIMITS_DEFAULT)
SECTION_PROMPTS = dict(SECTION_PROMPTS_DEFAULT)
CARD_LIMITS_DEFAULT: Dict[str, int] = dict(CARD_FIELD_LIMITS)


# ---------------------------------------------------------------------------
# User‑override helpers  (mirrors paper_summary.py)
# ---------------------------------------------------------------------------

def _load_user_config(user_id: int, feature: str = "paper_recommend") -> Dict[str, Any]:
    try:
        from services.user_settings_service import get_settings
        return get_settings(user_id, feature)
    except Exception:
        return {}


def _load_explicit_user_config(
    user_id: int,
    feature: str = "paper_recommend",
) -> Dict[str, Any]:
    """Return only explicit admin/user overrides, with user values winning."""
    try:
        from services.user_settings_service import (
            get_admin_overrides,
            get_raw_settings,
        )

        values = dict(get_admin_overrides(feature) or {})
        values.update(get_raw_settings(user_id, feature) or {})
        return values
    except Exception:
        return {}


def _prompt_signature(value: Any) -> str:
    punctuation = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
    return re.sub(r"\s+", "", str(value or "").translate(punctuation))


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


def build_effective_cfg(user_id: Optional[int] = None, feature: str = "paper_recommend") -> Dict[str, Any]:
    """Return a dict with all effective config values for summary_limit.

    When *user_id* is ``None`` every value comes straight from config.py.
    """
    cfg: Dict[str, Any] = {
        "temperature": summary_limit_temperature,
        "max_tokens": summary_limit_max_tokens,
        "input_hard_limit": summary_limit_input_hard_limit,
        "input_safety_margin": summary_limit_input_safety_margin,
        "headline_limit": summary_limit_headline_limit,
        "section_limits": dict(SECTION_LIMITS_DEFAULT),
        "section_prompts": dict(SECTION_PROMPTS_DEFAULT),
        "card_prompt": summary_limit_prompt_card,
        "card_limits": dict(CARD_LIMITS_DEFAULT),
        "headline_prompt": summary_limit_prompt_headline,
        "structure_check_prompt": summary_limit_prompt_structure_check,
        "structure_rewrite_prompt": summary_limit_prompt_structure_rewrite,
    }

    import config.config as _sys_cfg_sl
    key: str = ""
    base: str = ""
    model: str = ""
    use_pool: bool = bool(getattr(_sys_cfg_sl, "summary_limit_use_openrouter_free_pool", False))
    user_llm_configured = False

    if user_id is not None:
        ucfg = _load_user_config(user_id, feature)
        explicit_ucfg = _load_explicit_user_config(user_id, feature)
        if ucfg:
            # LLM connection — module-specific preset first, then generic fallback, then cascade from first step
            preset_id = ucfg.get("summary_limit_llm_preset_id") or ucfg.get("llm_preset_id") or ucfg.get("theme_select_llm_preset_id")
            preset = _resolve_llm_preset(user_id, preset_id) if preset_id else {}
            if preset:
                user_llm_configured = True
                key = (preset.get("api_key") or "").strip()
                base = (preset.get("base_url") or "").strip()
                model = (preset.get("model") or "").strip()
                cfg["enable_thinking"] = bool(preset.get("enable_thinking", False))
                if "use_openrouter_free_pool" in preset:
                    use_pool = bool(preset["use_openrouter_free_pool"])
                for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                    if preset.get(k) is not None:
                        cfg[k] = preset[k]
            else:
                user_llm_configured = any(
                    (ucfg.get(k) not in (None, ""))
                    for k in ("llm_api_key", "llm_base_url", "llm_model", "use_openrouter_free_pool")
                )
                key = (ucfg.get("llm_api_key") or "").strip()
                base = (ucfg.get("llm_base_url") or "").strip()
                model = (ucfg.get("llm_model") or "").strip()
                if "use_openrouter_free_pool" in ucfg:
                    use_pool = bool(ucfg["use_openrouter_free_pool"])
                for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                    if ucfg.get(k) is not None:
                        cfg[k] = ucfg[k]

            # Section limits
            limit_map = {
                "intro": "section_limit_intro",
                "method": "section_limit_method",
                "findings": "section_limit_findings",
                "opinion": "section_limit_opinion",
            }
            for sec, ukey in limit_map.items():
                if ucfg.get(ukey) is not None:
                    cfg["section_limits"][sec] = int(ucfg[ukey])
            if ucfg.get("headline_limit") is not None:
                cfg["headline_limit"] = int(ucfg["headline_limit"])

            # Section prompts
            prompt_map = {
                "intro": ("summary_limit_prompt_intro_preset_id", "summary_limit_prompt_intro"),
                "method": ("summary_limit_prompt_method_preset_id", "summary_limit_prompt_method"),
                "findings": ("summary_limit_prompt_findings_preset_id", "summary_limit_prompt_findings"),
                "opinion": ("summary_limit_prompt_opinion_preset_id", "summary_limit_prompt_opinion"),
            }
            for sec, (preset_key, text_key) in prompt_map.items():
                prompt_content = _resolve_prompt_preset(user_id, ucfg.get(preset_key)) if ucfg.get(preset_key) else ""
                if prompt_content:
                    cfg["section_prompts"][sec] = prompt_content
                elif ucfg.get(text_key):
                    cfg["section_prompts"][sec] = ucfg[text_key]

            card_preset_content = (
                _resolve_prompt_preset(
                    user_id, ucfg.get("summary_limit_prompt_card_preset_id")
                )
                if ucfg.get("summary_limit_prompt_card_preset_id")
                else ""
            )
            card_text = str(ucfg.get("summary_limit_prompt_card") or "").strip()
            explicit_card_prompt = bool(
                explicit_ucfg.get("summary_limit_prompt_card_preset_id")
            ) or bool(
                "summary_limit_prompt_card" in explicit_ucfg
                and _prompt_signature(explicit_ucfg.get("summary_limit_prompt_card"))
                != _prompt_signature(summary_limit_prompt_card)
            )
            if card_preset_content:
                cfg["card_prompt"] = card_preset_content
            elif "summary_limit_prompt_card" in explicit_ucfg:
                cfg["card_prompt"] = str(
                    explicit_ucfg.get("summary_limit_prompt_card") or ""
                ).strip()
            elif card_text:
                cfg["card_prompt"] = card_text

            limit_keys = {
                "headline_limit": summary_limit_headline_limit,
                "section_limit_intro": SECTION_LIMITS_DEFAULT["intro"],
                "section_limit_method": SECTION_LIMITS_DEFAULT["method"],
                "section_limit_findings": SECTION_LIMITS_DEFAULT["findings"],
                "section_limit_opinion": SECTION_LIMITS_DEFAULT["opinion"],
            }
            legacy_limits_customized = any(
                key in explicit_ucfg
                and explicit_ucfg.get(key) is not None
                and int(explicit_ucfg[key]) != int(default)
                for key, default in limit_keys.items()
            )
            section_prompt_keys = {
                "intro": (
                    "summary_limit_prompt_intro_preset_id",
                    "summary_limit_prompt_intro",
                ),
                "method": (
                    "summary_limit_prompt_method_preset_id",
                    "summary_limit_prompt_method",
                ),
                "findings": (
                    "summary_limit_prompt_findings_preset_id",
                    "summary_limit_prompt_findings",
                ),
                "opinion": (
                    "summary_limit_prompt_opinion_preset_id",
                    "summary_limit_prompt_opinion",
                ),
            }
            legacy_prompts_customized = any(
                bool(explicit_ucfg.get(preset_key))
                or (
                    text_key in explicit_ucfg
                    and _prompt_signature(explicit_ucfg.get(text_key))
                    != _prompt_signature(SECTION_PROMPTS_DEFAULT[sec])
                )
                for sec, (preset_key, text_key) in section_prompt_keys.items()
            )
            if (legacy_limits_customized or legacy_prompts_customized) and not explicit_card_prompt:
                # Existing custom section behavior remains authoritative until
                # the user explicitly opts into a full-card prompt.
                cfg["card_prompt"] = ""

    if user_id is not None and not user_llm_configured:
        try:
            from services import user_settings_service as _uss
            admin_llm = _uss.resolve_admin_llm_for_feature(feature)
        except Exception:
            admin_llm = {}
        if admin_llm:
            key = (admin_llm.get("llm_api_key") or key).strip()
            base = (admin_llm.get("llm_base_url") or base).strip()
            model = (admin_llm.get("llm_model") or model).strip()
            if "use_openrouter_free_pool" in admin_llm:
                use_pool = bool(admin_llm["use_openrouter_free_pool"])
            for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                if admin_llm.get(k) is not None:
                    cfg[k] = admin_llm[k]
            if admin_llm.get("enable_thinking") is not None:
                cfg["enable_thinking"] = bool(admin_llm["enable_thinking"])

    # Resolve LLM credentials (fall back to config.py when pool mode not active)
    if not use_pool and (not key or not base):
        if SLLM == 2:
            key = (summary_limit_gptgod_apikey or "").strip()
            base = (summary_limit_url_2 or "").strip()
            model = summary_limit_model_2
        elif SLLM == 3:
            key = (summary_limit_apikey_3 or "").strip()
            base = (summary_limit_url_3 or "").strip()
            model = summary_limit_model_3
        else:
            key = (qwen_api_key or "").strip()
            base = (summary_limit_base_url or "").strip()
            model = summary_limit_model
    elif not model:
        if SLLM == 2:
            model = summary_limit_model_2
        elif SLLM == 3:
            model = summary_limit_model_3
        else:
            model = summary_limit_model

    if not key and not use_pool:
        raise SystemExit("LLM API key missing (summary_limit)")
    if not base and not use_pool:
        raise SystemExit("LLM base URL missing (summary_limit)")

    cfg["api_key"] = key
    cfg["base_url"] = base
    cfg["model"] = model
    cfg.setdefault("llm_base_url", base)
    cfg.setdefault("enable_thinking", False)
    cfg["use_openrouter_free_pool"] = use_pool
    return cfg


def make_client_from_cfg(cfg: Dict[str, Any]) -> Any:
    from services.llm_client_factory import build_llm_client
    return build_llm_client({
        "api_key": cfg.get("api_key", ""),
        "base_url": cfg.get("base_url", ""),
        "use_openrouter_free_pool": cfg.get("use_openrouter_free_pool", False),
    })


def approx_input_tokens(text: str) -> int:
    if not text:
        return 0
    return len(text.encode("utf-8", errors="ignore"))


def crop_to_input_tokens(text: str, limit_tokens: int) -> str:
    budget = int(limit_tokens)
    if budget <= 0:
        return ""
    b = text.encode("utf-8", errors="ignore")
    if len(b) <= budget:
        return text
    return b[:budget].decode("utf-8", errors="ignore")


def _choice_text(resp: Any) -> str:
    """Extract non-None text from an OpenAI-compatible chat completion response."""
    choices = getattr(resp, "choices", None)
    if not choices:
        return ""
    msg = choices[0].message
    return (getattr(msg, "content", None) or "").strip()


def list_md_files(root: Path) -> List[Path]:
    return sorted(root.glob("*.md"))


def today_str() -> str:
    return datetime.now().date().isoformat()


def write_gather(single_dir: Path, gather_dir: Path, date_str: str) -> Path:
    files = list_md_files(single_dir)
    gather_dir.mkdir(parents=True, exist_ok=True)
    gather_path = gather_dir / f"{date_str}.txt"
    with gather_path.open("w", encoding="utf-8") as f:
        first = True
        for p in files:
            text = p.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                continue
            if not first:
                f.write("\n")
            first = False
            f.write("#" * 100 + "\n")
            f.write(f"{p.name}\n")
            f.write("#" * 100 + "\n")
            f.write(text)
            f.write("\n")
    return gather_path


def make_client() -> OpenAI:
    """Legacy entry-point – creates a client using config.py defaults."""
    cfg = build_effective_cfg(user_id=None)
    return make_client_from_cfg(cfg)


def get_summary_limit_model(cfg: Optional[Dict[str, Any]] = None) -> str:
    """Return the model name to use, honouring *cfg* overrides."""
    if cfg and cfg.get("model"):
        return cfg["model"]
    if SLLM == 2:
        return summary_limit_model_2
    if SLLM == 3:
        return summary_limit_model_3
    return summary_limit_model


def non_ws_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def normalize_heading(line: str) -> str:
    raw = line.strip()
    raw = re.sub(r"^#+\s*", "", raw)
    raw = re.sub(r"^[^\w\u4e00-\u9fff]+", "", raw)
    raw = raw.lstrip(":：- ").strip()
    return raw


def heading_key(line: str) -> Optional[str]:
    norm = normalize_heading(line)
    for key, labels in SECTION_LABELS.items():
        if norm.startswith(labels[0]) or norm.startswith(labels[1]):
            return key
    return None


def split_sections(lines: List[str]) -> Tuple[List[str], List[Tuple[str, str, List[str]]]]:
    prefix: List[str] = []
    sections: List[Tuple[str, str, List[str]]] = []
    current_key: Optional[str] = None
    current_heading: str = ""
    current_lines: List[str] = []

    for line in lines:
        key = heading_key(line)
        if key:
            if current_key:
                sections.append((current_key, current_heading, current_lines))
            elif current_lines:
                prefix.extend(current_lines)
            current_key = key
            if key == "memory":
                inline = re.match(
                    r"^\s*(?:一句话记忆版|一句话记忆)\s*[:：]\s*(.*)$",
                    line.strip(),
                )
                current_heading = "一句话记忆版："
                value = inline.group(1).strip() if inline else ""
                current_lines = [value] if value else []
            else:
                current_heading = line
                current_lines = []
            continue
        if current_key is None:
            prefix.append(line)
        else:
            current_lines.append(line)

    if current_key:
        sections.append((current_key, current_heading, current_lines))
    return prefix, sections


def ensure_section_spacing(text: str) -> str:
    if not text.strip():
        return text
    lines = text.splitlines()
    out: List[str] = []
    for line in lines:
        if heading_key(line):
            if out and out[-1].strip():
                out.append("")
        out.append(line)
    return "\n".join(out).rstrip() + "\n"


def normalize_style(text: str) -> str:
    lines = text.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if not raw:
            out.append("")
            i += 1
            continue
        if re.match(r"^-{3,}\s*$", raw):
            i += 1
            continue
        line = re.sub(r"^#+\s*", "", raw).strip()
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = line.replace("：", ":")

        m = re.match(r"^(?:📖\s*)?标题\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            out.append(f"📖标题：{m.group(1).strip()}")
            i += 1
            continue
        m = re.match(r"^(?:🌐\s*)?(?:来源|source)\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            out.append(f"🌐来源：{m.group(1).strip()}")
            i += 1
            continue
        m = re.match(r"^(?:机构|作者机构|单位|机构名)\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            out.append(f"{m.group(1).strip()}")
            i += 1
            continue

        if re.match(r"^(?:机构|作者机构|单位|机构名)$", line, re.IGNORECASE):
            content = ""
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if candidate:
                    content = re.sub(r"\*\*(.*?)\*\*", r"\1", candidate)
                    break
                j += 1
            out.append(content)
            i = j + 1
            continue
        if re.match(r"^标题$", line, re.IGNORECASE):
            content = ""
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if candidate:
                    content = re.sub(r"\*\*(.*?)\*\*", r"\1", candidate)
                    break
                j += 1
            out.append(f"📖标题：{content}" if content else "📖标题：")
            i = j + 1
            continue
        if re.match(r"^(?:来源|source)$", line, re.IGNORECASE):
            content = ""
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if candidate:
                    content = re.sub(r"\*\*(.*?)\*\*", r"\1", candidate)
                    break
                j += 1
            out.append(f"🌐来源：{content}" if content else "🌐来源：")
            i = j + 1
            continue

        key = heading_key(line)
        if key == "intro":
            if out and out[-1].strip():
                out.append("")
            out.append("🛎️文章简介")
            i += 1
            continue
        if key == "method":
            if out and out[-1].strip():
                out.append("")
            out.append("📝重点思路")
            i += 1
            continue
        if key == "findings":
            if out and out[-1].strip():
                out.append("")
            out.append("🔎分析总结")
            i += 1
            continue
        if key == "opinion":
            if out and out[-1].strip():
                out.append("")
            out.append("💡个人观点")
            i += 1
            continue
        if key == "memory":
            if out and out[-1].strip():
                out.append("")
            # Preserve the full line (e.g. "一句话记忆版：...") as-is
            out.append(line)
            i += 1
            continue

        if re.match(r"^(?:[-*•]|🔹|🔸)\s*", line) or re.match(r"^\d+[.)]\s*", line):
            content = re.sub(r"^(?:[-*•]|🔹|🔸)\s*", "", line)
            content = re.sub(r"^\d+[.)]\s*", "", content)
            content = re.sub(r"\*\*(.*?)\*\*", r"\1", content).strip()
            if content:
                out.append(f"🔸{content}")
            i += 1
            continue

        out.append(line)
        i += 1
    return "\n".join(out).strip() + "\n"


def card_needs_refinement(
    text: str,
    *,
    limits: Optional[Dict[str, int]] = None,
) -> bool:
    """Return whether a complete eight-field card exceeds the final contract."""
    card = parse_card(text)
    if not all(card.field_text(key).strip() for key in CARD_FIELD_ORDER):
        # A compressor must not invent a missing field. The existing structure
        # repair path is safer for incomplete model output.
        return False
    effective_limits = limits or CARD_LIMITS_DEFAULT
    if any(
        non_ws_len(card.field_text(key)) > int(effective_limits.get(key, 0) or 0)
        for key in CARD_FIELD_ORDER
        if effective_limits.get(key)
    ):
        return True
    return len(card.key_ideas) > 3 or len(card.analysis_summary) > 3


def card_contract_errors(
    candidate: str,
    *,
    source_draft: str,
    limits: Optional[Dict[str, int]] = None,
) -> List[str]:
    """Validate structure, limits, metadata and numeric preservation."""
    effective_limits = limits or CARD_LIMITS_DEFAULT
    card = parse_card(candidate)
    source_card = parse_card(source_draft)
    errors: List[str] = []

    missing = [key for key in CARD_FIELD_ORDER if not card.field_text(key).strip()]
    if missing:
        errors.append("missing=" + ",".join(missing))
    for key in CARD_FIELD_ORDER:
        limit = int(effective_limits.get(key, 0) or 0)
        if limit and non_ws_len(card.field_text(key)) > limit:
            errors.append(f"{key}>{limit}")
    if len(card.key_ideas) != 3:
        errors.append(f"key_ideas_count={len(card.key_ideas)}")
    if len(card.analysis_summary) != 3:
        errors.append(f"analysis_summary_count={len(card.analysis_summary)}")
    if card.research_question and not card.research_question.rstrip().endswith(("？", "?")):
        errors.append("research_question_not_question")

    for key in ("original_title", "source"):
        expected = str(getattr(source_card, key) or "").strip()
        actual = str(getattr(card, key) or "").strip()
        if expected and actual != expected:
            errors.append(f"{key}_changed")

    trace = card_deterministic_report(
        candidate,
        source_text=source_draft,
        refinement_input=source_draft,
    )
    unsupported_numbers = trace.get("unsupported_numbers") or {}
    if unsupported_numbers:
        errors.append("unsupported_numbers=" + ",".join(sorted(unsupported_numbers)))
    return errors


def rewrite_card(
    client: OpenAI,
    text: str,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
) -> str:
    """Compress all eight recommendation fields in one validated LLM call."""
    ecfg = effective_cfg or {}
    raw_prompt = (
        ecfg["card_prompt"] if "card_prompt" in ecfg else summary_limit_prompt_card
    )
    sys_prompt = str(raw_prompt or "").strip()
    source_draft = text.strip()
    if not sys_prompt or not source_draft:
        return text

    hard_limit = int(ecfg.get("input_hard_limit") or summary_limit_input_hard_limit)
    safety_margin = int(
        ecfg.get("input_safety_margin") or summary_limit_input_safety_margin
    )
    limit_total = hard_limit - safety_margin
    max_tok = ecfg.get("max_tokens")
    if max_tok is None:
        max_tok = summary_limit_max_tokens
    last_error: Optional[BaseException] = None
    previous_errors: List[str] = []

    for _ in range(max_retries):
        retry_note = ""
        if previous_errors:
            retry_note = (
                "\n\n上一次输出未通过程序校验："
                + "；".join(previous_errors)
                + "。请从原始卡片重新精简，不要解释。"
            )
        prompt = sys_prompt + retry_note
        user_budget = max(1, limit_total - approx_input_tokens(prompt))
        user_content = crop_to_input_tokens(source_draft, user_budget)
        kwargs: Dict[str, Any] = {
            "temperature": 0,
            "max_tokens": int(max_tok or 2048),
        }
        kwargs.update(build_thinking_kwargs(ecfg))
        resp = client.chat.completions.create(
            model=get_summary_limit_model(ecfg),
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            stream=False,
            **kwargs,
        )
        try:
            candidate = require_nonempty_text(
                _choice_text(resp),
                operation="summary_limit_card_rewrite",
            )
        except EmptyLlmResponseError as exc:
            last_error = exc
            previous_errors = ["empty_response"]
            continue
        candidate = ensure_section_spacing(normalize_style(candidate))
        previous_errors = card_contract_errors(
            candidate,
            source_draft=source_draft,
            limits=ecfg.get("card_limits", CARD_LIMITS_DEFAULT),
        )
        if not previous_errors:
            return candidate
        last_error = InvalidLlmResponseError(
            "full-card refinement failed validation: " + "; ".join(previous_errors)
        )

    if last_error is not None:
        raise last_error
    raise InvalidLlmResponseError("full-card refinement did not produce output")


def rewrite_block(
    client: OpenAI,
    text: str,
    sys_prompt: str,
    limit_chars: int,
    max_retries: int = 3,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> str:
    ecfg = effective_cfg or {}
    content = text.strip()
    if not content:
        return content
    last_error: Optional[BaseException] = None
    for _ in range(max_retries):
        hard_limit = int(ecfg.get("input_hard_limit") or summary_limit_input_hard_limit)
        safety_margin = int(ecfg.get("input_safety_margin") or summary_limit_input_safety_margin)
        limit_total = hard_limit - safety_margin
        sys_tokens = approx_input_tokens(sys_prompt)
        user_budget = max(1, limit_total - sys_tokens)
        user_content = crop_to_input_tokens(content, user_budget)
        temp = ecfg.get("temperature") if ecfg.get("temperature") is not None else summary_limit_temperature
        max_tok = ecfg.get("max_tokens") if ecfg.get("max_tokens") is not None else summary_limit_max_tokens
        kwargs: Dict[str, Any] = {}
        if temp is not None:
            kwargs["temperature"] = float(temp)
        if max_tok is not None:
            kwargs["max_tokens"] = int(max_tok)
        kwargs.update(build_thinking_kwargs(ecfg))
        resp = client.chat.completions.create(
            model=get_summary_limit_model(ecfg),
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=False,
            **kwargs,
        )
        try:
            new_text = require_nonempty_text(
                _choice_text(resp),
                operation="summary_limit_block_rewrite",
            )
        except EmptyLlmResponseError as exc:
            last_error = exc
            continue
        content = new_text
        if non_ws_len(content) <= limit_chars:
            return content
    if last_error is not None:
        raise last_error
    raise InvalidLlmResponseError(
        "model did not satisfy the summary block length limit"
    )


def compress_headline(
    client: OpenAI,
    text: str,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> str:
    ecfg = effective_cfg or {}
    raw_prompt = (
        ecfg["headline_prompt"]
        if "headline_prompt" in ecfg
        else summary_limit_prompt_headline
    )
    sys_prompt = str(raw_prompt or "").strip()
    content = text.strip()
    if not sys_prompt or not content:
        return text
    hard_limit = int(ecfg.get("input_hard_limit") or summary_limit_input_hard_limit)
    safety_margin = int(ecfg.get("input_safety_margin") or summary_limit_input_safety_margin)
    limit_total = hard_limit - safety_margin
    sys_tokens = approx_input_tokens(sys_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = crop_to_input_tokens(content, user_budget)
    max_tok = ecfg.get("max_tokens") if ecfg.get("max_tokens") is not None else summary_limit_max_tokens
    resp = client.chat.completions.create(
        model=get_summary_limit_model(ecfg),
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        max_tokens=max_tok or 2048,
        temperature=0,
        **build_thinking_kwargs(ecfg),
    )
    return require_nonempty_text(
        _choice_text(resp),
        operation="summary_limit_headline_rewrite",
    )


def apply_headline_limit(
    client: OpenAI,
    lines: List[str],
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> List[str]:
    ecfg = effective_cfg or {}
    hl_limit = int(ecfg.get("headline_limit") or summary_limit_headline_limit)
    title_idx = None
    for idx, line in enumerate(lines):
        if line.strip().startswith("📖标题"):
            title_idx = idx
            break
    if title_idx is None:
        return lines
    for prev_idx in range(title_idx - 1, -1, -1):
        candidate = lines[prev_idx].strip()
        if not candidate:
            continue
        if non_ws_len(candidate) <= hl_limit:
            return lines
        lines[prev_idx] = compress_headline(client, candidate, effective_cfg=ecfg) + "\n"
        return lines
    return lines


def extract_arxiv_id(source: str) -> Optional[str]:
    if not source:
        return None
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", source)
    if not m:
        return None
    version = m.group(2) or ""
    return f"{m.group(1)}{version}"


def load_pdf_info_map(date_str: str) -> Dict[str, Dict[str, str]]:
    info_path = Path(DATA_ROOT) / "pdf_info" / f"{date_str}.json"
    if not info_path.exists():
        return {}
    try:
        data = json.loads(info_path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "") or "")
        arxiv_id = extract_arxiv_id(source)
        if not arxiv_id:
            continue
        out[arxiv_id] = item
    return out


def load_pdf_info_map_for_run(
    date_str: str,
    *,
    user_id: int = 0,
    output_mode: str = "file",
    pdb: Any = None,
) -> Dict[str, Dict[str, str]]:
    """Load pdf metadata for inject_pdf_info (file json or pipeline_paper_info DB)."""
    if output_mode == "db" and pdb is not None:
        raw = pdb.get_paper_info_map(user_id, date_str)
        out: Dict[str, Dict[str, str]] = {}
        for arxiv_id, row in raw.items():
            out[arxiv_id] = {
                "title": str(row.get("title") or ""),
                "source": str(row.get("source") or ""),
                "instution": str(row.get("institution") or row.get("instution") or ""),
            }
        return out
    return load_pdf_info_map(date_str)


def inject_pdf_info(text: str, md_path: Path, pdf_info_map: Dict[str, Dict[str, str]]) -> str:
    if not text.strip() or not pdf_info_map:
        return text
    key = md_path.stem
    info = pdf_info_map.get(key)
    if info is None:
        key_no_version = re.sub(r"v\d+$", "", key)
        info = pdf_info_map.get(key_no_version)
    if not info:
        return text

    title = str(info.get("title", "") or "").strip()
    source = str(info.get("source", "") or "").strip()
    instution = str(info.get("instution") or info.get("institution") or "").strip()

    lines = text.splitlines()
    first_idx = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_idx = idx
            break
    if first_idx is None:
        first_idx = 0
        lines.insert(0, "笔记标题：")

    first_line = lines[first_idx].strip()
    if instution:
        if first_line.startswith("笔记标题"):
            rest = first_line[len("笔记标题"):].lstrip("：:")
            lines[first_idx] = f"{instution}：{rest}".rstrip()
        elif first_line.startswith("标题"):
            rest = first_line[len("标题"):].lstrip("：:")
            lines[first_idx] = f"{instution}：{rest}".rstrip()
        else:
            lines[first_idx] = f"{instution}：{first_line}".rstrip()

    # Remove existing title/source lines before the first section header
    top_end = len(lines)
    for idx, line in enumerate(lines):
        if heading_key(line):
            top_end = idx
            break
    filtered: List[str] = []
    for idx, line in enumerate(lines):
        if idx < top_end:
            s = line.strip()
            if s.startswith("📖标题") or s.startswith("标题") or s.startswith("🌐来源") or s.lower().startswith("source") or s.startswith("来源"):
                continue
        filtered.append(line)
    lines = filtered

    insert_lines: List[str] = []
    if title:
        insert_lines.append(f"📖标题：{title}")
    if source:
        insert_lines.append(f"🌐来源：{source}")

    if insert_lines:
        insert_at = min(first_idx + 1, len(lines))
        lines[insert_at:insert_at] = insert_lines

    return "\n".join(lines).rstrip() + "\n"


def structure_matches_example(
    client: OpenAI,
    text: str,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
    paper_id: str = "",
) -> bool:
    ecfg = effective_cfg or {}
    raw_prompt = (
        ecfg["structure_check_prompt"]
        if "structure_check_prompt" in ecfg
        else summary_limit_prompt_structure_check
    )
    sys_prompt = str(raw_prompt or "").strip()
    if not sys_prompt:
        return True
    content = text.strip()
    if not content:
        return False
    hard_limit = int(ecfg.get("input_hard_limit") or summary_limit_input_hard_limit)
    safety_margin = int(ecfg.get("input_safety_margin") or summary_limit_input_safety_margin)
    limit_total = hard_limit - safety_margin
    sys_tokens = approx_input_tokens(sys_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = crop_to_input_tokens(content, user_budget)
    resp = client.chat.completions.create(
        model=get_summary_limit_model(ecfg),
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        max_tokens=32,
        temperature=0,
        **build_thinking_kwargs(ecfg),
    )
    reply = require_nonempty_text(
        _choice_text(resp),
        operation="summary_limit_structure_check",
    ).upper()
    if reply.startswith("YES"):
        return True
    if reply.startswith("NO"):
        return False
    raise InvalidLlmResponseError(
        "model returned an invalid summary structure decision"
    )


def restructure_to_example(
    client: OpenAI,
    text: str,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> str:
    ecfg = effective_cfg or {}
    raw_prompt = (
        ecfg["structure_rewrite_prompt"]
        if "structure_rewrite_prompt" in ecfg
        else summary_limit_prompt_structure_rewrite
    )
    sys_prompt = str(raw_prompt or "").strip()
    if not sys_prompt:
        return text
    content = text.strip()
    if not content:
        return text
    hard_limit = int(ecfg.get("input_hard_limit") or summary_limit_input_hard_limit)
    safety_margin = int(ecfg.get("input_safety_margin") or summary_limit_input_safety_margin)
    limit_total = hard_limit - safety_margin
    sys_tokens = approx_input_tokens(sys_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = crop_to_input_tokens(content, user_budget)
    max_tok = ecfg.get("max_tokens") if ecfg.get("max_tokens") is not None else summary_limit_max_tokens
    resp = client.chat.completions.create(
        model=get_summary_limit_model(ecfg),
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        max_tokens=max_tok or 2048,
        temperature=0,
        **build_thinking_kwargs(ecfg),
    )
    return require_nonempty_text(
        _choice_text(resp),
        operation="summary_limit_structure_rewrite",
    )


def local_normalize_summary(
    md_path: Path,
    pdf_info_map: Dict[str, Dict[str, str]],
) -> str:
    """No-LLM fallback: inject metadata and normalize layout only."""
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        return ""
    text = inject_pdf_info(text, md_path, pdf_info_map)
    text = normalize_style(text)
    return ensure_section_spacing(text)


def refine_full_card_text(
    client: OpenAI,
    text: str,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[str, bool, Optional[BaseException]]:
    """Run only the validated full-card stage.

    The returned text is safe to freeze and feed into different downstream
    prompt chains during matched A/B evaluation.  A failed full-card rewrite
    intentionally returns the normalized original so production can continue
    through its legacy section fallback, exactly as before.
    """
    if not text.strip():
        raise ValueError("summary_limit input is empty")
    ecfg = effective_cfg or {}
    base_text = normalize_style(text)
    raw_card_prompt = (
        ecfg["card_prompt"] if "card_prompt" in ecfg else summary_limit_prompt_card
    )
    card_prompt = str(raw_card_prompt or "").strip()
    if not card_prompt or not card_needs_refinement(
        base_text,
        limits=ecfg.get("card_limits", CARD_LIMITS_DEFAULT),
    ):
        return base_text, False, None
    try:
        return rewrite_card(client, base_text, effective_cfg=ecfg), True, None
    except Exception as exc:
        return base_text, False, exc


def finalize_card_text(
    client: OpenAI,
    base_text: str,
    md_path: Path,
    pdf_info_map: Dict[str, Dict[str, str]],
    *,
    card_rewritten: bool,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Run only the user-visible downstream refinement stages."""
    ecfg = effective_cfg or {}
    sec_limits = ecfg.get("section_limits", SECTION_LIMITS_DEFAULT)
    sec_prompts = ecfg.get("section_prompts", SECTION_PROMPTS_DEFAULT)
    status = "copied"

    base_text = normalize_style(inject_pdf_info(base_text, md_path, pdf_info_map))
    lines = base_text.splitlines(keepends=True)
    lines = apply_headline_limit(client, lines, effective_cfg=ecfg)
    base_text = "".join(lines)
    structure_ok = card_rewritten or structure_matches_example(
        client, base_text, effective_cfg=ecfg, paper_id=md_path.stem
    )
    if structure_ok:
        prefix, sections = split_sections(lines)
        if not sections:
            raise InvalidLlmResponseError(
                "summary_limit output has no recognized sections"
            )
        out_lines: List[str] = []
        out_lines.extend(prefix)
        rewritten_any = False
        for key, heading, content_lines in sections:
            if out_lines and out_lines[-1].strip():
                out_lines.append("\n")
            block_text = "".join(content_lines).strip()
            limit = sec_limits.get(key, 0)
            if limit and non_ws_len(block_text) > limit:
                sys_prompt = sec_prompts.get(key, "")
                if sys_prompt:
                    block_text = rewrite_block(
                        client,
                        block_text,
                        sys_prompt,
                        limit_chars=limit,
                        effective_cfg=ecfg,
                    )
                    rewritten_any = True
            if key == "memory":
                memory_text = "".join(
                    line.strip() for line in block_text.splitlines()
                )
                out_lines.append(f"一句话记忆版：{memory_text}\n")
                continue
            out_lines.append(heading)
            if block_text:
                if not block_text.endswith("\n"):
                    block_text += "\n"
                out_lines.append(block_text)
        out_text = ensure_section_spacing("".join(out_lines))
        status = "rewritten" if card_rewritten or rewritten_any else "copied"
    else:
        out_text = restructure_to_example(client, base_text, effective_cfg=ecfg)
        out_text = ensure_section_spacing(normalize_style(out_text))
        status = "rewritten"

    out_text = require_nonempty_text(
        out_text,
        operation="summary_limit_output",
    )
    return out_text, status


def process_one_with_fallback(
    client: OpenAI,
    md_path: Path,
    out_path: Path,
    pdf_info_map: Dict[str, Dict[str, str]],
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[Path, str]:
    try:
        return process_one(
            client, md_path, out_path, pdf_info_map, effective_cfg=effective_cfg
        )
    except Exception as exc:
        fallback = require_nonempty_text(
            local_normalize_summary(md_path, pdf_info_map),
            operation="summary_limit_local_fallback",
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(fallback, encoding="utf-8")
        print(
            f"[SUMMARY_LIMIT] fallback=copied_local for {md_path.stem}: "
            f"{redact_sensitive_text(repr(exc), max_length=500)}",
            flush=True,
        )
        return md_path, "fallback"


def process_one(
    client: OpenAI,
    md_path: Path,
    out_path: Path,
    pdf_info_map: Dict[str, Dict[str, str]],
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[Path, str]:
    ecfg = effective_cfg or {}
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        raise ValueError(f"summary_limit input is empty: {md_path.name}")
    base_text, card_rewritten, refinement_error = refine_full_card_text(
        client,
        text,
        effective_cfg=ecfg,
    )
    if refinement_error is not None:
        print(
            f"[SUMMARY_LIMIT] fallback=legacy_sections for {md_path.stem}: "
            f"{redact_sensitive_text(repr(refinement_error), max_length=500)}",
            flush=True,
        )
    out_text, status = finalize_card_text(
        client,
        base_text,
        md_path,
        pdf_info_map,
        card_rewritten=card_rewritten,
        effective_cfg=ecfg,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_text, encoding="utf-8")
    return md_path, status


def run() -> None:
    import os as _os
    ap = argparse.ArgumentParser("summary_limit")
    ap.add_argument("--input-dir", default=str(Path(DATA_ROOT) / "paper_summary" / "single"))
    ap.add_argument("--out-root", default=str(Path(DATA_ROOT) / "summary_limit"))
    ap.add_argument("--date", default="")
    ap.add_argument("--concurrency", type=int, default=summary_limit_concurrency)
    ap.add_argument("--user-id", type=int, default=None, help="User ID for per-user config overrides")
    ap.add_argument("--output-mode", default=None, choices=["file", "db"],
                    help="output mode: 'file' (default) or 'db' (writes to pipeline_summaries.summary_limit)")
    args = ap.parse_args()

    output_mode = args.output_mode or _os.environ.get("PIPELINE_OUTPUT_MODE", "file")
    uid = args.user_id if args.user_id is not None else 0
    run_date = _os.environ.get("RUN_DATE") or today_str()
    date_str = args.date or run_date

    _pdb = None
    if output_mode == "db":
        try:
            _root_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            import sys as _sys
            _sys.path.insert(0, _root_dir)
            from services import pipeline_db_service as _pdb_mod
            _pdb = _pdb_mod
        except Exception as exc:
            print(f"[WARN] pipeline_db_service unavailable: {exc!r}; falling back to file", flush=True)
            output_mode = "file"

    # Determine input: DB mode reads raw summaries from DB as virtual .md; file mode reads files
    if output_mode == "db" and _pdb is not None:
        # Build synthetic Path->text mapping from DB
        summaries_map = _pdb.get_summaries_map(uid, date_str)
        if not summaries_map:
            print(f"[SUMMARY_LIMIT] No summaries in DB for user={uid} date={date_str}; skip", flush=True)
            return
        # Write raw summaries to a temp dir so process_one can read them as files
        import tempfile
        tmp_dir = Path(tempfile.mkdtemp(prefix="summary_limit_"))
        for arxiv_id, row in summaries_map.items():
            raw = row.get("summary_raw", "")
            if raw:
                (tmp_dir / f"{arxiv_id}.md").write_text(raw, encoding="utf-8")
        in_dir = tmp_dir
    else:
        in_root = Path(args.input_dir)
        if not in_root.exists():
            print(f"[SUMMARY_LIMIT] input dir not found: {in_root}, skip summary_limit", flush=True)
            return
        if date_str:
            candidate = in_root / date_str
            if candidate.is_dir():
                in_dir = candidate
            else:
                subdirs = sorted(
                    [d for d in in_root.iterdir() if d.is_dir()
                     and len(d.name) == 10 and d.name[4] == "-"],
                    key=lambda d: d.name,
                )
                if subdirs:
                    in_dir = subdirs[-1]
                    date_str = in_dir.name
                else:
                    in_dir = in_root
        else:
            in_dir = in_root

    files = list_md_files(in_dir)
    if not files:
        print(f"[SUMMARY_LIMIT] no md files in {in_dir}, skip summary_limit", flush=True)
        return
    print("============开始生成 summary_limit ============", flush=True)

    out_root = Path(args.out_root)
    single_dir = out_root / "single" / date_str
    gather_dir = out_root / "gather" / date_str
    single_dir.mkdir(parents=True, exist_ok=True)

    pdf_info_map = load_pdf_info_map_for_run(
        date_str, user_id=uid, output_mode=output_mode, pdb=_pdb
    )

    if output_mode == "db" and _pdb is not None:
        existing_db = _pdb.get_summaries_map(uid, date_str)
        to_run = [p for p in files if not existing_db.get(p.stem, {}).get("summary_limit")]
    else:
        to_run = [p for p in files if not (single_dir / f"{p.stem}.md").exists()]

    total = len(to_run)
    if total == 0:
        if output_mode != "db":
            gather_path = write_gather(single_dir, gather_dir, date_str)
            print(f"[SUMMARY_LIMIT] all files already processed, single_dir={single_dir}", flush=True)
            print(f"[SUMMARY_LIMIT] gather_path={gather_path}", flush=True)
        else:
            print(f"[SUMMARY_LIMIT] all already processed in DB for user={uid} date={date_str}", flush=True)
        return

    ecfg = build_effective_cfg(user_id=args.user_id)
    client = make_client_from_cfg(ecfg)
    workers = max(1, int(args.concurrency or 0))
    print(f"[SUMMARY_LIMIT] input_dir={in_dir} total={total} concurrency={workers} "
          f"user_id={args.user_id} output_mode={output_mode}", flush=True)

    start = time.monotonic()
    done = 0
    empty = 0
    copied = 0
    rewritten = 0
    fallbacks = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {
            ex.submit(
                process_one_with_fallback,
                client,
                p,
                single_dir / f"{p.stem}.md",
                pdf_info_map,
                effective_cfg=ecfg,
            ): p
            for p in to_run
        }
        for fut in as_completed(future_map):
            src = future_map[fut]
            try:
                out_path_result, status = fut.result()
                if not status:
                    empty += 1
                else:
                    if status == "copied":
                        copied += 1
                    elif status == "rewritten":
                        rewritten += 1
                    elif status == "fallback":
                        fallbacks += 1
                    # In DB mode, read the written file and persist to DB
                    if output_mode == "db" and _pdb is not None:
                        limit_file = single_dir / f"{src.stem}.md"
                        if limit_file.exists():
                            try:
                                limit_text = require_nonempty_text(
                                    limit_file.read_text(encoding="utf-8", errors="ignore"),
                                    operation="summary_limit_database_write",
                                )
                                _pdb.upsert_summary_limit(uid, date_str, src.stem, limit_text)
                            except Exception as db_exc:
                                errors += 1
                                print(f"\n[WARN] DB write summary_limit failed for {src.stem}: {db_exc!r}", flush=True)
            except Exception as e:
                errors += 1
                print(f"\r[SUMMARY_LIMIT] error on {src.name}: {e!r}", end="", flush=True)
            done += 1
            elapsed = time.monotonic() - start
            rate = done / elapsed if elapsed > 0 else 0.0
            print(f"\r[SUMMARY_LIMIT] progress done={done}/{total} empty={empty} rate={rate:.2f}/s", end="", flush=True)

    print()
    if output_mode != "db":
        gather_path = write_gather(single_dir, gather_dir, date_str)
        print(
            f"[SUMMARY_LIMIT] stats copied={copied} rewritten={rewritten} "
            f"fallbacks={fallbacks} errors={errors}",
            flush=True,
        )
        print(f"[SUMMARY_LIMIT] single_dir={single_dir}", flush=True)
        print(f"[SUMMARY_LIMIT] gather_path={gather_path}", flush=True)
    else:
        print(f"[SUMMARY_LIMIT] DB output complete for user={uid} date={date_str} "
              f"copied={copied} rewritten={rewritten} fallbacks={fallbacks} "
              f"errors={errors}", flush=True)
    if _pdb is not None and (fallbacks or errors):
        try:
            run_id = int(_os.environ.get("PIPELINE_RUN_ID") or 0)
        except (TypeError, ValueError):
            run_id = 0
        if run_id:
            _pdb.emit_event(
                run_id,
                "summary_limit completed with degraded or failed items",
                level="warning" if not errors else "error",
                event_type="summary_limit_quality",
                payload={"fallbacks": fallbacks, "errors": errors},
            )
    print("============结束生成 summary_limit ============", flush=True)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
