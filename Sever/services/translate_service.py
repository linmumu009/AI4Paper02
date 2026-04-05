"""
Translate MinerU Markdown for user-uploaded papers into Chinese and bilingual MD.

Uses chunked parallel LLM calls (OpenAI-compatible API) to stay within output limits.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

_translate_jobs: set[str] = set()
_translate_lock = threading.Lock()

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

TRANSLATE_SYSTEM_PROMPT = (
    "\u4f60\u662f\u4e00\u4f4d\u4e13\u4e1a\u7684\u5b66\u672f\u8bba\u6587\u7ffb\u8bd1\u4e13\u5bb6\uff0c"
    "\u8d1f\u8d23\u5c06\u82f1\u6587 Markdown \u9010\u6bb5\u7ffb\u8bd1\u4e3a\u4e2d\u6587\u3002\n\n"
    "\u8981\u6c42\uff1a\n"
    "1. \u9010\u6bb5\u7ffb\u8bd1\u6b63\u6587\uff0c\u7981\u6b62\u8bc4\u6790\u539f\u6587\u8d28\u91cf\u3001"
    "\u7981\u6b62\u8f93\u51fa\u201c\u95ee\u9898\u5206\u6790\u201d\u3001\u201c\u4f18\u5316\u5efa\u8bae\u201d\u3001"
    "\u201c\u63a8\u8350\u7248\u672c\u201d\u3001\u201c\u4f7f\u7528\u8bf4\u660e\u201d\u7b49\u5143\u5185\u5bb9\uff0c"
    "\u53ea\u8f93\u51fa\u7ffb\u8bd1\u540e\u7684\u6b63\u6587\u3002\n"
    "2. \u4fdd\u6301 Markdown \u683c\u5f0f\u7ed3\u6784\u4e0d\u53d8\uff0c\u5305\u62ec # \u6807\u9898\u5c42\u7ea7\u3001"
    "**\u52a0\u7c97**\u3001*\u659c\u4f53*\u3001\u5217\u8868\u3001\u8868\u683c\u7b49\u6807\u8bb0\u4e0d\u505a\u4fee\u6539\u3002\n"
    "3. \u4fdd\u7559 ![\u2026](\u2026) \u56fe\u7247\u5f15\u7528\u4e0d\u7ffb\u8bd1\uff0c\u56fe\u7247\u8def\u5f84\u548c URL \u4e0d\u53d8\u3002\n"
    "4. \u4fdd\u7559 $\u2026$\u3001$$\u2026$$\u3001LaTeX \u516c\u5f0f\u53ca\u6570\u5b66\u7b26\u53f7\u4e0d\u7ffb\u8bd1\u4e0d\u4fee\u6539\u3002\n"
    "5. \u4fdd\u7559\u7528 <<<\u2026>>> \u6807\u8bb0\u7684\u5360\u4f4d\u7b26\uff0c\u4e0d\u7ffb\u8bd1\uff0c\u4e0d\u4fee\u6539\u3002\n"
    "6. \u4fdd\u7559\u4e13\u6709\u540d\u8bcd\u3001\u4eba\u540d\u3001URL\u3001\u5f15\u7528\u7f16\u53f7\u3001BibTeX key\uff0c\u4e0d\u7ffb\u8bd1\u4e0d\u4fee\u6539\u3002\n"
    "7. \u4f7f\u7528\u5b66\u672f\u6027\u5f3a\u3001\u51c6\u786e\u6d41\u7545\u7684\u4e2d\u6587\u8868\u8fbe\uff0c\u7b26\u5408\u4e2d\u6587\u5b66\u672f\u8bba\u6587\u98ce\u683c\u3002\n"
    "8. \u53ea\u8f93\u51fa\u7ffb\u8bd1\u540e\u7684 Markdown\uff0c\u4e0d\u8f93\u51fa\u4efb\u4f55\u89e3\u91ca\u3001\u8bf4\u660e\u6216\u539f\u6587\u8bc4\u6790\u3002"
)


def is_translating(paper_id: str) -> bool:
    with _translate_lock:
        return paper_id in _translate_jobs


def _claim(paper_id: str) -> bool:
    with _translate_lock:
        if paper_id in _translate_jobs:
            return False
        _translate_jobs.add(paper_id)
        return True


def _release(paper_id: str) -> None:
    with _translate_lock:
        _translate_jobs.discard(paper_id)


def _protect_code_fences(text: str) -> Tuple[str, List[str]]:
    blocks: List[str] = []

    def _repl(m: re.Match[str]) -> str:
        blocks.append(m.group(0))
        return f"\n<<<{len(blocks) - 1}>>>\n"

    return _CODE_FENCE_RE.sub(_repl, text), blocks


def _restore_placeholders(text: str, blocks: List[str]) -> str:
    out = text
    for i, block in enumerate(blocks):
        out = out.replace(f"<<<{i}>>>", block)
    return out


def _merge_broken_paragraphs(text: str) -> str:
    """
    Lightweight paragraph-join helper used inside _build_bilingual_block for display pairing.

    Merges adjacent paragraph blocks where the first block does not end with sentence-final
    punctuation and the second block does not start like a structural markdown element.
    Structural blocks (headings, list items, tables, images, code fences, hr lines) are
    never used as merge sources.

    For a stronger version that also handles MinerU-specific PDF layout defects, see
    normalize_mineru_source().
    """
    _SENTENCE_END = re.compile(
        r'[.?!:;\)\]"\u2019\u201d\u3002\uff01\uff1f\uff1a\uff1b\u300d\u300f\u3011]\s*$'
    )
    _NEW_BLOCK_START = re.compile(
        r'^(?:#{1,6}\s|[-*+]\s|\d+\.\s|\||\!\[|```|---|\s*$)'
    )
    _PLACEHOLDER = re.compile(r'^<<<\d+>>>\s*$')

    paras = re.split(r'\n\n+', text)
    merged: List[str] = []
    i = 0
    while i < len(paras):
        p = paras[i]
        while (
            i + 1 < len(paras)
            and not _SENTENCE_END.search(p.rstrip())
            and not _NEW_BLOCK_START.match(p.lstrip())
            and not _NEW_BLOCK_START.match(paras[i + 1].lstrip())
            and not _PLACEHOLDER.match(p.strip())
            and not _PLACEHOLDER.match(paras[i + 1].strip())
        ):
            i += 1
            p = p.rstrip() + ' ' + paras[i].lstrip()
        merged.append(p)
        i += 1
    return '\n\n'.join(merged)


def normalize_mineru_source(text: str) -> str:
    """
    Dedicated MinerU source-normalization stage.  Applied once to the raw mineru.md
    content before translation chunking.  Stronger than _merge_broken_paragraphs
    because it handles MinerU/PDF-specific layout defects not covered by the lighter
    display-pairing helper.

    Extra cases handled here vs _merge_broken_paragraphs:

    Case 2 — bracket-label / parenthetical continuation:
      MinerU sometimes splits a hypothesis or enumeration like
          "Hypothesis 2. Knowledge digitization has a positive effect on (a)"
          <blank>
          "novel business model innovation and (b) efficient..."
      The trailing "(a)" ends with ')' which would normally stop the merge.
      However, if the NEXT paragraph starts with a lower-case letter, the ')' is
      clearly a mid-sentence label rather than a real sentence boundary, so we merge.

    All other merge rules (headings safe, structural blocks safe, placeholders safe)
    are identical to _merge_broken_paragraphs.
    """
    _SENTENCE_END = re.compile(
        r'[.?!:;\)\]"\u2019\u201d\u3002\uff01\uff1f\uff1a\uff1b\u300d\u300f\u3011]\s*$'
    )
    # Bracket/paren at end — potential mid-sentence label rather than real sentence end
    _BRACKET_LABEL_END = re.compile(r'[\)\]]\s*$')
    _NEW_BLOCK_START = re.compile(
        r'^(?:#{1,6}\s|[-*+]\s|\d+\.\s|\||\!\[|```|---|\s*$)'
    )
    _PLACEHOLDER = re.compile(r'^<<<\d+>>>\s*$')
    # Continuation paragraph starts with a lower-case letter → definitely a continuation
    _LOWERCASE_CONTINUATION = re.compile(r'^[a-z]')

    paras = re.split(r'\n\n+', text)
    merged: List[str] = []
    i = 0
    while i < len(paras):
        p = paras[i]
        while i + 1 < len(paras):
            next_p = paras[i + 1]

            # Never merge structural blocks (headings, lists, tables, etc.)
            if _NEW_BLOCK_START.match(p.lstrip()) or _PLACEHOLDER.match(p.strip()):
                break
            if _NEW_BLOCK_START.match(next_p.lstrip()) or _PLACEHOLDER.match(next_p.strip()):
                break

            p_rstripped = p.rstrip()
            has_sentence_end = bool(_SENTENCE_END.search(p_rstripped))

            if not has_sentence_end:
                # Case 1: no sentence-final punctuation — standard broken fragment
                i += 1
                p = p_rstripped + ' ' + next_p.lstrip()
                continue

            if (
                _BRACKET_LABEL_END.search(p_rstripped)
                and _LOWERCASE_CONTINUATION.match(next_p.lstrip())
            ):
                # Case 2: ends with bracket/paren label AND continuation is lowercase
                # This catches patterns like "...has a positive effect on (a)\n\nnovel..."
                i += 1
                p = p_rstripped + ' ' + next_p.lstrip()
                continue

            break

        merged.append(p)
        i += 1
    return '\n\n'.join(merged)


def _split_into_chunks(text: str, max_chars: int) -> List[str]:
    if not text.strip():
        return []
    sections = re.split(r"(?m)(?=^#{1,2}\s)", text)
    chunks: List[str] = []
    for sec in sections:
        s = sec
        if not s.strip():
            continue
        if len(s) <= max_chars:
            chunks.append(s)
            continue
        paras = re.split(r"\n\n+", s)
        buf = ""
        for p in paras:
            if not p.strip():
                continue
            sep = "\n\n" if buf else ""
            if len(buf) + len(sep) + len(p) <= max_chars:
                buf = buf + sep + p if buf else p
            else:
                if buf:
                    chunks.append(buf)
                if len(p) <= max_chars:
                    buf = p
                else:
                    for i in range(0, len(p), max_chars):
                        chunks.append(p[i : i + max_chars])
                    buf = ""
        if buf:
            chunks.append(buf)
    if not chunks:
        s = text.strip()
        while s:
            chunks.append(s[:max_chars])
            s = s[max_chars:]
    return chunks


def _resolve_llm_config() -> dict:
    import config.config as cfg

    api_key = (
        (os.environ.get("TRANSLATE_API_KEY") or "").strip()
        or (getattr(cfg, "translate_api_key", None) or "").strip()
        or (os.environ.get("QWEN_API_KEY") or "").strip()
        or (getattr(cfg, "qwen_api_key", None) or "").strip()
    )
    base_url = (getattr(cfg, "translate_base_url", None) or "").strip() or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model = getattr(cfg, "translate_model", None) or "qwen-plus"
    max_tokens = int(getattr(cfg, "translate_max_tokens", 4096) or 4096)
    temperature = float(getattr(cfg, "translate_temperature", 0.3) or 0.3)
    chunk_size = int(getattr(cfg, "translate_chunk_size", 6000) or 6000)
    concurrency = int(getattr(cfg, "translate_concurrency", 8) or 8)
    hard = int(getattr(cfg, "translate_input_hard_limit", 120000) or 120000)
    margin = int(getattr(cfg, "translate_input_safety_margin", 4096) or 4096)
    return {
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "chunk_size": max(500, chunk_size),
        "concurrency": max(1, min(16, concurrency)),
        "input_budget": max(8000, hard - margin),
    }


def _translate_one_chunk(
    index: int,
    chunk: str,
    *,
    client: object,
    model: str,
    max_tokens: int,
    temperature: float,
) -> Tuple[int, str]:
    user_msg = (
        "\u8bf7\u5c06\u4ee5\u4e0b\u82f1\u6587\u5b66\u672f\u8bba\u6587 Markdown "
        "\u9010\u6bb5\u7ffb\u8bd1\u4e3a\u4e2d\u6587\uff0c\u53ea\u8fd4\u56de\u8bd1\u6587\uff1a"
        f"\n\n{chunk}"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": TRANSLATE_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        choice = resp.choices[0].message.content
        text = (choice or "").strip()
        return index, text
    except Exception as exc:
        logger.exception("translate chunk %d failed: %s", index, exc)
        raise


def _split_paragraphs(text: str) -> List[str]:
    """
    Split markdown-ish text into paragraphs (double newlines).

    Special handling:
    - If a block starts with a # heading and continues with body on the next line (single \\n),
      split so the heading is its own paragraph.
    - Very short standalone lines (< 60 chars, non-heading) that are adjacent to other short
      lines are merged with the next paragraph to avoid over-splitting keyword lists, table
      captions, hypothesis labels, etc.  This reduces false "missing translation" reports when
      English and Chinese paragraph counts diverge due to different line-break conventions.
    """
    if not text or not text.strip():
        return []
    raw = re.split(r"\n\n+", text.strip())
    initial: List[str] = []
    for block in raw:
        b = block.strip()
        if not b:
            continue
        lines = b.splitlines()
        if len(lines) > 1 and re.match(r"^#{1,6}\s", lines[0]):
            initial.append(lines[0].strip())
            rest = "\n".join(lines[1:]).strip()
            if rest:
                initial.extend(_split_paragraphs(rest))
        else:
            initial.append(b)

    # Merge short isolated fragments with the following paragraph to reduce over-splitting.
    # A fragment is considered "short" when it has only 1 line and is under 60 characters,
    # and does not look like a standalone heading.
    out: List[str] = []
    i = 0
    while i < len(initial):
        block = initial[i]
        if (
            i + 1 < len(initial)
            and "\n" not in block
            and len(block) < 60
            and not re.match(r"^#{1,6}\s", block)
        ):
            # Merge this short fragment with the next paragraph.
            out.append(block + "\n\n" + initial[i + 1])
            i += 2
        else:
            out.append(block)
            i += 1
    return out


def _quote_block_as_md(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(f"> {line}" if line.strip() else ">" for line in lines) or ">"


def _build_bilingual_block(en: str, zh: str) -> str:
    en_stripped = en.strip()
    zh_stripped = zh.strip()
    if not en_stripped and not zh_stripped:
        return ""

    # If there is no Chinese translation for this chunk at all, show a single missing marker.
    if not zh_stripped:
        quoted_all = _quote_block_as_md(en_stripped)
        return f"{quoted_all}\n\n**[\u8bd1]**\n\n\uff08\u7ffb\u8bd1\u7f3a\u5931\uff09\n\n---\n\n"

    en_paras = _split_paragraphs(_merge_broken_paragraphs(en_stripped))
    zh_paras = _split_paragraphs(_merge_broken_paragraphs(zh_stripped))

    # Any paragraph-count mismatch triggers block-level fallback.
    # Index-by-index pairing is only safe when both sides split into exactly the same number of
    # paragraphs; even a difference of 1 can shift every subsequent translation by one slot,
    # producing the "Chinese under the wrong English paragraph" symptom visible in the output.
    en_n = len(en_paras)
    zh_n = len(zh_paras)
    use_block_fallback = (en_n > 0 and zh_n > 0) and en_n != zh_n

    parts: List[str] = []

    if use_block_fallback:
        # Display the whole English chunk quoted, then the whole Chinese translation once.
        quoted_all = _quote_block_as_md(en_stripped)
        parts.append(quoted_all)
        zh_combined = "\n\n".join(p.strip() for p in zh_paras if p.strip())
        parts.append(f"\n\n**[\u8bd1]**\n\n{zh_combined}\n\n---\n")
    else:
        for i, en_p in enumerate(en_paras):
            quoted = _quote_block_as_md(en_p)
            parts.append(quoted)
            zh_p = zh_paras[i].strip() if i < zh_n else "\uff08\u7ffb\u8bd1\u7f3a\u5931\uff09"
            parts.append(f"\n\n**[\u8bd1]**\n\n{zh_p}\n\n---\n")

        if zh_n > en_n:
            for zh_p in zh_paras[en_n:]:
                parts.append(f"\n**[\u8bd1]**\n\n{zh_p.strip()}\n\n---\n")

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Block-based translation helpers (Method A — canonical blocks from bundle)
# ---------------------------------------------------------------------------

def _group_blocks_into_batches(
    blocks: list,
    max_chars: int,
) -> List[List]:
    """Group translatable CanonicalBlocks into char-bounded batches."""
    batches: List[List] = []
    current: List = []
    current_len = 0
    for blk in blocks:
        if not blk.translatable:
            continue
        text_len = len(blk.render_md)
        if current and current_len + text_len > max_chars:
            batches.append(current)
            current = [blk]
            current_len = text_len
        else:
            current.append(blk)
            current_len += text_len
    if current:
        batches.append(current)
    return batches


def _translate_blocks_batch(
    index: int,
    batch: list,
    *,
    client: object,
    model: str,
    max_tokens: int,
    temperature: float,
) -> Tuple[int, dict]:
    """
    Translate a batch of CanonicalBlocks via LLM.
    Returns (index, {block_id: zh_text}).
    Each block is delimited with [BLOCK:id] so the response can be parsed
    without relying on paragraph counting.
    """
    lines: List[str] = []
    for blk in batch:
        lines.append(f"[BLOCK:{blk.block_id}]")
        lines.append(blk.render_md)
        lines.append("")
    batch_text = "\n".join(lines).strip()

    user_msg = (
        "请将以下各段学术论文 Markdown 翻译为中文。\n"
        "重要：必须保留每段的 [BLOCK:id] 标记（原样输出），"
        "只翻译标记后面的文本内容，保持 Markdown 格式不变：\n\n"
        + batch_text
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": TRANSLATE_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        response_text = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.exception("Block batch %d translation failed: %s", index, exc)
        raise
    return index, _parse_block_response(response_text, batch)


def _parse_block_response(response_text: str, batch: list) -> dict:
    """
    Parse LLM response into {block_id: zh_text}.
    Primary strategy: split on [BLOCK:id] markers.
    Fallback: map response paragraphs to batch order.
    """
    _MARKER = re.compile(r'\[BLOCK:([^\]]+)\]')
    matches = list(_MARKER.finditer(response_text))

    if matches:
        result: dict = {}
        for i, m in enumerate(matches):
            bid = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(response_text)
            zh = response_text[start:end].strip()
            if zh:
                result[bid] = zh
        if result:
            return result

    # Fallback: split by double newlines and map to batch in order
    parts = [p.strip() for p in re.split(r'\n\n+', response_text) if p.strip()]
    fallback: dict = {}
    for i, blk in enumerate(batch):
        if i < len(parts):
            fallback[blk.block_id] = parts[i]
    return fallback


def _assemble_zh_from_blocks(blocks: list, zh_map: dict) -> str:
    """
    Assemble _zh.md: translatable blocks use zh_map value,
    non-translatable blocks use render_md as-is.
    """
    parts: List[str] = []
    for blk in blocks:
        if blk.translatable:
            zh = zh_map.get(blk.block_id, "").strip()
            if zh:
                parts.append(zh)
        else:
            if blk.render_md.strip():
                parts.append(blk.render_md.strip())
    return "\n\n".join(parts)


def _assemble_bilingual_from_blocks(blocks: list, zh_map: dict) -> str:
    """
    Assemble _bilingual.md with deterministic block-id alignment.

    For each translatable block:
        > [English original — blockquoted]
        **[译]**
        [Chinese translation]
        ---

    Non-translatable blocks (image, table, equation) are rendered as-is.
    """
    parts: List[str] = []
    for blk in blocks:
        if blk.type in ("image", "equation"):
            if blk.render_md.strip():
                parts.append(blk.render_md.strip() + "\n\n")
        elif blk.type == "table":
            if blk.render_md.strip():
                parts.append(blk.render_md.strip() + "\n\n")
        elif blk.translatable:
            en_quoted = _quote_block_as_md(blk.render_md)
            zh = zh_map.get(blk.block_id, "").strip()
            if zh:
                parts.append(f"{en_quoted}\n\n**[\u8bd1]**\n\n{zh}\n\n---\n\n")
            else:
                parts.append(
                    f"{en_quoted}\n\n**[\u8bd1]**\n\n\uff08\u7ffb\u8bd1\u7f3a\u5931\uff09\n\n---\n\n"
                )
    return "".join(parts)


def _save_blocks_json(blocks: list, zh_map: dict, path: str) -> None:
    """Save a compact audit record: block_id → source_text + zh_text."""
    import json as _json
    data = [
        {
            "block_id": blk.block_id,
            "page_idx": blk.page_idx,
            "order": blk.order,
            "type": blk.type,
            "translatable": blk.translatable,
            "source_text": blk.source_text,
            "zh_text": zh_map.get(blk.block_id, ""),
        }
        for blk in blocks
    ]
    try:
        Path(path).write_text(
            _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("Failed to save blocks JSON to %s: %s", path, exc)


def _safe_progress(fn, paper_id: str, pct: int) -> None:
    try:
        fn(paper_id, pct)
    except Exception as exc:
        logger.warning("set_translate_progress failed: %s", exc)


def _run_block_translation(
    blocks: list,
    cfg: dict,
    client: object,
    progress_cb,
) -> dict:
    """
    Translate canonical blocks in parallel.
    Returns merged {block_id: zh_text} map.
    """
    batches = _group_blocks_into_batches(blocks, cfg["chunk_size"])
    if not batches:
        return {}

    n_total = len(batches)
    batch_results: List[dict | None] = [None] * n_total
    prog_lock = threading.Lock()
    done_count = [0]

    def _bump() -> None:
        with prog_lock:
            done_count[0] += 1
            d = done_count[0]
        pct = min(99, int(100 * d / n_total)) if n_total else 0
        progress_cb(pct)

    n_workers = min(cfg["concurrency"], n_total)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = {
            pool.submit(
                _translate_blocks_batch,
                i, batch,
                client=client,
                model=cfg["model"],
                max_tokens=cfg["max_tokens"],
                temperature=cfg["temperature"],
            ): i
            for i, batch in enumerate(batches)
        }
        for fut in as_completed(futs):
            submit_idx = futs[fut]
            try:
                idx, partial = fut.result()
                batch_results[idx] = partial
                _bump()
            except Exception as exc:
                raise RuntimeError(
                    f"\u5757\u7ffb\u8bd1\u5931\u8d25\uff08\u6279\u6b21 {submit_idx}\uff09: {exc}"
                ) from exc

    zh_map: dict = {}
    for d in batch_results:
        if d:
            zh_map.update(d)
    return zh_map


def _run_chunk_translation(
    chunks: List[str],
    cfg: dict,
    client: object,
    global_fences: List[str],
    progress_cb,
) -> List[str]:
    """
    Legacy chunk-based translation (fallback when no bundle is available).
    Returns list of translated strings in the same order as chunks.
    """
    n_total = len(chunks)
    results: List[str | None] = [None] * n_total
    prog_lock = threading.Lock()
    done_count = [0]

    def _bump() -> None:
        with prog_lock:
            done_count[0] += 1
            d = done_count[0]
        pct = min(99, int(100 * d / n_total)) if n_total else 0
        progress_cb(pct)

    n_workers = min(cfg["concurrency"], n_total)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = {
            pool.submit(
                _translate_one_chunk,
                i, ch,
                client=client,
                model=cfg["model"],
                max_tokens=cfg["max_tokens"],
                temperature=cfg["temperature"],
            ): i
            for i, ch in enumerate(chunks)
        }
        for fut in as_completed(futs):
            submit_idx = futs[fut]
            try:
                i2, translated = fut.result()
                results[i2] = _restore_placeholders(translated, global_fences)
                _bump()
            except Exception as exc:
                raise RuntimeError(
                    f"\u5206\u5757\u7ffb\u8bd1\u5931\u8d25\uff08\u5757 {submit_idx}\uff09: {exc}"
                ) from exc
    return [r or "" for r in results]


# ---------------------------------------------------------------------------
# Main translation entry points
# ---------------------------------------------------------------------------

def run_translation(user_id: int, paper_id: str) -> None:
    """Synchronous full translation run (invoke from background thread)."""
    from openai import OpenAI

    import services.user_paper_service as svc

    try:
        cfg = _resolve_llm_config()
        if not cfg["api_key"]:
            svc.set_translate_status(
                paper_id,
                status="failed",
                error="\u672a\u914d\u7f6e\u7ffb\u8bd1 API Key\uff08translate_api_key \u6216 TRANSLATE_API_KEY / QWEN_API_KEY\uff09",
                finished=True,
                progress=0,
            )
            return

        paper = svc.get_paper(user_id, paper_id)
        if not paper:
            logger.error("translate: paper %s not found for user %s", paper_id, user_id)
            svc.set_translate_status(
                paper_id,
                status="failed",
                error="\u8bba\u6587\u4e0d\u5b58\u5728",
                finished=True,
                progress=0,
            )
            return

        mineru_path = os.path.join(
            svc._USER_PAPERS_DIR, str(user_id), paper_id, f"{paper_id}_mineru.md"
        )
        out_dir = os.path.dirname(mineru_path)
        zh_path = os.path.join(out_dir, f"{paper_id}_zh.md")
        bi_path = os.path.join(out_dir, f"{paper_id}_bilingual.md")
        blocks_path = os.path.join(out_dir, f"{paper_id}_blocks.json")
        bundle_dir = os.path.join(out_dir, "mineru_bundle")

        if not os.path.isfile(mineru_path):
            raise FileNotFoundError("\u672a\u627e\u5230 MinerU \u89e3\u6790\u6587\u4ef6\uff0c\u8bf7\u5148\u5b8c\u6210\u8bba\u6587\u5904\u7406\uff08\u751f\u6210 _mineru.md\uff09")

        svc.set_translate_status(paper_id, status="processing", error="", started=True)
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        progress_cb = lambda pct: _safe_progress(svc.set_translate_progress, paper_id, pct)

        # ---- Method A: block-based (preferred when bundle exists) ----
        from services.mineru_blocks_service import load_canonical_blocks
        from services.mineru_normalize_service import _merge_adjacent_paragraphs
        blocks = load_canonical_blocks(bundle_dir) if os.path.isdir(bundle_dir) else None
        # Fall back if bundle has no translatable content
        if blocks is not None and not any(b.translatable for b in blocks):
            logger.warning("No translatable blocks in bundle for %s, using chunk fallback", paper_id)
            blocks = None

        if blocks is not None:
            # Apply paragraph merge so translated text is based on normalized blocks
            blocks = _merge_adjacent_paragraphs(blocks)
            logger.info("Using block-based translation for %s (%d blocks after merge)", paper_id, len(blocks))
            zh_map = _run_block_translation(blocks, cfg, client, progress_cb)
            _save_blocks_json(blocks, zh_map, blocks_path)
            zh_full = _assemble_zh_from_blocks(blocks, zh_map)
            bi_full = _assemble_bilingual_from_blocks(blocks, zh_map)
        else:
            # ---- Method B: legacy chunk-based fallback ----
            norm_md_path = os.path.join(out_dir, f"{paper_id}_mineru_normalized.md")
            if os.path.isfile(norm_md_path):
                logger.info("Using chunk-based translation for %s (normalized md)", paper_id)
                raw = Path(norm_md_path).read_text(encoding="utf-8")
            else:
                logger.info("Using chunk-based translation for %s (no usable bundle)", paper_id)
                raw = Path(mineru_path).read_text(encoding="utf-8")
                raw = normalize_mineru_source(raw)
            if len(raw) > cfg["input_budget"]:
                raw = raw[: cfg["input_budget"]]
                logger.warning("MinerU text truncated to %d chars", cfg["input_budget"])
            protected, global_fences = _protect_code_fences(raw)
            chunks = _split_into_chunks(protected, cfg["chunk_size"])
            if not chunks:
                raise ValueError("\u6ca1\u6709\u53ef\u7ffb\u8bd1\u7684\u5185\u5bb9")
            translated = _run_chunk_translation(chunks, cfg, client, global_fences, progress_cb)
            zh_parts: List[str] = []
            bi_parts: List[str] = []
            for orig, zh in zip(chunks, translated):
                orig_display = _restore_placeholders(orig, global_fences)
                zh_parts.append(zh)
                bi_parts.append(_build_bilingual_block(orig_display, zh))
            zh_full = "\n\n".join(p.strip() for p in zh_parts if p.strip())
            bi_full = "".join(bi_parts)

        Path(zh_path).write_text(zh_full, encoding="utf-8")
        Path(bi_path).write_text(bi_full, encoding="utf-8")

        svc.set_translate_status(
            paper_id, status="completed", error="", finished=True, progress=100
        )
        logger.info("Translation completed for %s", paper_id)
    except Exception as exc:
        logger.exception("Translation failed for %s: %s", paper_id, exc)
        try:
            import services.user_paper_service as svc2

            svc2.set_translate_status(
                paper_id,
                status="failed",
                error=str(exc)[:500],
                finished=True,
                progress=0,
            )
        except Exception:
            pass
    finally:
        _release(paper_id)


def start_translation(user_id: int, paper_id: str) -> Tuple[bool, str]:
    """
    Start translation in a daemon thread.
    Returns (ok, message).
    """
    import services.user_paper_service as svc

    paper = svc.get_paper(user_id, paper_id)
    if not paper:
        return False, "\u8bba\u6587\u4e0d\u5b58\u5728"

    if not _claim(paper_id):
        return False, "\u7ffb\u8bd1\u5df2\u5728\u8fdb\u884c\u4e2d"

    t = threading.Thread(
        target=run_translation,
        args=(user_id, paper_id),
        daemon=True,
        name=f"user-paper-translate-{paper_id}",
    )
    t.start()
    return True, "\u7ffb\u8bd1\u5df2\u542f\u52a8"


def paper_derivative_paths(user_id: int, paper_id: str) -> dict[str, str]:
    """Absolute paths for mineru / mineru_normalized / zh / bilingual markdown files."""
    import services.user_paper_service as svc

    base = os.path.join(svc._USER_PAPERS_DIR, str(user_id), paper_id)
    return {
        "mineru": os.path.join(base, f"{paper_id}_mineru.md"),
        "mineru_normalized": os.path.join(base, f"{paper_id}_mineru_normalized.md"),
        "zh": os.path.join(base, f"{paper_id}_zh.md"),
        "bilingual": os.path.join(base, f"{paper_id}_bilingual.md"),
    }


def kb_paper_derivative_paths(user_id: int, paper_id: str) -> dict[str, str]:
    """Absolute paths for KB paper mineru / mineru_normalized / zh / bilingual markdown files.
    KB papers store derivatives alongside the PDF in kb_files/{user_id}/{paper_id}/.
    """
    import services.kb_service as kbs

    base = os.path.join(kbs._KB_FILES_DIR, str(user_id), paper_id)
    return {
        "mineru": os.path.join(base, f"{paper_id}_mineru.md"),
        "mineru_normalized": os.path.join(base, f"{paper_id}_mineru_normalized.md"),
        "zh": os.path.join(base, f"{paper_id}_zh.md"),
        "bilingual": os.path.join(base, f"{paper_id}_bilingual.md"),
    }


def delete_derivative(user_id: int, paper_id: str, derivative_type: str) -> Tuple[bool, str]:
    """Remove a generated derivative file on disk. ``derivative_type``: mineru | zh | bilingual."""
    import services.user_paper_service as svc

    derivative_type = derivative_type.lower().strip()
    if derivative_type not in ("mineru", "zh", "bilingual"):
        return False, "invalid derivative type"

    if svc.get_paper(user_id, paper_id) is None:
        return False, "\u8bba\u6587\u4e0d\u5b58\u5728"

    paths = paper_derivative_paths(user_id, paper_id)
    base_dir = os.path.dirname(paths["mineru"])

    try:
        if derivative_type == "mineru":
            p = paths["mineru"]
            if os.path.isfile(p):
                os.remove(p)
            bundle = os.path.join(base_dir, "mineru_bundle")
            if os.path.isdir(bundle):
                shutil.rmtree(bundle, ignore_errors=True)
        else:
            p = paths[derivative_type]
            if os.path.isfile(p):
                os.remove(p)
            # Also remove the blocks audit file when clearing translation outputs
            if derivative_type == "zh":
                blocks_p = os.path.join(base_dir, f"{paper_id}_blocks.json")
                if os.path.isfile(blocks_p):
                    os.remove(blocks_p)
            zh_ok = os.path.isfile(paths["zh"])
            bi_ok = os.path.isfile(paths["bilingual"])
            if not zh_ok and not bi_ok:
                svc.set_translate_status(paper_id, status="none", error="", progress=0)
    except OSError as exc:
        logger.warning("delete_derivative failed: %s", exc)
        return False, str(exc)

    return True, "ok"


def run_kb_translation(user_id: int, paper_id: str, scope: str = "kb") -> None:
    """Synchronous full translation run for KB paper (invoke from background thread)."""
    from openai import OpenAI
    import services.kb_service as kbs

    try:
        cfg = _resolve_llm_config()
        if not cfg["api_key"]:
            kbs.set_kb_paper_translate_status(
                user_id, paper_id,
                status="failed",
                error="\u672a\u914d\u7f6e\u7ffb\u8bd1 API Key",
                scope=scope,
            )
            return

        paper = kbs.get_kb_paper(user_id, paper_id, scope=scope)
        if not paper:
            kbs.set_kb_paper_translate_status(
                user_id, paper_id, status="failed", error="\u8bba\u6587\u4e0d\u5b58\u5728", scope=scope
            )
            return

        paths = kb_paper_derivative_paths(user_id, paper_id)
        mineru_path = paths["mineru"]
        zh_path = paths["zh"]
        bi_path = paths["bilingual"]
        blocks_path = os.path.join(os.path.dirname(mineru_path), f"{paper_id}_blocks.json")
        bundle_dir = os.path.join(os.path.dirname(mineru_path), "mineru_bundle")

        if not os.path.isfile(mineru_path):
            raise FileNotFoundError("\u672a\u627e\u5230 MinerU \u89e3\u6790\u6587\u4ef6\uff0c\u8bf7\u5148\u5b8c\u6210\u8bba\u6587\u5904\u7406\uff08\u751f\u6210 _mineru.md\uff09")

        kbs.set_kb_paper_translate_status(
            user_id, paper_id, status="processing", error="", progress=0, scope=scope
        )
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

        def _kb_progress(pct: int) -> None:
            try:
                kbs.set_kb_paper_translate_progress(user_id, paper_id, pct, scope=scope)
            except Exception as pe:
                logger.warning("set_kb_paper_translate_progress failed: %s", pe)

        # ---- Method A: block-based ----
        from services.mineru_blocks_service import load_canonical_blocks
        from services.mineru_normalize_service import _merge_adjacent_paragraphs
        blocks = load_canonical_blocks(bundle_dir) if os.path.isdir(bundle_dir) else None
        if blocks is not None and not any(b.translatable for b in blocks):
            logger.warning("No translatable blocks in bundle for %s, using chunk fallback", paper_id)
            blocks = None

        if blocks is not None:
            # Apply paragraph merge so translated text is based on normalized blocks
            blocks = _merge_adjacent_paragraphs(blocks)
            logger.info("Using block-based translation for KB %s (%d blocks after merge)", paper_id, len(blocks))
            zh_map = _run_block_translation(blocks, cfg, client, _kb_progress)
            _save_blocks_json(blocks, zh_map, blocks_path)
            zh_full = _assemble_zh_from_blocks(blocks, zh_map)
            bi_full = _assemble_bilingual_from_blocks(blocks, zh_map)
        else:
            # ---- Method B: legacy chunk-based fallback ----
            kb_paper_dir = os.path.dirname(mineru_path)
            norm_md_path = os.path.join(kb_paper_dir, f"{paper_id}_mineru_normalized.md")
            if os.path.isfile(norm_md_path):
                logger.info("Using chunk-based translation for KB %s (normalized md)", paper_id)
                raw = Path(norm_md_path).read_text(encoding="utf-8")
            else:
                logger.info("Using chunk-based translation for KB %s (no usable bundle)", paper_id)
                raw = Path(mineru_path).read_text(encoding="utf-8")
                raw = normalize_mineru_source(raw)
            if len(raw) > cfg["input_budget"]:
                raw = raw[: cfg["input_budget"]]
            protected, global_fences = _protect_code_fences(raw)
            chunks = _split_into_chunks(protected, cfg["chunk_size"])
            if not chunks:
                raise ValueError("\u6ca1\u6709\u53ef\u7ffb\u8bd1\u7684\u5185\u5bb9")
            translated = _run_chunk_translation(chunks, cfg, client, global_fences, _kb_progress)
            zh_parts: List[str] = []
            bi_parts: List[str] = []
            for orig, zh in zip(chunks, translated):
                orig_display = _restore_placeholders(orig, global_fences)
                zh_parts.append(zh)
                bi_parts.append(_build_bilingual_block(orig_display, zh))
            zh_full = "\n\n".join(p.strip() for p in zh_parts if p.strip())
            bi_full = "".join(bi_parts)

        os.makedirs(os.path.dirname(zh_path), exist_ok=True)
        Path(zh_path).write_text(zh_full, encoding="utf-8")
        Path(bi_path).write_text(bi_full, encoding="utf-8")

        kbs.set_kb_paper_translate_status(
            user_id, paper_id, status="completed", error="", progress=100, scope=scope
        )
        logger.info("KB translation completed for %s", paper_id)
    except Exception as exc:
        logger.exception("KB translation failed for %s: %s", paper_id, exc)
        try:
            import services.kb_service as kbs2
            kbs2.set_kb_paper_translate_status(
                user_id, paper_id,
                status="failed",
                error=str(exc)[:500],
                scope=scope,
            )
        except Exception:
            pass
    finally:
        _release(paper_id)


def start_kb_translation(user_id: int, paper_id: str, scope: str = "kb") -> Tuple[bool, str]:
    """Start KB paper translation in a daemon thread. Returns (ok, message)."""
    import services.kb_service as kbs

    paper = kbs.get_kb_paper(user_id, paper_id, scope=scope)
    if not paper:
        return False, "\u8bba\u6587\u4e0d\u5b58\u5728"

    if not _claim(paper_id):
        return False, "\u7ffb\u8bd1\u5df2\u5728\u8fdb\u884c\u4e2d"

    t = threading.Thread(
        target=run_kb_translation,
        args=(user_id, paper_id, scope),
        daemon=True,
        name=f"kb-paper-translate-{paper_id}",
    )
    t.start()
    return True, "\u7ffb\u8bd1\u5df2\u542f\u52a8"


def delete_kb_derivative(
    user_id: int, paper_id: str, derivative_type: str, scope: str = "kb"
) -> Tuple[bool, str]:
    """Remove a generated derivative file for a KB paper. derivative_type: mineru | zh | bilingual."""
    import services.kb_service as kbs

    derivative_type = derivative_type.lower().strip()
    if derivative_type not in ("mineru", "zh", "bilingual"):
        return False, "invalid derivative type"

    if kbs.get_kb_paper(user_id, paper_id, scope=scope) is None:
        return False, "\u8bba\u6587\u4e0d\u5b58\u5728"

    paths = kb_paper_derivative_paths(user_id, paper_id)
    base_dir = os.path.dirname(paths["mineru"])

    try:
        if derivative_type == "mineru":
            p = paths["mineru"]
            if os.path.isfile(p):
                os.remove(p)
            bundle = os.path.join(base_dir, "mineru_bundle")
            if os.path.isdir(bundle):
                shutil.rmtree(bundle, ignore_errors=True)
            kbs.set_kb_paper_process_status(
                user_id, paper_id, status="none", step="", error="", scope=scope
            )
        else:
            p = paths[derivative_type]
            if os.path.isfile(p):
                os.remove(p)
            if derivative_type == "zh":
                blocks_p = os.path.join(base_dir, f"{paper_id}_blocks.json")
                if os.path.isfile(blocks_p):
                    os.remove(blocks_p)
            zh_ok = os.path.isfile(paths["zh"])
            bi_ok = os.path.isfile(paths["bilingual"])
            if not zh_ok and not bi_ok:
                kbs.set_kb_paper_translate_status(
                    user_id, paper_id, status="none", error="", progress=0, scope=scope
                )
    except OSError as exc:
        logger.warning("delete_kb_derivative failed: %s", exc)
        return False, str(exc)

    return True, "ok"
