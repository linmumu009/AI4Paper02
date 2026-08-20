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

import logging
import os
import re as _re
import threading
import time

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from services.private_file_access_service import PrivateKbFilesMiddleware
from services.safe_logging_service import (
    extract_error_reference,
    is_error_reference,
    is_public_error_detail,
    log_internal_error,
    public_error_detail,
)

from config.logging_config import configure_logging
configure_logging()

_logger = logging.getLogger(__name__)

from services import (
    analytics_service,
    auth_service,
    config_service,
    engagement_service,
    entitlement_service,
    llm_config_service,
    openrouter_key_pool_service,
    preference_service,
    project_service,
    prompt_config_service,
    research_service,
)
from community.community_router import router as community_router
from community import community_service

# Domain routers
from routers.admin_router import router as admin_router
from routers.auth_router import router as auth_router
from routers.download_router import router as download_router
from routers.engagement_router import router as engagement_router
from routers.entitlement_router import router as entitlement_router
from routers.idea_router import router as idea_router
from routers.kb_router import router as kb_router
from routers.paper_router import router as paper_router
from routers.pipeline_router import router as pipeline_router
from routers.project_router import router as project_router
from routers.preference_router import router as preference_router
from routers.radar_router import router as radar_router
from routers.recap_router import router as recap_router
from routers.research_router import router as research_router
from routers.search_router import router as search_router
from routers.seo_router import router as seo_router
from routers.user_paper_router import router as user_paper_router
from routers.task_center_router import router as task_center_router

# ---------------------------------------------------------------------------
# Weekly calibration scheduler (Sunday 03:00, per-user NDCG weight tuning)
# ---------------------------------------------------------------------------

_calibration_thread: threading.Thread | None = None
_calibration_last_run_date: str = ""


def _calibration_scheduler_loop() -> None:
    """Background thread: run weight calibration every Sunday at 03:00 UTC."""
    global _calibration_last_run_date
    while True:
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            today = now.date().isoformat()
            # Sunday = weekday 6; run window is 03:00–03:30 UTC
            if (
                now.weekday() == 6
                and now.hour == 3
                and now.minute < 30
                and _calibration_last_run_date != today
            ):
                _calibration_last_run_date = today
                _logger.info("[calibration_scheduler] Starting weekly weight calibration…")
                try:
                    from scripts.calibrate_user_weights import calibrate_user
                    from services import impression_service as _imp
                    eligible = _imp.get_unique_users_with_impressions(min_impressions=30, days=30)
                    wrote = skipped = 0
                    for uid in eligible:
                        res = calibrate_user(uid, days=30, min_saves=5)
                        if res and res.get("wrote"):
                            wrote += 1
                        else:
                            skipped += 1
                    _logger.info(
                        "[calibration_scheduler] Done: %d wrote, %d skipped", wrote, skipped
                    )
                except Exception as exc:
                    _logger.error("[calibration_scheduler] Run failed: %r", exc, exc_info=True)
        except Exception as exc:
            _logger.error("[calibration_scheduler] Loop error: %r", exc)
        # Check every 5 minutes
        time.sleep(300)


def _start_calibration_scheduler() -> None:
    global _calibration_thread
    if _calibration_thread is not None and _calibration_thread.is_alive():
        return
    _calibration_thread = threading.Thread(
        target=_calibration_scheduler_loop, daemon=True, name="calibration_scheduler"
    )
    _calibration_thread.start()
    _logger.info("Weekly calibration scheduler started")


# ---------------------------------------------------------------------------
# Daily bandit reward update (runs nightly around 02:00 UTC)
# ---------------------------------------------------------------------------

_bandit_reward_thread: threading.Thread | None = None
_bandit_reward_last_run: str = ""


def _bandit_reward_loop() -> None:
    global _bandit_reward_last_run
    while True:
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            today = now.date().isoformat()
            if now.hour == 2 and now.minute < 15 and _bandit_reward_last_run != today:
                _bandit_reward_last_run = today
                _logger.info("[bandit_reward] Starting daily bandit reward update…")
                try:
                    from services import preference_service as _pref
                    from services import impression_service as _imp
                    users = _imp.get_unique_users_with_impressions(min_impressions=5, days=30)
                    total = 0
                    for uid in users:
                        summary = _pref.update_bandit_rewards(uid)
                        if summary:
                            total += 1
                    _logger.info("[bandit_reward] Updated %d users", total)
                except Exception as exc:
                    _logger.error("[bandit_reward] Failed: %r", exc, exc_info=True)
        except Exception as exc:
            _logger.error("[bandit_reward] Loop error: %r", exc)
        time.sleep(300)


def _start_bandit_reward_scheduler() -> None:
    global _bandit_reward_thread
    if _bandit_reward_thread is not None and _bandit_reward_thread.is_alive():
        return
    _bandit_reward_thread = threading.Thread(
        target=_bandit_reward_loop, daemon=True, name="bandit_reward_scheduler"
    )
    _bandit_reward_thread.start()
    _logger.info("Daily bandit reward scheduler started")


# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ArxivPaper4 API",
    description="Backend API for ArxivPaper4 paper digest system",
    version="1.0.0",
)


@app.exception_handler(StarletteHTTPException)
async def sanitized_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    if exc.status_code < 500:
        return await http_exception_handler(request, exc)
    existing_reference = str((exc.headers or {}).get("X-Error-ID") or "")
    detail_reference = extract_error_reference(exc.detail)
    if is_public_error_detail(exc.detail) and is_error_reference(detail_reference):
        reference = (
            existing_reference
            if is_error_reference(existing_reference)
            and existing_reference == detail_reference
            else detail_reference
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers={"X-Error-ID": reference},
        )
    reference = log_internal_error(
        _logger,
        "http_exception",
        exc,
        request_path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": public_error_detail(reference)},
        headers={"X-Error-ID": reference},
    )


@app.exception_handler(Exception)
async def sanitized_unhandled_exception_handler(request: Request, exc: Exception):
    reference = log_internal_error(
        _logger,
        "unhandled_exception",
        exc,
        request_path=request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": public_error_detail(reference)},
        headers={"X-Error-ID": reference},
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
    openrouter_key_pool_service.init_db()
    seeded_prompts = prompt_config_service.seed_default_idea_prompts()
    if seeded_prompts:
        _logger.info("已写入 %d 条灵感生成默认提示词到数据库", seeded_prompts)
    seeded_llm = llm_config_service.seed_default_idea_llm_configs()
    if seeded_llm:
        _logger.info("已写入 %d 条灵感生成默认模型配置到数据库", seeded_llm)
    auth_service.init_auth_db()
    analytics_service.init_db()
    engagement_service.init_db()
    entitlement_service.init_db()
    community_service.init_db()
    research_service.init_db()
    project_service.init_db()
    preference_service.init_db()
    from services import recap_service as _recap_svc
    _recap_svc.init_db()
    from services import impression_service as _imp_svc
    _imp_svc.init_db()
    from services import calibration_service as _cal_svc
    _cal_svc.init_db()
    _start_calibration_scheduler()
    _start_bandit_reward_scheduler()

    # Daemon workers are terminated with the API process.  Reconcile their
    # persisted active states before accepting new work so users never see a
    # task stuck at "processing" forever after a deploy or crash.
    try:
        from services import background_task_recovery_service as _btr

        recovered = _btr.reconcile_interrupted_tasks()
        if recovered["total"]:
            _logger.warning(
                "已将 %d 个被服务重启中断的后台任务标记为可重试失败",
                recovered["total"],
            )
    except Exception as exc:
        _logger.error("background task reconciliation failed: %s", exc, exc_info=True)

    # Re-enqueue any classify jobs that were interrupted by the previous restart
    try:
        from services import auto_classify_service as acs
        recovered = acs.recover_all_stalled_jobs()
        if recovered:
            _logger.info("已恢复 %d 个被中断的自动分类任务", recovered)
    except Exception as exc:
        _logger.error("auto_classify recovery failed: %s", exc, exc_info=True)

    # Start PDF cleanup auto-scheduler if enabled
    try:
        from services import pdf_cleanup_service as _pcs
        import config.config as _cfg
        if getattr(_cfg, "PDF_CLEANUP_AUTO_ENABLED", False):
            _pcs.start_auto_scheduler()
            _logger.info("PDF 清理自动调度线程已启动")
    except Exception as exc:
        _logger.error("pdf_cleanup_service startup failed: %s", exc, exc_info=True)

    _sever_dir = os.path.dirname(os.path.abspath(__file__))
    _fc_dir = os.path.join(_sever_dir, "data", "file_collect")
    if not os.path.isdir(_fc_dir):
        _logger.warning(
            "data/file_collect 目录不存在: %s — 服务器端尚未运行流水线，日期下拉框和推荐卡片将为空。"
            "请将本地的 Sever/data/file_collect/ 目录上传到服务器，或在服务器上运行一次流水线以生成数据。",
            _fc_dir,
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
    "http://localhost:5174",   # Mobile dev server (legacy)
    "http://127.0.0.1:5174",  # Mobile dev server (legacy)
    "http://localhost:5175",   # Mobile dev server
    "http://127.0.0.1:5175",  # Mobile dev server
    "http://localhost:1420",   # Tauri desktop dev server
    "http://127.0.0.1:1420",  # Tauri desktop dev server
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "tauri://localhost",
    "https://tauri.localhost",
]
_extra_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
_allowed_origins = list(dict.fromkeys(_default_origins + _extra_origins))

_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
_ALLOWED_HEADERS = [
    "Content-Type", "Authorization", "Accept", "X-Requested-With",
    "Cookie", "X-CSRF-Token",
]

app.add_middleware(PrivateKbFilesMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=_ALLOWED_METHODS,
    allow_headers=_ALLOWED_HEADERS,
    max_age=600,
)

# ---------------------------------------------------------------------------
# Static mounts
# ---------------------------------------------------------------------------

_SEVER_ROOT = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_SEVER_ROOT, "data")

# SECURITY NOTE: Do NOT mount the entire data/ directory — it would expose all pipeline
# artifacts (paper PDFs, summaries, etc.) to unauthenticated requests. Each sub-directory
# that must be publicly reachable is mounted individually below.
#
# Previously the whole data/ directory was mounted at /static/data. This has been removed.
# If any new public asset type is needed, add a targeted sub-directory mount here.

_KB_FILES_DIR = os.path.join(_DATA_DIR, "kb_files")
os.makedirs(_KB_FILES_DIR, exist_ok=True)
# PrivateKbFilesMiddleware authorizes every request by owner session or by the
# short-lived HMAC URL returned from authenticated KB/user-paper endpoints.
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
app.include_router(engagement_router)    # /api/engagement/…
app.include_router(entitlement_router)   # /api/entitlements/…
app.include_router(kb_router)            # /api/kb/…
app.include_router(idea_router)          # /api/idea/…
app.include_router(research_router)      # /api/research/…
app.include_router(project_router)       # /api/projects/…
app.include_router(search_router)        # /api/search
app.include_router(user_paper_router)    # /api/user-papers/…
app.include_router(pipeline_router)      # /api/pipeline/…, /api/schedule/…
app.include_router(community_router)     # /api/community/…
app.include_router(preference_router)   # /api/preferences/…
app.include_router(recap_router)        # /api/recaps/…
app.include_router(radar_router)        # /api/radar/…
app.include_router(task_center_router)  # /api/tasks/…

# ---------------------------------------------------------------------------
# SPA hosting (production) — desktop (/) and mobile (/m/)
# Serve compiled Vue/Vite dist; unknown paths fall back to index.html.
# Build first:  cd View && npm run build
#               cd mobile_new && npm run build
# ---------------------------------------------------------------------------

_FRONTEND_DIST = os.path.normpath(os.path.join(_SEVER_ROOT, "..", "View", "dist"))
_MOBILE_DIST = os.path.normpath(os.path.join(_SEVER_ROOT, "..", "mobile_new", "dist"))

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
