"""
Task Center Router

Exposes a unified view of long-running tasks for the current user.

Routes (all prefixed with /api/tasks):
  GET  /tasks            – list tasks (query: status, kind, limit, include_completed)
  GET  /tasks/summary    – lightweight badge counts
  POST /tasks/{task_id}/retry    – retry a failed task
  POST /tasks/{task_id}/cancel   – cancel a running task (where supported)
  POST /tasks/{task_id}/continue – continue/resume a task (where supported)

task_id format: <kind>:<...parts>
  e.g. kb_process:kb:2403.12345
       pipeline_run:42
       deep_research:17
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from services import auth_service
from services.safe_logging_service import safe_failure_detail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_task_id(task_id: str) -> tuple[str, list[str]]:
    """Split 'kind:part1:part2' → (kind, [part1, part2])."""
    parts = task_id.split(":", 1)
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail=f"无效的 task_id: {task_id}")
    kind = parts[0]
    rest = parts[1].split(":")
    return kind, rest


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@router.get("", summary="List tasks for current user")
def api_list_tasks(
    status: Optional[str] = Query(default=None, description="active|pending|running|failed|completed"),
    kind: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    include_completed: bool = Query(default=False),
    _user=Depends(auth_service.require_user),
):
    from services import task_center_service as tcs
    is_admin = _user.get("role") in ("admin", "superadmin")

    return tcs.get_tasks(
        _user["id"],
        status_filter=status,
        kind_filter=kind,
        limit=limit,
        is_admin=is_admin,
        include_completed=include_completed,
    )


@router.get("/summary", summary="Get task badge counts for current user")
def api_task_summary(_user=Depends(auth_service.require_user)):
    from services import task_center_service as tcs
    is_admin = _user.get("role") in ("admin", "superadmin")
    return tcs.get_summary(_user["id"], is_admin=is_admin)


# ---------------------------------------------------------------------------
# Action endpoints
# ---------------------------------------------------------------------------

@router.post("/{task_id:path}/retry", summary="Retry a failed task")
def api_retry_task(task_id: str, _user=Depends(auth_service.require_user)):
    """Retry a failed task.  Only bridges to existing safe retry paths."""
    user_id = _user["id"]
    kind, parts = _parse_task_id(task_id)

    try:
        if kind == "kb_process":
            # parts: [scope, paper_id]
            if len(parts) < 2:
                raise HTTPException(status_code=400, detail="task_id 格式错误")
            scope, paper_id = parts[0], ":".join(parts[1:])
            from services import kb_pipeline_service
            ok, msg = kb_pipeline_service.start_kb_paper_process(user_id, paper_id, scope=scope)
            if not ok:
                raise HTTPException(status_code=400, detail=msg)
            return {"ok": True, "message": msg}

        elif kind == "kb_translate":
            if len(parts) < 2:
                raise HTTPException(status_code=400, detail="task_id 格式错误")
            scope, paper_id = parts[0], ":".join(parts[1:])
            from services import translate_service
            ok, msg = translate_service.start_kb_translation(user_id, paper_id, scope=scope)
            if not ok:
                raise HTTPException(status_code=400, detail=msg)
            return {"ok": True, "message": msg}

        elif kind == "kb_classify":
            if len(parts) < 2:
                raise HTTPException(status_code=400, detail="task_id 格式错误")
            scope, paper_id = parts[0], ":".join(parts[1:])
            from services import auto_classify_service, kb_service
            if not kb_service.is_paper_in_kb(user_id, paper_id, scope=scope):
                raise HTTPException(status_code=404, detail="论文不在知识库中")
            enqueued = auto_classify_service.enqueue_classify(user_id, paper_id, scope=scope)
            if not enqueued:
                if auto_classify_service.is_classifying(user_id, paper_id, scope=scope):
                    return {"ok": True, "message": "自动分类已在进行中"}
                from services.safe_logging_service import safe_stored_error

                paper = kb_service.get_kb_paper(user_id, paper_id, scope=scope) or {}
                raise HTTPException(
                    status_code=503,
                    detail=safe_stored_error(
                        paper.get("classify_error"),
                        "自动分类任务启动失败，请稍后重试",
                    ),
                )
            return {"ok": True, "message": "已重新加入分类队列"}

        elif kind == "user_paper_process":
            paper_id = ":".join(parts)
            from services import user_paper_pipeline_service
            ok, msg = user_paper_pipeline_service.start_processing(user_id, paper_id)
            if not ok:
                raise HTTPException(status_code=400, detail=msg)
            return {"ok": True, "message": msg}

        elif kind == "user_paper_translate":
            paper_id = ":".join(parts)
            from services import translate_service
            ok, msg = translate_service.start_translation(user_id, paper_id)
            if not ok:
                raise HTTPException(status_code=400, detail=msg)
            return {"ok": True, "message": msg}

        elif kind == "pipeline_run":
            # Admin only – direct to the richer admin rerun endpoint
            is_admin = _user.get("role") in ("admin", "superadmin")
            if not is_admin:
                raise HTTPException(status_code=403, detail="仅管理员可以重跑 Pipeline")
            raise HTTPException(
                status_code=422,
                detail="Pipeline 重跑请使用 /api/admin/pipeline/rerun 接口（支持 from_step / only_step 参数）",
            )

        else:
            raise HTTPException(status_code=400, detail=f"不支持对 {kind} 任务执行重试")

    except HTTPException:
        raise
    except Exception as exc:
        public_error = safe_failure_detail(
            logger,
            "任务重试失败，请稍后再试",
            exc,
            operation="task_center_retry",
        )
        raise HTTPException(status_code=500, detail=public_error) from exc


@router.post("/{task_id:path}/cancel", summary="Cancel a running task")
def api_cancel_task(task_id: str, _user=Depends(auth_service.require_user)):
    """Cancel a running task."""
    user_id = _user["id"]
    kind, parts = _parse_task_id(task_id)

    is_admin = _user.get("role") in ("admin", "superadmin")

    try:
        if kind == "user_paper_translate":
            paper_id = ":".join(parts)
            from services import translate_service
            ok, msg = translate_service.cancel_translation(user_id, paper_id)
            if not ok:
                raise HTTPException(status_code=400, detail=msg)
            return {"ok": True, "message": msg}

        if kind == "kb_translate":
            if len(parts) < 2:
                raise HTTPException(status_code=400, detail="task_id 格式错误")
            scope, paper_id = parts[0], ":".join(parts[1:])
            from services import translate_service
            ok, msg = translate_service.cancel_kb_translation(user_id, paper_id, scope=scope)
            if not ok:
                raise HTTPException(status_code=400, detail=msg)
            return {"ok": True, "message": msg}

        if kind == "pipeline_run":
            if not is_admin:
                raise HTTPException(status_code=403, detail="仅管理员可以停止 Pipeline")
            raise HTTPException(
                status_code=422,
                detail="Pipeline 停止请使用 /api/admin/pipeline/stop 接口",
            )

        raise HTTPException(
            status_code=422,
            detail=f"{kind} 任务不支持取消操作",
        )
    except HTTPException:
        raise
    except Exception as exc:
        public_error = safe_failure_detail(
            logger,
            "任务取消失败，请稍后再试",
            exc,
            operation="task_center_cancel",
        )
        raise HTTPException(status_code=500, detail=public_error) from exc


@router.post("/{task_id:path}/continue", summary="Continue or resume a task")
def api_continue_task(task_id: str, _user=Depends(auth_service.require_user)):
    """Continue a paused/failed task where resume semantics exist."""
    user_id = _user["id"]
    kind, parts = _parse_task_id(task_id)

    if kind == "pipeline_run":
        raise HTTPException(
            status_code=422,
            detail="Pipeline 继续执行请使用 /api/admin/pipeline/rerun 接口（支持 from_step 参数）",
        )

    if kind == "deep_research":
        # Research continuation is handled by the research router's own session creation
        raise HTTPException(
            status_code=422,
            detail="深度研究继续请在研究页面重新提交问题，当前不支持从任务中心直接继续",
        )

    raise HTTPException(
        status_code=422,
        detail=f"{kind} 任务不支持继续操作",
    )
