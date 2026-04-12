"""
Data service layer for reading paper data.

Dual-mode:
  1. DB mode  (new):  reads from pipeline_db_service tables keyed by (user_id, date_str)
  2. File mode (legacy): reads from data/file_collect/{date}/{paper_id}/ directory tree

Fallback logic:  when DB has no rows for (user_id, date), falls back to user_id=0 DB rows,
then to the legacy file-collect tree.
"""

import json
import os
import re
from collections import Counter
from typing import Any, Optional

# Resolve paths relative to the Sever/ directory
_SEVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_ROOT = os.path.join(_SEVER_ROOT, "data")
_DB_ROOT = os.path.join(_SEVER_ROOT, "database")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_local_pdf_url(paper_id: str) -> Optional[str]:
    """
    Search for a locally cached PDF and return a /static/data/... URL.

    Locations checked (newest date first):
      1. data/raw_pdf/{date}/{paper_id}.pdf
      2. data/file_collect/{date}/{paper_id}/{paper_id}.pdf

    Returns a relative URL path (e.g. /static/data/raw_pdf/2025-01-01/2504.00001.pdf)
    or None if not found.
    """
    raw_pdf_root = os.path.join(_DATA_ROOT, "raw_pdf")
    if os.path.isdir(raw_pdf_root):
        for date_dir in sorted(os.listdir(raw_pdf_root), reverse=True):
            candidate = os.path.join(raw_pdf_root, date_dir, f"{paper_id}.pdf")
            if os.path.isfile(candidate):
                return f"/static/data/raw_pdf/{date_dir}/{paper_id}.pdf"

    fc_root = os.path.join(_DATA_ROOT, "file_collect")
    if os.path.isdir(fc_root):
        for date_dir in sorted(os.listdir(fc_root), reverse=True):
            candidate = os.path.join(fc_root, date_dir, paper_id, f"{paper_id}.pdf")
            if os.path.isfile(candidate):
                return f"/static/data/file_collect/{date_dir}/{paper_id}/{paper_id}.pdf"

    return None

def _read_json(path: str) -> Any:
    """Read and parse a JSON file. Returns None if file doesn't exist."""
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_text(path: str) -> Optional[str]:
    """Read a text file. Returns None if file doesn't exist."""
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_jsonl(path: str) -> list[dict]:
    """Read a JSONL file. Returns empty list if file doesn't exist."""
    if not os.path.isfile(path):
        return []
    results: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return results


# ---------------------------------------------------------------------------
# _limit.md parser
# ---------------------------------------------------------------------------

def _parse_limit_md(text: str, paper_id: str) -> dict:
    """
    Parse a _limit.md file into a structured dict.

    Expected format:
        机构：短标题
        📖标题：English Title
        🌐来源：arxiv, 2602.xxxxx

        🛎️文章简介
        🔸研究问题:...
        🔸主要贡献:...

        📝重点思路
        🔸...
        🔸...

        🔎分析总结
        🔸...
        🔸...

        💡个人观点
        ...
    """
    lines = text.strip().splitlines()
    if not lines:
        return {"paper_id": paper_id}

    result: dict[str, Any] = {"paper_id": paper_id}

    # --- Line 1: "机构：短标题" or "机构:短标题" ---
    headline = lines[0].strip()
    # Split on first : or ：
    m = re.split(r'[:：]', headline, maxsplit=1)
    if len(m) == 2:
        result["institution"] = m[0].strip()
        result["short_title"] = m[1].strip()
    else:
        result["short_title"] = headline

    # --- Remaining lines: extract fields ---
    result["📖标题"] = ""
    result["🌐来源"] = ""
    result["推荐理由"] = ""
    result["🛎️文章简介"] = {"🔸研究问题": "", "🔸主要贡献": ""}
    result["📝重点思路"] = []
    result["🔎分析总结"] = []
    result["💡个人观点"] = ""
    result["一句话记忆版"] = ""

    current_section = None  # which section we're in

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue

        # Field: 📖标题：...
        if stripped.startswith("📖标题"):
            val = re.split(r'[:：]', stripped, maxsplit=1)
            result["📖标题"] = val[1].strip() if len(val) > 1 else ""
            current_section = None
            continue

        # Field: 🌐来源：...
        if stripped.startswith("🌐来源"):
            val = re.split(r'[:：]', stripped, maxsplit=1)
            result["🌐来源"] = val[1].strip() if len(val) > 1 else ""
            current_section = None
            continue

        # Field: 推荐理由：... (header section, before first emoji section)
        if stripped.startswith("推荐理由"):
            val = re.split(r'[:：]', stripped, maxsplit=1)
            result["推荐理由"] = val[1].strip() if len(val) > 1 else ""
            current_section = None
            continue

        # Field: 一句话记忆版：... (tail line, can appear after opinion section)
        if stripped.startswith("一句话记忆版"):
            val = re.split(r'[:：]', stripped, maxsplit=1)
            result["一句话记忆版"] = val[1].strip() if len(val) > 1 else ""
            current_section = None
            continue

        # Section headers
        if "🛎️文章简介" in stripped:
            current_section = "intro"
            continue
        if "📝重点思路" in stripped:
            current_section = "methods"
            continue
        if "🔎分析总结" in stripped:
            current_section = "findings"
            continue
        if "💡个人观点" in stripped:
            current_section = "opinion"
            continue

        # Section content
        if current_section == "intro":
            if "研究问题" in stripped:
                val = re.split(r'[:：]', stripped, maxsplit=1)
                result["🛎️文章简介"]["🔸研究问题"] = val[1].strip() if len(val) > 1 else stripped
            elif "主要贡献" in stripped:
                val = re.split(r'[:：]', stripped, maxsplit=1)
                result["🛎️文章简介"]["🔸主要贡献"] = val[1].strip() if len(val) > 1 else stripped

        elif current_section == "methods":
            result["📝重点思路"].append(stripped)

        elif current_section == "findings":
            result["🔎分析总结"].append(stripped)

        elif current_section == "opinion":
            # Opinion can be multi-line, concatenate with newline separator
            if result["💡个人观点"]:
                result["💡个人观点"] += "\n" + stripped
            else:
                result["💡个人观点"] = stripped

    return result


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _safe_path_component(value: str) -> str:
    """Reject values that could cause path traversal when used as a single
    directory component (date, paper_id, etc.)."""
    if '..' in value or '/' in value or '\\' in value or '\x00' in value:
        raise ValueError(f"Invalid path component: {value!r}")
    return value


# ---------------------------------------------------------------------------
# file_collect directory reader
# ---------------------------------------------------------------------------

def _get_file_collect_dir(date: str) -> str:
    _safe_path_component(date)
    return os.path.join(_DATA_ROOT, "file_collect", date)


def _find_limit_md(paper_dir: str, paper_id: str) -> Optional[str]:
    """Find the _limit.md file in a paper directory."""
    # Try exact name first
    exact = os.path.join(paper_dir, f"{paper_id}_limit.md")
    if os.path.isfile(exact):
        return exact
    # Fallback: find any file with _limit in name
    if os.path.isdir(paper_dir):
        for f in os.listdir(paper_dir):
            if "_limit" in f and f.endswith(".md"):
                return os.path.join(paper_dir, f)
    return None


def _list_paper_images(paper_dir: str) -> list[str]:
    """List image filenames in a paper's image/ subdirectory."""
    img_dir = os.path.join(paper_dir, "image")
    if not os.path.isdir(img_dir):
        return []
    images = sorted([
        f for f in os.listdir(img_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
    ])
    return images


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_dates(user_id: int = 0) -> list[str]:
    """
    Return sorted list of dates that have pipeline data available.

    Checks DB first (new multi-user path), then falls back to file_collect.
    """
    # Try DB first
    try:
        from services.pipeline_db_service import list_dates_with_data
        db_dates = list_dates_with_data(user_id)
        if db_dates:
            return db_dates
        # Try default user dates as fallback
        if user_id != 0:
            default_dates = list_dates_with_data(0)
            if default_dates:
                return default_dates
    except Exception:
        pass
    # Legacy file-collect fallback
    fc_dir = os.path.join(_DATA_ROOT, "file_collect")
    if not os.path.isdir(fc_dir):
        return []
    dates = [
        d for d in os.listdir(fc_dir)
        if os.path.isdir(os.path.join(fc_dir, d))
        and len(d) == 10  # YYYY-MM-DD
    ]
    dates.sort(reverse=True)
    return dates


def get_papers_by_date(
    date: str,
    search: Optional[str] = None,
    institution: Optional[str] = None,
    user_id: int = 0,
) -> list[dict]:
    """
    Get all papers for a given date.

    Checks DB first (multi-user path with personalized data), then falls back
    to the legacy file_collect tree.
    """
    papers = _get_papers_from_db(date, user_id=user_id)
    if papers is None:
        papers = _get_papers_from_files(date)

    if papers is None:
        papers = []

    # Apply search filter
    if search:
        q = search.lower()
        papers = [
            p for p in papers
            if q in p.get("📖标题", "").lower()
            or q in p.get("short_title", "").lower()
            or q in p.get("paper_id", "").lower()
            or q in p.get("institution", "").lower()
        ]

    # Apply institution filter
    if institution:
        q = institution.lower()
        papers = [
            p for p in papers
            if q in p.get("institution", "").lower()
        ]

    return papers


def _get_papers_from_db(date: str, user_id: int = 0) -> Optional[list[dict]]:
    """
    Try to load papers from pipeline DB tables.
    Returns None if no DB data is available (caller should fall back to files).
    """
    try:
        from services.pipeline_db_service import (
            get_digest_papers, has_final_selections,
        )
        # Check if DB has data (for user or default)
        if not has_final_selections(user_id, date) and not has_final_selections(0, date):
            return None
        db_papers = get_digest_papers(user_id, date, fallback_user_id=0)
        if not db_papers:
            return None

        # Convert DB format to the expected frontend format
        result = []
        for dp in db_papers:
            paper_id = dp.get("paper_id", "")
            # Parse limit markdown if available
            limit_text = dp.get("summary_limit", "") or dp.get("summary_raw", "")
            if limit_text:
                parsed = _parse_limit_md(limit_text, paper_id)
            else:
                parsed = {"paper_id": paper_id}
            parsed["institution"] = dp.get("institution", parsed.get("institution", ""))
            parsed["is_large_institution"] = dp.get("is_large_institution", False)
            parsed["institution_tier"] = dp.get("institution_tier") or 4
            parsed["abstract"] = dp.get("abstract", "")
            parsed["relevance_score"] = dp.get("relevance_score")
            parsed["headline"] = dp.get("headline", "")
            parsed["paper_assets"] = dp.get("paper_assets")
            parsed["is_personalized"] = dp.get("is_personalized", False)
            parsed["pipeline_user_id"] = dp.get("pipeline_user_id", 0)
            # Images from shared select_image dir (still file-based)
            select_img_path = os.path.join(
                _DATA_ROOT, "select_image", date, f"select_image_{date}.json"
            )
            if os.path.isfile(select_img_path):
                pass  # images are loaded per-paper in get_paper_detail
            parsed["images"] = []
            parsed["image_count"] = 0
            result.append(parsed)
        return result
    except Exception:
        return None


def _get_papers_from_files(date: str) -> Optional[list[dict]]:
    """Legacy file-based paper loading from file_collect."""
    fc_date_dir = _get_file_collect_dir(date)
    if not os.path.isdir(fc_date_dir):
        return None

    papers: list[dict] = []
    for paper_id in os.listdir(fc_date_dir):
        paper_dir = os.path.join(fc_date_dir, paper_id)
        if not os.path.isdir(paper_dir):
            continue

        # Find and parse _limit.md
        limit_path = _find_limit_md(paper_dir, paper_id)
        if limit_path is None:
            continue
        md_text = _read_text(limit_path)
        if md_text is None:
            continue

        data = _parse_limit_md(md_text, paper_id)

        # Merge pdf_info.json (institution, is_large, institution_tier, abstract)
        pdf_info = _read_json(os.path.join(paper_dir, "pdf_info.json"))
        if pdf_info:
            if pdf_info.get("instution"):
                data["institution"] = pdf_info["instution"]
            is_large = pdf_info.get("is_large", False)
            data["is_large_institution"] = is_large
            data["abstract"] = pdf_info.get("abstract", "")
            # institution_tier: use stored value, or derive from is_large for legacy files
            raw_tier = pdf_info.get("institution_tier")
            if raw_tier is not None:
                try:
                    t = int(raw_tier)
                    data["institution_tier"] = t if 1 <= t <= 4 else (3 if is_large else 4)
                except (TypeError, ValueError):
                    data["institution_tier"] = 3 if is_large else 4
            else:
                data["institution_tier"] = 3 if is_large else 4

        # List images
        data["images"] = _list_paper_images(paper_dir)
        data["image_count"] = len(data["images"])

        papers.append(data)

    # Merge theme relevance scores
    theme_scores = _load_theme_scores(date)
    if theme_scores:
        for p in papers:
            pid = p.get("paper_id", "")
            p["relevance_score"] = theme_scores.get(pid)

    # Sort: institution tier ascending (T1=1 first), then relevance_score descending within same tier
    papers.sort(
        key=lambda p: (
            p.get("institution_tier") or 4,
            -(p.get("relevance_score") or 0.0),
        )
    )

    return papers if papers else None


def get_paper_detail(paper_id: str, user_id: int = 0) -> Optional[dict]:
    """
    Get full detail for a single paper.
    Checks DB first (multi-user path), then falls back to file_collect.
    """
    # Security: sanitize paper_id to prevent path traversal
    try:
        _safe_path_component(paper_id)
    except ValueError:
        return None
    # --- Try DB ---
    try:
        from services.pipeline_db_service import (
            get_summaries, get_paper_info, get_paper_assets, get_theme_scores,
            has_final_selections, list_dates_with_data,
        )
        # Find dates that have this paper
        for candidate_uid in ([user_id, 0] if user_id != 0 else [0]):
            dates = list_dates_with_data(candidate_uid)
            for date_str in dates:
                info_rows = get_paper_info(candidate_uid, date_str, paper_id)
                if not info_rows:
                    info_rows = get_paper_info(0, date_str, paper_id)
                if not info_rows:
                    continue
                info = info_rows[0]

                sum_rows = get_summaries(candidate_uid, date_str, paper_id)
                if not sum_rows:
                    sum_rows = get_summaries(0, date_str, paper_id)
                summary_row = sum_rows[0] if sum_rows else {}

                assets_rows = get_paper_assets(candidate_uid, date_str, paper_id)
                if not assets_rows:
                    assets_rows = get_paper_assets(0, date_str, paper_id)
                assets_row = assets_rows[0] if assets_rows else {}

                limit_text = summary_row.get("summary_limit", "") or summary_row.get("summary_raw", "")
                if limit_text:
                    data = _parse_limit_md(limit_text, paper_id)
                else:
                    data = {"paper_id": paper_id}
                data["institution"] = info.get("institution", "")
                is_large = bool(info.get("is_large", 0))
                data["is_large_institution"] = is_large
                raw_tier = info.get("institution_tier")
                try:
                    t = int(raw_tier) if raw_tier is not None else 0
                    data["institution_tier"] = t if 1 <= t <= 4 else (3 if is_large else 4)
                except (TypeError, ValueError):
                    data["institution_tier"] = 3 if is_large else 4
                data["abstract"] = info.get("abstract", "")
                scores = get_theme_scores(candidate_uid, date_str)
                data["relevance_score"] = scores.get(paper_id)
                data["is_personalized"] = (candidate_uid != 0 and candidate_uid == user_id)

                # Images from select_image (still file-based)
                images = _list_paper_images_from_select_image(paper_id, date_str)

                local_pdf_url = _find_local_pdf_url(paper_id)
                _blocks = assets_row.get("blocks") if assets_row else None
                return {
                    "summary": data,
                    "paper_assets": {
                        "paper_id": paper_id,
                        "title": assets_row.get("title", ""),
                        "url": assets_row.get("url", ""),
                        "year": assets_row.get("year"),
                        "blocks": _blocks,
                    } if assets_row and _blocks else None,
                    "date": date_str,
                    "images": images,
                    "arxiv_url": f"https://arxiv.org/abs/{paper_id}",
                    "pdf_url": local_pdf_url or f"https://arxiv.org/pdf/{paper_id}",
                }
    except Exception:
        pass

    # --- Fallback: file_collect ---
    fc_root = os.path.join(_DATA_ROOT, "file_collect")
    if not os.path.isdir(fc_root):
        return None

    for date_dir in sorted(os.listdir(fc_root), reverse=True):
        paper_dir = os.path.join(fc_root, date_dir, paper_id)
        if not os.path.isdir(paper_dir):
            continue

        limit_path = _find_limit_md(paper_dir, paper_id)
        if limit_path is None:
            continue
        md_text = _read_text(limit_path)
        if md_text is None:
            continue

        data = _parse_limit_md(md_text, paper_id)

        pdf_info = _read_json(os.path.join(paper_dir, "pdf_info.json"))
        if pdf_info:
            if pdf_info.get("instution"):
                data["institution"] = pdf_info["instution"]
            is_large = pdf_info.get("is_large", False)
            data["is_large_institution"] = is_large
            data["abstract"] = pdf_info.get("abstract", "")
            raw_tier = pdf_info.get("institution_tier")
            if raw_tier is not None:
                try:
                    t = int(raw_tier)
                    data["institution_tier"] = t if 1 <= t <= 4 else (3 if is_large else 4)
                except (TypeError, ValueError):
                    data["institution_tier"] = 3 if is_large else 4
            else:
                data["institution_tier"] = 3 if is_large else 4

        images = _list_paper_images(paper_dir)

        assets_data = _load_paper_assets(date_dir)
        paper_assets = assets_data.get(paper_id)

        theme_scores = _load_theme_scores(date_dir)
        if theme_scores:
            data["relevance_score"] = theme_scores.get(paper_id)

        local_pdf_url = _find_local_pdf_url(paper_id)
        return {
            "summary": data,
            "paper_assets": paper_assets,
            "date": date_dir,
            "images": images,
            "arxiv_url": f"https://arxiv.org/abs/{paper_id}",
            "pdf_url": local_pdf_url or f"https://arxiv.org/pdf/{paper_id}",
        }

    return None


def get_daily_digest(date: str, user_id: int = 0) -> dict:
    """
    Build a daily digest. Checks DB first, falls back to file_collect.
    Includes a `notice` field when the pipeline ran but produced 0 papers.
    """
    papers = get_papers_by_date(date, user_id=user_id)
    total = len(papers)

    # Institution distribution
    institutions = [p.get("institution", "未知") for p in papers]
    inst_counter = Counter(institutions)
    inst_distribution = [
        {"name": name, "count": count}
        for name, count in inst_counter.most_common()
    ]

    # Count large institution papers
    large_count = sum(
        1 for p in papers if p.get("is_large_institution", False)
    )

    # Tier distribution: count papers per tier level
    tier_counter: dict = {}
    for p in papers:
        t = p.get("institution_tier") or 4
        tier_counter[t] = tier_counter.get(t, 0) + 1
    tier_distribution = [
        {"tier": t, "count": tier_counter[t]}
        for t in sorted(tier_counter.keys())
    ]

    # Average relevance score
    scores = [
        p["relevance_score"] for p in papers
        if p.get("relevance_score") is not None
    ]
    avg_score = sum(scores) / len(scores) if scores else None

    # When no papers exist, check if a notice explains why
    notice = None
    if total == 0:
        try:
            from services.pipeline_db_service import get_date_notice
            notice = get_date_notice(user_id, date)
            # Also try user_id=0 (shared/default pipeline notice)
            if notice is None and user_id != 0:
                notice = get_date_notice(0, date)
        except Exception:
            pass

    return {
        "date": date,
        "total_papers": total,
        "large_institution_count": large_count,
        "avg_relevance_score": round(avg_score, 3) if avg_score is not None else None,
        "institution_distribution": inst_distribution,
        "tier_distribution": tier_distribution,
        "papers": papers,
        "notice": notice,
    }


def get_pipeline_status(date: str) -> list[dict]:
    """Check which pipeline steps have completed for a given date."""
    step_outputs = {
        "arxiv_search": os.path.join(_DATA_ROOT, "arxivList", "md", f"{date}.md"),
        "paperList_remove_duplications": os.path.join(_DATA_ROOT, "paperList_remove_duplications", f"{date}.json"),
        "llm_select_theme": os.path.join(_DATA_ROOT, "llm_select_theme", f"{date}.json"),
        "paper_theme_filter": os.path.join(_DATA_ROOT, "paper_theme_filter", f"{date}.json"),
        "pdf_download": os.path.join(_DATA_ROOT, "raw_pdf", date, "_manifest.json"),
        "pdf_split": os.path.join(_DATA_ROOT, "preview_pdf", date, "_manifest.json"),
        "pdfsplite_to_minerU": os.path.join(_DATA_ROOT, "preview_pdf_to_mineru", date, "_manifest.json"),
        "pdf_info": os.path.join(_DATA_ROOT, "pdf_info", f"{date}.json"),
        "instutions_filter": os.path.join(_DATA_ROOT, "instutions_filter", date, f"{date}.json"),
        "selectpaper": os.path.join(_DATA_ROOT, "selectedpaper", date, "_manifest.json"),
        "selectedpaper_to_mineru": os.path.join(_DATA_ROOT, "selectedpaper_to_mineru", date, "_manifest.json"),
        "paper_summary": os.path.join(_DATA_ROOT, "paper_summary", "single", date),
        "summary_limit": os.path.join(_DATA_ROOT, "summary_limit", "single", date),
        "select_image": os.path.join(_DATA_ROOT, "select_image", date, f"select_image_{date}.json"),
        "file_collect": os.path.join(_DATA_ROOT, "file_collect", date),
        "paper_assets": os.path.join(_DATA_ROOT, "paper_assets", f"{date}.jsonl"),
    }

    steps_order = [
        "arxiv_search", "paperList_remove_duplications", "llm_select_theme",
        "paper_theme_filter", "pdf_download", "pdf_split",
        "pdfsplite_to_minerU", "pdf_info", "instutions_filter",
        "selectpaper", "selectedpaper_to_mineru", "paper_summary",
        "summary_limit", "select_image", "file_collect", "paper_assets",
    ]

    result = []
    for step in steps_order:
        path = step_outputs[step]
        done = os.path.isfile(path) or os.path.isdir(path)
        result.append({"step": step, "completed": done})
    return result


# ---------------------------------------------------------------------------
# Internal helpers for secondary data sources
# ---------------------------------------------------------------------------

def _list_paper_images_from_select_image(paper_id: str, date: str) -> list[str]:
    """
    Read image filenames for a paper from DB (pipeline_images) first,
    then fall back to scanning the select_image directory on disk.
    """
    # 1. Try DB first
    try:
        from services.pipeline_db_service import get_paper_images
        db_result = get_paper_images(date, paper_id)
        if db_result and paper_id in db_result:
            return db_result[paper_id]
    except Exception:
        pass

    # 2. Scan directory directly (images are at select_image/{date}/{paper_id}/)
    paper_img_dir = os.path.join(_DATA_ROOT, "select_image", date, paper_id)
    if os.path.isdir(paper_img_dir):
        imgs = sorted(
            f for f in os.listdir(paper_img_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
        )
        if imgs:
            return imgs

    # 3. Legacy: try the summary JSON (old format had per-paper entries)
    select_img_json = os.path.join(_DATA_ROOT, "select_image", date, f"select_image_{date}.json")
    if not os.path.isfile(select_img_json):
        return []
    data = _read_json(select_img_json)
    if not isinstance(data, dict):
        return []
    paper_entry = data.get(paper_id) or data.get(f"{paper_id}.pdf") or {}
    if isinstance(paper_entry, list):
        return [os.path.basename(p) for p in paper_entry]
    if isinstance(paper_entry, dict):
        imgs = paper_entry.get("images", [])
        return [os.path.basename(p) for p in imgs] if isinstance(imgs, list) else []
    return []


def _load_theme_scores(date: str) -> dict[str, float]:
    """Load relevance scores from llm_select_theme JSON."""
    path = os.path.join(_DATA_ROOT, "llm_select_theme", f"{date}.json")
    data = _read_json(path)
    if data is None:
        return {}
    papers_list = []
    if isinstance(data, dict):
        papers_list = data.get("papers", [])
    elif isinstance(data, list):
        papers_list = data

    scores: dict[str, float] = {}
    for item in papers_list:
        if not isinstance(item, dict):
            continue
        pid = item.get("arxiv_id", item.get("source", ""))
        score = item.get("theme_relevant_score", item.get("score"))
        if pid and score is not None:
            try:
                scores[pid] = float(score)
            except (ValueError, TypeError):
                pass
    return scores


def _load_paper_assets(date: str) -> dict[str, dict]:
    """Load paper assets JSONL, indexed by paper_id."""
    path = os.path.join(_DATA_ROOT, "paper_assets", f"{date}.jsonl")
    items = _read_jsonl(path)
    result = {}
    for item in items:
        pid = item.get("paper_id", "")
        if pid:
            result[pid] = item
    return result
