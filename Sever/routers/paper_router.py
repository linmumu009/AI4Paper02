"""
Paper Feed + Chat + Analytics event tracking Router.

Routes:
  GET  /api/dates
  GET  /api/papers
  GET  /api/papers/{paper_id}
  GET  /api/papers/{paper_id}/pdf
  GET  /api/papers/{paper_id}/chat
  POST /api/papers/{paper_id}/chat
  DELETE /api/papers/{paper_id}/chat
  GET  /api/chat/general
  POST /api/chat/general
  DELETE /api/chat/general
  GET  /api/digest/{date}
  GET  /api/pipeline/status
  POST /api/analytics/event
  POST /api/analytics/events

Registered in api.py via app.include_router(paper_router)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from services import analytics_service, auth_service, chat_service, data_service, engagement_service, entitlement_service, kb_service
from services.quota_stream_service import guard_quota_stream
from routers._deps import _get_optional_user, _tier_label, _tier_quota_limit, _analytics_limiter

router = APIRouter(prefix="/api", tags=["papers"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class PaperChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    reward_id: Optional[int] = Field(default=None, description="Engagement reward ID to apply a chat context boost")


class AnalyticsEventBody(BaseModel):
    event_type: str = Field(..., description="事件类型")
    target_type: Optional[str] = Field(None)
    target_id: Optional[str] = Field(None)
    value: Optional[float] = Field(None)
    meta: Optional[dict] = Field(None)


class AnalyticsEventBatchBody(BaseModel):
    events: list[AnalyticsEventBody] = Field(..., max_length=50)


# ---------------------------------------------------------------------------
# Paper feed
# ---------------------------------------------------------------------------

@router.get("/dates", summary="List available dates")
def api_list_dates(user: Optional[dict] = Depends(_get_optional_user)):
    uid = user["id"] if user else 0
    dates = data_service.list_dates(user_id=uid)
    return {"dates": dates}


@router.get("/papers", summary="List papers for a date")
def api_list_papers(
    date: str = Query(..., description="Date in YYYY-MM-DD format", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    search: str = Query(None, description="Search in title / paper_id / institution", max_length=200),
    institution: str = Query(None, description="Filter by institution name", max_length=200),
    user: Optional[dict] = Depends(_get_optional_user),
):
    uid = user["id"] if user else 0
    papers = data_service.get_papers_by_date(date, search=search, institution=institution, user_id=uid)
    total_available = len(papers)
    quota_limit = _tier_quota_limit(user)
    if quota_limit is not None:
        papers = papers[:quota_limit]
    return {
        "date": date,
        "count": len(papers),
        "papers": papers,
        "total_available": total_available,
        "quota_limit": quota_limit,
        "tier": _tier_label(user),
    }


@router.get("/papers/{paper_id}/pdf", summary="Serve local PDF for a paper")
def api_paper_pdf(
    request: Request,
    paper_id: str,
    user: Optional[dict] = Depends(_get_optional_user),
):
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录以查看 PDF")
    source = kb_service._find_pdf_in_file_collect(paper_id)
    if source is None:
        raise HTTPException(status_code=404, detail="PDF not found locally")

    import os as _os
    import hashlib as _hl
    import email.utils as _eu
    import time as _time

    file_size = _os.path.getsize(source)
    mtime = _os.path.getmtime(source)
    etag = f'"{_hl.md5(f"{paper_id}:{file_size}:{mtime}".encode()).hexdigest()}"'
    last_modified = _eu.formatdate(_time.mktime(_time.gmtime(mtime)), usegmt=True)

    base_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=86400",
        "ETag": etag,
        "Last-Modified": last_modified,
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "Accept-Ranges, Content-Range, Content-Length, ETag",
    }

    range_header = request.headers.get("Range")
    if range_header:
        # Parse "bytes=start-end" and return 206 Partial Content so PDF.js can
        # stream individual chunks instead of waiting for the full file.
        try:
            unit, rng = range_header.split("=", 1)
            if unit.strip().lower() != "bytes":
                raise ValueError("unsupported range unit")
            start_str, end_str = rng.split("-", 1)
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
            end = min(end, file_size - 1)
            if start > end or start >= file_size:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{file_size}"},
                )
            length = end - start + 1

            def _iter_range():
                with open(source, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            return StreamingResponse(
                _iter_range(),
                status_code=206,
                media_type="application/pdf",
                headers={
                    **base_headers,
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(length),
                },
            )
        except (ValueError, AttributeError):
            pass  # Fall through to full-file response

    # No Range header — return the full file with caching headers.
    return FileResponse(
        source,
        media_type="application/pdf",
        headers={**base_headers, "Content-Length": str(file_size)},
    )


@router.get("/papers/{paper_id}/images/{filename}", summary="Serve selected paper image")
def api_paper_image(
    paper_id: str,
    filename: str,
    date: str = Query(..., description="Pipeline date in YYYY-MM-DD format", pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    source = data_service.get_paper_image_path(date, paper_id, filename)
    if source is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(source)


@router.get("/papers/{paper_id}", summary="Get paper detail")
def api_paper_detail(
    paper_id: str,
    user: Optional[dict] = Depends(_get_optional_user),
):
    uid = user["id"] if user else 0
    detail = data_service.get_paper_detail(paper_id, user_id=uid)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
    return detail


# ---------------------------------------------------------------------------
# Paper chat
# ---------------------------------------------------------------------------

@router.get("/papers/{paper_id}/chat", summary="Get paper chat history")
def api_get_paper_chat(
    paper_id: str,
    user=Depends(auth_service.require_user),
):
    messages = chat_service.get_messages(user["id"], paper_id)
    return {"paper_id": paper_id, "messages": messages}


@router.post("/papers/{paper_id}/chat", summary="Send message and stream reply")
def api_post_paper_chat(
    paper_id: str,
    body: PaperChatBody,
    user=Depends(auth_service.require_user),
):
    if data_service.get_paper_detail(paper_id, user_id=user["id"]) is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")

    boost: dict = {}
    if body.reward_id is not None:
        boost = engagement_service.get_reward_boost(
            user["id"], "chat", body.reward_id
        )
    boost_state = {"input_multiplier": 1.0}

    def _commit_reward() -> None:
        if body.reward_id is not None and boost:
            try:
                engagement_service.use_reward(user["id"], body.reward_id, f"chat_boost_{paper_id}")
                boost_state["input_multiplier"] = boost.get(
                    "input_hard_limit_multiplier", 1.0
                )
            except ValueError:
                pass

    receipt = entitlement_service.reserve_quota(user["id"], "chat")
    stream = chat_service.stream_chat(
        user["id"],
        paper_id,
        body.message,
        input_multiplier=lambda: boost_state["input_multiplier"],
    )
    return StreamingResponse(
        guard_quota_stream(
            stream,
            receipt.get("reservation_id"),
            on_commit=_commit_reward,
            operation="paper_chat",
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/papers/{paper_id}/chat", summary="Clear paper chat history")
def api_delete_paper_chat(
    paper_id: str,
    user=Depends(auth_service.require_user),
):
    chat_service.clear_session(user["id"], paper_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# General assistant chat
# ---------------------------------------------------------------------------

@router.get("/chat/general", summary="Get general assistant chat history")
def api_get_general_chat(user=Depends(auth_service.require_user)):
    pid = chat_service.GENERAL_CHAT_PAPER_ID
    messages = chat_service.get_messages(user["id"], pid)
    return {"messages": messages}


@router.post("/chat/general", summary="General assistant chat (SSE stream)")
def api_post_general_chat(
    body: PaperChatBody,
    user=Depends(auth_service.require_user),
):
    # Gate check: general chat is Pro/Pro+ only
    if not entitlement_service.check_boolean_gate(user["id"], "general_chat"):
        raise HTTPException(status_code=403, detail="通用 AI 助手仅 Pro 及以上套餐可用，请升级以继续使用")
    boost: dict = {}
    if body.reward_id is not None:
        boost = engagement_service.get_reward_boost(
            user["id"], "chat", body.reward_id
        )
    boost_state = {"input_multiplier": 1.0}

    def _commit_reward() -> None:
        if body.reward_id is not None and boost:
            try:
                engagement_service.use_reward(user["id"], body.reward_id, "chat_boost_general")
                boost_state["input_multiplier"] = boost.get(
                    "input_hard_limit_multiplier", 1.0
                )
            except ValueError:
                pass

    pid = chat_service.GENERAL_CHAT_PAPER_ID
    receipt = entitlement_service.reserve_quota(user["id"], "chat")
    stream = chat_service.stream_chat(
        user["id"],
        pid,
        body.message,
        input_multiplier=lambda: boost_state["input_multiplier"],
    )
    return StreamingResponse(
        guard_quota_stream(
            stream,
            receipt.get("reservation_id"),
            on_commit=_commit_reward,
            operation="general_chat",
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/chat/general", summary="Clear general assistant chat history")
def api_delete_general_chat(user=Depends(auth_service.require_user)):
    chat_service.clear_session(user["id"], chat_service.GENERAL_CHAT_PAPER_ID)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Digest & pipeline status
# ---------------------------------------------------------------------------

@router.get("/digest/{date}", summary="Daily digest")
def api_daily_digest(
    date: str,
    user: Optional[dict] = Depends(_get_optional_user),
):
    uid = user["id"] if user else 0
    quota_limit = _tier_quota_limit(user)

    # Pre-fetch KB and dismissed IDs once (avoid repeated DB calls in fallback loop)
    kb_ids: set[str] = set()
    dismissed_ids: set[str] = set()
    if user:
        kb_ids = kb_service.get_kb_paper_ids(user["id"])
        dismissed_ids = kb_service.get_dismissed_paper_ids(user["id"])
    exclude_ids = kb_ids | dismissed_ids

    def _filter_papers(raw_papers: list) -> list:
        if not exclude_ids:
            return raw_papers
        return [p for p in raw_papers if p.get("paper_id") not in exclude_ids]

    # Try the requested date first
    digest = data_service.get_daily_digest(date, user_id=uid)
    papers = _filter_papers(digest.get("papers", []))
    effective_date = date
    is_fallback = False

    # Fallback: if the requested date has no unread papers, look for the most recent
    # earlier date that still has papers the user hasn't dismissed or collected.
    if not papers:
        all_dates = data_service.list_dates(user_id=uid)
        try:
            start_idx = all_dates.index(date)
        except ValueError:
            # Requested date not in list — start from the beginning
            start_idx = -1
        for earlier_date in all_dates[start_idx + 1:]:
            fallback_digest = data_service.get_daily_digest(earlier_date, user_id=uid)
            fallback_papers = _filter_papers(fallback_digest.get("papers", []))
            if fallback_papers:
                digest = fallback_digest
                papers = fallback_papers
                effective_date = earlier_date
                is_fallback = True
                break

    total_available = len(papers)
    if quota_limit is not None:
        digest["papers"] = papers[:quota_limit]
    else:
        digest["papers"] = papers
    digest["total_available"] = total_available
    digest["total_papers"] = len(digest["papers"])
    digest["quota_limit"] = quota_limit
    digest["tier"] = _tier_label(user)
    digest["effective_date"] = effective_date
    digest["is_fallback"] = is_fallback
    return digest


@router.get("/pipeline/status", summary="Pipeline status")
def api_pipeline_status(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
):
    status = data_service.get_pipeline_status(date)
    return {"date": date, "steps": status}


# ---------------------------------------------------------------------------
# Analytics event tracking (all logged-in or anonymous users)
# ---------------------------------------------------------------------------

def _maybe_record_preference_feedback(user_id: int, event_type: str, target_id: str, value: Optional[float]) -> None:
    """Translate analytics events into preference feedback signals (fire-and-forget)."""
    if user_id <= 0 or not target_id:
        return
    try:
        from services import preference_service as _pref
        action: Optional[str] = None
        if event_type == "paper_view_duration" and value is not None:
            action = "paper_view_deep" if value >= _pref.VIEW_DEEP_S else None
        elif event_type == "paper_view":
            action = "paper_view"
        if action is None:
            return
        feats = _pref.get_cached_paper_features(target_id)
        _pref.record_feedback(
            user_id=user_id,
            paper_id=target_id,
            action=action,
            categories=feats["categories"] if feats else None,
            keywords=feats["keywords"] if feats else None,
            institution_tier=feats["institution_tier"] if feats else 4,
            source="analytics",
        )
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).debug("preference feedback from analytics event skipped: %r", _exc)


@router.post("/analytics/event", summary="Report a single analytics event")
def api_analytics_event(body: AnalyticsEventBody, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _analytics_limiter.check(client_ip)
    user = auth_service.get_current_user_optional(request)
    user_id = user["id"] if user else 0
    eid = analytics_service.record_event(
        user_id=user_id,
        event_type=body.event_type,
        target_type=body.target_type,
        target_id=body.target_id,
        value=body.value,
        meta=body.meta,
    )
    # Translate paper_view / paper_view_duration into preference signals
    if body.target_type == "paper":
        _maybe_record_preference_feedback(user_id, body.event_type, body.target_id or "", body.value)
    return {"ok": True, "event_id": eid}


@router.post("/analytics/events", summary="Report analytics events in batch")
def api_analytics_events_batch(body: AnalyticsEventBatchBody, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _analytics_limiter.check(client_ip)
    user = auth_service.get_current_user_optional(request)
    user_id = user["id"] if user else 0
    events = [
        {
            "user_id": user_id,
            "event_type": e.event_type,
            "target_type": e.target_type,
            "target_id": e.target_id,
            "value": e.value,
            "meta": e.meta,
        }
        for e in body.events
    ]
    count = analytics_service.record_events_batch(events)
    # Translate relevant paper events into preference signals (batch)
    for e in body.events:
        if e.target_type == "paper":
            _maybe_record_preference_feedback(user_id, e.event_type, e.target_id or "", e.value)
    return {"ok": True, "count": count}
