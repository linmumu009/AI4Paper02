"""
Research Memory Service — aggregation layer for the knowledge base "Research Memory" feature.

Provides read-only views over idea_atoms and kb_papers:
  - get_paper_memory(user_id, paper_id)  → atoms grouped by type + metadata
  - get_memory_clusters(user_id, limit)  → tag-based topic clusters across all papers
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

# Reuse the same DB file as idea_service / kb_service
import os

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

# Display labels for each atom type
_ATOM_TYPE_LABELS: dict[str, str] = {
    "claim":      "核心论断",
    "method":     "方法",
    "setup":      "数据与设置",
    "limitation": "局限与机会",
    "tag":        "主题标签",
}

_ATOM_TYPE_ORDER = ["claim", "method", "setup", "limitation", "tag"]


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _atom_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.pop("tags_json", "[]"))
    d["evidence"] = json.loads(d.pop("evidence_json", "[]"))
    d.setdefault("confidence", 0.0)
    d.setdefault("status", "active")
    d.setdefault("source_scope", "kb")
    return d


# ---------------------------------------------------------------------------
# Paper-level memory
# ---------------------------------------------------------------------------

def get_paper_memory(user_id: int, paper_id: str) -> dict:
    """Return atoms grouped by type for a specific paper.

    Response shape::

        {
          "paper_id": "...",
          "has_atoms": true,
          "atom_count": 12,
          "last_extracted_at": "2026-05-01T...",
          "groups": [
            {"type": "claim", "label": "核心论断", "atoms": [...]},
            ...
          ]
        }

    All groups are always present even when empty.
    Only 'active' atoms are returned (archived/hidden are excluded).
    """
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT * FROM idea_atoms
               WHERE user_id = ? AND paper_id = ? AND status = 'active'
               ORDER BY atom_type, created_at""",
            (user_id, paper_id),
        ).fetchall()
    finally:
        conn.close()

    atoms = [_atom_row_to_dict(r) for r in rows]

    # Group by type preserving display order
    by_type: dict[str, list[dict]] = {t: [] for t in _ATOM_TYPE_ORDER}
    last_extracted_at: Optional[str] = None
    for a in atoms:
        t = a.get("atom_type", "claim")
        bucket = by_type.get(t)
        if bucket is None:
            by_type[t] = bucket = []
        bucket.append(a)
        ts = a.get("created_at", "")
        if last_extracted_at is None or ts > last_extracted_at:
            last_extracted_at = ts

    groups = [
        {
            "type": t,
            "label": _ATOM_TYPE_LABELS.get(t, t),
            "atoms": by_type.get(t, []),
            "count": len(by_type.get(t, [])),
        }
        for t in _ATOM_TYPE_ORDER
    ]

    return {
        "paper_id": paper_id,
        "has_atoms": len(atoms) > 0,
        "atom_count": len(atoms),
        "last_extracted_at": last_extracted_at,
        "groups": groups,
    }


# ---------------------------------------------------------------------------
# Topic clusters (tag-overlap based)
# ---------------------------------------------------------------------------

def get_memory_clusters(user_id: int, limit: int = 20) -> list[dict]:
    """Return topic clusters derived from tag co-occurrence across papers.

    Algorithm:
      1. Load all active atoms with their tags and paper_id.
      2. Build a tag → set[paper_id] index.
      3. For each tag that appears in ≥2 papers, create a cluster candidate.
      4. Merge clusters that share >50% of paper_ids.
      5. Return top ``limit`` clusters sorted by paper_count desc.

    Each cluster::

        {
          "cluster_id": "tag:<tag_name>",
          "label": "<tag_name>",
          "paper_ids": [...],
          "paper_count": N,
          "atom_ids": [...],
          "top_tags": [...],
          "summary_snippet": "..."   # first atom content found
        }
    """
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT id, paper_id, atom_type, content, tags_json
               FROM idea_atoms
               WHERE user_id = ? AND status = 'active'""",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    # Build tag → list[(paper_id, atom_id, content)]
    tag_index: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for row in rows:
        paper_id = row["paper_id"]
        atom_id = row["id"]
        content = row["content"] or ""
        tags = json.loads(row["tags_json"] or "[]")
        for tag in tags:
            if tag and isinstance(tag, str):
                tag_index[tag.strip().lower()].append((paper_id, atom_id, content))

    # Build cluster candidates: tags with ≥2 distinct papers
    candidates: list[dict] = []
    for tag, entries in tag_index.items():
        paper_ids = list({e[0] for e in entries})
        if len(paper_ids) < 2:
            continue
        atom_ids = [e[1] for e in entries]
        snippet = next((e[2] for e in entries if e[2]), "")[:200]
        candidates.append({
            "label": tag,
            "paper_ids": paper_ids,
            "atom_ids": atom_ids,
            "snippet": snippet,
        })

    if not candidates:
        return []

    # Merge overlapping clusters (jaccard similarity > 0.5)
    candidates.sort(key=lambda c: len(c["paper_ids"]), reverse=True)
    merged: list[dict] = []
    used: set[int] = set()
    for i, c in enumerate(candidates):
        if i in used:
            continue
        cluster_papers = set(c["paper_ids"])
        cluster_tags = {c["label"]}
        cluster_atoms = list(c["atom_ids"])
        cluster_snippet = c["snippet"]
        for j, other in enumerate(candidates):
            if j <= i or j in used:
                continue
            other_papers = set(other["paper_ids"])
            intersection = cluster_papers & other_papers
            union = cluster_papers | other_papers
            if union and len(intersection) / len(union) > 0.5:
                cluster_papers |= other_papers
                cluster_tags.add(other["label"])
                cluster_atoms += other["atom_ids"]
                used.add(j)
        merged.append({
            "paper_ids": list(cluster_papers),
            "top_tags": sorted(cluster_tags)[:5],
            "atom_ids": list(set(cluster_atoms)),
            "snippet": cluster_snippet,
        })

    # Sort by paper count desc, truncate
    merged.sort(key=lambda c: len(c["paper_ids"]), reverse=True)
    result = []
    for idx, c in enumerate(merged[:limit]):
        top_tag = c["top_tags"][0] if c["top_tags"] else f"cluster_{idx}"
        result.append({
            "cluster_id": f"tag:{top_tag}",
            "label": top_tag,
            "paper_ids": c["paper_ids"],
            "paper_count": len(c["paper_ids"]),
            "atom_ids": c["atom_ids"][:20],
            "top_tags": c["top_tags"],
            "summary_snippet": c["snippet"],
        })
    return result
