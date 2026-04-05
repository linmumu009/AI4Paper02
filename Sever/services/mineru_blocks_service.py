"""
mineru_blocks_service.py

Extract canonical content blocks from a MinerU bundle directory.
Provides deterministic block-level alignment for bilingual assembly.

Supported sources (in priority order):
  1. content_list_v2.json  — nested by page, rich structured content
  2. *_content_list.json   — flat list with page_idx field
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Block types that should be completely ignored
_SKIP_TYPES = frozenset({
    "page_header", "header", "page_footer", "footer",
    "page_number", "page_footnote", "footnote",
})


@dataclass
class CanonicalBlock:
    block_id: str       # e.g. "p0_b3"  — stable within a single bundle
    page_idx: int
    order: int          # global insertion order (for bilingual assembly)
    type: str           # title / paragraph / list / image / table / equation / caption
    source_text: str    # plain-ish text suitable for LLM translation
    render_md: str      # markdown representation used for display
    translatable: bool  # whether this block should be sent to LLM
    level: int = 0      # heading level (title blocks only)
    bbox: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Span-level text extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_spans(spans: object) -> str:
    """Flatten a list of content-span dicts into a markdown-ready string."""
    if not isinstance(spans, list):
        return str(spans).strip() if spans else ""
    parts: list[str] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        t = span.get("type", "")
        content = span.get("content", "")
        if t == "text":
            parts.append(str(content))
        elif t in ("equation_inline", "inline_equation"):
            # Preserve inline LaTeX as $…$
            parts.append(f"${content}$")
        # image / unknown span types → skip
    return "".join(parts).strip()


def _extract_list_items(list_items: list) -> Tuple[str, str]:
    """Return (source_text, render_md) for a list block."""
    plain: list[str] = []
    md: list[str] = []
    for item in list_items:
        if not isinstance(item, dict):
            continue
        item_content = item.get("item_content", [])
        text = _extract_text_spans(item_content)
        if text:
            plain.append(text)
            md.append(f"- {text}")
    return "\n".join(plain), "\n".join(md)


def _extract_caption_items(items: object) -> str:
    """
    Extract text from a caption/footnote field.
    MinerU stores these as either:
      - a list of span dicts (same as paragraph_content)
      - a list of content containers  [{content: [span, …]}, …]
    """
    if not items or not isinstance(items, list):
        return ""
    # If first element looks like a span dict, use span extractor directly
    if items and isinstance(items[0], dict) and "type" in items[0]:
        return _extract_text_spans(items)
    # Otherwise assume list of content containers
    parts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            inner = item.get("content", [])
            if isinstance(inner, list):
                parts.append(_extract_text_spans(inner))
            elif isinstance(inner, str):
                parts.append(inner.strip())
    return " ".join(p for p in parts if p).strip()


# ---------------------------------------------------------------------------
# content_list_v2.json  (nested: outer list = pages, inner list = blocks)
# ---------------------------------------------------------------------------

def _iter_v2(raw: list) -> Iterator[Tuple[int, dict]]:
    for page_idx, page in enumerate(raw):
        if not isinstance(page, list):
            continue
        for blk in page:
            if isinstance(blk, dict):
                yield page_idx, blk


def _parse_v2_block(
    page_idx: int, blk: dict, order: int, img_prefix: str
) -> List[CanonicalBlock]:
    btype = blk.get("type", "").lower()
    bbox = blk.get("bbox", [])
    content = blk.get("content") or {}
    bid = f"p{page_idx}_b{order}"

    if btype in _SKIP_TYPES:
        return []

    results: List[CanonicalBlock] = []

    if btype == "title":
        title_spans = content.get("title_content", [])
        level = int(content.get("level", 1))
        text = _extract_text_spans(title_spans)
        if not text:
            return results
        hashes = "#" * min(max(level, 1), 6)
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="title", source_text=text, render_md=f"{hashes} {text}",
            translatable=True, level=level, bbox=bbox,
        ))

    elif btype in ("paragraph", "text"):
        para_spans = content.get("paragraph_content",
                     content.get("text_content", []))
        if isinstance(para_spans, str):
            text = para_spans.strip()
        else:
            text = _extract_text_spans(para_spans)
        if not text:
            return results
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="paragraph", source_text=text, render_md=text,
            translatable=True, bbox=bbox,
        ))

    elif btype == "list":
        list_items = content.get("list_items", [])
        source_text, render_md = _extract_list_items(list_items)
        if not render_md:
            return results
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="list", source_text=source_text, render_md=render_md,
            translatable=True, bbox=bbox,
        ))

    elif btype == "image":
        img_path = (content.get("image_source") or {}).get("path", "")
        if img_path and img_prefix:
            img_path = img_prefix.rstrip("/") + "/" + img_path.lstrip("/")
        render_md = f"![]({img_path})" if img_path else ""
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="image", source_text="", render_md=render_md,
            translatable=False, bbox=bbox,
        ))
        # Image caption → separate translatable block
        cap = _extract_caption_items(content.get("image_caption", []))
        if cap:
            results.append(CanonicalBlock(
                block_id=f"{bid}_cap", page_idx=page_idx, order=order,
                type="caption", source_text=cap, render_md=cap,
                translatable=True, bbox=bbox,
            ))

    elif btype == "table":
        html = (content.get("html") or "").strip()
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="table", source_text="", render_md=html or "(table)",
            translatable=False, bbox=bbox,
        ))
        # Table caption
        cap = _extract_caption_items(content.get("table_caption", []))
        if cap:
            results.append(CanonicalBlock(
                block_id=f"{bid}_cap", page_idx=page_idx, order=order,
                type="caption", source_text=cap, render_md=cap,
                translatable=True, bbox=bbox,
            ))
        # Table footnote
        fn = _extract_caption_items(content.get("table_footnote", []))
        if fn:
            results.append(CanonicalBlock(
                block_id=f"{bid}_fn", page_idx=page_idx, order=order,
                type="caption", source_text=fn, render_md=fn,
                translatable=True, bbox=bbox,
            ))

    elif btype in ("equation", "formula", "block_equation"):
        eq: str = ""
        if isinstance(content, str):
            eq = content
        elif isinstance(content, dict):
            eq = str(
                content.get("content")
                or content.get("equation_content")
                or ""
            )
        render_md = f"$${eq}$$" if eq else "(equation)"
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="equation", source_text="", render_md=render_md,
            translatable=False, bbox=bbox,
        ))

    else:
        # Unknown type: try to extract plain text and treat as paragraph
        text = ""
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, dict):
            for key in ("text", "paragraph_content", "title_content", "content"):
                val = content.get(key)
                if isinstance(val, str) and val.strip():
                    text = val.strip()
                    break
                elif isinstance(val, list):
                    text = _extract_text_spans(val)
                    if text:
                        break
        if text:
            results.append(CanonicalBlock(
                block_id=bid, page_idx=page_idx, order=order,
                type="paragraph", source_text=text, render_md=text,
                translatable=True, bbox=bbox,
            ))

    return results


# ---------------------------------------------------------------------------
# Flat content_list.json  (flat list with page_idx per block)
# ---------------------------------------------------------------------------

def _iter_flat(raw: list) -> Iterator[Tuple[int, dict]]:
    for blk in raw:
        if isinstance(blk, dict):
            yield int(blk.get("page_idx", 0)), blk


def _parse_flat_block(
    page_idx: int, blk: dict, order: int, img_prefix: str
) -> List[CanonicalBlock]:
    btype = blk.get("type", "").lower()
    bbox = blk.get("bbox", [])
    bid = f"p{page_idx}_b{order}"

    if btype in _SKIP_TYPES:
        return []

    results: List[CanonicalBlock] = []
    text = str(blk.get("text", "") or "").strip()

    if btype == "title":
        level = int(blk.get("text_level", 1))
        if not text:
            return results
        hashes = "#" * min(max(level, 1), 6)
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="title", source_text=text, render_md=f"{hashes} {text}",
            translatable=True, level=level, bbox=bbox,
        ))

    elif btype in ("text", "paragraph"):
        if not text:
            return results
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="paragraph", source_text=text, render_md=text,
            translatable=True, bbox=bbox,
        ))

    elif btype == "list":
        if not text:
            return results
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        md = "\n".join(f"- {l}" for l in lines)
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="list", source_text=text, render_md=md,
            translatable=True, bbox=bbox,
        ))

    elif btype == "image":
        img_path = str(blk.get("img_path", "") or "")
        if img_path and img_prefix:
            img_path = img_prefix.rstrip("/") + "/" + img_path.lstrip("/")
        render_md = f"![]({img_path})" if img_path else ""
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="image", source_text="", render_md=render_md,
            translatable=False, bbox=bbox,
        ))

    elif btype == "table":
        html = str(blk.get("html", "") or "").strip()
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="table", source_text="", render_md=html or "(table)",
            translatable=False, bbox=bbox,
        ))

    elif btype in ("equation", "formula"):
        eq = str(blk.get("equation", text) or "").strip()
        results.append(CanonicalBlock(
            block_id=bid, page_idx=page_idx, order=order,
            type="equation", source_text="", render_md=f"$${eq}$$" if eq else "(equation)",
            translatable=False, bbox=bbox,
        ))

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_canonical_blocks(
    bundle_dir: str,
    img_prefix: str = "mineru_bundle",
) -> Optional[List[CanonicalBlock]]:
    """
    Load and normalize content blocks from a MinerU bundle directory.

    Returns an ordered list of CanonicalBlock objects, or None if no
    usable content_list file is found.

    img_prefix is prepended to relative image paths so they resolve
    correctly from the paper directory (where _bilingual.md lives).
    Pass empty string to keep paths as-is.
    """
    bundle = Path(bundle_dir)
    if not bundle.is_dir():
        return None

    # ---- Priority 1: content_list_v2.json ----
    v2_path = bundle / "content_list_v2.json"
    if v2_path.is_file():
        try:
            raw = json.loads(v2_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, list) and raw:
                result: List[CanonicalBlock] = []
                order = 0
                for page_idx, blk in _iter_v2(raw):
                    result.extend(_parse_v2_block(page_idx, blk, order, img_prefix))
                    order += 1
                if result:
                    logger.info(
                        "Loaded %d canonical blocks from %s",
                        len(result), v2_path.name,
                    )
                    return result
        except Exception as exc:
            logger.warning("Failed to parse content_list_v2.json: %s", exc)

    # ---- Priority 2: *_content_list.json (flat) ----
    flat_path: Optional[Path] = None
    for p in bundle.glob("*_content_list.json"):
        flat_path = p
        break
    if flat_path and flat_path.is_file():
        try:
            raw = json.loads(flat_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, list) and raw:
                result = []
                order = 0
                for page_idx, blk in _iter_flat(raw):
                    result.extend(_parse_flat_block(page_idx, blk, order, img_prefix))
                    order += 1
                if result:
                    logger.info(
                        "Loaded %d canonical blocks from %s",
                        len(result), flat_path.name,
                    )
                    return result
        except Exception as exc:
            logger.warning("Failed to parse flat content_list: %s", exc)

    # ---- Priority 3: search one level deep for nested ZIP extraction ----
    # MinerU ZIP may extract into a subdirectory (e.g. bundle/{paper_id}/content_list_v2.json).
    # In that case we must adjust img_prefix to include the subdirectory so image URLs resolve.
    try:
        for sub_dir in sorted(bundle.iterdir()):
            if not sub_dir.is_dir():
                continue
            nested_prefix = (img_prefix.rstrip("/") + "/" + sub_dir.name) if img_prefix else sub_dir.name
            sub_v2 = sub_dir / "content_list_v2.json"
            if sub_v2.is_file():
                logger.info(
                    "load_canonical_blocks: found content_list_v2.json in subdirectory %s; "
                    "using nested img_prefix=%s",
                    sub_dir.name, nested_prefix,
                )
                return load_canonical_blocks(str(sub_dir), img_prefix=nested_prefix)
            sub_flat: Optional[Path] = None
            for p in sub_dir.glob("*_content_list.json"):
                sub_flat = p
                break
            if sub_flat and sub_flat.is_file():
                logger.info(
                    "load_canonical_blocks: found flat content_list in subdirectory %s; "
                    "using nested img_prefix=%s",
                    sub_dir.name, nested_prefix,
                )
                return load_canonical_blocks(str(sub_dir), img_prefix=nested_prefix)
    except OSError as exc:
        logger.warning("load_canonical_blocks: error scanning subdirectories of %s: %s", bundle_dir, exc)

    return None
