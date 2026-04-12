"""Shared LLM utility helpers used by compare_service, research_service, etc."""

from __future__ import annotations

import re as _re


def approx_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English text.

    Chinese characters are roughly 1 token each; English words are roughly
    1.3 tokens each (sub-word tokenisation).  This is more accurate than a
    flat character-count heuristic for the mixed-language content typical in
    this application.
    """
    if not text:
        return 0
    zh_chars = len(_re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
    en_words = len(text.split()) - zh_chars // 2
    return zh_chars + max(0, int(en_words * 1.3))


def crop(text: str, budget: int) -> str:
    """Crop *text* so that approx_tokens(result) <= budget.

    Falls back to a conservative character-based slice when the token estimate
    would still exceed the budget after cropping (edge case for very short texts).
    """
    if approx_tokens(text) <= budget:
        return text
    char_limit = max(0, int(budget * 1.5))
    cropped = text[:char_limit]
    while cropped and approx_tokens(cropped) > budget:
        cropped = cropped[: int(len(cropped) * 0.9)]
    return cropped
