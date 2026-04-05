"""
FastAPI composition root for ArxivPaper4.

Responsibilities of this file (and ONLY this file):
  - Create the FastAPI app instance
  - Configure CORS middleware
  - Mount static-file directories
  - Register the startup hook
  - Include all domain routers
  - Provide the SPA / Mobile catch-all routes

All domain logic, Pydantic models, and route handlers live in routers/*.

Usage:
    uvicorn api:app --reload --port 8000
    (run from the Sever/ directory)
"""

import os
import re as _re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from services import (
    analytics_service,
    auth_service,
    config_service,
    llm_config_service,
    prompt_config_service,
)
from community.community_router import router as community_router
from community import community_service

# Domain routers
from routers.admin_router import router as admin_router
from routers.auth_router import router as auth_router
from routers.download_router import router as download_router
from routers.idea_router import router as idea_router
from routers.kb_router import router as kb_router
from routers.paper_router import router as paper_router
from routers.pipeline_router import router as pipeline_router
from routers.seo_router import router as seo_router
from routers.user_paper_router import router as user_paper_router

# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ArxivPaper4 API",
    description="Backend API for ArxivPaper4 paper digest system",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Load config, initialise DB tables, and warn if pipeline data is absent."""
    config_service.load_config()
    llm_config_service.init_db()
    prompt_config_service.init_db()
    seeded_prompts = prompt_config_service.seed_default_idea_prompts()
    if seeded_prompts:
        print(f"[STARTUP] 已写入 {seeded_prompts} 条灵感生成默认提示词到数据库")
    seeded_llm = llm_config_service.seed_default_idea_llm_configs()
    if seeded_llm:
        print(f"[STARTUP] 已写入 {seeded_llm} 条灵感生成默认模型配置到数据库")
    auth_service.init_auth_db()
    analytics_service.init_db()
    community_service.init_db()

    _sever_dir = os.path.dirname(os.path.abspath(__file__))
    _fc_dir = os.path.join(_sever_dir, "data", "file_collect")
    if not os.path.isdir(_fc_dir):
        print(
            f"[WARN] data/file_collect 目录不存在: {_fc_dir}\n"
            "       服务器端尚未运行流水线，日期下拉框和推荐卡片将为空。\n"
            "       请将本地的 Sever/data/file_collect/ 目录上传到服务器，\n"
            "       或在服务器上运行一次流水线以生成数据。",
            flush=True,
        )

# ---------------------------------------------------------------------------
# CORS
# 开发模式：固定允许 localhost 各端口
# 生产模式：通过环境变量 CORS_ORIGINS 追加服务器域名（逗号分隔）
# 示例：export CORS_ORIGINS="http://your-server.com,https://your-server.com"
# ---------------------------------------------------------------------------

_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://localhost:5174",   # Mobile dev server
    "http://127.0.0.1:5174",  # Mobile dev server
    "http://localhost:1420",   # Tauri desktop dev server
    "http://127.0.0.1:1420",  # Tauri desktop dev server
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "tauri://localhost",
    "https://tauri.localhost",
]
_extra_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
_allowed_origins = list(dict.fromkeys(_default_origins + _extra_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static mounts
# ---------------------------------------------------------------------------

_SEVER_ROOT = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_SEVER_ROOT, "data")

if os.path.isdir(_DATA_DIR):
    app.mount("/static/data", StaticFiles(directory=_DATA_DIR), name="data")

_KB_FILES_DIR = os.path.join(_DATA_DIR, "kb_files")
os.makedirs(_KB_FILES_DIR, exist_ok=True)
app.mount("/static/kb_files", StaticFiles(directory=_KB_FILES_DIR), name="kb_files")

_PDFJS_DIR = os.path.join(_SEVER_ROOT, "static", "pdfjs")
if os.path.isdir(_PDFJS_DIR):
    app.mount("/static/pdfjs", StaticFiles(directory=_PDFJS_DIR, html=True), name="pdfjs")

# ---------------------------------------------------------------------------
# Domain routers
# ---------------------------------------------------------------------------

app.include_router(seo_router)           # root-level: /sitemap.xml, /llms.txt, /.well-known/…
app.include_router(auth_router)          # /api/auth/…, /api/subscription/…, /api/announcements
app.include_router(admin_router)         # /api/admin/…
app.include_router(paper_router)         # /api/dates, /api/papers/…, /api/chat/…, /api/digest/…, /api/analytics/…
app.include_router(download_router)      # /api/download/…
app.include_router(kb_router)            # /api/kb/…
app.include_router(idea_router)          # /api/idea/…
app.include_router(user_paper_router)    # /api/user-papers/…
app.include_router(pipeline_router)      # /api/pipeline/…, /api/schedule/…
app.include_router(community_router)     # /api/community/…

# ---------------------------------------------------------------------------
# SPA hosting (production) — desktop (/) and mobile (/m/)
# Serve compiled Vue/Vite dist; unknown paths fall back to index.html.
# Build first:  cd View && npm run build
#               cd Mobile && npm run build
# ---------------------------------------------------------------------------

_FRONTEND_DIST = os.path.normpath(os.path.join(_SEVER_ROOT, "..", "View", "dist"))
_MOBILE_DIST = os.path.normpath(os.path.join(_SEVER_ROOT, "..", "Mobile", "dist"))

if os.path.isdir(_MOBILE_DIST):
    _mobile_assets = os.path.join(_MOBILE_DIST, "assets")
    if os.path.isdir(_mobile_assets):
        app.mount("/m/assets", StaticFiles(directory=_mobile_assets), name="mobile-assets")

    @app.get("/m/{full_path:path}", include_in_schema=False)
    async def serve_mobile_spa(full_path: str):
        """Mobile SPA catch-all — unknown paths return index.html."""
        if full_path:
            file_path = os.path.normpath(os.path.join(_MOBILE_DIST, full_path))
            if not file_path.startswith(_MOBILE_DIST + os.sep) and file_path != _MOBILE_DIST:
                return FileResponse(os.path.join(_MOBILE_DIST, "index.html"))
            if os.path.isfile(file_path):
                return FileResponse(file_path)
        return FileResponse(os.path.join(_MOBILE_DIST, "index.html"))


_TABLET_UA_RE = _re.compile(r"iPad|Tablet|PlayBook|Silk", _re.I)
_PHONE_UA_RE = _re.compile(r"Android|iPhone|iPod|Mobile|webOS|Windows Phone", _re.I)

if os.path.isdir(_FRONTEND_DIST):
    _dist_assets = os.path.join(_FRONTEND_DIST, "assets")
    if os.path.isdir(_dist_assets):
        app.mount("/assets", StaticFiles(directory=_dist_assets), name="vue-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(request: Request, full_path: str):
        """
        Desktop SPA catch-all:
        1. Redirect mobile User-Agents to /m/
        2. Serve real files from dist/ when they exist
        3. Fall back to index.html for Vue Router paths
        """
        if os.path.isdir(_MOBILE_DIST):
            ua = request.headers.get("user-agent", "")
            ua_lower = ua.lower()
            is_tablet = bool(_TABLET_UA_RE.search(ua) or ("android" in ua_lower and "mobile" not in ua_lower))
            is_phone = bool((not is_tablet) and _PHONE_UA_RE.search(ua))
            if is_phone:
                target = f"/m/{full_path}" if full_path else "/m/"
                qs = str(request.url.query)
                if qs:
                    target += f"?{qs}"
                return RedirectResponse(url=target, status_code=302)

        if full_path:
            file_path = os.path.normpath(os.path.join(_FRONTEND_DIST, full_path))
            if not file_path.startswith(_FRONTEND_DIST + os.sep) and file_path != _FRONTEND_DIST:
                return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))
            if os.path.isfile(file_path):
                return FileResponse(file_path)
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))
