"""
Pipeline Step Configuration Service.

Manages which pipeline steps are enabled/disabled for scheduled and manual runs.
Configuration is persisted in database/pipeline_step_config.json.

Provides:
  - Step definitions with full dependency graph
  - Read/save step enable configuration
  - Dependency validation (upstream must be enabled if downstream is enabled)
  - Runtime step filtering (returns filtered list + disabled set)
"""

import json
import os
from typing import Optional

_SEVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_SEVER_ROOT, "database", "pipeline_step_config.json")

# ---------------------------------------------------------------------------
# Step definitions with dependency graph
#
# requires: hard upstream deps — if step B is enabled, all of B's requires
#           must also be enabled (enforced at save time and at runtime).
# can_disable: False means the step is always forced on and the toggle is hidden
#              in the admin UI.
# default_enabled: used when no saved config exists for that key.
# cost_level: 'low' | 'medium' | 'high' — shown in the UI as an indicator.
# ---------------------------------------------------------------------------

STEP_DEFINITIONS: list[dict] = [
    # ── Shared phase ─────────────────────────────────────────────────────────
    {
        "key": "arxiv_search",
        "label": "ArXiv 论文搜索",
        "phase": "shared",
        "group": "共享采集",
        "default_enabled": True,
        "requires": [],
        "cost_level": "low",
        "can_disable": False,
        "description": "从 ArXiv API 搜索当日新论文列表",
    },
    {
        "key": "paperList_remove_duplications",
        "label": "论文去重",
        "phase": "shared",
        "group": "共享采集",
        "default_enabled": True,
        "requires": ["arxiv_search"],
        "cost_level": "low",
        "can_disable": False,
        "description": "对搜索结果去重，避免重复处理",
    },
    {
        "key": "pdf_download",
        "label": "PDF 下载",
        "phase": "shared",
        "group": "共享采集",
        "default_enabled": True,
        "requires": ["paperList_remove_duplications"],
        "cost_level": "low",
        "can_disable": False,
        "description": "下载候选论文 PDF",
    },
    {
        "key": "pdf_split",
        "label": "PDF 预处理",
        "phase": "shared",
        "group": "共享采集",
        "default_enabled": True,
        "requires": ["pdf_download"],
        "cost_level": "low",
        "can_disable": False,
        "description": "拆分和预处理 PDF 文件",
    },
    {
        "key": "pdfsplite_to_minerU",
        "label": "MinerU 解析（预览）",
        "phase": "shared",
        "group": "共享采集",
        "default_enabled": True,
        "requires": ["pdf_split"],
        "cost_level": "low",
        "can_disable": False,
        "description": "用 MinerU 解析 PDF，提取结构化文本（供 pdf_info 使用）",
    },
    {
        "key": "selectedpaper_to_mineru",
        "label": "MinerU 解析（精选完整版）",
        "phase": "shared",
        "group": "共享采集",
        "default_enabled": True,
        "requires": ["pdfsplite_to_minerU"],
        "cost_level": "medium",
        "can_disable": True,
        "description": "对精选论文做完整 MinerU 解析，供摘要和按需灵感生成使用",
    },
    # ── Per-user phase：论文推荐 ──────────────────────────────────────────────
    {
        "key": "llm_select_theme",
        "label": "主题筛选（LLM）",
        "phase": "per_user",
        "group": "论文推荐",
        "default_enabled": True,
        "requires": ["paperList_remove_duplications"],
        "cost_level": "medium",
        "can_disable": False,
        "description": "用 LLM 对论文按用户兴趣主题打分",
    },
    {
        "key": "paper_theme_filter",
        "label": "主题过滤",
        "phase": "per_user",
        "group": "论文推荐",
        "default_enabled": True,
        "requires": ["llm_select_theme"],
        "cost_level": "low",
        "can_disable": False,
        "description": "根据主题分数筛选候选论文",
    },
    {
        "key": "pdf_info",
        "label": "论文信息提取",
        "phase": "per_user",
        "group": "论文推荐",
        "default_enabled": True,
        "requires": ["pdfsplite_to_minerU"],
        "cost_level": "low",
        "can_disable": False,
        "description": "提取机构、摘要等基础信息",
    },
    {
        "key": "instutions_filter",
        "label": "最终精选（机构过滤）",
        "phase": "per_user",
        "group": "论文推荐",
        "default_enabled": True,
        "requires": ["paper_theme_filter", "pdf_info"],
        "cost_level": "low",
        "can_disable": False,
        "description": "综合主题分和机构做最终精选，写入推荐列表",
    },
    # ── Per-user phase：内容生成 ──────────────────────────────────────────────
    {
        "key": "paper_summary",
        "label": "论文摘要生成",
        "phase": "per_user",
        "group": "内容生成",
        "default_enabled": True,
        "requires": ["instutions_filter"],
        "cost_level": "high",
        "can_disable": True,
        "description": "为精选论文生成全文摘要（LLM 调用，消耗 token 较多）",
    },
    {
        "key": "summary_limit",
        "label": "摘要精简",
        "phase": "per_user",
        "group": "内容生成",
        "default_enabled": True,
        "requires": ["paper_summary"],
        "cost_level": "medium",
        "can_disable": True,
        "description": "将全文摘要精简为推荐卡片所用的短摘要（关闭后前端显示降级）",
    },
    {
        "key": "paper_assets",
        "label": "论文资产结构化",
        "phase": "per_user",
        "group": "内容生成",
        "default_enabled": True,
        "requires": ["summary_limit"],
        "cost_level": "low",
        "can_disable": True,
        "description": "将摘要、图片等整理为前端推荐卡片所需的结构化资产（推荐功能必需）",
    },
    # ── Per-user phase：灵感生成 ──────────────────────────────────────────────
    # 默认全部关闭；建议改用按需触发（用户对单篇论文点击「灵感涌现」）
    {
        "key": "idea_ingest",
        "label": "灵感原子提取（批处理）",
        "phase": "per_user",
        "group": "灵感生成（每日批处理）",
        "default_enabled": False,
        "requires": ["paper_assets"],
        "cost_level": "high",
        "can_disable": True,
        "description": "批量为每篇论文提取灵感原子，消耗大量 token；建议使用「按需灵感生成」替代",
    },
    {
        "key": "idea_combine",
        "label": "灵感问题与候选生成（批处理）",
        "phase": "per_user",
        "group": "灵感生成（每日批处理）",
        "default_enabled": False,
        "requires": ["idea_ingest"],
        "cost_level": "high",
        "can_disable": True,
        "description": "基于原子生成研究问题和灵感候选",
    },
    {
        "key": "idea_review",
        "label": "灵感评审（批处理）",
        "phase": "per_user",
        "group": "灵感生成（每日批处理）",
        "default_enabled": False,
        "requires": ["idea_combine"],
        "cost_level": "high",
        "can_disable": True,
        "description": "对灵感候选做多视角评审打分",
    },
    {
        "key": "idea_compound",
        "label": "灵感发布（批处理）",
        "phase": "per_user",
        "group": "灵感生成（每日批处理）",
        "default_enabled": False,
        "requires": ["idea_review"],
        "cost_level": "low",
        "can_disable": True,
        "description": "将评审通过的候选写入发布状态，出现在用户灵感推荐卡片中",
    },
    # ── 清理（两个阶段均有） ──────────────────────────────────────────────────
    {
        "key": "cleanup",
        "label": "清理中间文件",
        "phase": "both",
        "group": "清理",
        "default_enabled": True,
        "requires": [],
        "cost_level": "low",
        "can_disable": False,
        "description": "删除中间文件、释放磁盘空间（自动适配运行阶段，不可禁用）",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _defaults() -> dict[str, bool]:
    return {s["key"]: s["default_enabled"] for s in STEP_DEFINITIONS}


def _key_to_def() -> dict[str, dict]:
    return {s["key"]: s for s in STEP_DEFINITIONS}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_step_definitions() -> list[dict]:
    """Return all step definitions (copy-safe, no mutation)."""
    return list(STEP_DEFINITIONS)


def get_step_config() -> dict[str, bool]:
    """
    Read current step enable/disable state from config file.
    Missing keys fall back to the step's default_enabled value.
    Unknown keys in the file are ignored.
    """
    defaults = _defaults()
    if not os.path.isfile(_CONFIG_PATH):
        return defaults
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        config = defaults.copy()
        for k, v in raw.items():
            if k in defaults:
                config[k] = bool(v)
        return config
    except (json.JSONDecodeError, OSError):
        return defaults


def validate_step_config(config: dict[str, bool]) -> list[str]:
    """
    Validate that enabled steps don't violate hard upstream dependencies.
    Rule: if step B is enabled and B.requires = [A], then A must also be enabled.
    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []
    kd = _key_to_def()
    defaults = _defaults()
    for step_key, enabled in config.items():
        if not enabled:
            continue
        step_def = kd.get(step_key)
        if not step_def:
            continue
        for req in step_def.get("requires", []):
            req_enabled = config.get(req, defaults.get(req, True))
            if not req_enabled:
                req_label = kd[req]["label"] if req in kd else req
                errors.append(
                    f"步骤「{step_def['label']}」({step_key}) 依赖"
                    f"「{req_label}」({req})，但后者已被禁用"
                )
    return errors


def save_step_config(config: dict[str, bool]) -> list[str]:
    """
    Validate then persist step config.
    Returns validation errors on failure (empty list = saved successfully).
    """
    errors = validate_step_config(config)
    if errors:
        return errors
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    tmp = _CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _CONFIG_PATH)
    return []


def reset_step_config() -> None:
    """Delete the saved config file, reverting all steps to defaults."""
    if os.path.isfile(_CONFIG_PATH):
        os.remove(_CONFIG_PATH)


def get_enabled_steps(pipeline: str, base_steps: list[str]) -> tuple[list[str], set[str]]:
    """
    Filter base_steps according to current step config.

    Steps with can_disable=False are always kept regardless of config.
    Returns (enabled_steps, disabled_steps_set).
    """
    config = get_step_config()
    kd = _key_to_def()

    enabled: list[str] = []
    disabled: set[str] = set()

    for step in base_steps:
        step_def = kd.get(step, {})
        if not step_def.get("can_disable", True):
            # Non-disableable steps always run
            enabled.append(step)
            continue
        is_on = config.get(step, step_def.get("default_enabled", True))
        if is_on:
            enabled.append(step)
        else:
            disabled.add(step)

    return enabled, disabled
