"""
mineru_normalize_service.py

Rebuild a clean, reader-friendly Markdown from a MinerU bundle directory.

Uses content_list_v2.json (or *_content_list.json) as the ground truth, then
applies conservative paragraph-merging rules to fix PDF hard-line-breaks so the
output reads like a proper academic paper instead of a raw layout dump.

Public API
----------
build_normalized_markdown(bundle_dir, img_prefix) -> Optional[str]
    Returns the normalized Markdown string, or None when no content_list is found.
"""

from __future__ import annotations

import re
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regexes used for merge-decision logic
# ---------------------------------------------------------------------------

# A paragraph "closes" a sentence when it ends with one of these characters.
# If it does NOT end this way, it might be a hard-wrapped continuation.
_SENTENCE_END_RE = re.compile(
    r'[.?!;…\u2019\u201d\u3002\uff01\uff1f\uff1b\u300d\u300f\u3011]\s*$'
)

# Some paragraphs end with a bracket label like "(a)", "(b)", "[1]" and the
# text continues on the next block with lowercase — still the same sentence.
_BRACKET_END_RE = re.compile(r'[\)\]]\s*$')

# The next block starts a continuation when its first non-space character is
# a lower-case ASCII letter.
_LOWERCASE_START_RE = re.compile(r'^\s*[a-z]')

# Hyphenated word split across a line — strip the hyphen when joining.
_TRAILING_HYPHEN_RE = re.compile(r'-\s*$')


# ---------------------------------------------------------------------------
# Merge decision
# ---------------------------------------------------------------------------

def _should_merge_paragraphs(cur_text: str, nxt_text: str) -> bool:
    """
    Return True when two adjacent paragraph-block texts belong to the same
    logical paragraph and should be joined with a single space.

    Rules (conservative — false-negatives are safer than false-positives):

    1. Hard-wrap continuation: current text does NOT end with sentence-final
       punctuation AND next text starts with a lower-case letter.
       → typical PDF column / margin wrap.

    2. Bracket-label continuation: current text ends with ) or ] (e.g. "(a)")
       AND next text starts with a lower-case letter.
       → "Hypothesis 1 (a)" … "novel business model…"

    3. Hyphenated split: current text ends with "-" (hyphen at line end).
       → de-hyphenate and join unconditionally.
    """
    if not cur_text or not nxt_text:
        return False

    cur = cur_text.rstrip()
    nxt = nxt_text.lstrip()

    # Rule 3 — hyphenated word split (always merge, remove hyphen)
    if _TRAILING_HYPHEN_RE.search(cur):
        return True

    has_sentence_end = bool(_SENTENCE_END_RE.search(cur))

    # Rule 1
    if not has_sentence_end and bool(_LOWERCASE_START_RE.match(nxt)):
        return True

    # Rule 2
    if bool(_BRACKET_END_RE.search(cur)) and bool(_LOWERCASE_START_RE.match(nxt)):
        return True

    return False


# ---------------------------------------------------------------------------
# Paragraph merge pass
# ---------------------------------------------------------------------------

def _merge_adjacent_paragraphs(blocks: list) -> list:
    """
    Walk the block list and greedily merge adjacent paragraph blocks that pass
    _should_merge_paragraphs.  All other block types act as hard barriers — no
    merge crosses a title, list, image, table, equation, or caption boundary.

    Returns a new list; input is not mutated.
    """
    try:
        from services.mineru_blocks_service import CanonicalBlock
    except ImportError:
        from mineru_blocks_service import CanonicalBlock

    result: list = []
    i = 0
    while i < len(blocks):
        blk = blocks[i]

        if blk.type != "paragraph":
            result.append(blk)
            i += 1
            continue

        # Accumulate continuations
        cur_text = blk.source_text
        cur_render = blk.render_md

        while i + 1 < len(blocks):
            nxt = blocks[i + 1]
            if nxt.type != "paragraph":
                break
            if not _should_merge_paragraphs(cur_text, nxt.source_text):
                break

            # Join — handle trailing hyphen (de-hyphenate) vs. normal space
            sep = "" if _TRAILING_HYPHEN_RE.search(cur_text.rstrip()) else " "
            cur_text = _TRAILING_HYPHEN_RE.sub("", cur_text.rstrip()) + sep + nxt.source_text.lstrip()
            cur_render = _TRAILING_HYPHEN_RE.sub("", cur_render.rstrip()) + sep + nxt.render_md.lstrip()
            i += 1

        # Emit (possibly merged) paragraph block
        if cur_text != blk.source_text or cur_render != blk.render_md:
            merged = CanonicalBlock(
                block_id=blk.block_id,
                page_idx=blk.page_idx,
                order=blk.order,
                type="paragraph",
                source_text=cur_text,
                render_md=cur_render,
                translatable=blk.translatable,
                level=blk.level,
                bbox=blk.bbox,
            )
            result.append(merged)
        else:
            result.append(blk)

        i += 1

    return result


# ---------------------------------------------------------------------------
# Single-block renderer
# ---------------------------------------------------------------------------

def _render_block(blk) -> str:
    """
    Convert a single CanonicalBlock to its Markdown string.
    Returns an empty string for blocks that should be skipped.
    """
    btype = blk.type

    if btype == "title":
        return blk.render_md  # already "## Section Title"

    elif btype == "paragraph":
        # Sanitise any residual internal newlines (can appear in flat-format blocks)
        text = re.sub(r'\n+', ' ', blk.render_md).strip()
        return text

    elif btype == "list":
        return blk.render_md  # already "- item\n- item"

    elif btype == "image":
        return blk.render_md if blk.render_md else ""

    elif btype == "table":
        md = blk.render_md
        if not md or md == "(table)":
            return ""
        return md

    elif btype == "equation":
        md = blk.render_md
        if not md or md == "(equation)":
            return ""
        return md

    elif btype == "caption":
        text = blk.source_text.strip()
        if not text:
            return ""
        # Light italic hint to distinguish from body text; plain fallback if renderer strips it
        return f"*{text}*"

    return ""


# ---------------------------------------------------------------------------
# Full render pass
# ---------------------------------------------------------------------------

def _render_blocks_to_markdown(blocks: list) -> str:
    """
    Render the final (post-merge) block list to a clean Markdown string.
    Consecutive non-empty rendered parts are joined with a blank line.
    """
    parts: List[str] = []
    for blk in blocks:
        rendered = _render_block(blk)
        if rendered and rendered.strip():
            parts.append(rendered)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_normalized_markdown(
    bundle_dir: str,
    img_prefix: str = "mineru_bundle",
) -> Optional[str]:
    """
    Build a normalized Markdown string from a MinerU bundle directory.

    Steps:
      1. Load CanonicalBlocks via mineru_blocks_service (v2 → flat fallback).
      2. Apply conservative paragraph-merge rules.
      3. Render to clean Markdown.

    Returns None when no content_list JSON is found in bundle_dir.
    img_prefix is prepended to relative image paths (pass "" to keep as-is).
    """
    try:
        from services.mineru_blocks_service import load_canonical_blocks
    except ImportError:
        from mineru_blocks_service import load_canonical_blocks

    blocks = load_canonical_blocks(bundle_dir, img_prefix=img_prefix)
    if not blocks:
        logger.warning("build_normalized_markdown: no blocks found in %s", bundle_dir)
        return None

    logger.info(
        "build_normalized_markdown: %d raw blocks from %s", len(blocks), bundle_dir
    )

    merged = _merge_adjacent_paragraphs(blocks)

    logger.info(
        "build_normalized_markdown: %d blocks after paragraph merge (was %d)",
        len(merged), len(blocks),
    )

    md = _render_blocks_to_markdown(merged)
    return md if md.strip() else None
