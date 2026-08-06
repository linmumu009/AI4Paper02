"""
User-Uploaded Papers Router.

All routes are prefixed with /api/user-papers and registered in api.py via
    app.include_router(user_paper_router)
"""

import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from services import auth_service, engagement_service, entitlement_service, translate_service, user_paper_pipeline_service, user_paper_service
from services.private_file_access_service import build_signed_kb_file_url
from services.safe_logging_service import safe_failure_detail, safe_stored_error
from services.upload_guard import UploadTooLarge, read_upload_with_limit

router = APIRouter(prefix="/api/user-papers", tags=["user-papers"])
logger = logging.getLogger(__name__)


def _finalize_upload_quota(reservation_id: Optional[str], *, commit: bool) -> None:
    if not reservation_id:
        return
    try:
        if commit:
            entitlement_service.commit_quota_reservation(reservation_id)
        else:
            entitlement_service.release_quota_reservation(reservation_id)
    except Exception as exc:
        safe_failure_detail(
            logger,
            "论文导入额度状态更新失败",
            exc,
            operation="user_paper_upload_quota_finalize",
        )


def _create_paper_with_quota(user_id: int, **kwargs) -> dict:
    receipt = entitlement_service.reserve_quota(user_id, "upload")
    reservation_id = receipt.get("reservation_id")
    try:
        paper = user_paper_service.create_paper(user_id, **kwargs)
    except Exception:
        _finalize_upload_quota(reservation_id, commit=False)
        raise
    created = bool(paper.pop("_created", True))
    _finalize_upload_quota(reservation_id, commit=created)
    if kwargs.get("deduplicate_source"):
        paper["already_exists"] = not created
    return paper


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UserPaperManualBody(BaseModel):
    title: str = Field(..., description="论文标题")
    authors: list[str] = Field(default_factory=list)
    abstract: str = Field(default="")
    institution: str = Field(default="")
    year: Optional[int] = Field(default=None)
    external_url: str = Field(default="")


class UserPaperArxivBody(BaseModel):
    arxiv_id: str = Field(..., description="arXiv ID 或完整 URL，例如 2501.00001 或 https://arxiv.org/abs/2501.00001")


class UserPaperUpdateBody(BaseModel):
    title: Optional[str] = None
    authors: Optional[list[str]] = None
    abstract: Optional[str] = None
    institution: Optional[str] = None
    year: Optional[int] = None
    external_url: Optional[str] = None


class MoveUserPapersBody(BaseModel):
    paper_ids: list[str] = Field(..., min_length=1)
    target_folder_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Enrichment helpers
# ---------------------------------------------------------------------------

def _enrich_user_paper(p: dict) -> dict:
    uid = p.get("user_id")
    pid = p.get("paper_id")
    if p.get("pdf_path") and uid is not None:
        pdf_abs = os.path.join(user_paper_service._KB_FILES_DIR, p["pdf_path"])
        try:
            p["pdf_static_url"] = build_signed_kb_file_url(pdf_abs, int(uid))
        except ValueError:
            p["pdf_static_url"] = None
    if uid is not None and pid:
        try:
            paths = translate_service.paper_derivative_paths(int(uid), str(pid))
            def _kb_static_url(abs_path: str) -> str | None:
                if not os.path.isfile(abs_path):
                    return None
                try:
                    return build_signed_kb_file_url(abs_path, int(uid))
                except ValueError:
                    return None

            p["mineru_static_url"] = (
                _kb_static_url(paths["mineru_normalized"])
                or _kb_static_url(paths["mineru"])
            )
            p["zh_static_url"] = _kb_static_url(paths["zh"])
            p["bilingual_static_url"] = _kb_static_url(paths["bilingual"])
        except Exception:
            p["mineru_static_url"] = None
            p["zh_static_url"] = None
            p["bilingual_static_url"] = None
    p["source"] = "user_upload"
    if p.get("summary_json"):
        try:
            p["summary"] = json.loads(p["summary_json"])
        except Exception:
            p["summary"] = None
    else:
        p["summary"] = None
    if p.get("paper_assets_json"):
        try:
            p["paper_assets"] = json.loads(p["paper_assets_json"])
        except Exception:
            p["paper_assets"] = None
    else:
        p["paper_assets"] = None
    return p


def _enrich_user_paper_tree(tree: dict) -> dict:
    def walk_folder(folder: dict) -> None:
        for paper in folder.get("papers") or []:
            _enrich_user_paper(paper)
        for child in folder.get("children") or []:
            walk_folder(child)

    for paper in tree.get("papers") or []:
        _enrich_user_paper(paper)
    for folder in tree.get("folders") or []:
        walk_folder(folder)
    return tree


# ---------------------------------------------------------------------------
# Import endpoints
# ---------------------------------------------------------------------------

@router.post("/import/manual", summary="手动录入论文元数据")
def api_user_paper_import_manual(
    body: UserPaperManualBody,
    _user=Depends(auth_service.require_user),
):
    paper = _create_paper_with_quota(
        _user["id"],
        source_type="manual",
        source_ref="",
        title=body.title,
        authors=body.authors,
        abstract=body.abstract,
        institution=body.institution,
        year=body.year,
        external_url=body.external_url,
    )
    return paper


@router.post("/import/arxiv", summary="通过 arXiv ID 导入论文元数据")
def api_user_paper_import_arxiv(
    body: UserPaperArxivBody,
    _user=Depends(auth_service.require_user),
):
    try:
        clean_id = user_paper_service.normalize_arxiv_id(body.arxiv_id)
    except user_paper_service.ArxivMetadataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    existing = user_paper_service.get_paper_by_source(
        _user["id"], "arxiv", clean_id
    )
    if existing is not None:
        existing["arxiv_pdf_url"] = f"https://arxiv.org/pdf/{clean_id}"
        existing["already_exists"] = True
        return existing

    try:
        meta = user_paper_service.fetch_arxiv_metadata(clean_id)
    except user_paper_service.ArxivMetadataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        public_error = safe_failure_detail(
            logger,
            "arXiv 服务暂时不可用，请稍后重试",
            exc,
            operation="user_paper_arxiv_metadata_fetch",
        )
        raise HTTPException(status_code=502, detail=public_error) from exc

    paper = _create_paper_with_quota(
        _user["id"],
        source_type="arxiv",
        source_ref=meta["arxiv_id"],
        title=meta["title"],
        authors=meta["authors"],
        abstract=meta["abstract"],
        institution=meta["institution"],
        year=meta["year"],
        external_url=meta["external_url"],
        deduplicate_source=True,
    )
    paper["arxiv_pdf_url"] = meta["pdf_url"]
    return paper


@router.post("/import/pdf", summary="上传 PDF 并录入论文")
async def api_user_paper_import_pdf(
    file: UploadFile = File(...),
    title: str = Query(default=""),
    authors: str = Query(default="[]", description="JSON 数组字符串，例如 [\"作者1\",\"作者2\"]"),
    abstract: str = Query(default=""),
    institution: str = Query(default=""),
    year: Optional[int] = Query(default=None),
    external_url: str = Query(default=""),
    _user=Depends(auth_service.require_user),
):
    _MAX_UPLOAD_SIZE = 50 * 1024 * 1024
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    try:
        pdf_bytes = await read_upload_with_limit(file, _MAX_UPLOAD_SIZE)
    except UploadTooLarge:
        raise HTTPException(status_code=413, detail="文件大小超过限制（最大 50 MB）")

    try:
        authors_list: list[str] = json.loads(authors)
        if not isinstance(authors_list, list):
            authors_list = []
    except Exception:
        authors_list = []

    paper = _create_paper_with_quota(
        _user["id"],
        source_type="pdf",
        source_ref="",
        title=title or (file.filename or "未命名论文").replace(".pdf", ""),
        authors=authors_list,
        abstract=abstract,
        institution=institution,
        year=year,
        external_url=external_url,
        pdf_bytes=pdf_bytes,
        pdf_filename=file.filename or "paper.pdf",
    )
    return paper


# ---------------------------------------------------------------------------
# List / tree / detail / CRUD
# ---------------------------------------------------------------------------

@router.get("", summary="获取我的上传论文列表")
def api_user_paper_list(
    source_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    institution: Optional[str] = Query(None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user=Depends(auth_service.require_user),
):
    papers = user_paper_service.list_papers(
        _user["id"],
        source_type=source_type,
        search=search,
        institution=institution,
        limit=limit,
        offset=offset,
    )
    papers = [_enrich_user_paper(p) for p in papers]
    total = user_paper_service.count_papers(_user["id"])
    return {"total": total, "papers": papers}


@router.get("/institutions", summary="获取该用户所有不重复机构名列表")
def api_user_paper_institutions(
    _user=Depends(auth_service.require_user),
):
    institutions = user_paper_service.list_institutions(_user["id"])
    return {"institutions": institutions}


@router.get("/tree", summary="获取我的论文文件夹树")
def api_user_paper_tree(
    _user=Depends(auth_service.require_user),
):
    tree = user_paper_service.get_tree(_user["id"])
    return _enrich_user_paper_tree(tree)


@router.patch("/move", summary="批量移动我的论文到目标文件夹")
def api_user_paper_move(
    body: MoveUserPapersBody,
    _user=Depends(auth_service.require_user),
):
    count = user_paper_service.move_papers(_user["id"], body.paper_ids, body.target_folder_id)
    return {"ok": True, "moved": count}


@router.get("/{paper_id}", summary="获取单篇上传论文详情")
def api_user_paper_detail(
    paper_id: str,
    _user=Depends(auth_service.require_user),
):
    paper = user_paper_service.get_paper(_user["id"], paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="论文不存在")
    return _enrich_user_paper(paper)


@router.patch("/{paper_id}", summary="更新上传论文元数据")
def api_user_paper_update(
    paper_id: str,
    body: UserPaperUpdateBody,
    _user=Depends(auth_service.require_user),
):
    updated = user_paper_service.update_paper(
        _user["id"],
        paper_id,
        title=body.title,
        authors=body.authors,
        abstract=body.abstract,
        institution=body.institution,
        year=body.year,
        external_url=body.external_url,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="论文不存在")
    return updated


@router.post("/{paper_id}/upload-pdf", summary="为已录入论文补传 PDF")
async def api_user_paper_upload_pdf(
    paper_id: str,
    file: UploadFile = File(...),
    _user=Depends(auth_service.require_user),
):
    paper = user_paper_service.get_paper(_user["id"], paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="论文不存在")

    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    _MAX_UPLOAD_SIZE = 50 * 1024 * 1024
    try:
        pdf_bytes = await read_upload_with_limit(file, _MAX_UPLOAD_SIZE)
    except UploadTooLarge:
        raise HTTPException(status_code=413, detail="文件大小超过限制（最大 50 MB）")

    updated = user_paper_service.update_paper(
        _user["id"],
        paper_id,
        pdf_bytes=pdf_bytes,
        pdf_filename=file.filename or "paper.pdf",
    )
    if updated and updated.get("pdf_path"):
        pdf_abs = os.path.join(user_paper_service._KB_FILES_DIR, updated["pdf_path"])
        try:
            updated["pdf_static_url"] = build_signed_kb_file_url(pdf_abs, _user["id"])
        except ValueError:
            updated["pdf_static_url"] = None
    return updated


@router.delete("/{paper_id}", summary="删除上传论文")
def api_user_paper_delete(
    paper_id: str,
    _user=Depends(auth_service.require_user),
):
    ok = user_paper_service.delete_paper(_user["id"], paper_id)
    if not ok:
        raise HTTPException(status_code=404, detail="论文不存在")
    return {"ok": True, "paper_id": paper_id}


# ---------------------------------------------------------------------------
# Pipeline / translate / files
# ---------------------------------------------------------------------------

class ProcessPaperBody(BaseModel):
    reward_id: Optional[int] = Field(default=None, description="Fast-track engagement reward ID")


@router.post("/{paper_id}/process", summary="触发单篇论文流水线处理")
def api_user_paper_process(
    paper_id: str,
    body: ProcessPaperBody = ProcessPaperBody(),
    _user=Depends(auth_service.require_user),
):
    paper = user_paper_service.get_paper(_user["id"], paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="论文不存在")

    if user_paper_pipeline_service.is_processing(paper_id):
        return {"ok": False, "message": "处理已在进行中", "paper_id": paper_id}

    # Determine priority from fast-track reward
    priority = 0
    reward_applied = False
    if body.reward_id is not None:
        boost = engagement_service.get_reward_boost(_user["id"], "upload", body.reward_id)
        if boost.get("upload_priority", 0) > 0:
            try:
                engagement_service.use_reward(
                    _user["id"], body.reward_id,
                    f"upload_fast_track_{paper_id}"
                )
                priority = 1
                reward_applied = True
            except ValueError:
                pass  # Reward already used or expired — proceed normally

    started, message = user_paper_pipeline_service.start_processing(
        _user["id"], paper_id, priority=priority
    )
    if not started:
        return {"ok": False, "message": message, "paper_id": paper_id}
    return {"ok": True, "message": message, "paper_id": paper_id, "priority": priority, "reward_applied": reward_applied}


class BatchProcessBody(BaseModel):
    paper_ids: list[str] = Field(..., description="要处理的论文 ID 列表（最多 20 篇）")
    reward_id: Optional[int] = Field(default=None, description="Fast-track engagement reward ID（批量共享同一个 reward）")


@router.post("/batch-process", summary="批量启动多篇论文流水线处理")
def api_user_paper_batch_process(
    body: BatchProcessBody,
    _user=Depends(auth_service.require_user),
):
    if not body.paper_ids:
        raise HTTPException(status_code=400, detail="paper_ids 不能为空")
    if len(body.paper_ids) > 20:
        raise HTTPException(status_code=400, detail="单次最多批量处理 20 篇论文")

    # Resolve reward priority once for the whole batch
    priority = 0
    reward_applied = False
    if body.reward_id is not None:
        boost = engagement_service.get_reward_boost(_user["id"], "upload", body.reward_id)
        if boost.get("upload_priority", 0) > 0:
            try:
                engagement_service.use_reward(
                    _user["id"], body.reward_id,
                    f"upload_fast_track_batch_{body.paper_ids[0]}"
                )
                priority = 1
                reward_applied = True
            except ValueError:
                pass

    results = []
    for pid in body.paper_ids:
        paper = user_paper_service.get_paper(_user["id"], pid)
        if paper is None:
            results.append({"paper_id": pid, "ok": False, "message": "论文不存在"})
            continue
        started, message = user_paper_pipeline_service.start_processing(
            _user["id"], pid, priority=priority
        )
        results.append({
            "paper_id": pid,
            "ok": started,
            "message": message,
        })

    return {
        "results": results,
        "priority": priority,
        "reward_applied": reward_applied,
    }


@router.get("/{paper_id}/process-status", summary="查询单篇论文处理状态")
def api_user_paper_process_status(
    paper_id: str,
    _user=Depends(auth_service.require_user),
):
    paper = user_paper_service.get_paper(_user["id"], paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="论文不存在")
    return {
        "paper_id": paper_id,
        "process_status": paper.get("process_status", "none"),
        "process_step": paper.get("process_step", ""),
        "process_error": safe_stored_error(
            paper.get("process_error"), "论文处理失败，请重试"
        ),
        "process_started_at": paper.get("process_started_at"),
        "process_finished_at": paper.get("process_finished_at"),
    }


@router.post("/{paper_id}/translate", summary="手动触发论文全文翻译")
def api_user_paper_translate(
    paper_id: str,
    _user=Depends(auth_service.require_user),
):
    # Gate check: blocked if tier has translate=False
    if not entitlement_service.check_boolean_gate(_user["id"], "translate"):
        raise HTTPException(status_code=403, detail="当前套餐不支持全文翻译，请升级以继续使用")
    paper = user_paper_service.get_paper(_user["id"], paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="论文不存在")
    ok, msg = translate_service.start_translation(
        _user["id"],
        paper_id,
        charge_quota=True,
    )
    if not ok:
        return {"ok": False, "message": msg, "paper_id": paper_id}
    return {"ok": True, "message": msg, "paper_id": paper_id}


@router.post("/{paper_id}/retranslate", summary="重新触发论文全文翻译（同 translate）")
def api_user_paper_retranslate(
    paper_id: str,
    _user=Depends(auth_service.require_user),
):
    # Gate check: blocked if tier has translate=False
    if not entitlement_service.check_boolean_gate(_user["id"], "translate"):
        raise HTTPException(status_code=403, detail="当前套餐不支持全文翻译，请升级以继续使用")
    paper = user_paper_service.get_paper(_user["id"], paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="论文不存在")
    ok, msg = translate_service.start_translation(
        _user["id"],
        paper_id,
        charge_quota=True,
    )
    if not ok:
        return {"ok": False, "message": msg, "paper_id": paper_id}
    return {"ok": True, "message": msg, "paper_id": paper_id}


@router.delete(
    "/{paper_id}/derivatives/{derivative_type}",
    summary="删除论文衍生文件（MinerU Markdown 或翻译产物）",
)
def api_user_paper_delete_derivative(
    paper_id: str,
    derivative_type: str,
    _user=Depends(auth_service.require_user),
):
    ok, msg = translate_service.delete_derivative(_user["id"], paper_id, derivative_type)
    if not ok:
        code = 404 if msg == "论文不存在" else 400
        raise HTTPException(status_code=code, detail=msg)
    return {"ok": True, "message": msg, "paper_id": paper_id}


@router.get("/{paper_id}/translate-status", summary="查询论文翻译状态")
def api_user_paper_translate_status(
    paper_id: str,
    _user=Depends(auth_service.require_user),
):
    paper = user_paper_service.get_paper(_user["id"], paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="论文不存在")
    return {
        "paper_id": paper_id,
        "translate_status": paper.get("translate_status", "none"),
        "translate_error": safe_stored_error(
            paper.get("translate_error"), "论文翻译失败，请重试"
        ),
        "translate_progress": int(paper.get("translate_progress") or 0),
        "translate_started_at": paper.get("translate_started_at"),
        "translate_finished_at": paper.get("translate_finished_at"),
        "busy": translate_service.is_translating(
            paper_id,
            _user["id"],
            source="user",
        ),
    }


@router.get("/{paper_id}/files", summary="论文关联文件静态链接")
def api_user_paper_files(
    paper_id: str,
    _user=Depends(auth_service.require_user),
):
    paper = user_paper_service.get_paper(_user["id"], paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="论文不存在")
    enriched = _enrich_user_paper(dict(paper))
    paths = translate_service.paper_derivative_paths(_user["id"], paper_id)
    return {
        "paper_id": paper_id,
        "pdf_static_url": enriched.get("pdf_static_url"),
        "mineru_static_url": enriched.get("mineru_static_url"),
        "zh_static_url": enriched.get("zh_static_url"),
        "bilingual_static_url": enriched.get("bilingual_static_url"),
        "exists": {
            "pdf": bool(paper.get("pdf_path")),
            "mineru": os.path.isfile(paths["mineru"]),
            "zh": os.path.isfile(paths["zh"]),
            "bilingual": os.path.isfile(paths["bilingual"]),
        },
        "translate_status": paper.get("translate_status", "none"),
    }
