"""
Shared paper-file helpers used by multiple services (compare, research, …).

All functions that need to locate a paper's directory in ``data/file_collect/``
or read a specific file for that paper belong here.  Import this module instead
of duplicating the logic per service.

Public API
----------
find_paper_dir(paper_id) -> str | None
    Locate the directory for *paper_id* under ``data/file_collect/``.

read_paper_file(path) -> str | None
    Read a UTF-8 text file; return None on error or missing file.

load_summary(paper_id) -> str | None
    Load the AI summary markdown ({paper_id}_summary.md).

load_mineru(paper_id) -> str | None
    Load the MinerU full-text markdown ({paper_id}_mineru.md).

load_source_content(paper_id, data_source) -> str | None
    Dispatch to the right file based on *data_source* value:
    "full_text" → mineru md, "summary" → summary md, "abstract" → pdf_info.json.
"""

from __future__ import annotations

import json
import os
from typing import Optional

_SEVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FILE_COLLECT_DIR = os.path.join(_SEVER_ROOT, "data", "file_collect")


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def find_paper_dir(paper_id: str) -> Optional[str]:
    """Search all date directories under file_collect/ for a paper_id folder.

    Returns the absolute path to the paper directory, or None.
    Path-traversal characters in *paper_id* are rejected for safety.
    """
    if ".." in paper_id or "/" in paper_id or "\\" in paper_id or "\x00" in paper_id:
        return None
    if not os.path.isdir(_FILE_COLLECT_DIR):
        return None
    for date_dir in sorted(os.listdir(_FILE_COLLECT_DIR), reverse=True):
        paper_dir = os.path.join(_FILE_COLLECT_DIR, date_dir, paper_id)
        if os.path.isdir(paper_dir):
            return paper_dir
    return None


def read_paper_file(path: str) -> Optional[str]:
    """Read a UTF-8 text file.  Returns None if the file does not exist or cannot be read."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Higher-level loaders
# ---------------------------------------------------------------------------

def load_summary(paper_id: str) -> Optional[str]:
    """Load AI summary markdown ({paper_id}_summary.md) for *paper_id*."""
    paper_dir = find_paper_dir(paper_id)
    if paper_dir:
        return read_paper_file(os.path.join(paper_dir, f"{paper_id}_summary.md"))
    return None


def load_mineru(paper_id: str) -> Optional[str]:
    """Load MinerU full-text markdown ({paper_id}_mineru.md) for *paper_id*."""
    paper_dir = find_paper_dir(paper_id)
    if paper_dir:
        return read_paper_file(os.path.join(paper_dir, f"{paper_id}_mineru.md"))
    return None


def load_source_content(paper_id: str, data_source: str) -> Optional[str]:
    """Load content for a paper based on *data_source*.

    data_source values:
      - ``"full_text"`` → read ``{paper_id}_mineru.md``
      - ``"abstract"``  → read ``pdf_info.json`` → ``abstract`` field
      - ``"summary"``   → read ``{paper_id}_summary.md``
    """
    paper_dir = find_paper_dir(paper_id)
    if not paper_dir:
        return None

    if data_source == "full_text":
        return read_paper_file(os.path.join(paper_dir, f"{paper_id}_mineru.md"))

    if data_source == "abstract":
        path = os.path.join(paper_dir, "pdf_info.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                info = json.load(f)
            return info.get("abstract") or None
        except Exception:
            return None

    if data_source == "summary":
        return read_paper_file(os.path.join(paper_dir, f"{paper_id}_summary.md"))

    return None
