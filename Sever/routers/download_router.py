"""
Download Router.

Routes:
  GET  /api/download/paper-file
  GET  /api/download/note/{note_id}
  POST /api/download/batch
  GET  /api/download/latest-installer

Registered in api.py via app.include_router(download_router)
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from services import auth_service, entitlement_service, kb_service, translate_service, user_paper_service
from routers._deps import _KB_FILES_DIR, _EXE_RELEASE_DIR

router = APIRouter(prefix="/api/download", tags=["download"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class BatchDownloadItem(BaseModel):
    paper_id: str
    file_types: list[str] = Field(default=["pdf", "mineru", "zh", "bilingual"])
    scope: str = "kb"
    include_notes: bool = False


class BatchDownloadBody(BaseModel):
    items: list[BatchDownloadItem] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/paper-file", summary="下载论文衍生文件")
def api_download_paper_file(
    paper_id: str = Query(..., description="论文 ID"),
    file_type: str = Query(..., description="文件类型: pdf | mineru | zh | bilingual"),
    scope: str = Query("kb", description="来源: kb | mypapers"),
    fmt: str = Query("md", alias="format", description="输出格式: md | docx | pdf"),
    hue: int = Query(195, ge=0, le=360, description="双语 PDF 色相 (0-360)"),
    sat: int = Query(70, ge=0, le=100, description="双语 PDF 饱和度 (0-100)"),
    intensity: int = Query(6, ge=2, le=15, description="双语 PDF 背景浓度 (2-15)"),
    font_size: int = Query(15, ge=12, le=20, description="双语 PDF 基础字号 (12-20px)"),
    _user=Depends(auth_service.require_user),
):
    import re
    import tempfile
    from services import export_service

    file_type = file_type.lower().strip()
    if file_type not in ("pdf", "mineru", "zh", "bilingual"):
        raise HTTPException(status_code=400, detail="无效的 file_type，可选: pdf | mineru | zh | bilingual")

    fmt = fmt.lower().strip()
    if fmt not in ("md", "docx", "pdf"):
        raise HTTPException(status_code=400, detail="无效的 format，可选: md | docx | pdf")

    # Quota check: DOCX/PDF export consumes monthly export quota (all tiers)
    if fmt in ("docx", "pdf"):
        entitlement_service.consume_quota(_user["id"], "export")

    user_id = _user["id"]

    def _safe_title(raw: str) -> str:
        cleaned = re.sub(r'[\\/*?:"<>|\r\n]', "_", raw).strip()
        return cleaned[:80] or paper_id

    if scope == "mypapers":
        paper = user_paper_service.get_paper(user_id, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="论文不存在")
        title_raw = paper.get("title") or paper_id
        safe_base = _safe_title(title_raw)
        if file_type == "pdf":
            if not paper.get("pdf_path"):
                raise HTTPException(status_code=404, detail="PDF 不存在")
            abs_path = os.path.join(user_paper_service._KB_FILES_DIR, paper["pdf_path"])
            filename = f"{safe_base}.pdf"
            return FileResponse(
                path=abs_path,
                filename=filename,
                media_type="application/pdf",
            )
        else:
            paths = translate_service.paper_derivative_paths(user_id, paper_id)
            md_path = paths[file_type]
    else:
        paper = kb_service.get_kb_paper(user_id, paper_id, scope=scope)
        if paper is None:
            raise HTTPException(status_code=404, detail="论文不在知识库中")
        pd_data = paper.get("paper_data") or {}
        if isinstance(pd_data, str):
            try:
                import json as _json
                pd_data = _json.loads(pd_data)
            except Exception:
                pd_data = {}
        title_raw = pd_data.get("short_title") or pd_data.get("📖标题") or paper_id
        safe_base = _safe_title(str(title_raw))
        if file_type == "pdf":
            abs_path = os.path.join(_KB_FILES_DIR, str(user_id), paper_id, f"{paper_id}.pdf")
            filename = f"{safe_base}.pdf"
            return FileResponse(
                path=abs_path,
                filename=filename,
                media_type="application/pdf",
            )
        else:
            paths = translate_service.kb_paper_derivative_paths(user_id, paper_id)
            if file_type == "mineru" and not os.path.isfile(paths["mineru"]) and os.path.isfile(paths["mineru_normalized"]):
                md_path = paths["mineru_normalized"]
            else:
                md_path = paths[file_type]

    if not os.path.isfile(md_path):
        raise HTTPException(status_code=404, detail="文件不存在，请先生成")

    base_name = f"{safe_base}_{file_type}"

    if fmt == "md":
        return FileResponse(
            path=md_path,
            filename=f"{base_name}.md",
            media_type="text/markdown; charset=utf-8",
        )

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    if fmt == "docx":
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.close()
        try:
            export_service.markdown_to_docx(md_text, tmp.name, md_base_dir=os.path.dirname(md_path))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"DOCX 转换失败: {exc}") from exc
        docx_filename = f"{base_name}.docx"
        return FileResponse(
            path=tmp.name,
            filename=docx_filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            background=None,
        )

    if fmt == "pdf":
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.close()
        try:
            export_service.markdown_to_pdf(
                md_text,
                tmp.name,
                md_base_dir=os.path.dirname(md_path),
                bilingual=(file_type == "bilingual"),
                bilingual_hue=hue,
                bilingual_saturation=sat,
                bilingual_intensity=intensity,
                bilingual_font_size=font_size,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF 转换失败: {exc}") from exc
        pdf_filename = f"{base_name}.pdf"
        return FileResponse(
            path=tmp.name,
            filename=pdf_filename,
            media_type="application/pdf",
            background=None,
        )


@router.get("/note/{note_id}", summary="下载/导出笔记")
def api_download_note(
    note_id: int,
    _user=Depends(auth_service.require_user),
):
    import io
    note = kb_service.get_note(_user["id"], note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")

    if note.get("type") == "file" and note.get("file_path"):
        abs_path = os.path.join(_KB_FILES_DIR, note["file_path"])
        if not os.path.isfile(abs_path):
            raise HTTPException(status_code=404, detail="附件文件不存在")
        return FileResponse(
            path=abs_path,
            filename=note.get("title", "attachment"),
            media_type=note.get("mime_type") or "application/octet-stream",
        )

    title = note.get("title") or "note"
    content = note.get("content") or ""
    if note.get("type") == "link":
        content = f"# {title}\n\n{note.get('file_url') or ''}\n"
    md_bytes = content.encode("utf-8")
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:60].strip() or "note"
    filename = f"{safe_title}.md"
    from urllib.parse import quote
    encoded_filename = quote(filename, safe="")
    return Response(
        content=md_bytes,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"},
    )


@router.post("/batch", summary="批量下载论文数据（zip）")
def api_download_batch(
    body: BatchDownloadBody,
    _user=Depends(auth_service.require_user),
):
    # Gate check: batch export is Pro+ only
    if not entitlement_service.check_boolean_gate(_user["id"], "batch_export"):
        raise HTTPException(status_code=403, detail="批量导出仅 Pro+ 套餐可用，请升级以继续使用")

    import io
    import zipfile as _zipfile
    import re

    user_id = _user["id"]
    buf = io.BytesIO()

    with _zipfile.ZipFile(buf, mode="w", compression=_zipfile.ZIP_DEFLATED) as zf:
        for item in body.items:
            paper_id = item.paper_id
            scope = item.scope
            file_types = [ft.lower().strip() for ft in item.file_types if ft.lower().strip() in ("pdf", "mineru", "zh", "bilingual")]

            folder_name = paper_id
            if scope == "mypapers":
                p = user_paper_service.get_paper(user_id, paper_id)
                if p:
                    t = (p.get("title") or paper_id)[:50]
                    folder_name = re.sub(r'[\\/*?:"<>|]', "_", t)
            else:
                p = kb_service.get_kb_paper(user_id, paper_id, scope=scope)
                if p:
                    pd = p.get("paper_data") or {}
                    if isinstance(pd, str):
                        try:
                            import json as _json
                            pd = _json.loads(pd)
                        except Exception:
                            pd = {}
                    t = (pd.get("short_title") or pd.get("📖标题") or paper_id)[:50]
                    folder_name = re.sub(r'[\\/*?:"<>|]', "_", str(t))

            for ft in file_types:
                if scope == "mypapers":
                    if ft == "pdf":
                        pp = user_paper_service.get_paper(user_id, paper_id)
                        if pp and pp.get("pdf_path"):
                            abs_p = os.path.join(user_paper_service._KB_FILES_DIR, pp["pdf_path"])
                            ext = ".pdf"
                        else:
                            continue
                    else:
                        paths = translate_service.paper_derivative_paths(user_id, paper_id)
                        abs_p = paths.get(ft, "")
                        ext = f"_{ft}.md"
                else:
                    if ft == "pdf":
                        abs_p = os.path.join(_KB_FILES_DIR, str(user_id), paper_id, f"{paper_id}.pdf")
                        ext = ".pdf"
                    else:
                        paths = translate_service.kb_paper_derivative_paths(user_id, paper_id)
                        if ft == "mineru" and not os.path.isfile(paths.get("mineru", "")) and os.path.isfile(paths.get("mineru_normalized", "")):
                            abs_p = paths.get("mineru_normalized", "")
                        else:
                            abs_p = paths.get(ft, "")
                        ext = f"_{ft}.md"

                if abs_p and os.path.isfile(abs_p):
                    arc_name = f"{folder_name}/{paper_id}{ext}"
                    zf.write(abs_p, arcname=arc_name)

            if item.include_notes:
                notes = kb_service.list_notes(user_id, paper_id, scope=scope)
                for note in notes:
                    if note.get("type") == "file" and note.get("file_path"):
                        abs_p = os.path.join(_KB_FILES_DIR, note["file_path"])
                        if os.path.isfile(abs_p):
                            note_title = note.get("title") or "attachment"
                            arc_name = f"{folder_name}/notes/{note_title}"
                            zf.write(abs_p, arcname=arc_name)
                    elif note.get("type") in ("markdown", "link"):
                        content = note.get("content") or ""
                        if note.get("type") == "link":
                            content = f"# {note.get('title','')}\n\n{note.get('file_url','')}\n"
                        note_title = note.get("title") or "note"
                        safe_title = re.sub(r'[\\/*?:"<>|]', "_", note_title)[:60]
                        arc_name = f"{folder_name}/notes/{safe_title}.md"
                        zf.writestr(arc_name, content.encode("utf-8"))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="papers_export.zip"'},
    )


@router.get("/latest-installer")
async def download_latest_installer():
    """返回 exe_release 文件夹中最新的安装包文件（按修改时间排序）。"""
    if not os.path.isdir(_EXE_RELEASE_DIR):
        raise HTTPException(status_code=404, detail="安装包目录不存在")
    exes = [
        f for f in os.listdir(_EXE_RELEASE_DIR)
        if f.lower().endswith((".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".AppImage"))
    ]
    if not exes:
        raise HTTPException(status_code=404, detail="未找到安装包文件")
    exes.sort(key=lambda f: os.path.getmtime(os.path.join(_EXE_RELEASE_DIR, f)), reverse=True)
    latest = exes[0]
    file_path = os.path.join(_EXE_RELEASE_DIR, latest)
    return FileResponse(
        path=file_path,
        filename=latest,
        media_type="application/octet-stream",
    )
