"""Research Radar Router.

GET /api/radar/today?date=YYYY-MM-DD

Returns a combined daily summary for the research radar panel, aggregating
five existing services. Each authenticated section degrades gracefully on
failure so a single slow or broken service never blocks the whole panel.

Anonymous users receive only the ``papers`` section.
Authenticated users receive all five sections.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from routers._deps import _get_optional_user, _tier_quota_limit, _tier_label
from services import auth_service, data_service, idea_service, kb_service, preference_service, recap_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/radar", tags=["radar"])


@router.get("/today", summary="Research radar daily summary")
def api_radar_today(
    date: str = Query(..., description="Content date YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: Optional[dict] = Depends(_get_optional_user),
):
    """Return a combined daily research summary for the radar panel.

    Response shape::

        {
          "date": str,
          "tier": str,
          "papers": {
            "total_available": int, "visible_count": int,
            "quota_limit": int | null, "is_fallback": bool, "effective_date": str
          },
          "missed":        {"count": int, "preview": [...]} | null,
          "review":        {"count": int, "preview": [...]} | null,
          "recap":         {"status": str, "paper_count": int, "week_start": str, "week_end": str} | null,
          "ideas":         {"total_available": int, "visible_count": int} | null,
          "reactivation":  {"count": int, "preview": [...]} | null
        }

    ``null`` sections indicate the user is not authenticated or the section
    is temporarily unavailable.
    """
    uid = user["id"] if user else 0
    quota_limit = _tier_quota_limit(user)

    # ── 1. Papers (digest summary) – available to all ──────────────────────
    papers_section: dict = {
        "total_available": 0,
        "visible_count": 0,
        "quota_limit": quota_limit,
        "is_fallback": False,
        "effective_date": date,
    }
    # Store all unfiltered paper ids for later idea-section reuse.
    _all_paper_ids: list[str] = []
    _effective_date = date

    try:
        kb_ids: set[str] = kb_service.get_kb_paper_ids(uid) if uid else set()
        dismissed_ids: set[str] = kb_service.get_dismissed_paper_ids(uid) if uid else set()
        exclude_ids = kb_ids | dismissed_ids

        digest = data_service.get_daily_digest(date, user_id=uid)
        raw_papers = digest.get("papers", [])
        _all_paper_ids = [p["paper_id"] for p in raw_papers if p.get("paper_id")]

        if exclude_ids:
            raw_papers = [p for p in raw_papers if p.get("paper_id") not in exclude_ids]

        total = len(raw_papers)
        visible = len(raw_papers[:quota_limit]) if quota_limit is not None else total
        is_fallback = False

        # Fallback: look for the most recent earlier date that still has papers.
        if total == 0:
            all_dates = data_service.list_dates(user_id=uid)
            try:
                start_idx = all_dates.index(date)
            except ValueError:
                start_idx = -1
            for earlier in all_dates[start_idx + 1:]:
                fb_digest = data_service.get_daily_digest(earlier, user_id=uid)
                fb_papers = fb_digest.get("papers", [])
                _all_paper_ids = [p["paper_id"] for p in fb_papers if p.get("paper_id")]
                if exclude_ids:
                    fb_papers = [p for p in fb_papers if p.get("paper_id") not in exclude_ids]
                if fb_papers:
                    total = len(fb_papers)
                    visible = len(fb_papers[:quota_limit]) if quota_limit is not None else total
                    _effective_date = earlier
                    is_fallback = True
                    break

        papers_section.update({
            "total_available": total,
            "visible_count": visible,
            "quota_limit": quota_limit,
            "is_fallback": is_fallback,
            "effective_date": _effective_date,
        })
    except Exception as exc:
        logger.warning("radar: papers section failed: %r", exc)

    # Anonymous users get only the papers section.
    if not user:
        return {
            "date": date,
            "tier": "anonymous",
            "papers": papers_section,
            "missed": None,
            "review": None,
            "recap": None,
            "ideas": None,
            "reactivation": None,
        }

    # ── 2. Missed (Why-NOT suppressions) ───────────────────────────────────
    missed_section: dict = {"count": 0, "preview": []}
    try:
        suppressions = preference_service.get_suppressions(
            user_id=uid, date=_effective_date, top_n=3
        )
        missed_section = {
            "count": len(suppressions),
            "preview": suppressions[:2],
        }
    except Exception as exc:
        logger.warning("radar: missed section failed: %r", exc)

    # ── 3. Review cards ─────────────────────────────────────────────────────
    review_section: dict = {"count": 0, "preview": []}
    try:
        cards = recap_service.get_review_cards(uid, limit=3)
        review_section = {
            "count": len(cards),
            "preview": cards[:1],
        }
    except Exception as exc:
        logger.warning("radar: review section failed: %r", exc)

    # ── 4. Recap status (read-only, no LLM trigger) ─────────────────────────
    recap_section: dict = {"status": "none", "paper_count": 0, "week_start": "", "week_end": ""}
    try:
        recap_section = recap_service.get_recap_status_summary(uid)
    except Exception as exc:
        logger.warning("radar: recap section failed: %r", exc)

    # ── 5. Ideas count ──────────────────────────────────────────────────────
    ideas_section: dict = {
        "total_available": 0,
        "visible_count": 0,
        "is_fallback": False,
        "effective_date": _effective_date,
    }
    try:
        # Use quota-filtered paper ids so the count matches what the user actually
        # sees in /api/idea/digest/{date} (which also applies quota to paper ids).
        _quota_paper_ids = (
            _all_paper_ids[:quota_limit] if quota_limit is not None else _all_paper_ids
        )
        _, total_ideas = idea_service.list_shared_candidates_for_date(
            date_str=_effective_date,
            allowed_paper_ids=_quota_paper_ids,
            viewer_user_id=uid,
        )
        ideas_is_fallback = is_fallback  # mirrors the papers section fallback
        ideas_effective_date = _effective_date

        # If papers fell back and still no ideas, try searching earlier dates for ideas too.
        if total_ideas == 0 and not is_fallback:
            all_dates = data_service.list_dates(user_id=uid)
            try:
                start_idx = all_dates.index(date)
            except ValueError:
                start_idx = -1
            for earlier in all_dates[start_idx + 1:]:
                fb_digest = data_service.get_daily_digest(earlier, user_id=uid)
                fb_all_ids = [p["paper_id"] for p in fb_digest.get("papers", []) if p.get("paper_id")]
                fb_quota_ids = fb_all_ids[:quota_limit] if quota_limit is not None else fb_all_ids
                _, fb_total = idea_service.list_shared_candidates_for_date(
                    date_str=earlier,
                    allowed_paper_ids=fb_quota_ids,
                    viewer_user_id=uid,
                )
                if fb_total > 0:
                    total_ideas = fb_total
                    ideas_is_fallback = True
                    ideas_effective_date = earlier
                    break

        ideas_section = {
            "total_available": total_ideas,
            "visible_count": total_ideas,  # quota already applied to paper ids above
            "is_fallback": ideas_is_fallback,
            "effective_date": ideas_effective_date,
        }
    except Exception as exc:
        logger.warning("radar: ideas section failed: %r", exc)

    # ── 6. Reactivation suggestions (from most recent successful recap) ────────
    reactivation_section: dict = {"count": 0, "preview": []}
    try:
        suggestions = recap_service.get_reactivation_suggestions(uid, limit=3)
        reactivation_section = {
            "count": len(suggestions),
            "preview": suggestions,
        }
    except Exception as exc:
        logger.warning("radar: reactivation section failed: %r", exc)

    return {
        "date": date,
        "tier": _tier_label(user),
        "papers": papers_section,
        "missed": missed_section,
        "review": review_section,
        "recap": recap_section,
        "ideas": ideas_section,
        "reactivation": reactivation_section,
    }
