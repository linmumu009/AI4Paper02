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

from services import auth_service, compare_service, kb_pipeline_service, kb_service, translate_service
from routers._deps import _KB_FILES_DIR

router = APIRouter(prefix="/api/kb", tags=["kb"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateFolderBody(BaseModel):
    name: str
    parent_id: Optional[int] = None
    scope: str = "kb"


class RenameFolderBody(BaseModel):
    name: str
    scope: str = "kb"


class AddPaperBody(BaseModel):
    paper_id: str
    paper_data: dict
    folder_id: Optional[int] = None
    scope: str = "kb"


class MoveFolderBody(BaseModel):
    target_parent_id: Optional[int] = None
    scope: str = "kb"


class MovePapersBody(BaseModel):
    paper_ids: list[str]
    target_folder_id: Optional[int] = None
    scope: str = "kb"


class CreateNoteBody(BaseModel):
    title: str = "未命名笔记"
    content: str = ""
    scope: str = "kb"


class UpdateNoteBody(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


class AddLinkBody(BaseModel):
    title: str
    url: str
    scope: str = "kb"


class ComparePapersBody(BaseModel):
    paper_ids: list[str] = Field(default=[], min_length=0, max_length=5)
    scope: str = "kb"
    compare_result_ids: list[int] = Field(default_factory=list)


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
    except Exception:
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
# Tree / folders / papers
# ---------------------------------------------------------------------------

@router.get("/tree", summary="Get knowledge base tree")
def api_kb_tree(scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    tree = kb_service.get_tree(_user["id"], scope=scope)
    return _enrich_kb_tree(tree, _user["id"])


@router.get("/papers/{paper_id}/exists", summary="Check if paper is in KB")
def api_kb_paper_exists(
    paper_id: str,
    scope: str = Query("kb"),
    _user=Depends(auth_service.require_user),
):
    return {"exists": kb_service.is_paper_in_kb(_user["id"], paper_id, scope)}


@router.post("/folders", summary="Create folder")
def api_kb_create_folder(body: CreateFolderBody, _user=Depends(auth_service.require_user)):
    folder = kb_service.create_folder(_user["id"], body.name, body.parent_id, scope=body.scope)
    return folder


@router.patch("/folders/{folder_id}", summary="Rename folder")
def api_kb_rename_folder(folder_id: int, body: RenameFolderBody, _user=Depends(auth_service.require_user)):
    folder = kb_service.rename_folder(_user["id"], folder_id, body.name, scope=body.scope)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@router.patch("/folders/{folder_id}/move", summary="Move folder")
def api_kb_move_folder(folder_id: int, body: MoveFolderBody, _user=Depends(auth_service.require_user)):
    folder = kb_service.move_folder(_user["id"], folder_id, body.target_parent_id, scope=body.scope)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@router.delete("/folders/{folder_id}", summary="Delete folder")
def api_kb_delete_folder(folder_id: int, scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    ok = kb_service.delete_folder(_user["id"], folder_id, scope=scope)
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}


@router.post("/papers", summary="Add paper to KB")
def api_kb_add_paper(body: AddPaperBody, _user=Depends(auth_service.require_user)):
    paper = kb_service.add_paper(_user["id"], body.paper_id, body.paper_data, body.folder_id, scope=body.scope)
    try:
        kb_service.auto_attach_pdf(_user["id"], body.paper_id, scope=body.scope)
    except Exception:
        pass
    return paper


@router.delete("/papers/{paper_id}", summary="Remove paper from KB")
def api_kb_remove_paper(paper_id: str, scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    ok = kb_service.remove_paper(_user["id"], paper_id, scope=scope)
    if not ok:
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    return {"ok": True}


@router.patch("/papers/move", summary="Batch move papers")
def api_kb_move_papers(body: MovePapersBody, _user=Depends(auth_service.require_user)):
    count = kb_service.move_papers(_user["id"], body.paper_ids, body.target_folder_id, scope=body.scope)
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
    if total > 5:
        return JSONResponse(status_code=422, content={"detail": "At most 5 items allowed (paper_ids + compare_result_ids)"})
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
