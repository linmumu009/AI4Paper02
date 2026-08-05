"""
Task Center Service

Aggregates long-running task status from multiple data sources into a unified
list of TaskCenterItem dicts.  This layer is read-only: it never modifies task
state.  Action dispatching (retry/cancel/continue) lives in the router so that
routing concerns are separated from aggregation logic.

Data sources:
  - kb_papers      : KB process / translate / classify status
  - user_uploaded_papers : user-paper process / translate status
  - pipeline_runs  : admin pipeline runs (admin-only by default)
  - research_sessions : deep-research session status (running/error)

ID scheme:
  kb_process:<scope>:<paper_id>
  kb_translate:<scope>:<paper_id>
  kb_classify:<scope>:<paper_id>
  user_paper_process:<paper_id>
  user_paper_translate:<paper_id>
  pipeline_run:<run_id>
  deep_research:<session_id>
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Translate tasks stuck in 'processing' for longer than this are treated as stale.
_STALE_TRANSLATE_MINUTES = 10


def _is_stale(updated_at_str: str | None) -> bool:
    """Return True when updated_at is more than _STALE_TRANSLATE_MINUTES ago."""
    if not updated_at_str:
        return False
    try:
        ts = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - ts > timedelta(minutes=_STALE_TRANSLATE_MINUTES)
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Status mappers
# ---------------------------------------------------------------------------

_KB_PROCESS_STATUS_MAP = {
    "none": "none",
    "pending": "pending",
    "processing": "running",
    "completed": "completed",
    "failed": "failed",
}

_KB_TRANSLATE_STATUS_MAP = {
    "none": "none",
    "processing": "running",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
}

_KB_CLASSIFY_STATUS_MAP = {
    "none": "none",
    "pending": "pending",
    "running": "running",
    "done": "completed",
    "failed": "failed",
    "skipped": "skipped",
}

_PIPELINE_STATUS_MAP = {
    "pending": "pending",
    "running": "running",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
}

_RESEARCH_STATUS_MAP = {
    "running": "running",
    "done": "completed",
    "error": "failed",
    "pending": "pending",
}


def _map_status(raw: str, mapping: dict) -> str:
    return mapping.get(raw or "none", "none")


# ---------------------------------------------------------------------------
# Action computation
# ---------------------------------------------------------------------------

def _kb_process_actions(status: str) -> list[str]:
    if status in ("none", "failed"):
        return ["retry", "view"]
    if status in ("pending", "processing"):
        return ["view"]
    if status == "completed":
        return ["view"]
    return ["view"]


def _kb_translate_actions(status: str, stale: bool = False) -> list[str]:
    if status in ("none", "failed", "cancelled"):
        return ["retry", "view"]
    if status == "processing":
        return ["cancel", "view"] if not stale else ["retry", "view"]
    if status == "completed":
        return ["retry", "view"]
    return ["view"]


def _kb_classify_actions(status: str) -> list[str]:
    if status in ("none", "failed", "skipped"):
        return ["retry", "view"]
    if status in ("pending", "running"):
        return ["view"]
    if status == "done":
        return ["view"]
    return ["view"]


def _pipeline_actions(status: str, is_admin: bool) -> list[str]:
    # retry/cancel/continue for pipeline_run all redirect to /api/admin/pipeline/*
    # and return 422 via the task router — expose only "view" to avoid dead buttons.
    return ["view"]


def _research_actions(status: str) -> list[str]:
    # cancel and continue via the task router return 422 for deep_research;
    # resuming a session requires submitting a new question in the research page.
    return ["view"]


# ---------------------------------------------------------------------------
# Title helpers
# ---------------------------------------------------------------------------

def _paper_title(paper_data: object, paper_id: str) -> str:
    """Extract a display title from a kb_papers or user_paper row."""
    if isinstance(paper_data, dict):
        return (
            paper_data.get("short_title")
            or paper_data.get("📖标题")
            or paper_data.get("title")
            or paper_id
        )
    return paper_id


# ---------------------------------------------------------------------------
# Item builders
# ---------------------------------------------------------------------------

def _build_kb_items(user_id: int, scope: str, include_completed: bool) -> list[dict]:
    """Return TaskCenterItem dicts for KB tasks."""
    try:
        import services.kb_service as kbs
        papers = kbs.list_papers_with_active_tasks(user_id, scope=scope, include_completed=include_completed)
    except Exception as exc:
        logger.warning("task_center: failed to load KB papers: %s", exc)
        return []

    items: list[dict] = []
    for paper in papers:
        pid = paper.get("paper_id", "")
        paper_data = paper.get("paper_data", {})
        title = _paper_title(paper_data, pid)

        # --- process task ---
        proc_raw = paper.get("process_status", "none")
        if proc_raw != "none" and (include_completed or proc_raw in ("pending", "processing", "failed")):
            mapped = _map_status(proc_raw, _KB_PROCESS_STATUS_MAP)
            items.append({
                "id": f"kb_process:{scope}:{pid}",
                "kind": "kb_process",
                "status": mapped,
                "title": title,
                "subtitle": f"KB 论文解析",
                "entity_id": pid,
                "entity_type": "paper",
                "step": paper.get("process_step") or "",
                "progress": None,
                "error": paper.get("process_error") or "",
                "created_at": paper.get("created_at"),
                "updated_at": paper.get("updated_at"),
                "actions": _kb_process_actions(proc_raw),
                "source": "kb",
            })

        # --- translate task ---
        trans_raw = paper.get("translate_status", "none")
        if trans_raw != "none" and (include_completed or trans_raw in ("processing", "failed", "cancelled")):
            stale = trans_raw == "processing" and _is_stale(paper.get("updated_at"))
            mapped = "failed" if stale else _map_status(trans_raw, _KB_TRANSLATE_STATUS_MAP)
            items.append({
                "id": f"kb_translate:{scope}:{pid}",
                "kind": "kb_translate",
                "status": mapped,
                "title": title,
                "subtitle": "KB 论文翻译",
                "entity_id": pid,
                "entity_type": "paper",
                "step": None,
                "progress": paper.get("translate_progress"),
                "error": "任务已卡住（超时无响应），请重试" if stale else (paper.get("translate_error") or ""),
                "created_at": paper.get("created_at"),
                "updated_at": paper.get("updated_at"),
                "actions": _kb_translate_actions(trans_raw, stale=stale),
                "source": "kb",
            })

        # --- classify task ---
        classify_raw = paper.get("classify_status", "none")
        if classify_raw != "none" and (
            include_completed
            or classify_raw in ("pending", "running", "failed")
        ):
            mapped = _map_status(classify_raw, _KB_CLASSIFY_STATUS_MAP)
            items.append({
                "id": f"kb_classify:{scope}:{pid}",
                "kind": "kb_classify",
                "status": mapped,
                "title": title,
                "subtitle": "KB 自动分类",
                "entity_id": pid,
                "entity_type": "paper",
                "step": None,
                "progress": None,
                "error": paper.get("classify_error") or "",
                "created_at": paper.get("created_at"),
                "updated_at": paper.get("updated_at"),
                "actions": _kb_classify_actions(classify_raw),
                "source": "kb",
            })

    return items


def _build_user_paper_items(user_id: int, include_completed: bool) -> list[dict]:
    """Return TaskCenterItem dicts for user-uploaded paper tasks."""
    try:
        import services.user_paper_service as ups
        papers = ups.list_papers_with_active_tasks(user_id, include_completed=include_completed)
    except Exception as exc:
        logger.warning("task_center: failed to load user papers: %s", exc)
        return []

    items: list[dict] = []
    for paper in papers:
        pid = paper.get("paper_id", "")
        title = paper.get("title") or pid

        proc_raw = paper.get("process_status", "none")
        if proc_raw != "none" and (include_completed or proc_raw in ("pending", "processing", "failed")):
            mapped = _map_status(proc_raw, _KB_PROCESS_STATUS_MAP)
            items.append({
                "id": f"user_paper_process:{pid}",
                "kind": "user_paper_process",
                "status": mapped,
                "title": title,
                "subtitle": "我的论文解析",
                "entity_id": pid,
                "entity_type": "paper",
                "step": paper.get("process_step") or "",
                "progress": None,
                "error": paper.get("process_error") or "",
                "created_at": paper.get("created_at"),
                "updated_at": paper.get("updated_at"),
                "actions": _kb_process_actions(proc_raw),
                "source": "my_papers",
            })

        trans_raw = paper.get("translate_status", "none")
        if trans_raw and trans_raw != "none" and (
            include_completed or trans_raw in ("processing", "failed", "cancelled")
        ):
            stale = trans_raw == "processing" and _is_stale(paper.get("updated_at"))
            mapped = "failed" if stale else _map_status(trans_raw, _KB_TRANSLATE_STATUS_MAP)
            items.append({
                "id": f"user_paper_translate:{pid}",
                "kind": "user_paper_translate",
                "status": mapped,
                "title": title,
                "subtitle": "我的论文翻译",
                "entity_id": pid,
                "entity_type": "paper",
                "step": None,
                "progress": paper.get("translate_progress"),
                "error": "任务已卡住（超时无响应），请重试" if stale else (paper.get("translate_error") or ""),
                "created_at": paper.get("created_at"),
                "updated_at": paper.get("updated_at"),
                "actions": _kb_translate_actions(trans_raw, stale=stale),
                "source": "my_papers",
            })

    return items


def _build_pipeline_items(user_id: int, is_admin: bool, limit: int = 20) -> list[dict]:
    """Return TaskCenterItem dicts for pipeline runs (admin-filtered)."""
    if not is_admin:
        return []
    try:
        from services import pipeline_db_service as pdb
        runs = pdb.get_runs_recent(limit=limit)
    except Exception as exc:
        logger.warning("task_center: failed to load pipeline runs: %s", exc)
        return []

    items: list[dict] = []
    for run in runs:
        raw_status = run.get("status", "pending")
        mapped = _map_status(raw_status, _PIPELINE_STATUS_MAP)
        phase = run.get("phase") or run.get("run_type") or ""
        phase_label = {"shared": "共享", "per_user": f"用户{run.get('user_id', '')}", "orchestrator": "编排"}.get(phase, phase)
        items.append({
            "id": f"pipeline_run:{run['id']}",
            "kind": "pipeline_run",
            "status": mapped,
            "title": f"Pipeline {run.get('pipeline', '')} [{run.get('date_str', '')}]",
            "subtitle": phase_label or None,
            "entity_id": str(run["id"]),
            "entity_type": "run",
            "step": None,
            "progress": None,
            "error": run.get("error") or "",
            "created_at": run.get("created_at"),
            "updated_at": run.get("finished_at") or run.get("started_at"),
            "actions": _pipeline_actions(raw_status, is_admin),
            "source": "admin_pipeline",
        })

    return items


def _build_research_items(user_id: int, include_completed: bool) -> list[dict]:
    """Return TaskCenterItem dicts for deep-research sessions."""
    try:
        from services import research_service as rs
        sessions = rs.list_sessions(user_id, limit=20)
    except Exception as exc:
        logger.warning("task_center: failed to load research sessions: %s", exc)
        return []

    items: list[dict] = []
    for sess in sessions:
        raw_status = sess.get("status", "pending")
        # Only show running/error sessions unless include_completed
        if not include_completed and raw_status not in ("running", "error"):
            continue
        mapped = _map_status(raw_status, _RESEARCH_STATUS_MAP)
        question = sess.get("question") or ""
        items.append({
            "id": f"deep_research:{sess['id']}",
            "kind": "deep_research",
            "status": mapped,
            "title": question[:80] if question else f"深度研究 #{sess['id']}",
            "subtitle": "深度研究",
            "entity_id": str(sess["id"]),
            "entity_type": "research_session",
            "step": None,
            "progress": None,
            "error": "",
            "created_at": sess.get("created_at"),
            "updated_at": sess.get("updated_at"),
            "actions": _research_actions(raw_status),
            "source": "research",
        })

    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _build_summary(items: list[dict]) -> dict:
    running = sum(1 for i in items if i["status"] == "running")
    pending = sum(1 for i in items if i["status"] == "pending")
    failed = sum(1 for i in items if i["status"] == "failed")
    return {
        "running_count": running,
        "pending_count": pending,
        "failed_count": failed,
        "total_active": running + pending,
    }


def get_tasks(
    user_id: int,
    *,
    status_filter: Optional[str] = None,
    kind_filter: Optional[str] = None,
    limit: int = 100,
    is_admin: bool = False,
    include_completed: bool = False,
) -> dict:
    """Return aggregated task list + summary for a user.

    status_filter: 'active' | 'pending' | 'running' | 'failed' | 'completed' | None
    kind_filter:   one of the TaskKind string values, or None for all
    """
    items: list[dict] = []

    items.extend(_build_kb_items(user_id, "kb", include_completed))
    items.extend(_build_user_paper_items(user_id, include_completed))
    items.extend(_build_research_items(user_id, include_completed))
    if is_admin:
        items.extend(_build_pipeline_items(user_id, is_admin, limit=30))

    # Apply filters
    if status_filter == "active":
        items = [i for i in items if i["status"] in ("pending", "running")]
    elif status_filter:
        items = [i for i in items if i["status"] == status_filter]

    if kind_filter:
        items = [i for i in items if i["kind"] == kind_filter]

    # Sort: running first, then pending, then failed, then rest
    _order = {"running": 0, "pending": 1, "failed": 2, "completed": 3, "skipped": 4, "cancelled": 5, "none": 6}
    items.sort(key=lambda i: _order.get(i["status"], 9))

    if limit:
        items = items[:limit]

    return {"items": items, "summary": _build_summary(items)}


def get_summary(user_id: int, *, is_admin: bool = False) -> dict:
    """Return only the summary counts (cheap path for badge counts)."""
    result = get_tasks(user_id, is_admin=is_admin)
    return result["summary"]
