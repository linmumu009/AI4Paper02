"""
KB paper mini-pipeline service.

Processes a KB (knowledge base) paper through MinerU PDF extraction so that
translation can be run afterwards.  KB papers are arXiv papers already saved
by the user; their PDF is stored (or auto-copied) in:
    data/kb_files/{user_id}/{paper_id}/{paper_id}.pdf

The pipeline only performs the PDF-extraction step (not full LLM summarisation,
which the daily pipeline already provides for arXiv papers).

Steps:
    1. Locate the PDF in kb_files (via auto_attach_pdf if not yet present).
    2. Run MinerU API extraction → {paper_id}_mineru.md
    3. Fallback to PyMuPDF if MinerU unavailable or fails.
    4. Build normalized Markdown from MinerU bundle JSON → {paper_id}_mineru_normalized.md

All state is persisted in kb_papers.process_status / process_step / process_error
via kb_service helpers.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Optional

_SEVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SEVER_DIR not in sys.path:
    sys.path.insert(0, _SEVER_DIR)

logger = logging.getLogger(__name__)

_running_jobs: set[str] = set()
_running_lock = threading.Lock()


def is_processing(paper_id: str) -> bool:
    with _running_lock:
        return paper_id in _running_jobs


def _mark_running(paper_id: str) -> bool:
    with _running_lock:
        if paper_id in _running_jobs:
            return False
        _running_jobs.add(paper_id)
        return True


def _mark_done(paper_id: str) -> None:
    with _running_lock:
        _running_jobs.discard(paper_id)


def process_kb_paper(user_id: int, paper_id: str, scope: str = "kb") -> None:
    """
    Synchronous KB paper processing (run from a background thread).

    Extracts text/Markdown from the paper's PDF using MinerU (or PyMuPDF
    fallback) and saves it as {paper_id}_mineru.md alongside the PDF.
    """
    import services.kb_service as kbs
    from services.user_paper_pipeline_service import (
        _convert_pdf_via_mineru,
        _extract_text_pymupdf,
    )

    def _set(status: str, step: str = "", error: str = "") -> None:
        kbs.set_kb_paper_process_status(
            user_id, paper_id, status=status, step=step, error=error, scope=scope
        )

    try:
        _set("processing", step="starting")

        # 1. Ensure PDF is present in kb_files
        pdf_path = kbs.get_kb_pdf_path(user_id, paper_id)
        if pdf_path is None:
            _set("processing", step="pdf_attach")
            try:
                kbs.auto_attach_pdf(user_id, paper_id, scope=scope)
            except Exception as e:
                logger.warning("auto_attach_pdf failed for %s: %s", paper_id, e)
            pdf_path = kbs.get_kb_pdf_path(user_id, paper_id)

        if pdf_path is None:
            raise FileNotFoundError(
                f"未找到 PDF 文件。请先上传或确认该论文的 PDF 已存在于 file_collect 目录中。"
            )

        # 2. Determine output directory
        paper_dir = os.path.dirname(pdf_path)
        mineru_md_path = os.path.join(paper_dir, f"{paper_id}_mineru.md")
        bundle_dir_path = os.path.join(paper_dir, "mineru_bundle")

        # 3. Ensure we have _mineru.md + mineru_bundle/ with correct image paths.
        #
        # Priority order:
        #   a. Both already present → nothing to do for extraction.
        #   b. _mineru.md present but bundle missing → try to copy bundle from
        #      full_mineru_cache; if unavailable, re-run MinerU API to get
        #      fresh bundle (needed for normalized md and block-based translation).
        #   c. Neither present → try full_mineru_cache first (free), then MinerU API.
        #
        logger.info(
            "KB paper processing for %s: _mineru.md=%s, bundle=%s",
            paper_id,
            os.path.isfile(mineru_md_path),
            os.path.isdir(bundle_dir_path),
        )

        if os.path.isfile(mineru_md_path) and os.path.isdir(bundle_dir_path):
            # Case (a): fully populated — skip extraction.
            logger.info(
                "KB paper processing Case(a): mineru.md + bundle already present for %s", paper_id
            )

        elif os.path.isfile(mineru_md_path) and not os.path.isdir(bundle_dir_path):
            # Case (b): md exists but bundle is missing.
            # The bundle is needed for content_list_v2.json which drives normalized markdown
            # and block-based translation.  Without it, format and translation quality degrade.
            #
            # Strategy:
            #   1. Try to backfill bundle from shared MinerU cache (free, fast).
            #   2. If cache unavailable (cleanup already removed it), call MinerU API
            #      for a full re-extraction — user explicitly pressed the button.
            _set("processing", step="bundle_attach")
            logger.info(
                "KB paper processing Case(b): _mineru.md exists but no bundle for %s; "
                "attempting cache backfill", paper_id
            )
            cache_bundle = kbs._find_mineru_bundle_in_cache(paper_id)
            if cache_bundle is not None:
                logger.info(
                    "KB paper Case(b): backfilling bundle from cache=%s for %s",
                    cache_bundle, paper_id
                )
                try:
                    shutil.copytree(cache_bundle, bundle_dir_path)
                    # Rewrite image paths in _mineru.md, _zh.md, and _bilingual.md
                    for md_fname in (
                        f"{paper_id}_mineru.md",
                        f"{paper_id}_zh.md",
                        f"{paper_id}_bilingual.md",
                    ):
                        md_path_to_fix = os.path.join(paper_dir, md_fname)
                        if os.path.isfile(md_path_to_fix):
                            try:
                                raw = Path(md_path_to_fix).read_text(encoding="utf-8")
                                fixed = kbs._rewrite_mineru_image_paths(raw)
                                if fixed != raw:
                                    Path(md_path_to_fix).write_text(fixed, encoding="utf-8")
                            except Exception as fe:
                                logger.warning(
                                    "Failed to rewrite paths in %s: %s", md_fname, fe
                                )
                    logger.info(
                        "KB paper Case(b): backfilled bundle from cache for %s; "
                        "rewrote image paths", paper_id
                    )
                except Exception as exc:
                    logger.warning(
                        "KB paper Case(b): failed to copy bundle from cache for %s: %s",
                        paper_id, exc
                    )
            else:
                # Cache bundle is unavailable (slim-mineru / post-idea cleanup removed it).
                # Re-run MinerU API extraction so we get a fresh bundle with
                # content_list_v2.json — required for normalized markdown and translation.
                logger.info(
                    "KB paper Case(b): no cache bundle for %s; calling MinerU API "
                    "for full re-extraction to obtain bundle", paper_id
                )
                _set("processing", step="pdf_mineru")
                text = _convert_pdf_via_mineru(pdf_path, extract_root=paper_dir)
                if text.strip():
                    Path(mineru_md_path).write_text(text, encoding="utf-8")
                    logger.info(
                        "KB paper Case(b): refreshed _mineru.md + bundle via MinerU API for %s",
                        paper_id
                    )
                else:
                    # MinerU API unavailable or failed.  Do NOT overwrite _mineru.md with
                    # PyMuPDF output — the existing file came from the MinerU daily pipeline
                    # and is higher quality.  We keep it and let step 4 generate a
                    # normalized version using the fallback normalize_mineru_source path.
                    logger.warning(
                        "KB paper Case(b): MinerU API returned empty for %s; "
                        "keeping existing _mineru.md (PyMuPDF would downgrade quality)", paper_id
                    )

        else:
            # Case (c): _mineru.md is missing — produce it from cache or MinerU API.
            _set("processing", step="bundle_attach")
            logger.info(
                "KB paper processing Case(c): no _mineru.md for %s; checking cache bundle",
                paper_id
            )
            cache_bundle = kbs._find_mineru_bundle_in_cache(paper_id)
            built_from_cache = False
            if cache_bundle is not None:
                logger.info(
                    "KB paper Case(c): found cache bundle at %s for %s", cache_bundle, paper_id
                )
                try:
                    if not os.path.isdir(bundle_dir_path):
                        shutil.copytree(cache_bundle, bundle_dir_path)
                    # Pick the primary .md from the bundle
                    primary_md = os.path.join(bundle_dir_path, f"{paper_id}.md")
                    if not os.path.isfile(primary_md):
                        # Fall back to any non-"full" .md at the root
                        candidates = [
                            f for f in os.listdir(bundle_dir_path)
                            if f.endswith(".md") and f != "full.md"
                        ]
                        primary_md = os.path.join(bundle_dir_path, candidates[0]) if candidates else None
                    if primary_md and os.path.isfile(primary_md):
                        raw = Path(primary_md).read_text(encoding="utf-8")
                        text = kbs._rewrite_mineru_image_paths(raw)
                        Path(mineru_md_path).write_text(text, encoding="utf-8")
                        built_from_cache = True
                        logger.info("Built _mineru.md from cache bundle for %s", paper_id)
                    else:
                        logger.warning("Cache bundle for %s has no usable .md", paper_id)
                except Exception as exc:
                    logger.warning(
                        "Failed to use cache bundle for %s: %s; falling back to MinerU API",
                        paper_id, exc,
                    )

            if not built_from_cache:
                # Call MinerU API (or PyMuPDF fallback)
                _set("processing", step="pdf_mineru")
                text = _convert_pdf_via_mineru(pdf_path, extract_root=paper_dir)
                if not text.strip():
                    _set("processing", step="pdf_extract")
                    text = _extract_text_pymupdf(pdf_path)

                if not text.strip():
                    raise RuntimeError("无法从 PDF 提取文本（MinerU 和 PyMuPDF 均失败）")

                Path(mineru_md_path).write_text(text, encoding="utf-8")

        # 4. Build normalized Markdown from the bundle's content_list JSON (if not yet done).
        norm_md_path = os.path.join(paper_dir, f"{paper_id}_mineru_normalized.md")
        if os.path.isdir(bundle_dir_path):
            if not os.path.isfile(norm_md_path):
                try:
                    from services.mineru_normalize_service import build_normalized_markdown
                    normalized_text = build_normalized_markdown(
                        bundle_dir_path, img_prefix="mineru_bundle"
                    )
                    if normalized_text and normalized_text.strip():
                        Path(norm_md_path).write_text(normalized_text, encoding="utf-8")
                        logger.info("Saved normalized markdown to %s", norm_md_path)
                    else:
                        logger.warning(
                            "build_normalized_markdown returned empty for %s "
                            "(bundle_dir_path=%s); check content_list_v2.json contents",
                            paper_id, bundle_dir_path,
                        )
                except Exception as exc:
                    logger.warning(
                        "Failed to generate normalized markdown for %s: %s", paper_id, exc
                    )
            else:
                logger.info(
                    "Normalized markdown already exists for %s; skipping rebuild", paper_id
                )
        else:
            # No bundle directory — try to produce a lightweight normalized markdown from
            # the raw _mineru.md using paragraph-merge rules so that translation quality
            # and display format are still acceptable even without content_list_v2.json.
            if os.path.isfile(mineru_md_path) and not os.path.isfile(norm_md_path):
                try:
                    from services.translate_service import normalize_mineru_source
                    raw_md = Path(mineru_md_path).read_text(encoding="utf-8")
                    normalized_text = normalize_mineru_source(raw_md)
                    if normalized_text and normalized_text.strip():
                        Path(norm_md_path).write_text(normalized_text, encoding="utf-8")
                        logger.info(
                            "KB paper processing: generated normalized markdown from raw md "
                            "(no bundle; used normalize_mineru_source fallback) for %s",
                            paper_id,
                        )
                    else:
                        logger.warning(
                            "KB paper processing: normalize_mineru_source returned empty for %s",
                            paper_id,
                        )
                except Exception as exc:
                    logger.warning(
                        "KB paper processing: failed to generate fallback normalized md "
                        "for %s: %s", paper_id, exc
                    )
            else:
                logger.warning(
                    "KB paper processing: no bundle dir at %s after extraction for %s; "
                    "normalized markdown will not be generated. "
                    "Translation will fall back to chunk-based method (lower quality).",
                    bundle_dir_path, paper_id,
                )

        _set("completed", step="done")
        logger.info("KB paper processing completed for %s", paper_id)

    except Exception as exc:
        logger.exception("KB paper processing failed for %s: %s", paper_id, exc)
        try:
            import services.kb_service as kbs2
            kbs2.set_kb_paper_process_status(
                user_id, paper_id,
                status="failed",
                step="",
                error=str(exc)[:500],
                scope=scope,
            )
        except Exception:
            pass
    finally:
        _mark_done(paper_id)


def start_kb_paper_process(
    user_id: int, paper_id: str, scope: str = "kb"
) -> tuple[bool, str]:
    """
    Start KB paper processing in a daemon background thread.
    Returns (ok, message).
    """
    import services.kb_service as kbs

    paper = kbs.get_kb_paper(user_id, paper_id, scope=scope)
    if paper is None:
        return False, "论文不在知识库中"

    if not _mark_running(paper_id):
        return False, "处理已在进行中"

    # Reset status immediately so the UI shows progress
    kbs.set_kb_paper_process_status(
        user_id, paper_id, status="pending", step="queued", error="", scope=scope
    )

    t = threading.Thread(
        target=process_kb_paper,
        args=(user_id, paper_id, scope),
        daemon=True,
        name=f"kb-paper-process-{paper_id}",
    )
    t.start()
    return True, "处理已启动"
