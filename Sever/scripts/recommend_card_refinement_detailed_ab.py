"""Evaluate the final recommendation card emitted by the production pipeline.

Unlike the earlier prompt-only experiment, this runner includes full-card retries,
headline handling, structure checks, and the legacy section fallback.  Raw MinerU
text and complete model outputs stay in the private output directory; only
aggregate scores, hashes, and blind verdicts are written to committed reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


SEVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SEVER_ROOT.parent
if str(SEVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SEVER_ROOT))

import Controller.summary_limit as production_limit  # noqa: E402
from config.recommend_card_prompts import (  # noqa: E402
    ACTIVE_REFINEMENT_VERSION,
    CARD_FIELD_LIMITS,
    REFINEMENT_CANDIDATES,
)
from scripts.recommend_card_prompt_ab import (  # noqa: E402
    DEFAULT_PRIVATE_ROOT,
    _complete,
    _judge,
    _make_deepseek_client,
    _read_json,
    _sample_manifest,
    _write_json,
)
from services.recommend_card_prompt_eval import (  # noqa: E402
    FIELD_LABELS,
    FIELD_ORDER,
    aggregate_version_scores,
    combine_scores,
    deterministic_report,
    extract_json_object,
)
from services.llm_response_guard import (  # noqa: E402
    EmptyLlmResponseError,
    InvalidLlmResponseError,
)
from services.recommend_card_refinement_pairwise import (  # noqa: E402
    PAIRWISE_JUDGE_SYSTEM_PROMPT,
    detailed_promotion_decision,
    normalize_pairwise_result,
)


RAW_VERSION = "raw_no_refinement"
BASELINE_VERSION = "r1_field_limits"
CHALLENGERS = (
    "r4_safe_budget_template",
    "r5_atomic_safe_budget",
    "r6_evidence_safe_budget",
    "r8_atomic_evidence_budget",
    "r9_anchor_first_microcopy",
    "r10_r1_aligned_fallback",
    "r11_r4_aligned_fallback",
    "r12_r8_aligned_fallback",
    "r13_r4_contract_flow",
    "r14_r4_evidence_budget",
    "r15_r4_robust_evidence",
    "r16_r4_selective_contract",
    "r17_r4_reliable_selective",
)
VERSIONS = (RAW_VERSION, BASELINE_VERSION, *CHALLENGERS)
DRAFT_VERSION = "current"
PIPELINE_PROTOCOL_VERSION = 4
DISPLAY_EVALUATOR_VERSION = 2
DISPLAY_JUDGE_VERSION = "deepseek-v4-pro-display-final-v1"
PAIRWISE_JUDGE_VERSION = "deepseek-v4-pro-display-pairwise-v1"
DEFAULT_REPORT = REPO_ROOT / "docs" / "recommend_card_refinement_detailed_ab_results.md"
DEFAULT_LEDGER = REPO_ROOT / "docs" / "recommend_card_refinement_detailed_ab_ledger.json"


ALIGNED_HEADLINE_PROMPT = """\
你是推荐卡片中文短标题压缩器，只能删减或同义改写输入首行，禁止新增机构、作者、方法、结果或数字。
如果输入以“笔记标题：”开头，必须保留该标签并把标签后的标题压到10字以内。
如果输入是“机构：标题”，必须逐字保留已有机构名，把整行压到16字以内；不得猜测或替换机构。
标题只留一个核心对象或方法名，不写完整句、背景和评价。只输出压缩后的单行。
"""

ALIGNED_STRUCTURE_CHECK_PROMPT = """\
你是推荐卡片结构校验器。只判断结构，不评价内容。合法结构必须依次包含：第一行“笔记标题：...”或已有“机构：短标题”；“📖标题：...”；“🌐来源：...”；“推荐理由：...”；“🛎️文章简介”及研究问题、主要贡献；“📝重点思路”恰好3条；“🔎分析总结”恰好3条；“💡个人观点”；“一句话记忆版：...”。只输出YES或NO。
"""

ALIGNED_STRUCTURE_REWRITE_PROMPT = """\
你是推荐卡片结构整理器。只能移动输入已有内容并恢复标签，禁止删减、改写、新增或猜测。第一行保留原有“笔记标题：...”或“机构：短标题”；随后依次输出标题、来源、推荐理由、文章简介、重点思路、分析总结、个人观点、一句话记忆版。只输出整理后的完整卡片。
"""

ALIGNED_SECTION_PROMPTS = {
    "intro": """\
你是推荐卡片文章简介压缩器。只能删减、合并或同义改写输入已有内容，禁止新增事实、数字、因果或评价。严格输出两行：第一行“🔸研究问题：”加一个不超过50字、以“？”结尾的问题；第二行“🔸主要贡献：”加一句不超过60字的核心贡献。专有名词与数字必须保留语境。只输出两行。
""",
    "method": """\
你是推荐卡片重点思路压缩器。只能使用输入已有信息，禁止新增事实或数字。严格输出恰好3行，每行以“🔸”开头，每条只写一个“动作+对象/条件”，正文不超过55字，三条互不重复。只输出3条。
""",
    "findings": """\
你是推荐卡片分析总结压缩器。只能使用输入已有结论与数字，不得加强断言或把相关性改成因果。严格输出恰好3行，每行以“🔸”开头，每条只写一个“结果+必要条件”，正文不超过55字；每条最多保留一组带指标和比较对象的数字。只输出3条。
""",
    "opinion": """\
你是推荐卡片个人观点压缩器。只能删减或同义改写输入观点，禁止新增评价、场景或建议。用不超过55字的一句话保留论文价值与一个最重要边界。只输出正文。
""",
    "memory": """\
你是推荐卡片一句话记忆压缩器。只能删减或同义改写输入内容，禁止新增事实和数字。只保留“对象+关键区别”一个辨识钩子，不超过36字。只输出正文，不带字段名。
""",
}

ALIGNED_SECTION_LIMITS = {
    "intro": 125,
    "method": 180,
    "findings": 180,
    "opinion": 60,
    "memory": 40,
}

EVIDENCE_HEADLINE_PROMPT = """\
你是推荐卡片中文短标题压缩器，只能删减或同义改写输入首行，禁止新增机构、作者、方法、结果或数字。
如果输入以“笔记标题：”开头，必须保留该标签，并把标签后的标题压到16字以内；不要把标签字数算进标题预算。
标题优先保留最能辨识论文的“对象/方法”和“关键区别”；若原题表达“分离A与B”“A对B”之类对照关系，两个对照项都应保留。不要为了更短而删除仍可放进16字的辨识信息。
若输入已有机构前缀，只能逐字保留，不得猜测、替换或新增机构。只输出压缩后的单行。
"""

EVIDENCE_SECTION_PROMPTS = {
    "intro": """\
你是推荐卡片文章简介压缩器。只能删减、合并或同义改写输入已有内容，禁止新增事实、数字、因果或评价。严格输出两行：第一行“🔸研究问题：”加一个不超过65字、以“？”结尾的问题；第二行“🔸主要贡献：”加一句不超过80字的核心贡献。优先保留研究对象、关键约束和方法/数据集名称。只输出两行。
""",
    "method": """\
你是推荐卡片重点思路压缩器。只能使用输入已有信息，禁止新增事实或数字。严格输出恰好3行，每行以“🔸”开头；三条分别保留最关键的机制、实现或实验设计，互不重复。三条正文合计不超过205字，在总预算内优先保留方法名、条件和区分性细节，不要求每条等长。只输出3条。
""",
    "findings": """\
你是推荐卡片分析总结压缩器。只能使用输入已有结论与数字，不得加强断言、改变比较方向或把相关性写成因果。严格输出恰好3行，每行以“🔸”开头；三条正文合计不超过205字。每条保留一个最有区分度的结果及必要条件；关键数字必须连同指标、比较对象和方向一起保留，宁可少留一组数字也不要拆散语境。只输出3条。
""",
    "opinion": """\
你是推荐卡片个人观点压缩器。只能删减或同义改写输入观点，禁止新增评价、场景或建议。用不超过75字的一句话同时保留论文价值与最重要的适用边界。只输出正文。
""",
    "memory": """\
你是推荐卡片一句话记忆压缩器。只能删减或同义改写输入内容，禁止新增事实和数字。用不超过48字保留论文/方法名称（若输入有）与最关键区别，形成可与相邻论文区分的记忆钩子。只输出正文，不带字段名。
""",
}

EVIDENCE_SECTION_LIMITS = {
    "intro": 159,
    "method": 213,
    "findings": 213,
    "opinion": 75,
    "memory": 48,
}

ROBUST_EVIDENCE_SECTION_PROMPTS = {
    "intro": """\
你是推荐卡片文章简介压缩器。只能删减、合并或同义改写输入已有内容，禁止新增事实、数字、因果或评价。严格输出两行：第一行“🔸研究问题：”加一个不超过60字、以“？”结尾的问题；第二行“🔸主要贡献：”加一句不超过75字的核心贡献。优先保留研究对象、关键约束和方法/数据集名称，给标签与标点预留空间。只输出两行。
""",
    "method": """\
你是推荐卡片重点思路压缩器。只能使用输入已有信息，禁止新增事实或数字。严格输出恰好3行，每行以“🔸”开头；三条分别保留最关键的机制、实现或实验设计，互不重复。三条正文合计不超过185字，优先保留方法名、条件和区分性细节，不要求每条等长。只输出3条，不输出标题或解释。
""",
    "findings": """\
你是推荐卡片分析总结压缩器。只能使用输入已有结论与数字，不得加强断言、改变比较方向、把相关性写成因果，也不得新增“需、应、建议、优先”等行动建议。严格输出恰好3行，每行以“🔸”开头；三条正文合计不超过185字。每条保留一个最有区分度的结果及必要条件；数字须连同指标、比较对象和方向保留。只输出3条，不输出标题或解释。
""",
    "opinion": """\
你是推荐卡片个人观点压缩器。只能删减或同义改写输入观点，禁止新增评价、场景或建议。用不超过70字的一句话同时保留论文价值与最重要的适用边界。只输出正文。
""",
    "memory": """\
你是推荐卡片一句话记忆压缩器。只能删减或同义改写输入内容，禁止新增事实和数字。用不超过44字保留论文/方法名称（若输入有）与最关键区别，形成可与相邻论文区分的记忆钩子。只输出正文，不带字段名。
""",
}

SELECTIVE_SECTION_PROMPTS = {
    "intro": ROBUST_EVIDENCE_SECTION_PROMPTS["intro"],
    "method": """\
你是推荐卡片重点思路压缩器。只能使用输入已有信息，禁止新增事实或数字。严格输出恰好3行，每行以“🔸”开头，每条正文不超过55字；三条分别保留最关键的机制、实现或实验设计，互不重复。优先保留方法名、条件和区分性细节。只输出3条，不输出标题或解释。
""",
    "findings": """\
你是推荐卡片分析总结压缩器。只能使用输入已有结论与数字，不得加强断言、改变比较方向、把相关性写成因果，也不得新增“需、应、建议、优先”等行动建议。严格输出恰好3行，每行以“🔸”开头、正文不超过55字；每条保留一个最有区分度的结果及必要条件，数字须连同指标、比较对象和方向保留。只输出3条，不输出标题或解释。
""",
    "opinion": ROBUST_EVIDENCE_SECTION_PROMPTS["opinion"],
    "memory": ROBUST_EVIDENCE_SECTION_PROMPTS["memory"],
}

SELECTIVE_SECTION_LIMITS = {
    "intro": 159,
    "method": 213,
    "findings": 213,
    "opinion": 75,
    "memory": 48,
}

RELIABLE_SELECTIVE_SECTION_PROMPTS = dict(ALIGNED_SECTION_PROMPTS)

ALIGNED_CARD_BASE = {
    "r10_r1_aligned_fallback": "r1_field_limits",
    "r11_r4_aligned_fallback": "r4_safe_budget_template",
    "r12_r8_aligned_fallback": "r8_atomic_evidence_budget",
    "r13_r4_contract_flow": "r4_safe_budget_template",
    "r14_r4_evidence_budget": "r4_safe_budget_template",
    "r15_r4_robust_evidence": "r4_safe_budget_template",
    "r16_r4_selective_contract": "r4_safe_budget_template",
    "r17_r4_reliable_selective": "r4_safe_budget_template",
}

CONTRACT_FLOW_VERSIONS = {
    "r13_r4_contract_flow",
    "r14_r4_evidence_budget",
    "r15_r4_robust_evidence",
    "r16_r4_selective_contract",
    "r17_r4_reliable_selective",
}

EVIDENCE_BUDGET_VERSIONS = {"r14_r4_evidence_budget"}
ROBUST_EVIDENCE_VERSIONS = {"r15_r4_robust_evidence"}
SELECTIVE_CONTRACT_VERSIONS = {"r16_r4_selective_contract"}
RELIABLE_SELECTIVE_VERSIONS = {"r17_r4_reliable_selective"}

MATCHED_DOWNSTREAM_COMPARISONS = (
    ("r1_field_limits", "r10_r1_aligned_fallback"),
    ("r4_safe_budget_template", "r11_r4_aligned_fallback"),
    ("r8_atomic_evidence_budget", "r12_r8_aligned_fallback"),
    ("r11_r4_aligned_fallback", "r13_r4_contract_flow"),
    ("r13_r4_contract_flow", "r14_r4_evidence_budget"),
    ("r14_r4_evidence_budget", "r15_r4_robust_evidence"),
    ("r13_r4_contract_flow", "r15_r4_robust_evidence"),
    ("r13_r4_contract_flow", "r16_r4_selective_contract"),
    ("r15_r4_robust_evidence", "r16_r4_selective_contract"),
    ("r13_r4_contract_flow", "r17_r4_reliable_selective"),
    ("r16_r4_selective_contract", "r17_r4_reliable_selective"),
)


def _card_prompt(version: str) -> str:
    base_version = ALIGNED_CARD_BASE.get(version, version)
    return REFINEMENT_CANDIDATES[base_version]


def _uses_aligned_fallback(version: str) -> bool:
    return version in ALIGNED_CARD_BASE


def _stage_base_version(version: str) -> str:
    return ALIGNED_CARD_BASE.get(version, version)


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pipeline_fingerprint(version: str) -> str:
    aligned = _uses_aligned_fallback(version)
    evidence_budget = version in EVIDENCE_BUDGET_VERSIONS
    robust_evidence = version in ROBUST_EVIDENCE_VERSIONS
    selective_contract = version in SELECTIVE_CONTRACT_VERSIONS
    reliable_selective = version in RELIABLE_SELECTIVE_VERSIONS
    selective_limits = selective_contract or reliable_selective
    evidence_style = evidence_budget or robust_evidence or selective_limits
    contract_flow = version in CONTRACT_FLOW_VERSIONS
    payload = {
        "protocol": PIPELINE_PROTOCOL_VERSION,
        "version": version,
        "prompt": "" if version == RAW_VERSION else _card_prompt(version),
        "summary_limit_sha256": _file_sha256(Path(production_limit.__file__)),
        "card_limits": CARD_FIELD_LIMITS,
        "section_limits": (
            SELECTIVE_SECTION_LIMITS
            if selective_limits
            else (
                EVIDENCE_SECTION_LIMITS
                if evidence_style
                else (
                    ALIGNED_SECTION_LIMITS
                    if aligned
                    else production_limit.SECTION_LIMITS_DEFAULT
                )
            )
        ),
        "section_prompts": (
            RELIABLE_SELECTIVE_SECTION_PROMPTS
            if reliable_selective
            else (
                SELECTIVE_SECTION_PROMPTS
                if selective_contract
                else (
                    ROBUST_EVIDENCE_SECTION_PROMPTS
                    if robust_evidence
                    else (
                        EVIDENCE_SECTION_PROMPTS
                        if evidence_budget
                        else (
                            ALIGNED_SECTION_PROMPTS
                            if aligned
                            else production_limit.SECTION_PROMPTS_DEFAULT
                        )
                    )
                )
            )
        ),
        "headline_limit": (
            21
            if evidence_style
            else (
                16 if aligned else production_limit.summary_limit_headline_limit
            )
        ),
        "headline_prompt": (
            EVIDENCE_HEADLINE_PROMPT
            if evidence_style
            else (
                ALIGNED_HEADLINE_PROMPT
                if aligned
                else production_limit.summary_limit_prompt_headline
            )
        ),
        "structure_check": (
            ""
            if contract_flow
            else (
                ALIGNED_STRUCTURE_CHECK_PROMPT
                if aligned
                else production_limit.summary_limit_prompt_structure_check
            )
        ),
        "structure_rewrite": (
            ALIGNED_STRUCTURE_REWRITE_PROMPT
            if aligned
            else production_limit.summary_limit_prompt_structure_rewrite
        ),
    }
    return _text_sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _full_card_stage_fingerprint(version: str) -> str:
    base_version = _stage_base_version(version)
    payload = {
        "protocol": PIPELINE_PROTOCOL_VERSION,
        "base_version": base_version,
        "prompt": _card_prompt(base_version),
        "summary_limit_sha256": _file_sha256(Path(production_limit.__file__)),
        "card_limits": CARD_FIELD_LIMITS,
    }
    return _text_sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _classify_system_prompt(
    system_prompt: str,
    card_prompt: str,
    effective_cfg: Mapping[str, Any],
) -> str:
    if card_prompt and system_prompt.startswith(card_prompt.strip()):
        return "full_card"
    known = {
        str(effective_cfg.get("headline_prompt") or "").strip(): "headline",
        str(effective_cfg.get("structure_check_prompt") or "").strip(): "structure_check",
        str(effective_cfg.get("structure_rewrite_prompt") or "").strip(): "structure_rewrite",
    }
    for key, prompt in effective_cfg.get("section_prompts", {}).items():
        known[str(prompt or "").strip()] = f"section_{key}"
    known.pop("", None)
    return known.get(system_prompt.strip(), "other")


class _RecordingCompletions:
    def __init__(
        self,
        inner: Any,
        calls: list[str],
        card_prompt: str,
        effective_cfg: Mapping[str, Any],
    ):
        self._inner = inner
        self._calls = calls
        self._card_prompt = card_prompt
        self._effective_cfg = effective_cfg

    def create(self, *args: Any, **kwargs: Any) -> Any:
        messages = kwargs.get("messages") or []
        system_prompt = ""
        for message in messages:
            if message.get("role") == "system":
                system_prompt = str(message.get("content") or "")
                break
        self._calls.append(
            _classify_system_prompt(
                system_prompt, self._card_prompt, self._effective_cfg
            )
        )
        return self._inner.create(*args, **kwargs)


class _RecordingChat:
    def __init__(
        self,
        inner: Any,
        calls: list[str],
        card_prompt: str,
        effective_cfg: Mapping[str, Any],
    ):
        self.completions = _RecordingCompletions(
            inner.completions, calls, card_prompt, effective_cfg
        )


class _RecordingClient:
    def __init__(
        self,
        inner: Any,
        card_prompt: str,
        effective_cfg: Mapping[str, Any],
    ):
        self.calls: list[str] = []
        self.chat = _RecordingChat(
            inner.chat, self.calls, card_prompt, effective_cfg
        )


def _effective_cfg(
    *,
    version: str,
    generator_cfg: Mapping[str, Any],
) -> Dict[str, Any]:
    aligned = _uses_aligned_fallback(version)
    evidence_budget = version in EVIDENCE_BUDGET_VERSIONS
    robust_evidence = version in ROBUST_EVIDENCE_VERSIONS
    selective_contract = version in SELECTIVE_CONTRACT_VERSIONS
    reliable_selective = version in RELIABLE_SELECTIVE_VERSIONS
    selective_limits = selective_contract or reliable_selective
    evidence_style = evidence_budget or robust_evidence or selective_limits
    contract_flow = version in CONTRACT_FLOW_VERSIONS
    return {
        "temperature": 0,
        "max_tokens": int(generator_cfg.get("max_tokens") or 4096),
        "input_hard_limit": production_limit.summary_limit_input_hard_limit,
        "input_safety_margin": production_limit.summary_limit_input_safety_margin,
        "headline_limit": (
            21
            if evidence_style
            else (
                16 if aligned else production_limit.summary_limit_headline_limit
            )
        ),
        "section_limits": dict(
            SELECTIVE_SECTION_LIMITS
            if selective_limits
            else (
                EVIDENCE_SECTION_LIMITS
                if evidence_style
                else (
                    ALIGNED_SECTION_LIMITS
                    if aligned
                    else production_limit.SECTION_LIMITS_DEFAULT
                )
            )
        ),
        "section_prompts": dict(
            RELIABLE_SELECTIVE_SECTION_PROMPTS
            if reliable_selective
            else (
                SELECTIVE_SECTION_PROMPTS
                if selective_contract
                else (
                    ROBUST_EVIDENCE_SECTION_PROMPTS
                    if robust_evidence
                    else (
                        EVIDENCE_SECTION_PROMPTS
                        if evidence_budget
                        else (
                            ALIGNED_SECTION_PROMPTS
                            if aligned
                            else production_limit.SECTION_PROMPTS_DEFAULT
                        )
                    )
                )
            )
        ),
        "card_prompt": _card_prompt(version),
        "card_limits": dict(CARD_FIELD_LIMITS),
        "headline_prompt": (
            EVIDENCE_HEADLINE_PROMPT
            if evidence_style
            else (
                ALIGNED_HEADLINE_PROMPT
                if aligned
                else production_limit.summary_limit_prompt_headline
            )
        ),
        "structure_check_prompt": (
            ""
            if contract_flow
            else (
                ALIGNED_STRUCTURE_CHECK_PROMPT
                if aligned
                else production_limit.summary_limit_prompt_structure_check
            )
        ),
        "structure_rewrite_prompt": (
            ALIGNED_STRUCTURE_REWRITE_PROMPT
            if aligned
            else production_limit.summary_limit_prompt_structure_rewrite
        ),
        "model": str(generator_cfg["model"]),
        "base_url": str(generator_cfg["base_url"]),
        "llm_base_url": str(generator_cfg["base_url"]),
        "enable_thinking": bool(generator_cfg.get("thinking", False)),
    }


def _output_paths(
    output_root: Path,
    *,
    split: str,
    version: str,
    paper_id: str,
) -> Tuple[Path, Path]:
    output_file = (
        output_root
        / "outputs"
        / "refinement_display"
        / split
        / version
        / f"{paper_id}.md"
    )
    return output_file, output_file.with_suffix(".meta.json")


def _stage_paths(
    output_root: Path,
    *,
    split: str,
    base_version: str,
    paper_id: str,
) -> Tuple[Path, Path]:
    stage_file = (
        output_root
        / "outputs"
        / "refinement_full_card_stage"
        / split
        / base_version
        / f"{paper_id}.md"
    )
    return stage_file, stage_file.with_suffix(".meta.json")


def _run_full_card_stage(
    *,
    client: Any,
    generator_cfg: Mapping[str, Any],
    output_root: Path,
    split: str,
    version: str,
    paper_id: str,
) -> Tuple[str, Dict[str, Any]]:
    """Generate and freeze the shared input for matched downstream A/B."""
    base_version = _stage_base_version(version)
    draft_path = (
        output_root
        / "outputs"
        / "generation"
        / split
        / DRAFT_VERSION
        / f"{paper_id}.md"
    )
    if not draft_path.is_file():
        raise FileNotFoundError(f"missing production-shaped draft: {draft_path}")
    draft = draft_path.read_text(encoding="utf-8", errors="ignore")
    stage_file, metadata_file = _stage_paths(
        output_root,
        split=split,
        base_version=base_version,
        paper_id=paper_id,
    )
    fingerprint = _full_card_stage_fingerprint(base_version)
    input_sha256 = _text_sha256(draft)
    metadata = _read_json(metadata_file, {})
    if (
        stage_file.is_file()
        and metadata.get("stage_fingerprint") == fingerprint
        and metadata.get("input_sha256") == input_sha256
    ):
        frozen_text = stage_file.read_text(encoding="utf-8", errors="ignore")
        if metadata.get("output_sha256") == _text_sha256(frozen_text):
            return frozen_text, metadata

    effective_cfg = _effective_cfg(
        version=base_version,
        generator_cfg=generator_cfg,
    )
    card_prompt = _card_prompt(base_version)
    recorder = _RecordingClient(client, card_prompt, effective_cfg)
    frozen_text, card_rewritten, refinement_error = (
        production_limit.refine_full_card_text(
            recorder,
            draft,
            effective_cfg=effective_cfg,
        )
    )
    if refinement_error is not None and not isinstance(
        refinement_error,
        (EmptyLlmResponseError, InvalidLlmResponseError),
    ):
        raise refinement_error
    call_counts = dict(Counter(recorder.calls))
    if refinement_error is not None:
        print(
            f"[full-card/{split}] fallback {base_version} {paper_id}: "
            f"{type(refinement_error).__name__}",
            flush=True,
        )
    stage_file.parent.mkdir(parents=True, exist_ok=True)
    stage_file.write_text(frozen_text, encoding="utf-8")
    metadata = {
        "pipeline_protocol_version": PIPELINE_PROTOCOL_VERSION,
        "stage_fingerprint": fingerprint,
        "base_version": base_version,
        "input_sha256": input_sha256,
        "output_sha256": _text_sha256(frozen_text),
        "card_rewritten": bool(card_rewritten),
        "full_card_attempted": bool(call_counts.get("full_card")),
        "full_card_failed": refinement_error is not None,
        "error_type": (
            type(refinement_error).__name__ if refinement_error is not None else ""
        ),
        "call_counts": call_counts,
        "model_calls_total": sum(call_counts.values()),
    }
    _write_json(metadata_file, metadata)
    return frozen_text, metadata


def _run_pipeline_output(
    *,
    client: Any,
    generator_cfg: Mapping[str, Any],
    output_root: Path,
    split: str,
    version: str,
    paper_id: str,
) -> Tuple[str, Dict[str, Any]]:
    draft_path = (
        output_root
        / "outputs"
        / "generation"
        / split
        / DRAFT_VERSION
        / f"{paper_id}.md"
    )
    if not draft_path.is_file():
        raise FileNotFoundError(f"missing production-shaped draft: {draft_path}")
    draft = draft_path.read_text(encoding="utf-8", errors="ignore")
    output_file, metadata_file = _output_paths(
        output_root, split=split, version=version, paper_id=paper_id
    )
    fingerprint = _pipeline_fingerprint(version)
    input_sha256 = _text_sha256(draft)
    metadata = _read_json(metadata_file, {})
    if (
        output_file.is_file()
        and metadata.get("pipeline_fingerprint") == fingerprint
        and metadata.get("input_sha256") == input_sha256
    ):
        candidate = output_file.read_text(encoding="utf-8", errors="ignore")
        if metadata.get("output_sha256") == _text_sha256(candidate):
            return candidate, metadata

    output_file.parent.mkdir(parents=True, exist_ok=True)
    if version == RAW_VERSION:
        candidate = draft
        output_file.write_text(candidate, encoding="utf-8")
        call_counts: Dict[str, int] = {}
        downstream_call_counts: Dict[str, int] = {}
        stage_metadata: Dict[str, Any] = {}
        status = "raw"
    else:
        frozen_text, stage_metadata = _run_full_card_stage(
            client=client,
            generator_cfg=generator_cfg,
            output_root=output_root,
            split=split,
            version=version,
            paper_id=paper_id,
        )
        card_prompt = _card_prompt(version)
        effective_cfg = _effective_cfg(
            version=version, generator_cfg=generator_cfg
        )
        recorder = _RecordingClient(client, card_prompt, effective_cfg)
        try:
            candidate, status = production_limit.finalize_card_text(
                recorder,
                frozen_text,
                draft_path,
                {},
                card_rewritten=bool(stage_metadata.get("card_rewritten")),
                effective_cfg=effective_cfg,
            )
        except (EmptyLlmResponseError, InvalidLlmResponseError) as exc:
            candidate = production_limit.local_normalize_summary(draft_path, {})
            status = "fallback"
            print(
                f"[downstream/{split}] local fallback {version} {paper_id}: "
                f"{type(exc).__name__}",
                flush=True,
            )
        output_file.write_text(candidate, encoding="utf-8")
        downstream_call_counts = dict(Counter(recorder.calls))
        call_counts = dict(Counter(stage_metadata.get("call_counts", {})))
        call_counts.update(
            {
                key: call_counts.get(key, 0) + count
                for key, count in downstream_call_counts.items()
            }
        )

    metadata = {
        "pipeline_protocol_version": PIPELINE_PROTOCOL_VERSION,
        "pipeline_fingerprint": fingerprint,
        "input_sha256": input_sha256,
        "output_sha256": _text_sha256(candidate),
        "status": status,
        "call_counts": call_counts,
        "downstream_call_counts": downstream_call_counts,
        "model_calls_total": sum(call_counts.values()),
        "stage_base_version": stage_metadata.get("base_version", ""),
        "stage_output_sha256": stage_metadata.get("output_sha256", ""),
        "stage_card_rewritten": bool(stage_metadata.get("card_rewritten")),
        "full_card_fallback": bool(stage_metadata.get("full_card_failed")),
        "downstream_fallback": status == "fallback",
    }
    _write_json(metadata_file, metadata)
    return candidate, metadata


def _cached_judge(
    scores: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    paper_id: str,
    candidate_sha256: str,
) -> Optional[Mapping[str, Any]]:
    for version_items in scores.values():
        item = version_items.get(paper_id, {})
        if (
            item.get("judge_version") == DISPLAY_JUDGE_VERSION
            and item.get("candidate_sha256") == candidate_sha256
            and item.get("judge")
        ):
            return item["judge"]
    return None


def _score_split(
    *,
    client: Any,
    generator_cfg: Mapping[str, Any],
    judge_cfg: Mapping[str, Any],
    sample_root: Path,
    output_root: Path,
    split: str,
    versions: Sequence[str],
    workers: int,
) -> Dict[str, Dict[str, Any]]:
    samples = sorted((sample_root / split).glob("*.md"))
    outputs: Dict[Tuple[str, str], Tuple[str, Dict[str, Any]]] = {}
    stage_tasks = sorted(
        {
            (_stage_base_version(version), path.stem)
            for version in versions
            if version != RAW_VERSION
            for path in samples
        }
    )

    def prepare_stage(task: Tuple[str, str]) -> Tuple[str, str, Dict[str, Any]]:
        base_version, paper_id = task
        _, metadata = _run_full_card_stage(
            client=client,
            generator_cfg=generator_cfg,
            output_root=output_root,
            split=split,
            version=base_version,
            paper_id=paper_id,
        )
        return base_version, paper_id, metadata

    # Complete every unique full-card stage before downstream variants start.
    # This prevents paired variants from racing and independently sampling the
    # same nominal prompt.
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        futures = {
            executor.submit(prepare_stage, task): task for task in stage_tasks
        }
        for future in as_completed(futures):
            base_version, paper_id, metadata = future.result()
            print(
                f"[full-card/{split}] frozen {base_version} {paper_id}: "
                f"calls={metadata.get('model_calls_total', 0)}",
                flush=True,
            )

    output_tasks = [
        (version, path.stem)
        for version in versions
        for path in samples
    ]

    def produce(task: Tuple[str, str]) -> Tuple[str, str, str, Dict[str, Any]]:
        version, paper_id = task
        candidate, metadata = _run_pipeline_output(
            client=client,
            generator_cfg=generator_cfg,
            output_root=output_root,
            split=split,
            version=version,
            paper_id=paper_id,
        )
        return version, paper_id, candidate, metadata

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        futures = {executor.submit(produce, task): task for task in output_tasks}
        for future in as_completed(futures):
            version, paper_id, candidate, metadata = future.result()
            outputs[(version, paper_id)] = (candidate, metadata)
            print(
                f"[display/{split}] output {version} {paper_id}: "
                f"calls={metadata.get('model_calls_total', 0)}",
                flush=True,
            )

    score_path = output_root / "scores" / f"refinement_display_{split}.json"
    scores: Dict[str, Dict[str, Any]] = _read_json(score_path, {})
    judge_tasks = []
    for version, paper_id in output_tasks:
        candidate, metadata = outputs[(version, paper_id)]
        candidate_sha256 = _text_sha256(candidate)
        existing = scores.get(version, {}).get(paper_id, {})
        if (
            existing.get("evaluator_version") == DISPLAY_EVALUATOR_VERSION
            and existing.get("candidate_sha256") == candidate_sha256
        ):
            continue
        judge_tasks.append((version, paper_id, candidate, metadata, candidate_sha256))

    def evaluate(task: Tuple[str, str, str, Dict[str, Any], str]):
        version, paper_id, candidate, metadata, candidate_sha256 = task
        source_text = (sample_root / split / f"{paper_id}.md").read_text(
            encoding="utf-8", errors="ignore"
        )
        draft = (
            output_root
            / "outputs"
            / "generation"
            / split
            / DRAFT_VERSION
            / f"{paper_id}.md"
        ).read_text(encoding="utf-8", errors="ignore")
        deterministic = deterministic_report(
            candidate,
            source_text=source_text,
            refinement_input=draft,
        )
        judge = _cached_judge(
            scores,
            paper_id=paper_id,
            candidate_sha256=candidate_sha256,
        ) or _judge(
            client,
            judge_cfg,
            paper_id=paper_id,
            source_text=source_text,
            candidate_text=candidate,
            stage="用户可见精简终稿（完整生产链路）",
            refinement_input=draft,
        )
        combined = combine_scores(
            judge_result=judge,
            deterministic=deterministic,
        )
        combined.update(
            {
                "evaluator_version": DISPLAY_EVALUATOR_VERSION,
                "judge_version": DISPLAY_JUDGE_VERSION,
                "candidate_sha256": candidate_sha256,
                "draft_version": DRAFT_VERSION,
                "refinement_attempts": metadata.get("model_calls_total", 0),
                "pipeline_status": metadata.get("status"),
                "pipeline_call_counts": metadata.get("call_counts", {}),
                "downstream_call_counts": metadata.get(
                    "downstream_call_counts", {}
                ),
                "full_card_fallback": bool(metadata.get("full_card_fallback")),
                "downstream_fallback": bool(metadata.get("downstream_fallback")),
                "stage_base_version": metadata.get("stage_base_version", ""),
                "stage_output_sha256": metadata.get(
                    "stage_output_sha256", ""
                ),
            }
        )
        return version, paper_id, combined

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        futures = {executor.submit(evaluate, task): task for task in judge_tasks}
        for future in as_completed(futures):
            version, paper_id, combined = future.result()
            scores.setdefault(version, {})[paper_id] = combined
            _write_json(score_path, scores)
            print(
                f"[display/{split}] score {version} {paper_id}: "
                f"{combined['score']}",
                flush=True,
            )
    return scores


def _blind_labels(seed: int, *parts: str) -> Tuple[str, str]:
    digest = hashlib.sha256(
        f"{seed}|{'|'.join(parts)}".encode("utf-8")
    ).hexdigest()
    challenger = "X" if int(digest[:2], 16) % 2 == 0 else "Y"
    return challenger, "Y" if challenger == "X" else "X"


def _pairwise_cache_key(
    *,
    split: str,
    paper_id: str,
    baseline_version: str,
    challenger_version: str,
    baseline_sha256: str,
    challenger_sha256: str,
) -> str:
    return ":".join(
        (
            PAIRWISE_JUDGE_VERSION,
            split,
            paper_id,
            baseline_version,
            challenger_version,
            baseline_sha256[:20],
            challenger_sha256[:20],
        )
    )


def _pairwise_verdicts(
    *,
    client: Any,
    judge_cfg: Mapping[str, Any],
    sample_root: Path,
    output_root: Path,
    split: str,
    baseline_version: str,
    challenger_version: str,
    scores: Mapping[str, Mapping[str, Mapping[str, Any]]],
    seed: int,
    workers: int,
) -> list[Dict[str, Any]]:
    cache_path = output_root / "scores" / "refinement_display_pairwise.json"
    cache: Dict[str, Any] = _read_json(cache_path, {})
    paper_ids = sorted(
        set(scores.get(baseline_version, {}))
        & set(scores.get(challenger_version, {}))
    )

    def evaluate(paper_id: str) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        baseline_path, _ = _output_paths(
            output_root,
            split=split,
            version=baseline_version,
            paper_id=paper_id,
        )
        challenger_path, _ = _output_paths(
            output_root,
            split=split,
            version=challenger_version,
            paper_id=paper_id,
        )
        baseline_text = baseline_path.read_text(encoding="utf-8", errors="ignore")
        challenger_text = challenger_path.read_text(
            encoding="utf-8", errors="ignore"
        )
        baseline_sha256 = _text_sha256(baseline_text)
        challenger_sha256 = _text_sha256(challenger_text)
        cache_key = _pairwise_cache_key(
            split=split,
            paper_id=paper_id,
            baseline_version=baseline_version,
            challenger_version=challenger_version,
            baseline_sha256=baseline_sha256,
            challenger_sha256=challenger_sha256,
        )
        cached = cache.get(cache_key, {})
        challenger_label, baseline_label = _blind_labels(
            seed,
            split,
            paper_id,
            baseline_version,
            challenger_version,
        )
        raw = cached.get("raw") if cached.get("judge_version") == PAIRWISE_JUDGE_VERSION else None
        if not raw:
            source_text = (sample_root / split / f"{paper_id}.md").read_text(
                encoding="utf-8", errors="ignore"
            )
            draft = (
                output_root
                / "outputs"
                / "generation"
                / split
                / DRAFT_VERSION
                / f"{paper_id}.md"
            ).read_text(encoding="utf-8", errors="ignore")
            candidates = {
                baseline_label: baseline_text,
                challenger_label: challenger_text,
            }
            last_error: Optional[BaseException] = None
            for attempt in range(3):
                retry_note = ""
                if attempt:
                    retry_note = "\n上一次JSON缺字段或值非法；请按固定结构完整重答。"
                reply = _complete(
                    client,
                    judge_cfg,
                    system_prompt=PAIRWISE_JUDGE_SYSTEM_PROMPT,
                    user_prompt=(
                        f"论文ID：{paper_id}\n<论文原文>\n{source_text}\n</论文原文>\n"
                        f"<精简前卡片>\n{draft}\n</精简前卡片>\n"
                        f"<候选X>\n{candidates['X']}\n</候选X>\n"
                        f"<候选Y>\n{candidates['Y']}\n</候选Y>{retry_note}"
                    ),
                    json_mode=True,
                )
                try:
                    raw = extract_json_object(reply)
                    normalize_pairwise_result(
                        raw, challenger_label=challenger_label
                    )
                    break
                except (ValueError, json.JSONDecodeError) as exc:
                    last_error = exc
                    raw = None
            if raw is None:
                raise RuntimeError(
                    f"invalid pairwise result after 3 attempts: {last_error!r}"
                )
        normalized = normalize_pairwise_result(
            raw, challenger_label=challenger_label
        )
        normalized["paper_id"] = paper_id
        cache_entry = {
            "judge_version": PAIRWISE_JUDGE_VERSION,
            "challenger_label": challenger_label,
            "raw": raw,
        }
        return cache_key, cache_entry, normalized

    verdicts: list[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        futures = {executor.submit(evaluate, paper_id): paper_id for paper_id in paper_ids}
        for future in as_completed(futures):
            cache_key, cache_entry, normalized = future.result()
            cache[cache_key] = cache_entry
            verdicts.append(normalized)
            _write_json(cache_path, cache)
            print(
                f"[pairwise/{split}] {baseline_version} vs {challenger_version} "
                f"{normalized['paper_id']}: {normalized['overall_preference']}",
                flush=True,
            )
    return sorted(verdicts, key=lambda item: item["paper_id"])


def _version_summary(
    scores: Mapping[str, Mapping[str, Mapping[str, Any]]],
    versions: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for version in versions:
        items = scores.get(version, {})
        aggregate = aggregate_version_scores(items)
        count = len(items)
        aggregate["fallback_rate"] = round(
            100.0
            * sum(bool(item.get("full_card_fallback")) for item in items.values())
            / count,
            2,
        ) if count else 0.0
        result[version] = aggregate
    return result


def _matched_stage_checks(
    scores: Mapping[str, Mapping[str, Mapping[str, Any]]],
    comparisons: Sequence[Tuple[str, str]],
) -> list[Dict[str, Any]]:
    checks: list[Dict[str, Any]] = []
    for baseline, challenger in comparisons:
        paper_ids = sorted(
            set(scores.get(baseline, {})) & set(scores.get(challenger, {}))
        )
        mismatches = [
            paper_id
            for paper_id in paper_ids
            if not scores[baseline][paper_id].get("stage_output_sha256")
            or scores[baseline][paper_id].get("stage_output_sha256")
            != scores[challenger][paper_id].get("stage_output_sha256")
        ]
        checks.append(
            {
                "baseline_version": baseline,
                "challenger_version": challenger,
                "paper_count": len(paper_ids),
                "matched_count": len(paper_ids) - len(mismatches),
                "all_matched": bool(paper_ids) and not mismatches,
                "mismatch_paper_ids": mismatches,
            }
        )
    return checks


def _rounds(
    *,
    client: Any,
    judge_cfg: Mapping[str, Any],
    sample_root: Path,
    output_root: Path,
    split: str,
    scores: Mapping[str, Mapping[str, Mapping[str, Any]]],
    comparisons: Sequence[Tuple[str, str]],
    seed: int,
    workers: int,
) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for round_index, (baseline, challenger) in enumerate(comparisons, start=1):
        verdicts = _pairwise_verdicts(
            client=client,
            judge_cfg=judge_cfg,
            sample_root=sample_root,
            output_root=output_root,
            split=split,
            baseline_version=baseline,
            challenger_version=challenger,
            scores=scores,
            seed=seed,
            workers=workers,
        )
        decision = detailed_promotion_decision(
            baseline_items=scores.get(baseline, {}),
            challenger_items=scores.get(challenger, {}),
            verdicts=verdicts,
        )
        decision.update(
            {
                "round": round_index,
                "baseline_version": baseline,
                "challenger_version": challenger,
                "verdicts": verdicts,
            }
        )
        rows.append(decision)
    return rows


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    output.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(output)


def _round_table(rows: Sequence[Mapping[str, Any]]) -> str:
    return _table(
        (
            "轮",
            "A基线",
            "B挑战",
            "A分",
            "B分",
            "差值",
            "硬校验",
            "盲评B胜/平/负",
            "事实差",
            "最差字段",
            "结论",
        ),
        [
            (
                row["round"],
                row["baseline_version"],
                row["challenger_version"],
                row["baseline"]["score"],
                row["challenger"]["score"],
                f"{row['score_delta']:+.2f}",
                f"{row['baseline']['contract_pass_rate']:.0f}%→"
                f"{row['challenger']['contract_pass_rate']:.0f}%",
                f"{row['pairwise']['overall']['win']}/"
                f"{row['pairwise']['overall']['tie']}/"
                f"{row['pairwise']['overall']['loss']}",
                f"{row['factuality_delta']:+.2f}",
                f"{FIELD_LABELS.get(row['worst_field'], row['worst_field'])} "
                f"{row['worst_field_delta']:+.2f}",
                "晋级" if row["promoted"] else "保留基线",
            )
            for row in rows
        ],
    )


def _build_report(ledger: Mapping[str, Any]) -> str:
    dev_scores = ledger["dev"]["version_scores"]
    posthoc_scores = ledger["posthoc"]["version_scores"]
    version_rows = [
        (
            version,
            dev_scores[version]["score"],
            f"{dev_scores[version]['contract_pass_rate']:.0f}%",
            dev_scores[version]["factuality_score"],
            dev_scores[version]["mean_refinement_attempts"],
            f"{dev_scores[version]['fallback_rate']:.0f}%",
            posthoc_scores[version]["score"],
            f"{posthoc_scores[version]['contract_pass_rate']:.0f}%",
        )
        for version in VERSIONS
    ]
    per_paper_rows = []
    for split_name in ("dev", "posthoc"):
        for version in VERSIONS:
            for paper_id, item in sorted(
                ledger[split_name]["per_paper"][version].items()
            ):
                per_paper_rows.append(
                    (
                        split_name,
                        paper_id,
                        version,
                        item["score"],
                        "通过" if item["contract_pass"] else "未通过",
                        item["model_calls"],
                        "是" if item["full_card_fallback"] else "否",
                        "是" if item["downstream_fallback"] else "否",
                    )
                )
    type1_dev = ledger["dev"]["type1"]
    type1_posthoc = ledger["posthoc"]["type1"]
    type1_rows = [
        (
            "dev",
            type1_dev["baseline"]["score"],
            type1_dev["challenger"]["score"],
            f"{type1_dev['score_delta']:+.2f}",
            f"{type1_dev['baseline']['contract_pass_rate']:.0f}%→"
            f"{type1_dev['challenger']['contract_pass_rate']:.0f}%",
            f"{type1_dev['pairwise']['overall']['win']}/"
            f"{type1_dev['pairwise']['overall']['tie']}/"
            f"{type1_dev['pairwise']['overall']['loss']}",
        ),
        (
            "post-hoc",
            type1_posthoc["baseline"]["score"],
            type1_posthoc["challenger"]["score"],
            f"{type1_posthoc['score_delta']:+.2f}",
            f"{type1_posthoc['baseline']['contract_pass_rate']:.0f}%→"
            f"{type1_posthoc['challenger']['contract_pass_rate']:.0f}%",
            f"{type1_posthoc['pairwise']['overall']['win']}/"
            f"{type1_posthoc['pairwise']['overall']['tie']}/"
            f"{type1_posthoc['pairwise']['overall']['loss']}",
        ),
    ]
    stage_check_rows = [
        (
            split_name,
            check["baseline_version"],
            check["challenger_version"],
            f"{check['matched_count']}/{check['paper_count']}",
            "通过" if check["all_matched"] else "失败",
        )
        for split_name, checks in (
            ("dev", ledger["dev"]["matched_stage_checks"]),
            ("post-hoc", ledger["posthoc"]["matched_stage_checks"]),
        )
        for check in checks
    ]
    return "\n".join(
        [
            "# 推荐卡片用户可见精简终稿：详细 A/B 实验",
            "",
            f"- 运行时间（UTC）：{ledger['run']['finished_at']}",
            f"- 生成模型：`{ledger['run']['generation_model']}`；盲评模型：`{ledger['run']['judge_model']}`。",
            "- 评分对象是完整生产链路最终落盘、用户实际会看到的文本；包含整卡重试、首行处理、结构检查及分段兜底。",
            "- 原始 MinerU 全文和完整候选输出只保存在仓库外；本报告仅包含哈希、分数和盲评结论。",
            "- 原2篇隐藏集已经在前一实验打开，本轮降级为 post-hoc；本轮结果不能直接替换线上默认。",
            "",
            "## 冻结规则",
            "",
            "单候选仍按八字段0–100分评审，并叠加程序硬校验。类型2挑战者必须同时满足：均分至少提高2分、最终硬校验100%、事实性下降不超过1分、客观事实护栏全净、成对盲评至少半数论文判B胜、成对事实性不劣、零新增不支持内容、零实质信息损失、任一字段均分下降不超过3分。规则在本轮新候选输出生成前冻结。",
            "",
            "## 类型1：不做精简 vs 当前线上精简",
            "",
            _table(
                ("数据", "原稿分", "当前精简分", "变化", "硬校验", "B胜/平/负"),
                type1_rows,
            ),
            "",
            "## 类型2：当前基线 vs 多轮提示词",
            "",
            _table(
                ("版本", "开发分", "开发硬校验", "开发事实性", "平均模型调用", "整卡兜底率", "post-hoc分", "post-hoc硬校验"),
                version_rows,
            ),
            "",
            "### 开发集逐轮结果",
            "",
            _round_table(ledger["dev"]["rounds"]),
            "",
            "### 已打开样本的 post-hoc 复核",
            "",
            _round_table(ledger["posthoc"]["rounds"]),
            "",
            "## 第二阶段：相同整卡结果下的精简后处理 A/B",
            "",
            "为排除模型重复生成造成的随机波动，每篇论文、每个整卡提示词只生成一次中间卡片；旧后处理与新后处理逐字共享该冻结输入。以下输入同一性检查是实验有效性的前置条件。",
            "",
            _table(
                ("数据", "A旧后处理", "B新后处理", "相同输入", "检查"),
                stage_check_rows,
            ),
            "",
            "### 开发集配对结果",
            "",
            _round_table(ledger["dev"]["matched_downstream_rounds"]),
            "",
            "### 已打开样本的 post-hoc 配对复核",
            "",
            _round_table(ledger["posthoc"]["matched_downstream_rounds"]),
            "",
            "## 链路审计发现",
            "",
            "当前整卡合同要求“笔记标题”和八个用户字段，但旧后处理仍按“机构：摘要首行”的历史结构判断与压缩；其分段预算也宽于整卡字段预算，一句话记忆原先还不会进入分段压缩。因此，单独优化整卡提示词不能保证最终展示合格，首行、结构、各字段和记忆句必须作为同一个展示合同共同评测。",
            "",
            "## 逐论文最终输出得分",
            "",
            _table(
                (
                    "数据",
                    "论文",
                    "版本",
                    "0–100分",
                    "硬校验",
                    "模型调用",
                    "整卡失败兜底",
                    "终段本地兜底",
                ),
                per_paper_rows,
            ),
            "",
            "## 结论",
            "",
            f"严格晋级冠军（未过门槛即保留基线）：`{ledger['decision']['dev_champion']}`；最佳合同合规候选：`{ledger['decision']['best_contract_candidate']}`；线上默认仍为 `{ledger['decision']['production_baseline']}`。",
            "",
            ledger["decision"]["reason"],
            "",
            "## 下一步",
            "",
            "1. 把分段模型失败从“整卡回退”改为“仅该字段回退”，保留其他已经成功且通过校验的字段；对每个字段输出分别做结构、长度和数字追溯校验。",
            "2. 以 `r13_r4_contract_flow` 为开发基线，验证单字段失败隔离是否能在不增加信息损失的前提下维持100%最终硬校验。",
            "3. 冻结新的未见论文集后再做盲评；在新隐藏集通过全部门槛前，不改服务器管理员默认提示词。",
            "",
            "## 解释限制",
            "",
            "只有5篇已授权公开论文，且其中2篇已被查看，样本量不足以估计跨学科稳定性。自动生成与盲评来自同一模型家族，可能存在共同风格偏好；成对盲评、硬校验和事实护栏只能降低、不能消除该风险。",
            "",
        ]
    )


def _per_paper_summary(
    scores: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> Dict[str, Dict[str, Any]]:
    return {
        version: {
            paper_id: {
                "score": item["score"],
                "factuality_score": item["factuality_score"],
                "contract_pass": bool(
                    item.get("deterministic", {}).get("contract_pass")
                ),
                "contract_errors": item.get("deterministic", {}).get(
                    "contract_errors", []
                ),
                "model_calls": item.get("refinement_attempts", 0),
                "full_card_fallback": bool(item.get("full_card_fallback")),
                "downstream_fallback": bool(item.get("downstream_fallback")),
                "stage_base_version": item.get("stage_base_version", ""),
                "stage_output_sha256": item.get("stage_output_sha256", ""),
                "candidate_sha256": item.get("candidate_sha256", ""),
            }
            for paper_id, item in sorted(scores.get(version, {}).items())
        }
        for version in VERSIONS
    }


def run(args: argparse.Namespace) -> Dict[str, Any]:
    sample_root = args.sample_root.resolve()
    output_root = args.private_output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    samples = _sample_manifest(sample_root)
    if len(samples["dev"]) < 3 or len(samples["holdout"]) < 2:
        raise SystemExit("the authorized 3 dev + 2 post-hoc MinerU files are required")
    if ACTIVE_REFINEMENT_VERSION != BASELINE_VERSION:
        raise SystemExit(
            "detailed A/B baseline must match the active production refinement"
        )

    client, generator_cfg, judge_cfg = _make_deepseek_client()
    dev_scores = _score_split(
        client=client,
        generator_cfg=generator_cfg,
        judge_cfg=judge_cfg,
        sample_root=sample_root,
        output_root=output_root,
        split="dev",
        versions=VERSIONS,
        workers=args.workers,
    )
    posthoc_scores = _score_split(
        client=client,
        generator_cfg=generator_cfg,
        judge_cfg=judge_cfg,
        sample_root=sample_root,
        output_root=output_root,
        split="holdout",
        versions=VERSIONS,
        workers=args.workers,
    )
    dev_stage_checks = _matched_stage_checks(
        dev_scores, MATCHED_DOWNSTREAM_COMPARISONS
    )
    posthoc_stage_checks = _matched_stage_checks(
        posthoc_scores, MATCHED_DOWNSTREAM_COMPARISONS
    )
    failed_stage_checks = [
        check
        for check in (*dev_stage_checks, *posthoc_stage_checks)
        if not check["all_matched"]
    ]
    if failed_stage_checks:
        raise RuntimeError(
            "matched downstream A/B did not share frozen full-card inputs: "
            + json.dumps(failed_stage_checks, ensure_ascii=False)
        )

    type1_dev_verdicts = _pairwise_verdicts(
        client=client,
        judge_cfg=judge_cfg,
        sample_root=sample_root,
        output_root=output_root,
        split="dev",
        baseline_version=RAW_VERSION,
        challenger_version=BASELINE_VERSION,
        scores=dev_scores,
        seed=args.seed,
        workers=args.workers,
    )
    type1_posthoc_verdicts = _pairwise_verdicts(
        client=client,
        judge_cfg=judge_cfg,
        sample_root=sample_root,
        output_root=output_root,
        split="holdout",
        baseline_version=RAW_VERSION,
        challenger_version=BASELINE_VERSION,
        scores=posthoc_scores,
        seed=args.seed,
        workers=args.workers,
    )
    type1_dev = detailed_promotion_decision(
        baseline_items=dev_scores[RAW_VERSION],
        challenger_items=dev_scores[BASELINE_VERSION],
        verdicts=type1_dev_verdicts,
        minimum_score_delta=0.0,
        maximum_field_regression=5.0,
    )
    type1_posthoc = detailed_promotion_decision(
        baseline_items=posthoc_scores[RAW_VERSION],
        challenger_items=posthoc_scores[BASELINE_VERSION],
        verdicts=type1_posthoc_verdicts,
        minimum_score_delta=0.0,
        maximum_field_regression=5.0,
    )

    comparisons: list[Tuple[str, str]] = []
    champion = BASELINE_VERSION
    dev_rounds: list[Dict[str, Any]] = []
    for challenger in CHALLENGERS:
        comparison = (champion, challenger)
        rows = _rounds(
            client=client,
            judge_cfg=judge_cfg,
            sample_root=sample_root,
            output_root=output_root,
            split="dev",
            scores=dev_scores,
            comparisons=(comparison,),
            seed=args.seed,
            workers=args.workers,
        )
        row = rows[0]
        row["round"] = len(dev_rounds) + 1
        dev_rounds.append(row)
        comparisons.append(comparison)
        if row["promoted"]:
            champion = challenger

    posthoc_rounds = _rounds(
        client=client,
        judge_cfg=judge_cfg,
        sample_root=sample_root,
        output_root=output_root,
        split="holdout",
        scores=posthoc_scores,
        comparisons=comparisons,
        seed=args.seed,
        workers=args.workers,
    )
    matched_dev_rounds = _rounds(
        client=client,
        judge_cfg=judge_cfg,
        sample_root=sample_root,
        output_root=output_root,
        split="dev",
        scores=dev_scores,
        comparisons=MATCHED_DOWNSTREAM_COMPARISONS,
        seed=args.seed,
        workers=args.workers,
    )
    matched_posthoc_rounds = _rounds(
        client=client,
        judge_cfg=judge_cfg,
        sample_root=sample_root,
        output_root=output_root,
        split="holdout",
        scores=posthoc_scores,
        comparisons=MATCHED_DOWNSTREAM_COMPARISONS,
        seed=args.seed,
        workers=args.workers,
    )

    finished_at = datetime.now(timezone.utc).isoformat()
    dev_version_scores = _version_summary(dev_scores, VERSIONS)
    posthoc_version_scores = _version_summary(posthoc_scores, VERSIONS)
    contract_candidates = [
        version
        for version in VERSIONS
        if dev_version_scores[version]["contract_pass_rate"] == 100.0
    ]
    best_contract_candidate = max(
        contract_candidates,
        key=lambda version: dev_version_scores[version]["score"],
        default=BASELINE_VERSION,
    )
    r13_comparison = next(
        (
            row
            for row in matched_dev_rounds
            if row["baseline_version"] == "r11_r4_aligned_fallback"
            and row["challenger_version"] == "r13_r4_contract_flow"
        ),
        None,
    )
    if r13_comparison:
        pairwise = r13_comparison["pairwise"]["overall"]
        material_loss = r13_comparison["pairwise"][
            "challenger_material_loss_count"
        ]
        comparison_note = (
            f"相对r11的盲评为{pairwise['win']}胜/{pairwise['tie']}平/"
            f"{pairwise['loss']}负，并有{material_loss}篇被判实质信息损失"
        )
    else:
        comparison_note = "尚无完整配对结果"
    candidate_dev = dev_version_scores[best_contract_candidate]
    candidate_posthoc = posthoc_version_scores[best_contract_candidate]
    reason = (
        f"最佳合同合规候选为{best_contract_candidate}：开发集"
        f"{candidate_dev['score']:.2f}分、硬校验"
        f"{candidate_dev['contract_pass_rate']:.0f}%，post-hoc为"
        f"{candidate_posthoc['score']:.2f}分、硬校验"
        f"{candidate_posthoc['contract_pass_rate']:.0f}%；但{comparison_note}。"
        "它未通过冻结的成对质量门槛，且旧留出集已经打开，不能提供新的泛化证据。"
        "因此不得替换管理员后台或服务器默认；下一步应先实现单字段失败隔离，再用新增且冻结的隐藏集复核。"
    )
    ledger: Dict[str, Any] = {
        "schema_version": 1,
        "run": {
            "finished_at": finished_at,
            "seed": args.seed,
            "generation_model": generator_cfg["model"],
            "judge_model": judge_cfg["model"],
            "display_evaluator_version": DISPLAY_EVALUATOR_VERSION,
            "pairwise_judge_version": PAIRWISE_JUDGE_VERSION,
            "production_pipeline_sha256": _file_sha256(
                Path(production_limit.__file__)
            ),
        },
        "samples": samples,
        "protocol": {
            "raw_version": RAW_VERSION,
            "baseline_version": BASELINE_VERSION,
            "challengers": list(CHALLENGERS),
            "draft_version": DRAFT_VERSION,
            "posthoc_split_source_name": "holdout",
            "minimum_score_delta": 2.0,
            "factuality_tolerance": 1.0,
            "maximum_field_regression": 3.0,
            "requires_contract_pass_rate": 100.0,
            "requires_zero_pairwise_unsupported": True,
            "requires_zero_pairwise_material_loss": True,
            "matched_downstream_comparisons": [
                list(item) for item in MATCHED_DOWNSTREAM_COMPARISONS
            ],
        },
        "dev": {
            "version_scores": dev_version_scores,
            "per_paper": _per_paper_summary(dev_scores),
            "type1": type1_dev,
            "rounds": dev_rounds,
            "matched_stage_checks": dev_stage_checks,
            "matched_downstream_rounds": matched_dev_rounds,
        },
        "posthoc": {
            "version_scores": posthoc_version_scores,
            "per_paper": _per_paper_summary(posthoc_scores),
            "type1": type1_posthoc,
            "rounds": posthoc_rounds,
            "matched_stage_checks": posthoc_stage_checks,
            "matched_downstream_rounds": matched_posthoc_rounds,
        },
        "decision": {
            "dev_champion": champion,
            "best_contract_candidate": best_contract_candidate,
            "production_baseline": BASELINE_VERSION,
            "production_change_allowed": False,
            "reason": reason,
        },
    }
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    _write_json(args.ledger, ledger)
    args.report.write_text(_build_report(ledger), encoding="utf-8")
    return ledger


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser("recommend_card_refinement_detailed_ab")
    parser.add_argument("--sample-root", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, default=DEFAULT_PRIVATE_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--seed", type=int, default=20260818)
    parser.add_argument("--workers", type=int, default=2)
    return parser.parse_args(argv)


if __name__ == "__main__":
    result = run(parse_args())
    print(
        json.dumps(
            {
                "dev_champion": result["decision"]["dev_champion"],
                "production_change_allowed": result["decision"][
                    "production_change_allowed"
                ],
            },
            ensure_ascii=False,
        )
    )
