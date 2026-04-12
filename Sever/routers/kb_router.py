"""
Knowledge Base Router.

All routes are prefixed with /api/kb and registered in api.py via
    app.include_router(kb_router)
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from services import auth_service, compare_service, engagement_service, entitlement_service, kb_pipeline_service, kb_service, translate_service, auto_classify_service
from routers._deps import _KB_FILES_DIR

router = APIRouter(prefix="/api/kb", tags=["kb"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateFolderBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    parent_id: Optional[int] = None
    scope: str = Field(default="kb", pattern="^(kb|idea_library)$")


class RenameFolderBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scope: str = Field(default="kb", pattern="^(kb|idea_library)$")


class AddPaperBody(BaseModel):
    paper_id: str = Field(..., min_length=1, max_length=64)
    paper_data: dict
    folder_id: Optional[int] = None
    scope: str = Field(default="kb", pattern="^(kb|idea_library)$")


class MoveFolderBody(BaseModel):
    target_parent_id: Optional[int] = None
    scope: str = Field(default="kb", pattern="^(kb|idea_library)$")


class MovePapersBody(BaseModel):
    paper_ids: list[str] = Field(..., max_length=100)
    target_folder_id: Optional[int] = None
    scope: str = Field(default="kb", pattern="^(kb|idea_library)$")


class RenamePaperBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    scope: str = Field(default="kb", pattern="^(kb|idea_library)$")


class CreateNoteBody(BaseModel):
    title: str = Field(default="未命名笔记", max_length=256)
    content: str = Field(default="", max_length=500000)
    scope: str = Field(default="kb", pattern="^(kb|idea_library)$")


class UpdateNoteBody(BaseModel):
    title: Optional[str] = Field(None, max_length=256)
    content: Optional[str] = Field(None, max_length=500000)


class AddLinkBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    url: str = Field(..., min_length=1, max_length=2048)
    scope: str = Field(default="kb", pattern="^(kb|idea_library)$")


class ComparePapersBody(BaseModel):
    paper_ids: list[str] = Field(default=[], min_length=0, max_length=10)
    scope: str = "kb"
    compare_result_ids: list[int] = Field(default_factory=list)
    reward_id: Optional[int] = Field(default=None, description="Engagement reward ID to apply a compare boost")


class DismissPaperBody(BaseModel):
    paper_id: str


class RenamePaperBody(BaseModel):
    title: str
    scope: str = "kb"


class SaveCompareResultBody(BaseModel):
    title: str
    markdown: str
    paper_ids: list[str]
    folder_id: Optional[int] = None


class RenameCompareResultBody(BaseModel):
    title: str


class MoveCompareResultBody(BaseModel):
    target_folder_id: Optional[int] = None


class CreateAnnotationBody(BaseModel):
    page: int
    type: str = "highlight"
    content: str = ""
    color: str = "#FFFF00"
    position_data: str = ""
    scope: str = "kb"


class UpdateAnnotationBody(BaseModel):
    content: Optional[str] = None
    color: Optional[str] = None


# ---------------------------------------------------------------------------
# Enrichment helpers
# ---------------------------------------------------------------------------

def _enrich_kb_paper(p: dict, user_id: int) -> dict:
    paper_id = p.get("paper_id", "")
    kb_root = os.path.normpath(_KB_FILES_DIR)

    def _kb_static(abs_path: str) -> str | None:
        if not os.path.isfile(abs_path):
            return None
        rel = os.path.relpath(abs_path, kb_root).replace("\\", "/")
        return f"/static/kb_files/{rel}"

    pdf_abs = os.path.join(_KB_FILES_DIR, str(user_id), paper_id, f"{paper_id}.pdf")
    p["pdf_static_url"] = _kb_static(pdf_abs)

    try:
        paths = translate_service.kb_paper_derivative_paths(user_id, paper_id)
        p["mineru_static_url"] = (
            _kb_static(paths["mineru_normalized"])
            or _kb_static(paths["mineru"])
        )
        p["zh_static_url"] = _kb_static(paths["zh"])
        p["bilingual_static_url"] = _kb_static(paths["bilingual"])
    except Exception as _exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("KB paper enrichment failed for %s: %s", p.get("paper_id"), _exc)
        p["mineru_static_url"] = None
        p["zh_static_url"] = None
        p["bilingual_static_url"] = None

    return p


def _enrich_kb_tree(tree: dict, user_id: int) -> dict:
    def _walk(folder: dict) -> None:
        for paper in folder.get("papers") or []:
            _enrich_kb_paper(paper, user_id)
        for child in folder.get("children") or []:
            _walk(child)

    for paper in tree.get("papers") or []:
        _enrich_kb_paper(paper, user_id)
    for folder in tree.get("folders") or []:
        _walk(folder)
    return tree


# ---------------------------------------------------------------------------
# KB tree short-TTL cache (reduces O(N) filesystem I/O for large KBs)
# ---------------------------------------------------------------------------

import threading as _threading
import time as _time

_TREE_CACHE: dict = {}
_TREE_CACHE_TTL = 15  # seconds — enough to absorb rapid successive loads
_tree_cache_lock = _threading.Lock()


def _get_tree_cached(user_id: int, scope: str) -> dict:
    """Return cached enriched KB tree if fresh, else rebuild and cache it."""
    key = (user_id, scope)
    now = _time.monotonic()
    with _tree_cache_lock:
        entry = _TREE_CACHE.get(key)
        if entry and (now - entry["ts"]) < _TREE_CACHE_TTL:
            return entry["data"]
    tree = kb_service.get_tree(user_id, scope=scope)
    enriched = _enrich_kb_tree(tree, user_id)
    with _tree_cache_lock:
        _TREE_CACHE[key] = {"data": enriched, "ts": _time.monotonic()}
    return enriched


def _invalidate_tree_cache(user_id: int, scope: str = "kb") -> None:
    """Call after any write that modifies the tree (add/remove paper, folder ops)."""
    for s in (scope, "idea_library"):
        key = (user_id, s)
        with _tree_cache_lock:
            _TREE_CACHE.pop(key, None)


# ---------------------------------------------------------------------------
# Tree / folders / papers
# ---------------------------------------------------------------------------

@router.get("/tree", summary="Get knowledge base tree")
def api_kb_tree(scope: str = Query("kb", pattern="^(kb|idea_library)$"), _user=Depends(auth_service.require_user)):
    return _get_tree_cached(_user["id"], scope)


@router.get("/papers/{paper_id}/exists", summary="Check if paper is in KB")
def api_kb_paper_exists(
    paper_id: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    return {"exists": kb_service.is_paper_in_kb(_user["id"], paper_id, scope)}


@router.post("/folders", summary="Create folder")
def api_kb_create_folder(body: CreateFolderBody, _user=Depends(auth_service.require_user)):
    # Only enforce folder limit for the default "kb" scope
    if body.scope == "kb":
        limit_check = entitlement_service.check_kb_folder_limit(_user["id"])
        if not limit_check["allowed"]:
            raise HTTPException(
                status_code=403,
                detail=f"知识库文件夹已达上限（{limit_check['limit']} 个），请升级套餐以创建更多文件夹",
            )
    folder = kb_service.create_folder(_user["id"], body.name, body.parent_id, scope=body.scope)
    _invalidate_tree_cache(_user["id"], body.scope)
    return folder


@router.patch("/folders/{folder_id}", summary="Rename folder")
def api_kb_rename_folder(folder_id: int, body: RenameFolderBody, _user=Depends(auth_service.require_user)):
    folder = kb_service.rename_folder(_user["id"], folder_id, body.name, scope=body.scope)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    _invalidate_tree_cache(_user["id"], body.scope)
    return folder


@router.patch("/folders/{folder_id}/move", summary="Move folder")
def api_kb_move_folder(folder_id: int, body: MoveFolderBody, _user=Depends(auth_service.require_user)):
    folder = kb_service.move_folder(_user["id"], folder_id, body.target_parent_id, scope=body.scope)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    _invalidate_tree_cache(_user["id"], body.scope)
    return folder


@router.delete("/folders/{folder_id}", summary="Delete folder")
def api_kb_delete_folder(folder_id: int, scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    ok = kb_service.delete_folder(_user["id"], folder_id, scope=scope)
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
    _invalidate_tree_cache(_user["id"], scope)
    return {"ok": True}


@router.post("/papers", summary="Add paper to KB")
def api_kb_add_paper(body: AddPaperBody, _user=Depends(auth_service.require_user)):
    # Only enforce KB paper limit for the default "kb" scope
    if body.scope == "kb":
        limit_check = entitlement_service.check_kb_paper_limit(_user["id"])
        if not limit_check["allowed"]:
            raise HTTPException(
                status_code=403,
                detail=f"知识库论文已达上限（{limit_check['limit']} 篇），请升级套餐以保存更多论文",
            )
    paper = kb_service.add_paper(_user["id"], body.paper_id, body.paper_data, body.folder_id, scope=body.scope)
    _invalidate_tree_cache(_user["id"], body.scope)
    try:
        kb_service.auto_attach_pdf(_user["id"], body.paper_id, scope=body.scope)
    except Exception as _exc:
        import logging as _logging
        _logging.getLogger(__name__).warning("auto_attach_pdf failed for %s: %s", body.paper_id, _exc)
    # Trigger auto-classification when no explicit folder was given
    if body.folder_id is None and body.scope == "kb":
        try:
            auto_classify_service.enqueue_classify(_user["id"], body.paper_id, scope=body.scope)
        except Exception as _exc:
            import logging as _logging
            _logging.getLogger(__name__).warning("enqueue_classify failed for %s: %s", body.paper_id, _exc)
    return paper


@router.delete("/papers/{paper_id}", summary="Remove paper from KB")
def api_kb_remove_paper(paper_id: str, scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    ok = kb_service.remove_paper(_user["id"], paper_id, scope=scope)
    if not ok:
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    _invalidate_tree_cache(_user["id"], scope)
    return {"ok": True}


@router.patch("/papers/move", summary="Batch move papers")
def api_kb_move_papers(body: MovePapersBody, _user=Depends(auth_service.require_user)):
    count = kb_service.move_papers(_user["id"], body.paper_ids, body.target_folder_id, scope=body.scope)
    _invalidate_tree_cache(_user["id"], body.scope)
    return {"ok": True, "moved": count}


# ---------------------------------------------------------------------------
# Notes / files / links
# ---------------------------------------------------------------------------

@router.get("/papers/{paper_id}/notes", summary="List notes for a paper")
def api_kb_list_notes(paper_id: str, scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    notes = kb_service.list_notes(_user["id"], paper_id, scope=scope)
    return {"paper_id": paper_id, "notes": notes}


@router.post("/papers/{paper_id}/notes", summary="Create markdown note")
def api_kb_create_note(paper_id: str, body: CreateNoteBody, _user=Depends(auth_service.require_user)):
    if not kb_service.is_paper_in_kb(_user["id"], paper_id, scope=body.scope):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    # Limit check: only enforce for the default "kb" scope
    if body.scope == "kb":
        limit_check = entitlement_service.check_kb_note_limit(_user["id"])
        if not limit_check["allowed"]:
            raise HTTPException(
                status_code=403,
                detail=f"笔记数量已达上限（{limit_check['limit']}），请升级套餐以继续创建",
            )
    note = kb_service.create_note(_user["id"], paper_id, body.title, body.content, scope=body.scope)
    return note


@router.get("/notes/{note_id}", summary="Get note detail")
def api_kb_get_note(note_id: int, _user=Depends(auth_service.require_user)):
    note = kb_service.get_note(_user["id"], note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.patch("/notes/{note_id}", summary="Update note")
def api_kb_update_note(note_id: int, body: UpdateNoteBody, _user=Depends(auth_service.require_user)):
    note = kb_service.update_note(_user["id"], note_id, body.title, body.content)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.delete("/notes/{note_id}", summary="Delete note")
def api_kb_delete_note(note_id: int, _user=Depends(auth_service.require_user)):
    ok = kb_service.delete_note(_user["id"], note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}


@router.post("/papers/{paper_id}/notes/upload", summary="Upload file")
async def api_kb_upload_file(
    paper_id: str,
    scope: str = Query("kb"),
    file: UploadFile = File(...),
    _user=Depends(auth_service.require_user),
):
    # Gate check: note file attachment upload is Pro/Pro+ only
    if not entitlement_service.check_boolean_gate(_user["id"], "note_file_upload"):
        raise HTTPException(status_code=403, detail="笔记附件上传仅 Pro 及以上套餐可用，请升级以继续使用")
    if not kb_service.is_paper_in_kb(_user["id"], paper_id, scope=scope):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")

    _MAX_UPLOAD_SIZE = 50 * 1024 * 1024
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过限制（最大 50 MB）")

    mime = file.content_type or "application/octet-stream"
    note = kb_service.add_note_file(_user["id"], paper_id, file.filename or "upload", file_bytes, mime, scope=scope)
    return note


@router.post("/papers/{paper_id}/notes/link", summary="Add link")
def api_kb_add_link(paper_id: str, body: AddLinkBody, _user=Depends(auth_service.require_user)):
    if not kb_service.is_paper_in_kb(_user["id"], paper_id, scope=body.scope):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    note = kb_service.add_note_link(_user["id"], paper_id, body.title, body.url, scope=body.scope)
    return note


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

@router.post("/compare", summary="Compare papers via LLM (SSE)")
def api_kb_compare(body: ComparePapersBody, _user=Depends(auth_service.require_user)):
    from fastapi.responses import JSONResponse
    total = len(body.paper_ids) + len(body.compare_result_ids)
    if total < 2:
        return JSONResponse(status_code=422, content={"detail": "At least 2 items required (paper_ids + compare_result_ids)"})

    # Compute tier-aware max_items baseline, then apply engagement boost on top
    raw_boost: dict = {}
    if body.reward_id is not None:
        raw_boost = engagement_service.get_reward_boost(_user["id"], "compare", body.reward_id)

    # get_effective_compare_max uses tier baseline + engagement delta
    max_items = entitlement_service.get_effective_compare_max(_user["id"], raw_boost)

    # Validate selection size BEFORE consuming quota to avoid wasting credits
    if total > max_items:
        detail = f"最多可对比 {max_items} 篇论文"
        return JSONResponse(status_code=422, content={"detail": detail})

    # Quota check: consume one compare session credit (Free: 3/month limit)
    entitlement_service.consume_quota(_user["id"], "compare")

    # Consume the reward only if the delta is actually meaningful
    if body.reward_id is not None and raw_boost:
        delta = entitlement_service.ENGAGEMENT_BOOST_DELTAS.get(
            raw_boost.get("reward_code", ""), {}
        ).get("compare_max_items_delta", 0)
        if delta > 0:
            try:
                engagement_service.use_reward(
                    _user["id"], body.reward_id,
                    f"compare_{total}_items"
                )
            except ValueError:
                pass  # Already used / expired — boost was already applied, proceed

    return StreamingResponse(
        compare_service.stream_compare(
            _user["id"], body.paper_ids, body.scope,
            compare_result_ids=body.compare_result_ids,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Dismiss / Rename
# ---------------------------------------------------------------------------

@router.post("/dismiss", summary="Dismiss paper")
def api_kb_dismiss_paper(body: DismissPaperBody, user=Depends(auth_service.require_user)):
    kb_service.dismiss_paper(user["id"], body.paper_id)
    return {"ok": True}


@router.patch("/papers/{paper_id}/rename", summary="Rename paper")
def api_kb_rename_paper(paper_id: str, body: RenamePaperBody, _user=Depends(auth_service.require_user)):
    result = kb_service.rename_paper(_user["id"], paper_id, body.title, scope=body.scope)
    if result is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return result


# ---------------------------------------------------------------------------
# Compare results
# ---------------------------------------------------------------------------

@router.get("/compare-results/tree", summary="Get compare results tree")
def api_kb_compare_results_tree(_user=Depends(auth_service.require_user)):
    return kb_service.get_compare_results_tree(_user["id"])


@router.post("/compare-results", summary="Save compare result")
def api_kb_save_compare_result(body: SaveCompareResultBody, _user=Depends(auth_service.require_user)):
    # Limit check: max saved compare results per tier
    limit_check = entitlement_service.check_kb_compare_result_limit(_user["id"])
    if not limit_check["allowed"]:
        raise HTTPException(
            status_code=403,
            detail=f"保存的对比结果已达上限（{limit_check['limit']}），请升级套餐以继续保存",
        )
    result = kb_service.add_compare_result(
        _user["id"], body.title, body.markdown, body.paper_ids, body.folder_id,
    )
    return result


@router.get("/compare-results/{result_id}", summary="Get compare result")
def api_kb_get_compare_result(result_id: int, _user=Depends(auth_service.require_user)):
    result = kb_service.get_compare_result(_user["id"], result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Compare result not found")
    return result


@router.patch("/compare-results/{result_id}", summary="Rename compare result")
def api_kb_rename_compare_result(result_id: int, body: RenameCompareResultBody, _user=Depends(auth_service.require_user)):
    result = kb_service.rename_compare_result(_user["id"], result_id, body.title)
    if result is None:
        raise HTTPException(status_code=404, detail="Compare result not found")
    return result


@router.patch("/compare-results/{result_id}/move", summary="Move compare result")
def api_kb_move_compare_result(result_id: int, body: MoveCompareResultBody, _user=Depends(auth_service.require_user)):
    result = kb_service.move_compare_result(_user["id"], result_id, body.target_folder_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Compare result not found")
    return result


@router.delete("/compare-results/{result_id}", summary="Delete compare result")
def api_kb_delete_compare_result(result_id: int, _user=Depends(auth_service.require_user)):
    ok = kb_service.delete_compare_result(_user["id"], result_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Compare result not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------

@router.get("/papers/{paper_id}/annotations", summary="List annotations")
def api_kb_list_annotations(paper_id: str, scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    annotations = kb_service.list_annotations(_user["id"], paper_id, scope=scope)
    return {"paper_id": paper_id, "annotations": annotations}


@router.post("/papers/{paper_id}/annotations", summary="Create annotation")
def api_kb_create_annotation(
    paper_id: str, body: CreateAnnotationBody, _user=Depends(auth_service.require_user)
):
    annotation = kb_service.create_annotation(
        _user["id"], paper_id, body.page, body.type, body.content, body.color, body.position_data,
        scope=body.scope,
    )
    return annotation


@router.patch("/annotations/{annotation_id}", summary="Update annotation")
def api_kb_update_annotation(
    annotation_id: int, body: UpdateAnnotationBody, _user=Depends(auth_service.require_user)
):
    annotation = kb_service.update_annotation(_user["id"], annotation_id, body.content, body.color)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return annotation


@router.delete("/annotations/{annotation_id}", summary="Delete annotation")
def api_kb_delete_annotation(annotation_id: int, _user=Depends(auth_service.require_user)):
    ok = kb_service.delete_annotation(_user["id"], annotation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# KB paper pipeline / translate / files
# ---------------------------------------------------------------------------

@router.post("/papers/{paper_id}/process", summary="触发 KB 论文 MinerU 解析")
def api_kb_paper_process(
    paper_id: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    ok, msg = kb_pipeline_service.start_kb_paper_process(_user["id"], paper_id, scope=scope)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@router.get("/papers/{paper_id}/process-status", summary="查询 KB 论文处理状态")
def api_kb_paper_process_status(
    paper_id: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    paper = kb_service.get_kb_paper(_user["id"], paper_id, scope=scope)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    return {
        "paper_id": paper_id,
        "process_status": paper.get("process_status", "none"),
        "process_step": paper.get("process_step", ""),
        "process_error": paper.get("process_error", ""),
    }


@router.post("/papers/{paper_id}/translate", summary="触发 KB 论文翻译")
def api_kb_paper_translate(
    paper_id: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    # Gate check: translation is Pro/Pro+ only
    if not entitlement_service.check_boolean_gate(_user["id"], "translate"):
        raise HTTPException(status_code=403, detail="论文全文翻译仅 Pro 及以上套餐可用，请升级以继续使用")
    # Quota check: consume one translation credit (Pro: 10/month, Pro+: unlimited)
    entitlement_service.consume_quota(_user["id"], "translate")
    ok, msg = translate_service.start_kb_translation(_user["id"], paper_id, scope=scope)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@router.post("/papers/{paper_id}/retranslate", summary="重新翻译 KB 论文")
def api_kb_paper_retranslate(
    paper_id: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    # Gate check: translation is Pro/Pro+ only
    if not entitlement_service.check_boolean_gate(_user["id"], "translate"):
        raise HTTPException(status_code=403, detail="论文全文翻译仅 Pro 及以上套餐可用，请升级以继续使用")
    # Quota check: consume one translation credit (Pro: 10/month, Pro+: unlimited)
    entitlement_service.consume_quota(_user["id"], "translate")
    paths = translate_service.kb_paper_derivative_paths(_user["id"], paper_id)
    for key in ("zh", "bilingual"):
        p = paths[key]
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
    kb_service.set_kb_paper_translate_status(
        _user["id"], paper_id, status="none", error="", progress=0, scope=scope
    )
    ok, msg = translate_service.start_kb_translation(_user["id"], paper_id, scope=scope)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@router.get("/papers/{paper_id}/translate-status", summary="查询 KB 论文翻译状态")
def api_kb_paper_translate_status(
    paper_id: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    paper = kb_service.get_kb_paper(_user["id"], paper_id, scope=scope)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    return {
        "paper_id": paper_id,
        "translate_status": paper.get("translate_status", "none"),
        "translate_progress": paper.get("translate_progress", 0),
        "translate_error": paper.get("translate_error", ""),
        "busy": translate_service.is_translating(paper_id),
    }


@router.get("/papers/{paper_id}/files", summary="KB 论文关联文件静态链接")
def api_kb_paper_files(
    paper_id: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    paper = kb_service.get_kb_paper(_user["id"], paper_id, scope=scope)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")

    enriched = _enrich_kb_paper(dict(paper), _user["id"])
    paths = translate_service.kb_paper_derivative_paths(_user["id"], paper_id)
    pdf_abs = os.path.join(_KB_FILES_DIR, str(_user["id"]), paper_id, f"{paper_id}.pdf")

    return {
        "paper_id": paper_id,
        "pdf_static_url": enriched.get("pdf_static_url"),
        "mineru_static_url": enriched.get("mineru_static_url"),
        "zh_static_url": enriched.get("zh_static_url"),
        "bilingual_static_url": enriched.get("bilingual_static_url"),
        "exists": {
            "pdf": os.path.isfile(pdf_abs),
            "mineru": os.path.isfile(paths["mineru"]),
            "zh": os.path.isfile(paths["zh"]),
            "bilingual": os.path.isfile(paths["bilingual"]),
        },
        "process_status": paper.get("process_status", "none"),
        "process_step": paper.get("process_step", ""),
        "translate_status": paper.get("translate_status", "none"),
        "translate_progress": paper.get("translate_progress", 0),
    }


@router.delete(
    "/papers/{paper_id}/derivatives/{derivative_type}",
    summary="删除 KB 论文衍生文件",
)
def api_kb_paper_delete_derivative(
    paper_id: str,
    derivative_type: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    ok, msg = translate_service.delete_kb_derivative(
        _user["id"], paper_id, derivative_type, scope=scope
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Auto-classify endpoints
# ---------------------------------------------------------------------------

class AutoClassifySyncFoldersBody(BaseModel):
    folders: list = []
    scope: str = "kb"


class AutoClassifyReclassifyBody(BaseModel):
    scope: str = "kb"


class UpdateReadStatusBody(BaseModel):
    status: str  # 'unread' | 'reading' | 'read'
    scope: str = "kb"


@router.get("/auto-classify/pending-count", summary="待分类论文数量")
def api_auto_classify_pending_count(
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    count = kb_service.count_pending_classify(_user["id"], scope=scope)
    return {"pending": count}


@router.get("/auto-classify/unclassified-count", summary="「未分类」文件夹中的论文数量")
def api_auto_classify_unclassified_count(
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    count = kb_service.count_unclassified_papers(_user["id"], scope=scope)
    return {"unclassified": count}

@router.post("/auto-classify/sync-folders", summary="同步分类目录定义到实际 KB 文件夹")
def api_auto_classify_sync_folders(
    body: AutoClassifySyncFoldersBody,
    _user=Depends(auth_service.require_user),
):
    """
    Create missing KB folders from the user's auto-classify folder definition
    and return the updated list with folder_id populated.
    """
    updated = auto_classify_service.sync_folders(_user["id"], body.folders, scope=body.scope)
    return {"ok": True, "folders": updated}


@router.post("/auto-classify/reclassify-all", summary="重新分类所有知识库论文")
def api_auto_classify_reclassify_all(
    body: AutoClassifyReclassifyBody,
    _user=Depends(auth_service.require_user),
):
    count = auto_classify_service.enqueue_reclassify_all(_user["id"], scope=body.scope)
    return {"ok": True, "enqueued": count}


@router.post("/papers/{paper_id}/classify", summary="手动触发单篇论文分类")
def api_kb_classify_paper(
    paper_id: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    if not kb_service.is_paper_in_kb(_user["id"], paper_id, scope=scope):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    enqueued = auto_classify_service.enqueue_classify(_user["id"], paper_id, scope=scope)
    return {"ok": True, "enqueued": enqueued}


@router.get("/papers/{paper_id}/classify-status", summary="获取论文分类状态")
def api_kb_classify_status(
    paper_id: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    paper = kb_service.get_kb_paper(_user["id"], paper_id, scope=scope)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    return {
        "paper_id": paper_id,
        "classify_status": paper.get("classify_status", "none"),
        "classify_folder_id": paper.get("classify_folder_id"),
        "classify_confidence": paper.get("classify_confidence"),
        "classify_error": paper.get("classify_error", ""),
        "busy": auto_classify_service.is_classifying(_user["id"], paper_id, scope),
    }


# ---------------------------------------------------------------------------
# Read-status endpoints
# ---------------------------------------------------------------------------

@router.patch("/papers/{paper_id}/read-status", summary="更新论文阅读状态")
def api_kb_update_read_status(
    paper_id: str,
    body: UpdateReadStatusBody,
    _user=Depends(auth_service.require_user),
):
    valid = {"unread", "reading", "read"}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"无效的 read_status，允许值: {valid}")
    if not kb_service.is_paper_in_kb(_user["id"], paper_id, scope=body.scope):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    kb_service.set_read_status(_user["id"], paper_id, body.status, scope=body.scope)
    return {"ok": True, "paper_id": paper_id, "read_status": body.status}


# ---------------------------------------------------------------------------
# KB export (full portable archive as JSON)
# ---------------------------------------------------------------------------

@router.get("/export", summary="导出知识库为 JSON 归档（可携带备份）")
def api_kb_export(
    scope: str = Query("kb", pattern="^(kb|idea_library)$"),
    _user=Depends(auth_service.require_user),
):
    """
    Return a full export of the user's knowledge base as a structured JSON
    document containing folders, papers (metadata only), and all notes.
    This gives power users a portable backup they can store offline or
    import into other tools.

    The response is streamed as an attachment for direct browser download.
    """
    import json as _json

    tree = kb_service.get_tree(_user["id"], scope=scope)
    notes_by_paper: dict = {}

    def _collect_papers(folder: dict) -> list:
        result = []
        for p in folder.get("papers") or []:
            pid = p.get("paper_id", "")
            # Collect notes once per paper
            if pid and pid not in notes_by_paper:
                try:
                    notes_by_paper[pid] = kb_service.list_notes(_user["id"], pid, scope=scope)
                except Exception:
                    notes_by_paper[pid] = []
            result.append({
                "paper_id": pid,
                "title": p.get("title") or p.get("short_title") or "",
                "institution": p.get("institution") or "",
                "year": p.get("year"),
                "authors": p.get("authors") or [],
                "abstract": p.get("abstract") or "",
                "notes": notes_by_paper.get(pid) or [],
                "folder_id": folder.get("id"),
                "folder_name": folder.get("name"),
            })
        for child in folder.get("children") or []:
            result.extend(_collect_papers(child))
        return result

    papers_flat: list = []
    for p in tree.get("papers") or []:
        pid = p.get("paper_id", "")
        if pid and pid not in notes_by_paper:
            try:
                notes_by_paper[pid] = kb_service.list_notes(_user["id"], pid, scope=scope)
            except Exception:
                notes_by_paper[pid] = []
        papers_flat.append({
            "paper_id": pid,
            "title": p.get("title") or p.get("short_title") or "",
            "institution": p.get("institution") or "",
            "year": p.get("year"),
            "authors": p.get("authors") or [],
            "abstract": p.get("abstract") or "",
            "notes": notes_by_paper.get(pid) or [],
            "folder_id": None,
            "folder_name": None,
        })

    for folder in tree.get("folders") or []:
        papers_flat.extend(_collect_papers(folder))

    export_doc = {
        "schema_version": 1,
        "scope": scope,
        "exported_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "folder_tree": tree.get("folders") or [],
        "papers": papers_flat,
    }

    payload = _json.dumps(export_doc, ensure_ascii=False, indent=2)
    from fastapi.responses import Response as _Response
    return _Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="kb_export_{scope}.json"'},
    )

