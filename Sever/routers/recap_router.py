"""
Weekly Recap Router.

Endpoints:
  GET  /api/recaps/current                  – get (or generate) this week's recap
  POST /api/recaps/current/generate         – force-regenerate this week's recap
  GET  /api/recaps/history                  – list past recaps (status=ok only)
  GET  /api/recaps/review-cards             – get papers due for spaced review
  POST /api/recaps/review-cards/{paper_id}/response – record review response
"""

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query

from services import auth_service, recap_service

router = APIRouter(prefix="/api/recaps", tags=["recaps"])


@router.get("/current", summary="Get or generate current weekly recap")
def api_get_current_recap(
    force: bool = Query(False, description="Force regenerate even if cached"),
    user=Depends(auth_service.require_user),
):
    """Return this week's research recap for the calling user.

    If a cached recap exists (status=ok | insufficient_papers | no_llm_config)
    it is returned immediately unless ``force=true``.

    Response fields:
      status          – "ok" | "insufficient_papers" | "no_llm_config" | "error"
      week_start      – ISO date string (Monday of the recap window)
      week_end        – ISO date string (Sunday of the recap window)
      paper_count     – number of papers saved in the window
      recap           – the generated recap object, or null
      papers          – list of {paper_id, title, title_en, institution, categories, saved_at}
    """
    return recap_service.get_or_generate_recap(user["id"], force=force)


@router.post("/current/generate", summary="Force-regenerate current weekly recap")
def api_generate_recap(user=Depends(auth_service.require_user)):
    """Trigger a fresh LLM recap generation for the current week, ignoring the cache."""
    return recap_service.get_or_generate_recap(user["id"], force=True)


@router.get("/history", summary="List past weekly recaps")
def api_recap_history(
    limit: int = Query(12, ge=1, le=52),
    user=Depends(auth_service.require_user),
):
    """Return past successful recaps for the calling user (most recent first)."""
    return {"recaps": recap_service.get_recap_history(user["id"], limit=limit)}


@router.get("/review-cards", summary="Get papers due for spaced review")
def api_get_review_cards(
    limit: int = Query(3, ge=1, le=5),
    user=Depends(auth_service.require_user),
):
    """Return up to *limit* papers saved ~7/30/90 days ago that are due for review.

    Each item in the returned list is a paper summary dict with extra fields:
      card_kind='review', review_reason, days_since_saved, saved_at
    """
    cards = recap_service.get_review_cards(user["id"], limit=limit)
    return {"cards": cards, "count": len(cards)}


class ReviewResponseBody(BaseModel):
    response: str  # 'remember' | 'reread' | 'dismiss_forever' | 'skip'


@router.post("/review-cards/{paper_id}/response", summary="Record review card response")
def api_record_review_response(
    paper_id: str,
    body: ReviewResponseBody,
    user=Depends(auth_service.require_user),
):
    """Record the user's response to a review card.

    Valid responses: remember | reread | dismiss_forever | skip
    """
    valid = {"remember", "reread", "dismiss_forever", "skip"}
    if body.response not in valid:
        raise HTTPException(status_code=422, detail=f"response must be one of: {valid}")
    recap_service.record_review_response(user["id"], paper_id, body.response)
    return {"ok": True}
