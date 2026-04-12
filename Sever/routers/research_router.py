"""
Deep Research Q&A Router.

Routes:
  POST   /api/research/start                         — Start a new research session (SSE stream)
  POST   /api/research/{session_id}/continue-round3  — Re-run Round 3 from existing R1/R2 (SSE stream)
  POST   /api/research/{session_id}/followup         — Follow-up using parent R1, re-run R2+R3 (SSE stream)
  POST   /api/research/{session_id}/cancel           — Cancel a running session
  GET    /api/research/sessions                      — List user's research sessions
  GET    /api/research/tree                          — Get folder tree with nested sessions
  PATCH  /api/research/move                          — Batch-move sessions to a folder
  PATCH  /api/research/{session_id}/rename           — Rename (update question) of a session
  PATCH  /api/research/{session_id}/save             — Save or unsave a session
  GET    /api/research/{session_id}                  — Get a session with all round results
  DELETE /api/research/{session_id}                  — Delete a session

Registered in api.py via app.include_router(research_router).
"""

import asyncio
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.requests import Request

from services import auth_service, engagement_service, entitlement_service, research_service

router = APIRouter(prefix="/api/research", tags=["research"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ResearchConfig(BaseModel):
    top_n: int = Field(default=5, ge=1, le=30, description="Top N papers to use after ranking (up to 30 with reward)")
    force_full_read: bool = Field(default=False, description="Force Round 3 full-text read even when Round 2 is sufficient")


class StartResearchBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    paper_ids: list[str] = Field(..., min_length=1, max_length=30)
    scope: str = Field(default="kb")
    config: ResearchConfig = Field(default_factory=ResearchConfig)
    reward_id: Optional[int] = Field(default=None, description="Engagement reward ID to apply a research boost")


class FollowupBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    context: Optional[str] = Field(default=None, max_length=4000,
                                   description="Previous answer summary for continuity")


class RenameBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class MoveSessionsBody(BaseModel):
    session_ids: list[int] = Field(..., min_length=1)
    target_folder_id: Optional[int] = Field(default=None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/start", summary="Start a deep research session (SSE stream)")
async def api_start_research(
    body: StartResearchBody,
    request: Request,
    user=Depends(auth_service.require_user),
):
    # Quota check: consume one research session credit (Free: 2/month, Pro: 15/month)
    entitlement_service.consume_quota(user["id"], "research")

    # Apply engagement reward boost if provided.
    # Consume the reward first; only apply the boost to config if consumption succeeds.
    # This prevents a race where the boost takes effect even when the reward is already used/expired.
    config_dict = body.config.model_dump()
    reward_used = False
    if body.reward_id is not None:
        boost = engagement_service.get_reward_boost(user["id"], "research", body.reward_id)
        if boost:
            try:
                engagement_service.use_reward(
                    user["id"], body.reward_id,
                    f"research_start_{len(body.paper_ids)}_papers"
                )
                reward_used = True
                # Apply boost only after successful consumption
                multiplier = boost.get("input_hard_limit_multiplier", 1.0)
                if multiplier > 1.0:
                    base_limit = config_dict.get("input_hard_limit", 200000)
                    config_dict["input_hard_limit"] = int(base_limit * multiplier)
                max_top_n = boost.get("max_top_n", 20)
                if config_dict.get("top_n", 5) > 20:
                    config_dict["top_n"] = min(config_dict["top_n"], max_top_n)
            except ValueError:
                pass  # Already used, expired, or honorary — proceed without boost

    # Threading event shared between the async disconnect-watcher and the sync generator.
    cancel_event = threading.Event()

    async def _watch_disconnect() -> None:
        """Background coroutine: sets cancel_event when the client disconnects."""
        while not cancel_event.is_set():
            if await request.is_disconnected():
                cancel_event.set()
                return
            await asyncio.sleep(0.5)

    watch_task = asyncio.create_task(_watch_disconnect())

    def _gen():
        try:
            yield from research_service.stream_research(
                user_id=user["id"],
                question=body.question,
                paper_ids=body.paper_ids,
                scope=body.scope,
                config=config_dict,
                cancel_event=cancel_event,
            )
        finally:
            # Signal the watcher to stop regardless of how the generator exits.
            cancel_event.set()
            watch_task.cancel()

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Reward-Applied": "1" if reward_used else "0",
        },
    )


@router.post("/{session_id}/continue-round3", summary="Continue with Round 3 from an existing session (SSE stream)")
async def api_continue_round3(
    session_id: int,
    request: Request,
    user=Depends(auth_service.require_user),
):
    # Quota check: R3 re-runs full-text LLM calls — counts against research quota
    entitlement_service.consume_quota(user["id"], "research")

    cancel_event = threading.Event()

    async def _watch_disconnect() -> None:
        while not cancel_event.is_set():
            if await request.is_disconnected():
                cancel_event.set()
                return
            await asyncio.sleep(0.5)

    watch_task = asyncio.create_task(_watch_disconnect())

    def _gen():
        try:
            yield from research_service.stream_continue_round3(
                user_id=user["id"],
                session_id=session_id,
                cancel_event=cancel_event,
            )
        finally:
            cancel_event.set()
            watch_task.cancel()

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{session_id}/followup", summary="Follow-up on a completed session reusing R1 (SSE stream)")
async def api_followup_research(
    session_id: int,
    body: FollowupBody,
    request: Request,
    user=Depends(auth_service.require_user),
):
    # Quota check: followup re-runs R2+R3 LLM calls — counts against research quota
    entitlement_service.consume_quota(user["id"], "research")

    cancel_event = threading.Event()

    async def _watch_disconnect() -> None:
        while not cancel_event.is_set():
            if await request.is_disconnected():
                cancel_event.set()
                return
            await asyncio.sleep(0.5)

    watch_task = asyncio.create_task(_watch_disconnect())

    def _gen():
        try:
            yield from research_service.stream_followup(
                user_id=user["id"],
                parent_session_id=session_id,
                question=body.question,
                context=body.context,
                cancel_event=cancel_event,
            )
        finally:
            cancel_event.set()
            watch_task.cancel()

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{session_id}/cancel", summary="Cancel a running research session")
def api_cancel_session(
    session_id: int,
    user=Depends(auth_service.require_user),
):
    ok = research_service.cancel_session(user["id"], session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found or not currently running")
    return {"ok": True}


@router.get("/sessions", summary="List user's research sessions")
def api_list_sessions(
    limit: int = 20,
    saved_only: bool = False,
    user=Depends(auth_service.require_user),
):
    ent = entitlement_service.get_user_entitlements(user["id"])
    retention_days = ent.get("retention", {}).get("research_history_days")
    sessions = research_service.list_sessions(
        user["id"],
        limit=min(limit, 200),
        saved_only=saved_only,
        retention_days=retention_days,
    )
    return {"sessions": sessions}


@router.get("/tree", summary="Get research session folder tree")
def api_get_tree(user=Depends(auth_service.require_user)):
    ent = entitlement_service.get_user_entitlements(user["id"])
    retention_days = ent.get("retention", {}).get("research_history_days")
    return research_service.get_tree(user["id"], retention_days=retention_days)


@router.patch("/move", summary="Batch-move research sessions to a folder")
def api_move_sessions(
    body: MoveSessionsBody,
    user=Depends(auth_service.require_user),
):
    count = research_service.move_sessions(user["id"], body.session_ids, body.target_folder_id)
    return {"moved": count}


@router.patch("/{session_id}/rename", summary="Rename a research session")
def api_rename_session(
    session_id: int,
    body: RenameBody,
    user=Depends(auth_service.require_user),
):
    ok = research_service.rename_session(user["id"], session_id, body.question)
    if not ok:
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"ok": True}


@router.patch("/{session_id}/save", summary="Save or unsave a research session")
def api_save_session(
    session_id: int,
    saved: bool = True,
    user=Depends(auth_service.require_user),
):
    ok = research_service.save_session(user["id"], session_id, saved)
    if not ok:
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"ok": True}


@router.get("/{session_id}", summary="Get a research session with all rounds")
def api_get_session(
    session_id: int,
    user=Depends(auth_service.require_user),
):
    session = research_service.get_session(user["id"], session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Research session not found")
    return session


@router.delete("/{session_id}", summary="Delete a research session")
def api_delete_session(
    session_id: int,
    user=Depends(auth_service.require_user),
):
    deleted = research_service.delete_session(user["id"], session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"ok": True}


@router.get("/{session_id}/download", summary="Download research result as MD / DOCX / PDF")
def api_download_research(
    session_id: int,
    format: str = "md",
    user=Depends(auth_service.require_user),
):
    import re
    import tempfile
    from fastapi.responses import FileResponse, Response
    from services import export_service

    format = format.lower().strip()
    if format not in ("md", "docx", "pdf"):
        raise HTTPException(status_code=400, detail="format must be md | docx | pdf")

    if format in ("docx", "pdf"):
        entitlement_service.consume_quota(user["id"], "export")

    session = research_service.get_session(user["id"], session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Research session not found")

    # Extract final text (R3 preferred, fall back to R2)
    final_text = ""
    rounds = session.get("rounds") or []
    for r in rounds:
        if r.get("round_type") == "full_text":
            out = r.get("output") or {}
            if out.get("full_text"):
                final_text = out["full_text"]
                break
    if not final_text:
        for r in rounds:
            if r.get("round_type") == "summary_analysis":
                out = r.get("output") or {}
                if out.get("full_text"):
                    final_text = out["full_text"]
                    break

    if not final_text:
        raise HTTPException(status_code=404, detail="No result text found in this session")

    question = session.get("question", "research_result")
    safe_q = re.sub(r'[^\w\u4e00-\u9fff\s\-]', '', question)[:40].strip().replace(' ', '_') or "research_result"
    base_name = f"research_{safe_q}"

    if format == "md":
        from urllib.parse import quote as _quote
        md_filename = f"{base_name}.md"
        encoded_md_filename = _quote(md_filename, safe="")
        content = final_text.encode("utf-8")
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_md_filename}"},
        )

    if format == "docx":
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.close()
        export_service.markdown_to_docx(final_text, tmp.name)
        return FileResponse(
            tmp.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"{base_name}.docx",
        )

    # pdf
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    export_service.markdown_to_pdf(final_text, tmp.name)
    return FileResponse(
        tmp.name,
        media_type="application/pdf",
        filename=f"{base_name}.pdf",
    )
