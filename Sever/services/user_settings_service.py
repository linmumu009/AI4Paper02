"""
User settings service layer.

Stores per-user, per-feature configuration in the ``user_settings`` table
(same SQLite database as auth / KB).

Table schema
------------
    user_settings (
        user_id   INTEGER NOT NULL,
        feature   TEXT    NOT NULL,          -- e.g. 'compare', 'paper_summary'
        settings_json TEXT NOT NULL DEFAULT '{}',
        updated_at    TEXT NOT NULL,
        PRIMARY KEY (user_id, feature)
    )

Each *feature* has its own set of default values defined in ``_FEATURE_DEFAULTS``.
``get_settings`` merges stored values on top of those defaults so that the
caller always receives a complete dict.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from services.secret_storage_service import (
    protect_secret_mapping,
    unprotect_secret_mapping,
)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create the user_settings table if it does not exist."""
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id       INTEGER NOT NULL,
                feature       TEXT    NOT NULL,
                settings_json TEXT    NOT NULL DEFAULT '{}',
                updated_at    TEXT    NOT NULL,
                PRIMARY KEY (user_id, feature)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Default values per feature
# ---------------------------------------------------------------------------

# Keys that should NEVER be filled with defaults (user must provide them).
_NO_DEFAULT_KEYS: dict[str, set[str]] = {
    "compare": {"llm_base_url", "llm_api_key", "llm_model", "llm_preset_id", "prompt_preset_id"},
    "inspiration": {"llm_base_url", "llm_api_key", "llm_model", "llm_preset_id", "prompt_preset_id"},
    "paper_chat": {"llm_base_url", "llm_api_key", "llm_model", "llm_preset_id", "prompt_preset_id"},
    "deep_research": {"llm_base_url", "llm_api_key", "llm_model", "llm_preset_id", "prompt_preset_id"},
    "translate": {"llm_base_url", "llm_api_key", "llm_model", "llm_preset_id"},
    "idea_generate": {
        "llm_base_url", "llm_api_key", "llm_model", "llm_preset_id", "prompt_preset_id",
        # Per-phase LLM preset IDs (每阶段独立 1:1)
        "ingest_llm_preset_id",    "ingest_prompt_preset_id",
        "question_llm_preset_id",  "question_prompt_preset_id",
        "candidate_llm_preset_id", "candidate_prompt_preset_id",
        "review_llm_preset_id",    "review_prompt_preset_id",
        "revise_llm_preset_id",    "revise_prompt_preset_id",
        "plan_llm_preset_id",      "plan_prompt_preset_id",
        "eval_llm_preset_id",      "eval_prompt_preset_id",
    },
    "paper_recommend": {
        "llm_base_url", "llm_api_key", "llm_model", "llm_preset_id", "prompt_preset_id",
        # Per-module LLM preset IDs
        "theme_select_llm_preset_id", "org_llm_preset_id",
        "summary_llm_preset_id", "summary_limit_llm_preset_id",
        # Per-module prompt preset IDs
        "theme_select_prompt_preset_id", "org_prompt_preset_id",
        "summary_prompt_preset_id",
        "summary_limit_prompt_intro_preset_id", "summary_limit_prompt_method_preset_id",
        "summary_limit_prompt_findings_preset_id", "summary_limit_prompt_opinion_preset_id",
        # MinerU 服务密钥
        "mineru_token",
    },
    "my_papers": {
        "llm_base_url", "llm_api_key", "llm_model", "llm_preset_id", "prompt_preset_id",
        # Per-module LLM preset IDs
        "org_llm_preset_id", "summary_llm_preset_id", "summary_limit_llm_preset_id",
        # Per-module prompt preset IDs
        "org_prompt_preset_id", "summary_prompt_preset_id",
        "summary_limit_prompt_intro_preset_id", "summary_limit_prompt_method_preset_id",
        "summary_limit_prompt_findings_preset_id", "summary_limit_prompt_opinion_preset_id",
        # MinerU 服务密钥
        "mineru_token",
    },
    "auto_classify": {
        # llm_preset_id must come from user; empty string means not configured
        "llm_preset_id",
        # folders list is user-defined; don't overwrite with empty default
        "folders",
    },
}

_COMPARE_SYSTEM_PROMPT_DEFAULT = """\
你是一位资深的科研助手，擅长对多篇学术论文进行横向对比分析。

用户会提供 2-5 篇论文的摘要/结构化信息。请你从以下维度进行全面的对比分析，输出结构清晰的 Markdown 报告：

## 输出格式要求
请按以下结构输出（使用 Markdown 格式）：

### 📋 论文概览
用表格列出每篇论文的标题、机构、核心贡献（一句话）。

### 🔬 研究问题对比
比较各论文要解决的核心问题，找出共同关注点和差异点。

### 🛠️ 方法论差异
对比各论文采用的技术路线、模型架构、关键机制，分析各自的优势和局限。

### 📊 实验与结果比较
（如果有可用数据）对比实验设置、数据集、评估指标和实验结果。

### 🔗 互补性与关联
分析这些论文之间的学术关联：是否解决同一问题的不同方案？是否构成上下游关系？方法是否可以互相借鉴？

### 💡 综合建议
给出综合评价：哪篇论文的方法最有潜力？如果要开展后续研究，可以从这些论文中获取哪些启发？

## 要求
- 保持客观、学术性的语言风格
- 使用中文撰写，专有名词（模型名、数据集名、指标名）保留英文
- 如果某个维度信息不足，简要说明并跳过，不要编造
- 控制总篇幅在 1500 字以内
"""

_INSPIRATION_SYSTEM_PROMPT_DEFAULT = """\
你是一位富有创造力的科研灵感助手，擅长从多篇论文的关联中发现新的研究灵感和创新方向。

用户会提供若干条灵感涌现记录，每条包含标题、摘要和相关论文信息。请你综合分析这些灵感条目，深入挖掘其中的潜在联系，并输出结构清晰的 Markdown 报告：

## 输出格式要求
请按以下结构输出（使用 Markdown 格式）：

### 💡 灵感概览
简要总结用户选中的灵感条目，概括它们各自的核心思路。

### 🔗 跨领域关联
分析这些灵感之间是否存在深层次的技术关联或方法互补，找出可以互相融合的点。

### 🚀 研究方向建议
基于这些灵感的交叉点，提出 2-3 个具体的、可操作的研究方向或项目构想，包括：
- 研究问题是什么
- 可能采用的技术路线
- 预期的创新点和价值

### 📋 可行性评估
对提出的研究方向进行简要的可行性分析，包括技术难度、数据需求、潜在挑战等。

### 🎯 下一步行动
给出具体的行动建议：应该先读哪些论文、先做哪些实验、需要什么资源等。

## 要求
- 注重创新性和启发性，鼓励跨领域思考
- 使用中文撰写，专有名词（模型名、数据集名、指标名）保留英文
- 建议要具体、可操作，避免空泛的建议
- 控制总篇幅在 1500 字以内
"""

_PAPER_RECOMMEND_SYSTEM_PROMPT_DEFAULT = (
    '你是一个论文笔记助手，请阅读论文内容，用中文输出一个\u201c极简但有判断力\u201d的论文笔记，'
    '目标是让读者在最短时间内看懂论文的核心价值，并且可以直接拿去做口头汇报。'
    '不要面面俱到，不要复述大段背景，不要改写摘要，不要写成宣传文案。'
    '所有内容都要围绕三个问题展开：这篇论文到底解决了什么、怎么解决、结果说明了什么。'
    '请严格控制信息密度，只保留最有价值的内容。'
    '不要使用空话、套话和泛泛评价，例如\u201c很有意义\u201d\u201c值得关注\u201d\u201c效果很好\u201d\u201c提出了新方法\u201d等。'
    '推荐理由和个人观点必须写成判断句，不能空泛。'
    '研究问题必须是一个明确的问句。'
    '主要贡献只能写一句话，而且必须回答\u201c这篇论文最大的贡献是什么\u201d。'
    '重点思路只写3条，分别对应最核心的方法设计、最关键的技术机制、最重要的训练/推理/系统做法。'
    '分析总结只写3条，分别对应最重要的实验结果、方法为什么有效或提升了什么能力、最值得记住的对比实验或消融结论。'
    '每一条尽量控制在一句话内，避免展开解释。'
    '如果论文中有关键实验数字，优先保留；能量化就量化，不能量化就直接给出结论，禁止编造数字。'
    '推荐理由、研究问题、主要贡献、个人观点、一句话记忆版都尽量只写一句话。'
    '笔记标题要像一个10字左右的中文短句，直接概括论文最核心的贡献，不要空泛。'
    '请优先从论文首页、摘要、方法、实验、结论中提炼内容。'
    '如果能识别论文原标题和 arXiv 编号，则必须填写；如果无法确认，不要编造。'
    '全文控制在900字以内，语言风格要短、硬、准，追求信息密度最大化。'
    '不要添加任何格式说明、解释性前言或结尾。'
    '输出必须严格遵循以下格式：\n'
    '笔记标题：（10个字左右的中文短句，直接概括论文最核心的贡献）\n'
    '📖标题：论文原标题\n'
    '🌐来源：arXiv,[论文编号]\n'
    '推荐理由：（一句话，直接点出这篇论文最值得看的地方）\n'
    '🛎️文章简介\n'
    '🔸研究问题：（用一个问句描述论文试图解决什么问题）\n'
    '🔸主要贡献：（一句话回答这篇论文最大的贡献是什么）\n'
    '📝重点思路\n'
    '🔸（核心方法1）\n'
    '🔸（核心方法2）\n'
    '🔸（核心方法3）\n'
    '🔎分析总结\n'
    '🔸（最重要实验结果，尽量带关键数字）\n'
    '🔸（方法为何有效，或具体提升了什么能力）\n'
    '🔸（最值得记住的对比实验或消融结论）\n'
    '💡个人观点\n'
    '（一句话，判断这篇论文真正重要的价值或局限）\n'
    '一句话记忆版：（一句话概括整篇论文）'
)

_PAPER_CHAT_SYSTEM_PROMPT_DEFAULT = (
    "你是一位专业的学术论文问答助手。用户会就论文内容向你提问，请基于提供的论文内容作出准确、有深度的回答。\n"
    "\n"
    "回答规范：\n"
    "- 使用中文回答，专有名词（模型名、数据集名、指标名、方法名）保留英文原文\n"
    "- 如果论文中没有明确提及相关信息，如实说明「论文中未提及」，不要编造内容\n"
    "- 回答要简洁有力，聚焦于用户问题，避免无关铺垫\n"
    "- 涉及实验数据时优先引用论文中的具体数字\n"
    "- 可以适当指出论文的局限性或尚未解决的问题"
)

_PAPER_RECOMMEND_LIMIT_PROMPT_INTRO = (
    "你是一名严谨的学术论文摘要编辑。你的任务是把用户提供的【文章简介】压缩成更短的版本。\n"
    "硬性规则：\n"
    "只允许基于原文改写与删减，禁止新增论文未明确出现的数字、结论、因果解释、背景信息。\n"
    "必须保留两件事：①研究问题（1句内）②主要贡献/做了什么（1句内）。\n"
    "删除所有修饰、铺垫、泛化评价（如\"很有意义/非常重要\"）。\n"
    "输出 2 句中文，整体不超过 180 字（按去空白字符计）。\n"
    "只输出压缩后的正文，不要标题、不要字数说明、不要解释。"
)

_PAPER_RECOMMEND_LIMIT_PROMPT_METHOD = (
    "你是一名学术方法部分的精炼编辑。你的任务是把用户提供的【重点思路】压缩到更短、更\"信息密度高\"的版本。\n"
    "硬性规则：\n"
    "只允许删减与同义改写，禁止新增论文未明确出现的实验设置、对比对象、指标、结论与数字。\n"
    "只保留\"怎么做\"的关键动作：benchmark/数据/任务设计/训练或评测策略（优先保留带数字/专有名词的信息）。\n"
    "输出格式固定为 最多 4 条，每条以\"🔸\"开头，每条 1 句。\n"
    "整体不超过 280 字（去空白字符计）。\n"
    "只输出压缩后的条目，不要额外说明。"
)

_PAPER_RECOMMEND_LIMIT_PROMPT_FINDINGS = (
    "你是一名结果与结论部分的审稿式编辑。你的任务是把用户提供的【分析总结】压缩为更短的\"关键发现列表\"。\n"
    "硬性规则：\n"
    "只允许删减与同义改写，禁止新增论文未明确出现的解释、推断、因果链、建议或外延应用。\n"
    "必须保留最核心的 2–4 个发现（优先保留：一致性变化、失败模式、能力对比、训练方式影响）。\n"
    "输出格式固定为 最多 4 条，每条以\"🔸\"开头，每条 1 句，句子尽量短。\n"
    "整体不超过 280 字（去空白字符计）。\n"
    "只输出压缩后的条目，不要总结段、不要字数说明。"
)

_PAPER_RECOMMEND_LIMIT_PROMPT_OPINION = (
    "你是一名克制、保真的学术评论编辑。你的任务是把用户提供的【个人观点】压缩为极短版本。\n"
    "硬性规则：\n"
    "只允许基于原文观点做删减与改写，禁止新增论文未提到的价值判断、应用场景、改进建议或任何推断性结论。\n"
    "允许保留\"评价框架\"，但措辞必须克制（避免\"必然/革命性/全面提升\"等强断言）。\n"
    "输出 1–2 句中文，整体不超过 160 字（去空白字符计）。\n"
    "只输出压缩后的正文，不要标题、不要解释、不要字数说明。"
)

_DEEP_RESEARCH_ROUND1_SYSTEM_DEFAULT = """你是一个学术论文相关性评估专家。
给定一个研究问题和若干论文的摘要/标题，请评估每篇论文与该问题的相关性，并输出 JSON 排序结果。

输出格式（严格 JSON，不要有任何多余文字）：
{
  "rankings": [
    {
      "paper_id": "论文ID",
      "score": 0.95,
      "level": "high",
      "reason": "相关性原因（一句话）"
    }
  ]
}

score 范围 0.0-1.0，level 为 "high"(>=0.6)、"medium"(>=0.3)、"low"(<0.3)。
按 score 从高到低排序。所有输入论文都必须出现在输出中。"""

_DEEP_RESEARCH_ROUND2_SYSTEM_DEFAULT = """你是一个学术研究助手，擅长从论文摘要中提炼信息并回答研究问题。

你的任务：
1. 仔细阅读给定论文的 AI 摘要，尝试回答用户的研究问题。
2. 如果摘要中的信息足够回答问题，请直接给出详尽、有条理的回答。
3. 如果摘要信息不足（需要查阅全文的实验数据、详细方法或具体数值），请在回答末尾附上以下 JSON 块（不要在其他地方输出 JSON）：

```json
{"action":"read_full","papers":["paper_id_1","paper_id_2"]}
```

只有当确实需要全文才能更好回答时才建议阅读全文。如果摘要已足够，不要输出 JSON 块。
回答时请用中文，结构清晰，引用具体论文时注明论文 ID。"""

_DEEP_RESEARCH_ROUND3_SYSTEM_DEFAULT = """你是一个学术研究助手，能够深度分析论文全文并回答研究问题。

你已经阅读了相关论文的摘要并做了初步分析，现在你获得了以下论文的全文内容（经过结构化解析）。
请结合全文内容，给出更深入、更准确的回答。

回答要求：
- 用中文，条理清晰
- 引用具体证据时注明来源论文 ID 和相关章节
- 如果全文中有关键实验数据、方法细节或结论，要明确引用
- 综合之前的摘要分析和本次全文阅读，给出完整的最终回答"""

_FEATURE_DEFAULTS: dict[str, dict[str, Any]] = {
    "compare": {
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 1.0,
        "max_tokens": 4096,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
        "data_source": "summary",
        "system_prompt": _COMPARE_SYSTEM_PROMPT_DEFAULT,
    },
    "inspiration": {
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 1.0,
        "max_tokens": 4096,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
        "system_prompt": _INSPIRATION_SYSTEM_PROMPT_DEFAULT,
    },
    "paper_recommend": {
        # --- LLM 连接配置 ---
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 1.0,
        "max_tokens": 2048,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
        # --- 提示词配置 ---
        "system_prompt": _PAPER_RECOMMEND_SYSTEM_PROMPT_DEFAULT,
        "summary_limit_prompt_intro": _PAPER_RECOMMEND_LIMIT_PROMPT_INTRO,
        "summary_limit_prompt_method": _PAPER_RECOMMEND_LIMIT_PROMPT_METHOD,
        "summary_limit_prompt_findings": _PAPER_RECOMMEND_LIMIT_PROMPT_FINDINGS,
        "summary_limit_prompt_opinion": _PAPER_RECOMMEND_LIMIT_PROMPT_OPINION,
        # --- 字数上限 ---
        "section_limit_intro": 170,
        "section_limit_method": 270,
        "section_limit_findings": 270,
        "section_limit_opinion": 150,
        "headline_limit": 18,
        # --- arXiv 检索分类 ---
        "search_categories": ["cs.CL", "cs.LG", "cs.AI", "stat.ML"],
    },
    "my_papers": {
        # --- LLM 连接配置 ---
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 1.0,
        "max_tokens": 2048,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
        # --- 提示词配置 ---
        "system_prompt": _PAPER_RECOMMEND_SYSTEM_PROMPT_DEFAULT,
        "summary_limit_prompt_intro": _PAPER_RECOMMEND_LIMIT_PROMPT_INTRO,
        "summary_limit_prompt_method": _PAPER_RECOMMEND_LIMIT_PROMPT_METHOD,
        "summary_limit_prompt_findings": _PAPER_RECOMMEND_LIMIT_PROMPT_FINDINGS,
        "summary_limit_prompt_opinion": _PAPER_RECOMMEND_LIMIT_PROMPT_OPINION,
        # --- 字数上限 ---
        "section_limit_intro": 170,
        "section_limit_method": 270,
        "section_limit_findings": 270,
        "section_limit_opinion": 150,
        "headline_limit": 18,
    },
    "paper_chat": {
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 0.7,
        "max_tokens": 4096,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
        "data_source": "summary",
        "system_prompt": _PAPER_CHAT_SYSTEM_PROMPT_DEFAULT,
        # Context strategy: recent_k | summary | full
        "context_strategy": "recent_k",
        # K value used by recent_k and summary strategies (number of turns)
        "context_k": 10,
    },
    "deep_research": {
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 0.5,
        "max_tokens": 8192,
        "input_hard_limit": 200000,
        "input_safety_margin": 8192,
        "system_prompt": "",
        "round1_system_prompt": _DEEP_RESEARCH_ROUND1_SYSTEM_DEFAULT,
        "round2_system_prompt": _DEEP_RESEARCH_ROUND2_SYSTEM_DEFAULT,
        "round3_system_prompt": _DEEP_RESEARCH_ROUND3_SYSTEM_DEFAULT,
    },
    "translate": {
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 0.3,
        "max_tokens": 4096,
        "input_hard_limit": 120000,
        "input_safety_margin": 4096,
        "chunk_size": 6000,
        "concurrency": 8,
    },
    "idea_generate": {
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 0.7,
        "max_tokens": 8192,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
        # system_prompt kept for backward compatibility (maps to ingest phase)
        "system_prompt": "",
        # Per-phase prompt text overrides (每阶段独立，空值 = 回退到 config.py 默认值)
        "ingest_system_prompt":    "",
        "question_system_prompt":  "",
        "candidate_system_prompt": "",
        "review_system_prompt":    "",
        "revise_system_prompt":    "",
        "plan_system_prompt":      "",
        "eval_system_prompt":      "",
    },
    # Future features can be added here:
    # "theme_filter": { ... },
    "auto_classify": {
        "enabled": False,
        # LLM preset (id) to use for classification; empty = not configured
        "llm_preset_id": "",
        # Minimum confidence (0.0–1.0) to assign a folder; below this goes to '未分类'
        "confidence_threshold": 0.6,
        # User-defined folder list for classification
        # Each entry: {"name": str, "description": str, "folder_id": null | int}
        "folders": [],
    },
}


def get_hardcoded_defaults(feature: str) -> dict[str, Any]:
    """Return the original hardcoded default values for *feature* (empty dict if unknown).
    These are the built-in defaults from code, unaffected by admin overrides."""
    return dict(_FEATURE_DEFAULTS.get(feature, {}))


def get_defaults(feature: str) -> dict[str, Any]:
    """Return the effective default values for *feature*.

    Priority: admin overrides (user_id=0 in DB) > hardcoded _FEATURE_DEFAULTS.
    Returns empty dict if feature is unknown.
    """
    hardcoded = get_hardcoded_defaults(feature)
    if not hardcoded:
        return {}
    admin_overrides = get_admin_overrides(feature)
    if admin_overrides:
        merged = dict(hardcoded)
        merged.update(admin_overrides)
        return merged
    return hardcoded


# ---------------------------------------------------------------------------
# Admin default overrides (user_id = 0)
# ---------------------------------------------------------------------------

_ADMIN_USER_ID = 0


def get_admin_overrides(feature: str) -> dict[str, Any]:
    """Return only the admin-set overrides for *feature* (user_id=0 raw JSON).
    Returns empty dict if no admin overrides are set."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT settings_json FROM user_settings WHERE user_id = ? AND feature = ?",
            (_ADMIN_USER_ID, feature),
        ).fetchone()
        if row:
            try:
                return unprotect_secret_mapping(json.loads(row["settings_json"]) or {})
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    finally:
        conn.close()


def save_admin_defaults(feature: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Save admin overrides for *feature* (writes to user_id=0 row).
    Returns the new effective defaults after saving."""
    now = _now_iso()
    protected = protect_secret_mapping(
        overrides,
        existing=get_admin_overrides(feature),
    )
    settings_str = json.dumps(protected, ensure_ascii=False)
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO user_settings (user_id, feature, settings_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, feature) DO UPDATE SET
                settings_json = excluded.settings_json,
                updated_at    = excluded.updated_at
            """,
            (_ADMIN_USER_ID, feature, settings_str, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_defaults(feature)


def reset_admin_defaults(feature: str) -> None:
    """Delete admin overrides for *feature*, reverting to hardcoded defaults."""
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM user_settings WHERE user_id = ? AND feature = ?",
            (_ADMIN_USER_ID, feature),
        )
        conn.commit()
    finally:
        conn.close()


def list_admin_defaults() -> list[dict[str, Any]]:
    """Return info for all known features: effective defaults, hardcoded defaults,
    admin overrides, and whether admin overrides are active."""
    features = list(_FEATURE_DEFAULTS.keys())
    result = []
    for feature in features:
        hardcoded = get_hardcoded_defaults(feature)
        overrides = get_admin_overrides(feature)
        effective = dict(hardcoded)
        if overrides:
            effective.update(overrides)
        result.append({
            "feature": feature,
            "has_admin_overrides": bool(overrides),
            "effective_defaults": effective,
            "hardcoded_defaults": hardcoded,
            "admin_overrides": overrides,
        })
    return result


def resolve_admin_llm_for_feature(feature: str) -> dict[str, Any]:
    """Resolve the admin-configured default LLM for *feature*.

    Reads `admin_llm_config_id` from the admin overrides (user_id=0) for the
    given feature, then looks up the full LLM config from the llm_config table.

    Returns a dict with keys matching the service `cfg` convention::

        {
            "llm_base_url": ...,
            "llm_api_key":  ...,
            "llm_model":    ...,
            "max_tokens":   ...,  # only if set
            "temperature":  ...,  # only if set
        }

    Returns an empty dict if no admin LLM config is set for this feature or if
    the referenced config no longer exists.
    """
    overrides = get_admin_overrides(feature)
    config_id = overrides.get("admin_llm_config_id")
    if not config_id:
        return {}
    try:
        from services import llm_config_service
        llm_cfg = llm_config_service.get_config(int(config_id))
    except Exception:
        return {}
    if not llm_cfg:
        return {}
    result: dict[str, Any] = {
        "llm_base_url": llm_cfg.get("base_url", ""),
        "llm_api_key":  llm_cfg.get("api_key", ""),
        "llm_model":    llm_cfg.get("model", ""),
        "enable_thinking": bool(llm_cfg.get("enable_thinking", 0)),
        "use_openrouter_free_pool": bool(llm_cfg.get("use_openrouter_free_pool", 0)),
    }
    if llm_cfg.get("max_tokens") is not None:
        result["max_tokens"] = llm_cfg["max_tokens"]
    if llm_cfg.get("temperature") is not None:
        result["temperature"] = llm_cfg["temperature"]
    if llm_cfg.get("input_hard_limit") is not None:
        result["input_hard_limit"] = llm_cfg["input_hard_limit"]
    if llm_cfg.get("input_safety_margin") is not None:
        result["input_safety_margin"] = llm_cfg["input_safety_margin"]
    return result


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def get_settings(user_id: int, feature: str) -> dict[str, Any]:
    """
    Return the merged settings for a user + feature.

    - Keys that have defaults are filled in when the user has not set them.
    - Keys in ``_NO_DEFAULT_KEYS`` are returned as-is (empty string if unset).
    """
    defaults = get_defaults(feature)
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT settings_json FROM user_settings WHERE user_id = ? AND feature = ?",
            (user_id, feature),
        ).fetchone()
        user_vals: dict[str, Any] = {}
        if row:
            try:
                user_vals = unprotect_secret_mapping(json.loads(row["settings_json"]))
            except (json.JSONDecodeError, TypeError):
                user_vals = {}

        # Merge: user values override defaults
        merged = dict(defaults)
        merged.update(user_vals)

        # For "no-default" keys, do NOT fill from defaults — keep user value
        no_defaults = _NO_DEFAULT_KEYS.get(feature, set())
        for key in no_defaults:
            merged[key] = user_vals.get(key, "")

        return merged
    finally:
        conn.close()


def get_raw_settings(user_id: int, feature: str) -> dict[str, Any]:
    """Return only the user-provided settings (no defaults merged)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT settings_json FROM user_settings WHERE user_id = ? AND feature = ?",
            (user_id, feature),
        ).fetchone()
        if row:
            try:
                return unprotect_secret_mapping(json.loads(row["settings_json"]))
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    finally:
        conn.close()


def save_settings(user_id: int, feature: str, settings: dict[str, Any]) -> dict[str, Any]:
    """
    Upsert settings for a user + feature.

    Returns the merged settings after saving.
    """
    now = _now_iso()
    protected = protect_secret_mapping(
        settings,
        existing=get_raw_settings(user_id, feature),
    )
    settings_str = json.dumps(protected, ensure_ascii=False)
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO user_settings (user_id, feature, settings_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, feature) DO UPDATE SET
                settings_json = excluded.settings_json,
                updated_at    = excluded.updated_at
            """,
            (user_id, feature, settings_str, now),
        )
        conn.commit()
    finally:
        conn.close()

    return get_settings(user_id, feature)


def list_users_with_custom_configs(features: list[str] | None = None) -> list[int]:
    """
    Return a list of user_ids that have at least one non-empty custom config
    for any of the specified *features* (default: ['paper_recommend', 'idea_generate']).

    user_id=0 is excluded (that is the system/default user).
    """
    if features is None:
        features = ["paper_recommend", "idea_generate"]
    conn = _connect()
    try:
        placeholders = ",".join("?" for _ in features)
        rows = conn.execute(
            f"SELECT DISTINCT user_id FROM user_settings "
            f"WHERE feature IN ({placeholders}) AND user_id != 0 "
            f"AND settings_json != '{{}}' AND settings_json != ''",
            features,
        ).fetchall()
        return [r["user_id"] for r in rows]
    finally:
        conn.close()


def collect_all_search_categories() -> list[str]:
    """
    Return the union of search_categories across all users' paper_recommend settings,
    merged with the system-level SEARCH_CATEGORIES default.

    Used by the shared pipeline phase to ensure all users' preferred arXiv categories
    are fetched in one go.
    """
    from config import config as _config
    system_cats: list[str] = list(getattr(_config, "SEARCH_CATEGORIES", ["cs.CL", "cs.LG", "cs.AI", "stat.ML"]) or [])
    default_cats: list[str] = _FEATURE_DEFAULTS.get("paper_recommend", {}).get("search_categories", system_cats)

    all_cats: set[str] = set(system_cats)

    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT settings_json FROM user_settings WHERE feature = 'paper_recommend'"
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        try:
            settings = json.loads(row["settings_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            settings = {}
        user_cats = settings.get("search_categories")
        if isinstance(user_cats, list) and user_cats:
            all_cats.update(user_cats)

    if not all_cats:
        return list(default_cats)
    return sorted(all_cats)


# ---------------------------------------------------------------------------
# Admin audit: all users with custom configs
# ---------------------------------------------------------------------------

def get_custom_config_audit() -> dict[str, Any]:
    """Return an audit of every user that has at least one non-empty custom config.

    Covers three sources:
    - user_settings rows (feature-level settings, including preset references)
    - user_llm_presets rows (named LLM connection presets)
    - user_prompt_presets rows (named system-prompt presets)

    Returns
    -------
    {
        "summary": {
            "total_users_with_custom_config": int,
            "total_active_llm_preset_refs":   int,   # preset IDs actually referenced by a feature
            "total_active_prompt_preset_refs": int,
            "total_unused_llm_presets":        int,   # presets created but not referenced
            "total_unused_prompt_presets":     int,
        },
        "users": [
            {
                "user_id": int,
                "username": str,
                "tier": str,
                "role": str,
                "feature_count": int,
                "llm_preset_ref_count": int,
                "prompt_preset_ref_count": int,
                "total_llm_presets": int,
                "total_prompt_presets": int,
                "unused_llm_presets": [...],
                "unused_prompt_presets": [...],
                "last_updated": str | None,
                "feature_configs": [...],
            },
            ...
        ],
    }

    api_key values are never returned; only has_api_key (bool) is exposed.
    """
    conn = _connect()
    try:
        settings_rows = conn.execute(
            "SELECT user_id, feature, settings_json, updated_at "
            "FROM user_settings "
            "WHERE user_id != 0 AND settings_json != '{}' AND settings_json != ''"
        ).fetchall()

        llm_rows = conn.execute("SELECT * FROM user_llm_presets").fetchall()
        prompt_rows = conn.execute("SELECT * FROM user_prompt_presets").fetchall()
        auth_rows = conn.execute(
            "SELECT id, username, role, tier FROM auth_users"
        ).fetchall()
    finally:
        conn.close()

    # ---- lookup maps ----
    auth_map: dict[int, dict] = {r["id"]: dict(r) for r in auth_rows}

    llm_by_user: dict[int, dict[int, dict]] = {}
    for r in llm_rows:
        uid = r["user_id"]
        llm_by_user.setdefault(uid, {})[r["id"]] = dict(r)

    prompt_by_user: dict[int, dict[int, dict]] = {}
    for r in prompt_rows:
        uid = r["user_id"]
        prompt_by_user.setdefault(uid, {})[r["id"]] = dict(r)

    settings_by_user: dict[int, list[dict]] = {}
    for r in settings_rows:
        uid = r["user_id"]
        try:
            sdata = json.loads(r["settings_json"]) or {}
        except (json.JSONDecodeError, TypeError):
            sdata = {}
        settings_by_user.setdefault(uid, []).append({
            "feature": r["feature"],
            "settings": sdata,
            "updated_at": r["updated_at"],
        })

    # ---- collect all user_ids with any custom config ----
    all_uids: set[int] = set(settings_by_user)
    all_uids |= set(llm_by_user)
    all_uids |= set(prompt_by_user)

    # ---- build per-user records ----
    user_records: list[dict] = []
    for uid in sorted(all_uids):
        user_info = auth_map.get(uid, {})
        user_llm_presets_map = llm_by_user.get(uid, {})
        user_prompt_presets_map = prompt_by_user.get(uid, {})
        user_settings_list = settings_by_user.get(uid, [])

        llm_preset_refs_used: set[int] = set()
        prompt_preset_refs_used: set[int] = set()
        feature_configs: list[dict] = []

        for fs in user_settings_list:
            feature = fs["feature"]
            settings = fs["settings"]
            feature_llm_refs: dict[str, dict] = {}
            feature_prompt_refs: dict[str, dict] = {}
            direct_params: dict[str, Any] = {}

            for key, val in settings.items():
                # --- LLM preset reference ---
                if val and (key == "llm_preset_id" or key.endswith("_llm_preset_id")):
                    try:
                        pid = int(val)
                    except (TypeError, ValueError):
                        continue
                    llm_preset_refs_used.add(pid)
                    p = user_llm_presets_map.get(pid, {})
                    feature_llm_refs[key] = {
                        "preset_id": pid,
                        "preset_name": p.get("name", "（已删除）") if p else "（已删除）",
                        "model": p.get("model", "") if p else "",
                        "base_url": p.get("base_url", "") if p else "",
                        "has_api_key": bool(p.get("api_key")) if p else False,
                        "temperature": p.get("temperature") if p else None,
                        "max_tokens": p.get("max_tokens") if p else None,
                        "enable_thinking": bool(p.get("enable_thinking")) if p else False,
                    }

                # --- Prompt preset reference ---
                elif val and (key == "prompt_preset_id" or key.endswith("_prompt_preset_id")):
                    try:
                        pid = int(val)
                    except (TypeError, ValueError):
                        continue
                    prompt_preset_refs_used.add(pid)
                    p = user_prompt_presets_map.get(pid, {})
                    content = p.get("prompt_content", "") if p else ""
                    feature_prompt_refs[key] = {
                        "preset_id": pid,
                        "preset_name": p.get("name", "（已删除）") if p else "（已删除）",
                        "content_preview": (content[:120] + "…") if len(content) > 120 else content,
                    }

            # direct non-preset params worth surfacing
            for k in ("llm_model", "llm_base_url", "temperature", "max_tokens",
                      "search_categories", "data_source", "context_strategy"):
                if settings.get(k) not in (None, "", [], {}):
                    direct_params[k] = settings[k]

            feature_configs.append({
                "feature": feature,
                "updated_at": fs["updated_at"],
                "llm_preset_refs": feature_llm_refs,
                "prompt_preset_refs": feature_prompt_refs,
                "direct_params": direct_params,
                "has_direct_llm_config": bool(
                    settings.get("llm_base_url") or settings.get("llm_model")
                ),
            })

        # presets created but not currently referenced by any feature
        unused_llm = [
            {
                "id": pid,
                "name": p["name"],
                "model": p.get("model", ""),
                "base_url": p.get("base_url", ""),
                "has_api_key": bool(p.get("api_key")),
            }
            for pid, p in user_llm_presets_map.items()
            if pid not in llm_preset_refs_used
        ]
        unused_prompt = [
            {
                "id": pid,
                "name": p["name"],
                "content_preview": (p["prompt_content"][:120] + "…")
                if len(p.get("prompt_content", "")) > 120
                else p.get("prompt_content", ""),
            }
            for pid, p in user_prompt_presets_map.items()
            if pid not in prompt_preset_refs_used
        ]

        updated_ats = [fs["updated_at"] for fs in user_settings_list]
        last_updated = max(updated_ats) if updated_ats else None

        user_records.append({
            "user_id": uid,
            "username": user_info.get("username", f"user_{uid}"),
            "tier": user_info.get("tier", "free"),
            "role": user_info.get("role", "user"),
            "feature_count": len(feature_configs),
            "llm_preset_ref_count": len(llm_preset_refs_used),
            "prompt_preset_ref_count": len(prompt_preset_refs_used),
            "total_llm_presets": len(user_llm_presets_map),
            "total_prompt_presets": len(user_prompt_presets_map),
            "unused_llm_presets": unused_llm,
            "unused_prompt_presets": unused_prompt,
            "last_updated": last_updated,
            "feature_configs": feature_configs,
        })

    total_llm_refs = sum(r["llm_preset_ref_count"] for r in user_records)
    total_prompt_refs = sum(r["prompt_preset_ref_count"] for r in user_records)
    total_unused_llm = sum(len(r["unused_llm_presets"]) for r in user_records)
    total_unused_prompt = sum(len(r["unused_prompt_presets"]) for r in user_records)

    return {
        "summary": {
            "total_users_with_custom_config": len(user_records),
            "total_active_llm_preset_refs": total_llm_refs,
            "total_active_prompt_preset_refs": total_prompt_refs,
            "total_unused_llm_presets": total_unused_llm,
            "total_unused_prompt_presets": total_unused_prompt,
        },
        "users": user_records,
    }


# Ensure table exists on import
init_db()
