"""
User paper mini-pipeline service.

Processes a single user-uploaded paper through the same steps as the daily
arXiv pipeline: PDF text extraction → institution/abstract extraction (pdf_info)
→ full summary (paper_summary) → condensed summary (summary_limit)
→ structured blocks (paper_assets).

PDF extraction strategy (same as daily pipeline):
  1. MinerU API (when minerU_Token is configured) — high-quality Markdown with
     layout, tables and formulae preserved.
  2. PyMuPDF fallback — plain text extraction when MinerU is unavailable or fails.

All results are stored in the user_uploaded_papers table via user_paper_service.
Processing runs in a background thread so the HTTP request returns immediately.
"""

from __future__ import annotations

import json
import logging
import os
import posixpath
import re
import shutil
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Ensure Sever root is in sys.path so Controller imports work
_SEVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SEVER_DIR not in sys.path:
    sys.path.insert(0, _SEVER_DIR)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory registry to prevent duplicate concurrent processing
# ---------------------------------------------------------------------------

_running_jobs: set[str] = set()
_running_lock = threading.Lock()


def is_processing(paper_id: str) -> bool:
    with _running_lock:
        return paper_id in _running_jobs


def _mark_running(paper_id: str) -> bool:
    """Returns True if successfully claimed; False if already running."""
    with _running_lock:
        if paper_id in _running_jobs:
            return False
        _running_jobs.add(paper_id)
        return True


def _mark_done(paper_id: str) -> None:
    with _running_lock:
        _running_jobs.discard(paper_id)


# ---------------------------------------------------------------------------
# PDF text extraction — PyMuPDF fallback
# ---------------------------------------------------------------------------

def _extract_text_pymupdf(pdf_path: str, max_chars: int = 200_000) -> str:
    """Extract plain text from a PDF file using PyMuPDF (fitz)."""
    try:
        import fitz  # type: ignore
        doc = fitz.open(pdf_path)
        parts: list[str] = []
        total = 0
        for page in doc:
            t = page.get_text()
            if not t:
                continue
            parts.append(t)
            total += len(t)
            if total >= max_chars:
                break
        doc.close()
        text = "\n".join(parts)
        if len(text) > max_chars:
            text = text[:max_chars]
        return text
    except Exception as exc:
        logger.warning("PyMuPDF extraction failed for %s: %s", pdf_path, exc)
        return ""


# ---------------------------------------------------------------------------
# PDF text extraction — MinerU API (high-quality Markdown, matches daily pipeline)
# ---------------------------------------------------------------------------

def _get_mineru_token() -> str:
    """Return the MinerU API token from config, or empty string if not set."""
    try:
        from config.config import minerU_Token  # type: ignore
        return (minerU_Token or "").strip()
    except Exception:
        return ""


def _first_md_under(root: Path) -> Tuple[Path, str]:
    """Pick shallowest .md under root (same ordering as pick_first_md on zip)."""
    mds = [p for p in root.rglob("*.md") if p.is_file()]
    if not mds:
        raise RuntimeError(f"no .md file under {root}")

    def sort_key(p: Path) -> tuple[int, int]:
        rel = p.relative_to(root).as_posix()
        return (rel.count("/"), len(rel))

    mds.sort(key=sort_key)
    chosen = mds[0]
    rel = chosen.relative_to(root).as_posix()
    return chosen, rel


def _rewrite_mineru_md_paths(md_text: str, md_rel_posix: str, bundle_segment: str) -> str:
    """Prefix relative image paths so they resolve from .../{paper_id}/{paper_id}_mineru.md."""
    md_parent = posixpath.dirname(md_rel_posix)
    base_prefix = bundle_segment.rstrip("/") + "/"
    if md_parent:
        base_prefix = base_prefix + md_parent.rstrip("/") + "/"

    def join_rel(href: str) -> str:
        href = href.strip().strip('"').strip("'")
        if not href or href.startswith("#"):
            return href
        lower = href.lower()
        if lower.startswith("http://") or lower.startswith("https://") or lower.startswith("data:"):
            return href
        if href.startswith("//"):
            return href
        if href.startswith("/"):
            return href
        combined = posixpath.normpath(base_prefix + href).replace("\\", "/")
        if combined.startswith(".."):
            return href
        return combined

    def repl_md_img(m: re.Match[str]) -> str:
        alt, path = m.group(1), m.group(2)
        path_stripped = path.strip()
        if not path_stripped:
            return m.group(0)
        new_p = join_rel(path_stripped)
        return f"![{alt}]({new_p})"

    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl_md_img, md_text)

    def repl_src(m: re.Match[str]) -> str:
        qs = m.group(1)
        path = m.group(2)
        new_p = join_rel(path)
        return f"src={qs}{new_p}{qs}"

    text = re.sub(
        r'src=(["\'])([^"\']*)\1',
        repl_src,
        text,
        flags=re.IGNORECASE,
    )
    return text


def _iter_pages_from_content_list(raw: Any) -> Any:
    """Yield (page_idx, blocks) from MinerU content_list JSON (list-of-pages or flat list)."""
    if not isinstance(raw, list) or not raw:
        return
    if isinstance(raw[0], dict):
        yield 0, raw
        return
    for page_idx, page_blocks in enumerate(raw):
        if isinstance(page_blocks, list):
            yield page_idx, page_blocks


def _fallback_mineru_images_from_pdf(pdf_path: str, bundle_dir: Path) -> None:
    """If ZIP omitted images/, crop regions from the source PDF using content_list_v2.json bboxes."""
    try:
        import fitz  # type: ignore
    except ImportError:
        logger.warning("PyMuPDF (fitz) not available; cannot run MinerU image fallback")
        return

    images_dir = bundle_dir / "images"
    if images_dir.is_dir():
        try:
            if any(images_dir.iterdir()):
                return
        except OSError:
            pass

    cl_path = bundle_dir / "content_list_v2.json"
    if not cl_path.is_file():
        cl_path = bundle_dir / "content_list.json"
    if not cl_path.is_file():
        for p in bundle_dir.rglob("*content_list*.json"):
            cl_path = p
            break
    if not cl_path.is_file():
        logger.warning("MinerU image fallback: no content_list JSON under %s", bundle_dir)
        return

    try:
        raw = json.loads(cl_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        logger.warning("MinerU image fallback: cannot read %s: %s", cl_path, exc)
        return

    doc = fitz.open(pdf_path)
    n_written = 0
    try:
        for page_idx, page_blocks in _iter_pages_from_content_list(raw):
            if page_idx >= doc.page_count:
                continue
            page = doc[page_idx]
            for block in page_blocks:
                if not isinstance(block, dict) or block.get("type") != "image":
                    continue
                img_path_rel = (block.get("content") or {}).get("image_source", {}).get("path")
                if not img_path_rel or not isinstance(img_path_rel, str):
                    continue
                bbox = block.get("bbox")
                if not bbox or len(bbox) < 4:
                    continue
                rel_norm = img_path_rel.replace("\\", "/").lstrip("/")
                dest = bundle_dir / rel_norm
                if dest.is_file():
                    continue
                try:
                    x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
                except (TypeError, ValueError):
                    continue
                rect = fitz.Rect(x0, y0, x1, y1)
                if rect.width <= 0.5 or rect.height <= 0.5:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    mat = fitz.Matrix(2.0, 2.0)
                    pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
                    pix.save(str(dest))
                    n_written += 1
                except Exception as exc:
                    logger.debug("MinerU image fallback skip %s: %s", rel_norm, exc)
    finally:
        doc.close()

    if n_written:
        logger.info("MinerU image fallback: wrote %d image(s) from PDF into %s", n_written, images_dir)


def _convert_pdf_via_mineru(pdf_path: str, extract_root: Optional[str] = None) -> str:
    """Upload a single PDF to MinerU API and return extracted Markdown text.

    Reuses MinerUClient and helpers from Controller/selectedpaper_to_mineru.py,
    which is the same code path used by the daily shared-cache pipeline.
    Returns empty string on any error so the caller can fallback to PyMuPDF.
    """
    try:
        from Controller.selectedpaper_to_mineru import (  # type: ignore
            MinerUClient,
            upload_to_presigned_url,
            wait_batch_done,
            download_zip,
            extract_zip,
            pick_first_md,
        )
    except Exception as exc:
        logger.warning("selectedpaper_to_mineru import failed: %s", exc)
        return ""

    token = _get_mineru_token()
    if not token:
        return ""

    base_url = os.environ.get("MINERU_BASE_URL", "https://mineru.net")
    model_version = os.environ.get("MINERU_MODEL_VERSION", "vlm")

    pdf_path_obj = Path(pdf_path)
    stem = pdf_path_obj.stem
    filename = pdf_path_obj.name

    try:
        client = MinerUClient(base_url, token)

        # Request a pre-signed upload URL for this single file
        applied = client.apply_upload_urls(
            [{"name": filename, "data_id": stem}],
            model_version=model_version,
            extra={"return_images": True},
        ).get("data") or {}
        put_urls = applied.get("file_urls") or []
        batch_id = applied.get("batch_id") or ""
        if not batch_id or not put_urls:
            logger.warning("MinerU apply_upload_urls returned no batch_id/url for %s", filename)
            return ""

        upload_to_presigned_url(pdf_path_obj, put_urls[0])
        logger.info("MinerU: uploaded %s, batch_id=%s, waiting for parse result…", filename, batch_id)

        items = wait_batch_done(client, batch_id, expected_total=1, timeout_sec=300, poll_sec=3)

        def _matches_stem(raw_id: str) -> bool:
            """Return True when the MinerU result id corresponds to our PDF stem.

            arXiv IDs contain a dot (e.g. "2603.30016"), so split(".")[0] would
            wrongly truncate them to "2603".  Instead we compare the full string
            first, then strip only a trailing .pdf extension before comparing.
            """
            s = str(raw_id).strip()
            if s == stem:
                return True
            # Handle file_name that may carry a .pdf suffix
            base, sep, ext = s.rpartition(".")
            if sep and ext.lower() == "pdf":
                return base == stem
            return False

        item = next(
            (
                it for it in items
                if _matches_stem(it.get("data_id") or it.get("file_name") or "")
            ),
            None,
        )
        if not item:
            logger.warning("MinerU: no result item for %s (stem=%s, available=%s)",
                           filename, stem,
                           [it.get("data_id") or it.get("file_name") for it in items])
            return ""

        state = str(item.get("state") or "").lower()
        if state != "done":
            logger.warning("MinerU: item state=%s for %s", state, filename)
            return ""

        zip_url = item.get("full_zip_url")
        if not zip_url:
            logger.warning("MinerU: no full_zip_url for %s", filename)
            return ""

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / f"{stem}.zip"
            download_zip(zip_url, token, zip_path)
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    names = zf.namelist()
                    logger.info(
                        "MinerU ZIP contents (%s): %d entries, sample=%s",
                        filename,
                        len(names),
                        names[: min(40, len(names))],
                    )
            except Exception as exc:
                logger.warning("MinerU: could not list ZIP %s: %s", filename, exc)
            if extract_root:
                bundle_name = "mineru_bundle"
                bundle_dir = Path(extract_root) / bundle_name
                try:
                    shutil.rmtree(bundle_dir, ignore_errors=True)
                except Exception:
                    pass
                bundle_dir.mkdir(parents=True, exist_ok=True)
                extract_zip(zip_path, bundle_dir)
                _fallback_mineru_images_from_pdf(pdf_path, bundle_dir)
                md_file, md_rel = _first_md_under(bundle_dir)
                raw = md_file.read_text(encoding="utf-8", errors="replace")
                md_text = _rewrite_mineru_md_paths(raw, md_rel, bundle_name)
            else:
                md_text = pick_first_md(zip_path)

        logger.info("MinerU: successfully extracted Markdown for %s (%d chars)", filename, len(md_text))
        return md_text

    except Exception as exc:
        logger.warning("MinerU extraction failed for %s: %s", pdf_path, exc)
        return ""


# ---------------------------------------------------------------------------
# PDF download helper
# ---------------------------------------------------------------------------

def _download_arxiv_pdf(arxiv_id: str, dest_path: str) -> bool:
    """Download a PDF from arXiv to dest_path. Returns True on success."""
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 ArxivPaperBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if len(data) < 1000:
            return False
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        return True
    except Exception as exc:
        logger.warning("arXiv PDF download failed for %s: %s", arxiv_id, exc)
        return False


# ---------------------------------------------------------------------------
# Step: pdf_info (institution + abstract extraction)
# ---------------------------------------------------------------------------

def _run_pdf_info(text: str, user_id: int) -> Dict[str, Any]:
    """Extract institution, is_large, abstract from raw PDF text via LLM.

    Returns dict with keys: instution, is_large, abstract.
    """
    try:
        from Controller.pdf_info import _resolve_llm_for_user, call_qwen, parse_json_or_fallback
    except Exception:
        return {"instution": "", "is_large": False, "abstract": ""}

    cfg = _resolve_llm_for_user(user_id)
    sys_prompt = cfg.get("system_prompt", "")
    if not sys_prompt or not text.strip():
        return {"instution": "", "is_large": False, "abstract": ""}

    max_chars = 120_000
    content = text[:max_chars] if len(text) > max_chars else text
    user_content = f"文本：\n{content}"

    try:
        raw = call_qwen(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model=cfg["model"],
            system_prompt=sys_prompt,
            user_content=user_content,
            temperature=cfg.get("temperature", 1.0),
            max_tokens=cfg.get("max_tokens", 1024),
        )
        return parse_json_or_fallback(raw)
    except Exception as exc:
        logger.warning("pdf_info LLM call failed: %s", exc)
        return {"instution": "", "is_large": False, "abstract": ""}


# ---------------------------------------------------------------------------
# Step: paper_summary
# ---------------------------------------------------------------------------

def _run_paper_summary(text: str, paper_id: str, user_id: int) -> str:
    """Generate full structured summary from paper text. Returns markdown string."""
    if not text.strip():
        return ""
    try:
        from Controller.paper_summary import make_client_for_user, summarize_one
    except Exception as exc:
        logger.warning("paper_summary import failed: %s", exc)
        return ""

    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = Path(tmpdir) / f"{paper_id}.md"
        md_path.write_text(text, encoding="utf-8")
        try:
            client, ecfg = make_client_for_user(user_id=user_id)
            _, summary_text = summarize_one(client, md_path, effective_cfg=ecfg)
            return summary_text or ""
        except Exception as exc:
            logger.warning("paper_summary LLM call failed: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# Step: summary_limit
# ---------------------------------------------------------------------------

def _run_summary_limit(
    summary_text: str,
    paper_id: str,
    user_id: int,
    meta: Dict[str, Any],
) -> str:
    """Produce condensed/structured summary from full summary markdown."""
    if not summary_text.strip():
        return ""
    try:
        from Controller.summary_limit import (
            build_effective_cfg,
            make_client_from_cfg,
            process_one,
        )
    except Exception as exc:
        logger.warning("summary_limit import failed: %s", exc)
        return ""

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = Path(tmpdir) / f"{paper_id}.md"
        out_path = Path(tmpdir) / f"{paper_id}_limit.md"

        # Build a minimal pdf_info_map so inject_pdf_info can work
        institution = meta.get("institution") or meta.get("instution") or ""
        title = meta.get("title", "")
        arxiv_id = meta.get("source_ref", "")
        source = f"arxiv, {arxiv_id}" if arxiv_id else ""
        pdf_info_map = {}
        if institution or title:
            pdf_info_map[paper_id] = {
                "instution": institution,
                "title": title,
                "source": source,
            }

        in_path.write_text(summary_text, encoding="utf-8")
        try:
            ecfg = build_effective_cfg(user_id=user_id)
            client = make_client_from_cfg(ecfg)
            process_one(
                client, in_path, out_path, pdf_info_map, effective_cfg=ecfg
            )
            # process_one writes output to out_path; return value is a status string, not content
            if out_path.exists():
                return out_path.read_text(encoding="utf-8")
            return ""
        except Exception as exc:
            logger.warning("summary_limit LLM call failed: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# Step: paper_assets
# ---------------------------------------------------------------------------

def _run_paper_assets(summary_text: str, user_id: int) -> Dict[str, Any]:
    """Generate structured asset blocks from summary markdown."""
    if not summary_text.strip():
        return {}
    try:
        from Controller.paper_assets import (
            make_client_for_user,
            extract_blocks_with_llm,
            ensure_blocks_structure,
        )
    except Exception as exc:
        logger.warning("paper_assets import failed: %s", exc)
        return {}

    try:
        client, ecfg = make_client_for_user(user_id=user_id)
        blocks = extract_blocks_with_llm(client, summary_text, effective_cfg=ecfg)
        return ensure_blocks_structure(blocks)
    except Exception as exc:
        logger.warning("paper_assets LLM call failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_summary_to_json(limit_text: str, raw_text: str, paper: Dict[str, Any]) -> str:
    """Convert summary_limit markdown text into a JSON-serialisable PaperSummary dict."""
    import re

    def _extract_section(text: str, header: str) -> list[str]:
        """Extract bullet lines under a section header."""
        lines = text.splitlines()
        collecting = False
        result: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(header):
                collecting = True
                continue
            if collecting:
                if stripped and any(
                    stripped.startswith(h)
                    for h in ["📖", "🌐", "🛎️", "📝", "🔎", "💡", "一句话", "推荐理由"]
                ):
                    break
                if stripped.startswith("🔸"):
                    result.append(stripped[1:].strip())
                elif stripped.startswith(("- ", "* ", "• ")):
                    result.append(stripped[2:].strip())
                elif stripped:
                    result.append(stripped)
        return result

    def _extract_line(text: str, header: str) -> str:
        for line in text.splitlines():
            s = line.strip()
            if s.startswith(header):
                rest = s[len(header):].lstrip("：: ").strip()
                return rest
        return ""

    use_text = limit_text if limit_text.strip() else raw_text
    institution = paper.get("institution") or ""
    short_title = _extract_line(use_text, "笔记标题") or _extract_line(use_text, "标题")
    if not short_title and institution:
        for line in use_text.splitlines():
            s = line.strip()
            if s.startswith(institution + "："):
                short_title = s[len(institution) + 1:].strip()
                break
    if not short_title:
        for line in use_text.splitlines():
            s = line.strip()
            if s and not any(
                s.startswith(h) for h in ["#", "📖", "🌐", "🛎️", "📝", "🔎", "💡", "一句话", "推荐理由"]
            ):
                short_title = s[:80]
                break

    full_title = _extract_line(use_text, "📖标题") or paper.get("title", "")
    source_ref = paper.get("source_ref") or paper.get("paper_id", "")
    source_line = _extract_line(use_text, "🌐来源") or (f"arxiv,{source_ref}" if source_ref else "")

    intro_q = _extract_line(use_text, "🔸研究问题")
    intro_c = _extract_line(use_text, "🔸主要贡献")
    if not intro_q and not intro_c:
        intro_bullets = _extract_section(use_text, "🛎️文章简介")
        intro_q = intro_bullets[0] if len(intro_bullets) > 0 else ""
        intro_c = intro_bullets[1] if len(intro_bullets) > 1 else ""

    result = {
        "institution": institution,
        "short_title": short_title,
        "📖标题": full_title,
        "🌐来源": source_line,
        "paper_id": paper.get("paper_id", ""),
        "推荐理由": _extract_line(use_text, "推荐理由"),
        "🛎️文章简介": {
            "🔸研究问题": intro_q,
            "🔸主要贡献": intro_c,
        },
        "📝重点思路": _extract_section(use_text, "📝重点思路"),
        "🔎分析总结": _extract_section(use_text, "🔎分析总结"),
        "💡个人观点": _extract_line(use_text, "💡个人观点"),
        "一句话记忆版": _extract_line(use_text, "一句话记忆版"),
        "abstract": paper.get("abstract", ""),
        "summary_raw": raw_text,
        "summary_limit": limit_text,
    }
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main pipeline function
# ---------------------------------------------------------------------------

def process_single_paper(user_id: int, paper_id: str) -> None:
    """Run the full mini-pipeline for one user paper in the current thread.

    Caller should invoke this inside a daemon thread.
    Updates process_status in DB at every stage transition.
    """
    import services.user_paper_service as svc

    def _set(status: str, step: str = "", error: str = "", started: bool = False, finished: bool = False):
        try:
            svc.set_process_status(
                paper_id,
                status=status,
                step=step,
                error=error,
                started=started,
                finished=finished,
            )
        except Exception as e:
            logger.warning("Failed to update process status: %s", e)

    # Load paper row
    paper = svc.get_paper(user_id, paper_id)
    if not paper:
        logger.error("process_single_paper: paper %s not found for user %d", paper_id, user_id)
        return

    _set("processing", step="starting", started=True)

    try:
        # ------------------------------------------------------------------
        # Step 1: Ensure we have a PDF on disk
        # ------------------------------------------------------------------
        _set("processing", step="pdf_prepare")
        pdf_path: Optional[str] = None

        # Reconstruct absolute path from relative pdf_path stored in DB
        if paper.get("pdf_path"):
            rel = paper["pdf_path"].replace("\\", "/")
            from services.user_paper_service import _KB_FILES_DIR
            abs_pdf = os.path.join(_KB_FILES_DIR, rel)
            if os.path.isfile(abs_pdf):
                pdf_path = abs_pdf

        # For arXiv papers without a local PDF, download it
        if not pdf_path and paper.get("source_type") == "arxiv" and paper.get("source_ref"):
            arxiv_id = paper["source_ref"]
            from services.user_paper_service import _USER_PAPERS_DIR
            dest = os.path.join(_USER_PAPERS_DIR, str(user_id), paper_id, "paper.pdf")
            _set("processing", step="pdf_download")
            ok = _download_arxiv_pdf(arxiv_id, dest)
            if ok:
                pdf_path = dest
                # Persist pdf_path in DB (relative to kb_files)
                rel_path = os.path.join("user_papers", str(user_id), paper_id, "paper.pdf")
                svc.update_paper(user_id, paper_id, pdf_filename="paper.pdf")
                try:
                    import sqlite3
                    from services.user_paper_service import _DB_PATH, _now_iso
                    conn = sqlite3.connect(_DB_PATH, timeout=30)
                    conn.execute(
                        "UPDATE user_uploaded_papers SET pdf_path=?, updated_at=? WHERE paper_id=?",
                        (rel_path, _now_iso(), paper_id),
                    )
                    conn.commit()
                    conn.close()
                except Exception as db_exc:
                    logger.warning("Failed to persist pdf_path: %s", db_exc)

        if not pdf_path:
            _set("failed", step="pdf_prepare", error="无法获取 PDF 文件（请上传 PDF 或确保 arXiv ID 正确）", finished=True)
            return

        # ------------------------------------------------------------------
        # Step 2: Extract text / Markdown from PDF
        # Priority: MinerU API (high-quality Markdown, same as daily pipeline)
        # Fallback: PyMuPDF plain text extraction
        # ------------------------------------------------------------------
        from services.user_paper_service import _USER_PAPERS_DIR

        md_dir = os.path.join(_USER_PAPERS_DIR, str(user_id), paper_id)
        os.makedirs(md_dir, exist_ok=True)

        text = ""
        mineru_token = _get_mineru_token()
        if mineru_token:
            _set("processing", step="pdf_mineru")
            text = _convert_pdf_via_mineru(pdf_path, extract_root=md_dir)
            if not text.strip():
                logger.warning("MinerU returned empty result for %s, falling back to PyMuPDF", paper_id)
                _set("processing", step="pdf_extract")
                text = _extract_text_pymupdf(pdf_path)
        else:
            _set("processing", step="pdf_extract")
            text = _extract_text_pymupdf(pdf_path)

        if not text.strip():
            _set("failed", step="pdf_extract", error="PDF 文本提取失败，文件可能为空或加密（MinerU 和 PyMuPDF 均未提取到内容）", finished=True)
            return

        # Persist extracted text as Markdown for later translation / download
        try:
            mineru_md_path = os.path.join(md_dir, f"{paper_id}_mineru.md")
            with open(mineru_md_path, "w", encoding="utf-8") as _mf:
                _mf.write(text)
            logger.info("Saved extracted markdown to %s", mineru_md_path)
        except Exception as exc:
            logger.warning("Failed to persist mineru markdown for %s: %s", paper_id, exc)

        # ------------------------------------------------------------------
        # Step 2b: Build normalized Markdown from MinerU bundle JSON
        # Produces {paper_id}_mineru_normalized.md alongside _mineru.md.
        # This version reconstructs the document from content_list_v2.json,
        # applying paragraph-merge rules to fix PDF hard-breaks so the output
        # reads like a proper academic paper.
        # ------------------------------------------------------------------
        bundle_dir_path = os.path.join(md_dir, "mineru_bundle")
        if os.path.isdir(bundle_dir_path):
            try:
                from services.mineru_normalize_service import build_normalized_markdown
                normalized_text = build_normalized_markdown(
                    bundle_dir_path, img_prefix="mineru_bundle"
                )
                if normalized_text and normalized_text.strip():
                    norm_md_path = os.path.join(md_dir, f"{paper_id}_mineru_normalized.md")
                    with open(norm_md_path, "w", encoding="utf-8") as _nf:
                        _nf.write(normalized_text)
                    logger.info("Saved normalized markdown to %s", norm_md_path)
                else:
                    logger.warning(
                        "Normalized markdown was empty for %s; skipping write", paper_id
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to generate normalized markdown for %s: %s", paper_id, exc
                )

        # ------------------------------------------------------------------
        # Step 3: pdf_info – extract institution / abstract
        # ------------------------------------------------------------------
        _set("processing", step="pdf_info")
        info = _run_pdf_info(text, user_id)
        institution = info.get("instution") or info.get("institution") or paper.get("institution") or ""
        abstract = info.get("abstract") or paper.get("abstract") or ""

        # Persist institution / abstract back to DB
        svc.update_summary_and_assets(paper_id, institution=institution, abstract=abstract)
        # Also refresh paper dict for later steps
        paper["institution"] = institution
        paper["abstract"] = abstract

        # ------------------------------------------------------------------
        # Step 4: paper_summary – full structured summary
        # ------------------------------------------------------------------
        _set("processing", step="paper_summary")
        raw_summary = _run_paper_summary(text, paper_id, user_id)
        if not raw_summary.strip():
            _set("failed", step="paper_summary", error="摘要生成失败，请检查 LLM 配置", finished=True)
            return

        # ------------------------------------------------------------------
        # Step 5: summary_limit – condensed summary
        # ------------------------------------------------------------------
        _set("processing", step="summary_limit")
        limit_summary = _run_summary_limit(raw_summary, paper_id, user_id, paper)
        if not limit_summary.strip():
            limit_summary = raw_summary  # fallback to raw

        # ------------------------------------------------------------------
        # Step 6: paper_assets – structured blocks
        # Use raw_summary as input (same as daily pipeline DB mode)
        # ------------------------------------------------------------------
        _set("processing", step="paper_assets")
        blocks = _run_paper_assets(raw_summary, user_id)

        # ------------------------------------------------------------------
        # Persist results
        # ------------------------------------------------------------------
        summary_json = _parse_summary_to_json(limit_summary, raw_summary, paper)
        paper_assets_obj = {
            "paper_id": paper_id,
            "title": paper.get("title", ""),
            "url": paper.get("external_url") or (
                f"https://arxiv.org/abs/{paper['source_ref']}" if paper.get("source_ref") else ""
            ),
            "year": paper.get("year"),
            "blocks": blocks,
        }
        paper_assets_json = json.dumps(paper_assets_obj, ensure_ascii=False)

        svc.update_summary_and_assets(
            paper_id,
            summary_json=summary_json,
            paper_assets_json=paper_assets_json,
            institution=institution,
            abstract=abstract,
        )
        _set("completed", step="done", finished=True)
        logger.info("User paper pipeline completed: %s", paper_id)

    except Exception as exc:
        logger.exception("User paper pipeline error for %s: %s", paper_id, exc)
        _set("failed", step="", error=str(exc)[:500], finished=True)
    finally:
        _mark_done(paper_id)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def start_processing(user_id: int, paper_id: str) -> bool:
    """Launch pipeline in background thread.

    Returns True if started; False if already running.
    """
    if not _mark_running(paper_id):
        return False

    import services.user_paper_service as svc
    svc.set_process_status(paper_id, status="pending", step="queued")

    t = threading.Thread(
        target=process_single_paper,
        args=(user_id, paper_id),
        daemon=True,
        name=f"user-paper-pipeline-{paper_id}",
    )
    t.start()
    return True
