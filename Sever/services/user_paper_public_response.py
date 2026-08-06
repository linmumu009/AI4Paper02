"""Pure normalization rules for user-visible user-paper responses."""

from __future__ import annotations

from typing import Any

from services.llm_response_guard import has_meaningful_text


_RENDERABLE_SUMMARY_KEYS = (
    "🛎️文章简介",
    "📝重点思路",
    "🔎分析总结",
    "💡个人观点",
    "一句话记忆版",
    "summary",
    "one_sentence_summary",
)


def has_renderable_summary(summary: Any) -> bool:
    """Require insight content rendered by current or supported legacy clients."""
    if not isinstance(summary, dict):
        return False
    return any(
        has_meaningful_text(summary.get(key))
        for key in _RENDERABLE_SUMMARY_KEYS
    )


def normalize_public_user_paper_state(
    paper: dict[str, Any],
    *,
    translation_available: bool | None = None,
    check_process_result: bool = True,
) -> dict[str, Any]:
    """Turn impossible completed states into actionable public failures."""
    normalized = dict(paper)
    if (
        check_process_result
        and normalized.get("process_status") == "completed"
        and not has_renderable_summary(normalized.get("summary"))
    ):
        normalized["process_status"] = "failed"
        normalized["process_step"] = "paper_summary"
        normalized["process_error"] = "论文内容暂不可用，请重新处理"

    if (
        translation_available is not None
        and normalized.get("translate_status") == "completed"
        and not translation_available
    ):
        normalized["translate_status"] = "failed"
        normalized["translate_error"] = "翻译文件暂不可用，请重新翻译"
    return normalized
