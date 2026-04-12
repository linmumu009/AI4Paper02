"""
Task-signin engagement router.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import analytics_service, auth_service, engagement_service

router = APIRouter(prefix="/api/engagement", tags=["engagement"])


class EngagementTaskRecordBody(BaseModel):
    action: str = Field(..., description="view | collect | analyze")
    source: Optional[str] = Field(default=None, description="event source, e.g. digest/paper-list")
    target_id: Optional[str] = Field(default=None, description="paper_id or session_id")


class UseRewardBody(BaseModel):
    context: Optional[str] = Field(default="", description="Usage context, e.g. 'compare_8_items'")


@router.get("/signin-status", summary="Get task-signin status")
def api_get_signin_status(user=Depends(auth_service.require_user)):
    status = engagement_service.get_signin_status(user["id"])
    return {"ok": True, **status}


@router.post("/tasks/record", summary="Record task action for signin")
def api_record_task(body: EngagementTaskRecordBody, user=Depends(auth_service.require_user)):
    try:
        result = engagement_service.record_task_action(
            user_id=user["id"],
            action=body.action,
            source=body.source,
            target_id=body.target_id,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="非法 action，允许: view/collect/analyze")

    # Analytics hooks for the new engagement funnel.
    analytics_service.record_event(
        user_id=user["id"],
        event_type="signin_task_recorded",
        target_type="engagement_action",
        target_id=body.action,
        meta={
            "source": body.source or "",
            "target_id": body.target_id or "",
            "day_key": result.get("day_key", ""),
            "progress_count": result.get("progress", {}).get("progress_count", 0),
        },
    )
    if result.get("just_completed"):
        analytics_service.record_event(
            user_id=user["id"],
            event_type="signin_day_completed",
            target_type="engagement_day",
            target_id=result.get("day_key", ""),
            meta={"streak": result.get("streak", {}).get("current", 0)},
        )
    granted = result.get("just_granted_reward")
    if granted:
        analytics_service.record_event(
            user_id=user["id"],
            event_type="signin_milestone_granted",
            target_type="engagement_reward",
            target_id=granted.get("reward_code", ""),
            meta={
                "streak_day": granted.get("streak_day", 0),
                "expires_at": granted.get("expires_at", ""),
            },
        )

    return {"ok": True, **result}


@router.get("/rewards", summary="List user rewards")
def api_list_rewards(
    status: Optional[str] = None,
    limit: int = 50,
    user=Depends(auth_service.require_user),
):
    rows = engagement_service.list_rewards(user_id=user["id"], status=status, limit=limit)
    return {"ok": True, "rewards": rows}


@router.get("/rewards/active-for-feature", summary="Get active rewards applicable to a specific feature")
def api_active_rewards_for_feature(
    feature: str,
    user=Depends(auth_service.require_user),
):
    """
    Returns active rewards that can be applied to the given feature.
    feature: 'compare' | 'research' | 'upload'
    """
    if feature not in ("compare", "research", "upload"):
        raise HTTPException(status_code=400, detail="feature 必须为 compare / research / upload")
    rewards = engagement_service.get_active_rewards_for_feature(user["id"], feature)
    return {"ok": True, "feature": feature, "rewards": rewards}


@router.get("/activity-calendar", summary="Get user activity calendar heatmap data")
def api_activity_calendar(
    days: int = 60,
    user=Depends(auth_service.require_user),
):
    """
    Returns daily task completion status for the past N days (max 180, min 7).
    Each day entry: {day_key, completed, partial, tasks_done}.
    """
    result = engagement_service.get_activity_calendar(user_id=user["id"], days=days)
    return {"ok": True, **result}


@router.post("/rewards/{reward_id}/use", summary="Consume (use) a reward")
def api_use_reward(
    reward_id: int,
    body: UseRewardBody,
    user=Depends(auth_service.require_user),
):
    """
    Mark a reward as used. Returns the reward with its boost parameters.
    The calling feature endpoint should use the returned boost dict to adjust limits.
    """
    try:
        result = engagement_service.use_reward(
            user_id=user["id"],
            reward_id=reward_id,
            context=body.context or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    analytics_service.record_event(
        user_id=user["id"],
        event_type="engagement_reward_used",
        target_type="engagement_reward",
        target_id=result.get("reward_code", ""),
        meta={
            "reward_id": reward_id,
            "context": body.context or "",
        },
    )

    return {"ok": True, **result}


@router.get("/freeze-status", summary="Get streak freeze status for current user")
def api_get_freeze_status(user=Depends(auth_service.require_user)):
    """
    Returns the user's streak freeze availability and whether a freeze can be applied now.
    """
    result = engagement_service.get_freeze_status(user["id"])
    return {"ok": True, **result}


@router.post("/freeze", summary="Use a streak freeze to recover a missed day")
def api_use_streak_freeze(user=Depends(auth_service.require_user)):
    """
    Spend one streak freeze to cover yesterday's missed day.
    Only valid when streak_would_break is true and freeze_remaining > 0.
    """
    try:
        result = engagement_service.use_streak_freeze(user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    analytics_service.record_event(
        user_id=user["id"],
        event_type="engagement_streak_frozen",
        target_type="engagement_streak",
        target_id=result.get("frozen_day", ""),
        meta={
            "new_streak": result.get("new_streak", 0),
            "freeze_remaining": result.get("freeze_remaining", 0),
        },
    )

    return {"ok": True, **result}
