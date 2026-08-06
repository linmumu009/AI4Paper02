"""Reconcile database task states left behind by terminated daemon workers.

The API currently runs several user-triggered jobs in daemon threads.  A
process restart terminates those workers, while their database rows can remain
``pending`` or ``processing`` forever.  Paid or external work is not replayed
automatically; instead, startup converts only active orphan states to an
explicit, retryable failure and preserves every completed artifact.
"""

from __future__ import annotations

from datetime import datetime, timezone


_INTERRUPTED_ERROR = "服务重启导致任务中断，请重新尝试"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_rowcount(cursor) -> int:
    try:
        return max(0, int(cursor.rowcount))
    except (AttributeError, TypeError, ValueError):
        return 0


def _reconcile_user_paper_tasks() -> dict[str, int]:
    from services import user_paper_service

    now = _now_iso()
    conn = user_paper_service._connect()
    try:
        process_cursor = conn.execute(
            """
            UPDATE user_uploaded_papers
            SET process_status='failed', process_step='interrupted',
                process_error=?, process_finished_at=?, updated_at=?
            WHERE process_status IN ('pending', 'processing')
            """,
            (_INTERRUPTED_ERROR, now, now),
        )
        translate_cursor = conn.execute(
            """
            UPDATE user_uploaded_papers
            SET translate_status='failed', translate_error=?,
                translate_finished_at=?, updated_at=?
            WHERE translate_status='processing'
            """,
            (_INTERRUPTED_ERROR, now, now),
        )
        conn.commit()
        return {
            "user_paper_process": _safe_rowcount(process_cursor),
            "user_paper_translate": _safe_rowcount(translate_cursor),
        }
    finally:
        conn.close()


def _reconcile_kb_paper_tasks() -> dict[str, int]:
    from services import kb_service

    conn = kb_service._connect()
    try:
        process_cursor = conn.execute(
            """
            UPDATE kb_papers
            SET process_status='failed', process_step='interrupted', process_error=?
            WHERE process_status IN ('pending', 'processing')
            """,
            (_INTERRUPTED_ERROR,),
        )
        translate_cursor = conn.execute(
            """
            UPDATE kb_papers
            SET translate_status='failed', translate_error=?
            WHERE translate_status='processing'
            """,
            (_INTERRUPTED_ERROR,),
        )
        conn.commit()
        return {
            "kb_paper_process": _safe_rowcount(process_cursor),
            "kb_paper_translate": _safe_rowcount(translate_cursor),
        }
    finally:
        conn.close()


def _reconcile_research_sessions() -> dict[str, int]:
    from services import research_service

    conn = research_service._connect()
    try:
        cursor = conn.execute(
            "UPDATE research_sessions SET status='error', updated_at=? "
            "WHERE status='running'",
            (_now_iso(),),
        )
        conn.commit()
        return {"research_sessions": _safe_rowcount(cursor)}
    finally:
        conn.close()


def reconcile_interrupted_tasks() -> dict[str, int]:
    """Mark every orphaned daemon-backed task as failed and return counts."""
    counts = {
        **_reconcile_user_paper_tasks(),
        **_reconcile_kb_paper_tasks(),
        **_reconcile_research_sessions(),
    }
    counts["total"] = sum(counts.values())
    return counts
