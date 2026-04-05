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
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from services import analytics_service, auth_service, chat_service, data_service, kb_service
from routers._deps import _get_optional_user, _tier_label, _tier_quota_limit

router = APIRouter(prefix="/api", tags=["papers"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class PaperChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class AnalyticsEventBody(BaseModel):
    event_type: str = Field(..., description="事件类型")
    target_type: Optional[str] = Field(None)
    target_id: Optional[str] = Field(None)
    value: Optional[float] = Field(None)
    meta: Optional[dict] = Field(None)


class AnalyticsEventBatchBody(BaseModel):
    events: list[AnalyticsEventBody] = Field(...)


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
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    search: str = Query(None, description="Search in title / paper_id / institution"),
    institution: str = Query(None, description="Filter by institution name"),
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


@router.get("/papers/{paper_id}/pdf", summary="Serve local PDF for a paper")
def api_paper_pdf(paper_id: str):
    source = kb_service._find_pdf_in_file_collect(paper_id)
    if source is None:
        raise HTTPException(status_code=404, detail="PDF not found locally")
    return FileResponse(source, media_type="application/pdf")


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
    return StreamingResponse(
        chat_service.stream_chat(user["id"], paper_id, body.message),
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
    pid = chat_service.GENERAL_CHAT_PAPER_ID
    return StreamingResponse(
        chat_service.stream_chat(user["id"], pid, body.message),
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
    digest = data_service.get_daily_digest(date, user_id=uid)
    papers = digest.get("papers", [])

    kb_ids: set[str] = set()
    dismissed_ids: set[str] = set()
    if user:
        kb_ids = kb_service.get_kb_paper_ids(user["id"])
        dismissed_ids = kb_service.get_dismissed_paper_ids(user["id"])
    exclude_ids = kb_ids | dismissed_ids
    if exclude_ids:
        papers = [p for p in papers if p.get("paper_id") not in exclude_ids]

    total_available = len(papers)
    quota_limit = _tier_quota_limit(user)
    if quota_limit is not None:
        digest["papers"] = papers[:quota_limit]
    else:
        digest["papers"] = papers
    digest["total_available"] = total_available
    digest["total_papers"] = len(digest["papers"])
    digest["quota_limit"] = quota_limit
    digest["tier"] = _tier_label(user)
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

@router.post("/analytics/event", summary="Report a single analytics event")
def api_analytics_event(body: AnalyticsEventBody, request: Request):
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
    return {"ok": True, "event_id": eid}


@router.post("/analytics/events", summary="Report analytics events in batch")
def api_analytics_events_batch(body: AnalyticsEventBatchBody, request: Request):
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
    return {"ok": True, "count": count}
