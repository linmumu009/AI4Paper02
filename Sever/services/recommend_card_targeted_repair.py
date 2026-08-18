"""Evaluation-only targeted repair used by the recorded prompt experiment.

The strategy failed its pairwise safety gate and is deliberately not imported by
the production summary pipeline.  Keeping it here makes the negative result
reproducible without silently changing live behavior.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Tuple

from config.recommend_card_prompts import CARD_FIELD_LIMITS
from services.llm_request_options import build_thinking_kwargs
from services.llm_response_guard import require_nonempty_text
from services.recommend_card_prompt_eval import (
    FIELD_ORDER,
    deterministic_report,
    non_ws_len,
    parse_card,
    render_card,
)


_FIELD_LABELS = {
    "short_title": "中文短标题",
    "recommendation_reason": "推荐理由",
    "research_question": "研究问题",
    "main_contribution": "主要贡献",
    "key_ideas": "重点思路",
    "analysis_summary": "分析总结",
    "personal_opinion": "个人观点",
    "memory_sentence": "一句话记忆",
}

_SAFE_TARGETS = {
    "short_title": 10,
    "recommendation_reason": 50,
    "research_question": 45,
    "main_contribution": 55,
    "key_ideas": 150,
    "analysis_summary": 150,
    "personal_opinion": 50,
    "memory_sentence": 30,
}


def _choice_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    return str(getattr(message, "content", "") or "").strip()


def _contract_errors(candidate: str, source_draft: str) -> List[str]:
    report = deterministic_report(
        candidate,
        source_text=source_draft,
        refinement_input=source_draft,
    )
    return list(report.get("contract_errors") or [])


def _parse_field(key: str, text: str) -> Any:
    content = re.sub(r"^```(?:markdown|text)?\s*", "", (text or "").strip())
    content = re.sub(r"\s*```$", "", content).strip()
    if not content:
        return [] if key in {"key_ideas", "analysis_summary"} else ""
    if any(label in content for label in _FIELD_LABELS.values()):
        value = getattr(parse_card(content), key)
        if value:
            return value
    if key in {"key_ideas", "analysis_summary"}:
        items: List[str] = []
        for line in content.splitlines():
            value = re.sub(r"^(?:[-*•]|🔹|🔸)\s*", "", line.strip())
            value = re.sub(r"^\d+[.)、）]\s*", "", value).strip()
            if not value or value.rstrip("：:") == _FIELD_LABELS[key]:
                continue
            items.extend(
                part.strip()
                for part in re.split(r"[；;]", value)
                if part.strip()
            )
        return items if len(items) == 3 else []
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return ""
    value = lines[0]
    for label in (
        _FIELD_LABELS[key],
        "笔记标题" if key == "short_title" else "",
        "一句话记忆版" if key == "memory_sentence" else "",
    ):
        if label:
            value = re.sub(
                rf"^(?:[-*•]|🔸)?\s*{re.escape(label)}\s*[:：]\s*",
                "",
                value,
            )
    return value.strip().strip('"“”')


def _clip(text: str, limit: int, *, question: bool = False) -> str:
    value = (text or "").strip()
    if question:
        value = value.rstrip("。.!！?？；;，,")
        limit = max(1, limit - 1)
    if non_ws_len(value) > limit:
        kept: List[str] = []
        count = 0
        for char in value:
            if not char.isspace():
                if count >= limit:
                    break
                count += 1
            kept.append(char)
        value = "".join(kept).rstrip().rstrip("，,；;：:、-")
    if question:
        value = value.rstrip("。.!！?？") + "？"
    return value


def _clip_field(key: str, value: Any) -> Any:
    target = _SAFE_TARGETS[key]
    if key in {"key_ideas", "analysis_summary"}:
        items = list(value or [])
        if len(items) != 3:
            return []
        return [_clip(item, target // 3) for item in items]
    return _clip(
        str(value or ""), target, question=key == "research_question"
    )


def _repair_field(
    client: Any,
    *,
    key: str,
    current_value: str,
    source_value: str,
    config: Mapping[str, Any],
) -> Any:
    target = min(CARD_FIELD_LIMITS[key], _SAFE_TARGETS[key])
    if key in {"key_ideas", "analysis_summary"}:
        output_rule = (
            f"只输出恰好3行，每行以“🔸”开头；每行不超过{target // 3}字，"
            f"三条合计不超过{target}字。"
        )
        max_tokens = 768
    else:
        output_rule = f"只输出一行字段正文，不带字段名；不超过{target}字。"
        if key == "research_question":
            output_rule += "必须以“？”结尾。"
        max_tokens = 384
    response = client.chat.completions.create(
        model=str(config.get("model") or ""),
        messages=[
            {
                "role": "system",
                "content": (
                    f"你是论文推荐卡片的单字段修复器。本次只修复【{_FIELD_LABELS[key]}】。"
                    "只能从原始字段删减、合并或同义改写，禁止新增事实、数字、比较、因果或评价。"
                    + output_rule
                    + "输出前按去空白字符计数；英文、数字和标点都计入。不要解释。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"<原始字段>\n{source_value}\n</原始字段>\n"
                    f"<待修字段>\n{current_value}\n</待修字段>"
                ),
            },
        ],
        stream=False,
        temperature=0,
        max_tokens=max_tokens,
        **build_thinking_kwargs(dict(config)),
    )
    return _parse_field(
        key,
        require_nonempty_text(
            _choice_text(response), operation=f"eval_targeted_repair_{key}"
        ),
    )


def repair_card_contract(
    client: Any,
    candidate: str,
    *,
    source_draft: str,
    effective_cfg: Mapping[str, Any],
    max_rounds: int = 2,
) -> Tuple[str, int]:
    source_card = parse_card(source_draft)
    working = candidate
    calls = 0
    for _ in range(max(1, max_rounds)):
        card = parse_card(working)
        card.original_title = source_card.original_title
        card.source = source_card.source
        errors = _contract_errors(render_card(card), source_draft)
        if not errors:
            return render_card(card), calls
        repair_keys: set[str] = set()
        unsupported_keys: set[str] = set()
        for error in errors:
            matched = re.match(r"^([a-z_]+)>\d+$", error)
            if matched and matched.group(1) in FIELD_ORDER:
                repair_keys.add(matched.group(1))
            elif error.startswith("missing="):
                repair_keys.update(
                    key
                    for key in error.split("=", 1)[1].split(",")
                    if key in FIELD_ORDER
                )
            elif error.startswith("key_ideas_count="):
                repair_keys.add("key_ideas")
            elif error.startswith("analysis_summary_count="):
                repair_keys.add("analysis_summary")
            elif error == "research_question_not_question":
                repair_keys.add("research_question")
            elif error.startswith("unsupported_numbers="):
                unsupported_keys.update(
                    key
                    for key in error.split("=", 1)[1].split(",")
                    if key in FIELD_ORDER
                )
                repair_keys.update(unsupported_keys)
        for key in FIELD_ORDER:
            if key not in repair_keys:
                continue
            if key in unsupported_keys or not card.field_text(key).strip():
                source_attr = getattr(source_card, key)
                setattr(
                    card,
                    key,
                    list(source_attr) if isinstance(source_attr, list) else source_attr,
                )
            repaired = _repair_field(
                client,
                key=key,
                current_value=card.field_text(key),
                source_value=source_card.field_text(key),
                config=effective_cfg,
            )
            calls += 1
            if repaired:
                setattr(card, key, repaired)
            clipped = _clip_field(key, getattr(card, key))
            if clipped:
                setattr(card, key, clipped)
        working = render_card(card)
    errors = _contract_errors(working, source_draft)
    if errors:
        raise ValueError("targeted repair failed: " + "; ".join(errors))
    return working, calls
