"""Preference API Router.

Endpoints under /api/preferences for the user-preference learning closed loop.

  GET  /api/preferences/profile              – current user's preference profile summary
  POST /api/preferences/nudge               – apply a 'more like this' / 'less like this' signal
  POST /api/preferences/rebuild             – force-rebuild profile (useful for testing)
  GET  /api/preferences/suppressions        – Why-NOT: papers suppressed by the preference filter
  GET  /api/preferences/calibration/status  – per-user calibration status (Week 4)
  GET  /api/preferences/admin/stats         – admin-only preference system statistics
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import auth_service, preference_service, calibration_service

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


# ── Request models ─────────────────────────────────────────────────────────────

class NudgeBody(BaseModel):
    paper_id: str = Field(..., min_length=1, max_length=64)
    direction: Literal["more", "less"]
    categories: list[str] = Field(default_factory=list, max_length=20)
    keywords: list[str] = Field(default_factory=list, max_length=40)
    institution_tier: int = Field(default=4, ge=1, le=4)


class CategoryNudgeBody(BaseModel):
    category: str = Field(..., min_length=1, max_length=64)
    direction: Literal["more", "less", "reset"]


# ── User endpoints ─────────────────────────────────────────────────────────────

@router.get("/profile", summary="Get user preference profile summary")
def api_get_preference_profile(user=Depends(auth_service.require_user)):
    """Return the calling user's preference profile (categories, keywords, etc.)."""
    return preference_service.get_user_profile_summary(user["id"])


@router.post("/nudge", summary="Send 'more like this' or 'less like this' signal")
def api_nudge(body: NudgeBody, user=Depends(auth_service.require_user)):
    """Record a manual preference nudge from the UI.

    Allows users to explicitly signal that they want more or fewer recommendations
    similar to a given paper, without modifying their knowledge base.
    """
    preference_service.nudge(
        user_id=user["id"],
        paper_id=body.paper_id,
        direction=body.direction,
        categories=body.categories or None,
        keywords=body.keywords or None,
        institution_tier=body.institution_tier,
    )
    return {"ok": True, "direction": body.direction}


@router.post("/category-nudge", summary="Send 'more / less / reset' signal for a whole research category")
def api_category_nudge(body: CategoryNudgeBody, user=Depends(auth_service.require_user)):
    """Record a direct category-level calibration signal from the preference panel.

    Unlike /nudge (which is tied to a specific paper), this endpoint lets the user
    explicitly push a whole research category up or down, or reset any prior explicit
    signal.  The backend stores it as a synthetic paper_id = 'manual-category:<category>'
    in the existing user_paper_feedback table so the profile rebuild picks it up.
    """
    preference_service.nudge_category(
        user_id=user["id"],
        category=body.category,
        direction=body.direction,
    )
    return {"ok": True, "category": body.category, "direction": body.direction}


@router.post("/rebuild", summary="Force-rebuild preference profile")
def api_rebuild_profile(user=Depends(auth_service.require_user)):
    """Force a synchronous rebuild of the preference profile for the calling user.

    The rebuilt profile is returned immediately. Useful after bulk actions or
    when the user wants to re-calibrate their profile.
    """
    profile = preference_service.build_and_cache_profile(user["id"])
    return preference_service.get_user_profile_summary(user["id"])


# ── Why-NOT endpoint ───────────────────────────────────────────────────────────

@router.get("/suppressions", summary="Papers suppressed by preference filter (Why-NOT)")
def api_get_suppressions(
    date: str = Query(..., description="Content date YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    top_n: int = Query(default=5, ge=1, le=20, description="Max suppressed papers to return"),
    user=Depends(auth_service.require_user),
):
    """Return top-N high-relevance papers that the preference filter deprioritised.

    Each entry contains:
    - paper metadata (paper_id, title, institution, relevance_score)
    - pref_score and contributions list explaining why it was suppressed
    - suppression_summary: one-sentence Chinese explanation

    The frontend can use this to render a "Today's filtered papers" drawer,
    and each card can include a "其实想看 →" nudge_more button.
    """
    if top_n < 1 or top_n > 20:
        raise HTTPException(status_code=400, detail="top_n must be between 1 and 20")
    results = preference_service.get_suppressions(
        user_id=user["id"],
        date=date,
        top_n=top_n,
    )
    return {
        "date": date,
        "count": len(results),
        "suppressions": results,
    }


# ── Calibration status endpoint ────────────────────────────────────────────────

@router.get("/calibration/status", summary="Per-user calibration status")
def api_calibration_status(user=Depends(auth_service.require_user)):
    """Return the current user's calibration status.

    Includes:
    - whether a personal weight vector has been calibrated
    - the current effective score weights (personal or global defaults)
    - the last calibration timestamp and NDCG improvement from the audit log
    - recent calibration history (up to 5 entries)
    """
    profile = preference_service.get_or_build_profile(user["id"])
    score_weights = profile.get("score_weights")
    built_at = profile.get("built_at", "")

    last_cal = calibration_service.get_last_calibration(user["id"])
    history = calibration_service.get_calibration_history(user["id"], limit=5)

    return {
        "has_personal_weights": score_weights is not None,
        "score_weights": score_weights or {
            "theme": preference_service.W_THEME,
            "pref":  preference_service.W_PREF,
            "novel": preference_service.W_NOVEL,
        },
        "last_calibrated":  last_cal["calibrated_at"] if last_cal else None,
        "ndcg_old":         last_cal["ndcg_old"]       if last_cal else None,
        "ndcg_new":         last_cal["ndcg_new"]       if last_cal else None,
        "ndcg_improvement": round((last_cal["ndcg_new"] - last_cal["ndcg_old"]) / max(last_cal["ndcg_old"], 1e-9), 4)
                            if last_cal else None,
        "n_impressions_last": last_cal["n_impressions"] if last_cal else None,
        "n_saves_last":       last_cal["n_saves"]       if last_cal else None,
        "history":            history,
        "profile_built_at":   built_at,
    }


# ── Admin endpoints ────────────────────────────────────────────────────────────

@router.get("/admin/stats", summary="Preference system stats (admin only)")
def api_admin_preference_stats(
    days: int = 30,
    user=Depends(auth_service.require_admin_user),
):
    """Return system-wide preference signal stats for the admin analytics panel."""
    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365")
    return preference_service.get_preference_stats(days=days)


@router.get("/admin/loop-stats", summary="Preference loop system-wide health stats (admin only)")
def api_admin_loop_stats(
    days: int = Query(default=30, ge=1, le=365),
    user=Depends(auth_service.require_admin_user),
):
    """Aggregate stats for the full preference loop: impressions, calibration, bandit.

    Used by the AdminPreferenceLoop dashboard.
    """
    from services import impression_service
    pref_stats = preference_service.get_preference_stats(days=days)
    imp_stats  = impression_service.get_admin_stats(days=days)
    cal_stats  = calibration_service.get_admin_calibration_stats(days=days)

    # Percentage of users who have personal calibrated weights
    users_total = pref_stats.get("users_with_profile", 0)
    users_calibrated = cal_stats.get("unique_users", 0)
    pct_personal_weights = (
        round(100.0 * users_calibrated / users_total, 1)
        if users_total > 0 else 0.0
    )

    return {
        "days": days,
        "impressions": imp_stats,
        "calibration": cal_stats,
        "preference":  pref_stats,
        "pct_users_with_personal_weights": pct_personal_weights,
    }


@router.get("/admin/user-loop/{user_id}", summary="Per-user preference loop details (admin only)")
def api_admin_user_loop(
    user_id: int,
    admin=Depends(auth_service.require_admin_user),
):
    """Return complete preference loop state for one user: profile, weights, bandit, calibration."""
    from services import impression_service
    profile_summary = preference_service.get_user_profile_summary(user_id)
    imp_count = len(impression_service.get_impressions_for_user(user_id, days=30))
    cal_history = calibration_service.get_calibration_history(user_id, limit=10)
    last_cal = cal_history[0] if cal_history else None

    # Bandit params
    try:
        import sqlite3 as _sq
        import os as _os
        _db = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "database", "paper_analysis.db")
        _conn = _sq.connect(_db)
        _conn.row_factory = _sq.Row
        bandit_rows = _conn.execute(
            "SELECT arm_idx, alpha, beta FROM user_exploration_arm WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        _conn.close()
        bandit = [
            {
                "arm_idx": r["arm_idx"],
                "ratio": preference_service.BANDIT_ARMS[r["arm_idx"]] if r["arm_idx"] < len(preference_service.BANDIT_ARMS) else None,
                "alpha": round(float(r["alpha"]), 4),
                "beta":  round(float(r["beta"]),  4),
                "mean":  round(float(r["alpha"]) / (float(r["alpha"]) + float(r["beta"])), 4),
            }
            for r in bandit_rows
        ]
    except Exception:
        bandit = []

    return {
        "user_id": user_id,
        "profile": profile_summary,
        "impressions_last_30d": imp_count,
        "calibration_history": cal_history,
        "last_calibrated": last_cal["calibrated_at"] if last_cal else None,
        "ndcg_improvement": round((last_cal["ndcg_new"] - last_cal["ndcg_old"]) / max(last_cal["ndcg_old"], 1e-9), 4) if last_cal else None,
        "bandit_arms": bandit,
    }
