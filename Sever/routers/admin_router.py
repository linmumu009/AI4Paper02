"""
Admin Router.

Covers: users / redeem-keys / analytics / system-config / LLM-config / prompt-config.

All routes are prefixed with /api/admin and registered in api.py via
    app.include_router(admin_router)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services import analytics_service, auth_service
from services import config_service, config_mapper, llm_config_service, prompt_config_service
from routers._deps import _admin_error_response

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UpdateUserTierBody(BaseModel):
    tier: str = Field(..., pattern="^(free|pro|pro_plus)$")
    duration_days: int = Field(30, ge=1, le=3650)


class UpdateUserRoleBody(BaseModel):
    role: str = Field(..., pattern="^(user|admin|superadmin)$")


class AdminResetPasswordBody(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128)


class AdminIssueRedeemKeysBody(BaseModel):
    plan_tier: str = Field(..., pattern="^(pro|pro_plus)$")
    duration_days: int = Field(..., ge=1, le=3650)
    key_count: int = Field(default=1, ge=1, le=500)
    valid_days: Optional[int] = Field(default=None, ge=1, le=3650)
    max_uses: int = Field(default=1, ge=1, le=20)
    note: str = Field(default="", max_length=256)


class AnalyticsEventBody(BaseModel):
    event_type: str = Field(..., description="事件类型")
    target_type: Optional[str] = Field(None)
    target_id: Optional[str] = Field(None)
    value: Optional[float] = Field(None)
    meta: Optional[dict] = Field(None)


class AnalyticsEventBatchBody(BaseModel):
    events: list[AnalyticsEventBody] = Field(...)


class SystemConfigBody(BaseModel):
    config: dict = Field(..., description="配置项字典")


class LlmConfigBody(BaseModel):
    name: str = Field(..., description="配置名称")
    remark: Optional[str] = Field(None)
    base_url: str = Field(...)
    api_key: str = Field(...)
    model: str = Field(...)
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    concurrency: Optional[int] = None
    input_hard_limit: Optional[int] = None
    input_safety_margin: Optional[int] = None
    endpoint: Optional[str] = None
    completion_window: Optional[str] = None
    out_root: Optional[str] = None
    jsonl_root: Optional[str] = None


class ApplyLlmConfigBody(BaseModel):
    usage_prefix: str = Field(..., description="使用前缀（如 theme_select, org, summary 等）")


class PromptConfigBody(BaseModel):
    name: str = Field(..., description="配置名称")
    remark: Optional[str] = Field(None)
    prompt_content: str = Field(...)


class ApplyPromptConfigBody(BaseModel):
    variable_name: str = Field(..., description="目标变量名")


class BatchApplyLlmItem(BaseModel):
    config_id: int = Field(...)
    prefix: str = Field(...)


class BatchApplyPromptItem(BaseModel):
    config_id: int = Field(...)
    variable: str = Field(...)


class BatchApplyConfigBody(BaseModel):
    llm_applies: list[BatchApplyLlmItem] = Field(default_factory=list)
    prompt_applies: list[BatchApplyPromptItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

@router.get("/users", summary="Admin list users")
def api_admin_list_users(_admin=Depends(auth_service.require_admin_user)):
    return {"users": auth_service.list_users()}


@router.get("/users/custom-config-count", summary="Count users with custom pipeline configs")
def api_admin_custom_config_count(_admin=Depends(auth_service.require_admin_user)):
    try:
        from services.user_settings_service import list_users_with_custom_configs
        users = list_users_with_custom_configs()
        return {"count": len(users), "user_ids": users}
    except Exception as exc:
        return {"count": 0, "user_ids": [], "error": str(exc)}


@router.get("/users/{user_id}/detail", summary="Admin get user detail")
def api_admin_get_user_detail(
    user_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    detail = auth_service.get_admin_user_detail(user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return detail


@router.patch("/users/{user_id}/tier", summary="Admin update user tier")
def api_admin_update_user_tier(
    user_id: int,
    body: UpdateUserTierBody,
    _admin=Depends(auth_service.require_admin_user),
):
    user = auth_service.update_user_tier(user_id, body.tier, body.duration_days)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True, "user": user}


@router.patch("/users/{user_id}/role", summary="Superadmin update user role")
def api_admin_update_user_role(
    user_id: int,
    body: UpdateUserRoleBody,
    admin=Depends(auth_service.require_superadmin_user),
):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    user = auth_service.update_user_role(user_id, body.role)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True, "user": user}


@router.post("/users/{user_id}/reset-password", summary="Admin reset user password")
def api_admin_reset_password(
    user_id: int,
    body: AdminResetPasswordBody,
    _admin=Depends(auth_service.require_admin_user),
):
    user = auth_service.admin_reset_password(user_id, body.new_password)
    return {"ok": True, "user": user}


@router.post("/users/{user_id}/force-logout", summary="Admin force logout all sessions")
def api_admin_force_logout(
    user_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    count = auth_service.admin_force_logout(user_id)
    return {"ok": True, "sessions_deleted": count}


@router.post("/users/{user_id}/disable", summary="Admin disable user account")
def api_admin_disable_user(
    user_id: int,
    admin=Depends(auth_service.require_admin_user),
):
    user = auth_service.admin_disable_user(user_id, admin["id"])
    return {"ok": True, "user": user}


@router.post("/users/{user_id}/enable", summary="Admin enable user account")
def api_admin_enable_user(
    user_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    user = auth_service.admin_enable_user(user_id)
    return {"ok": True, "user": user}


@router.delete("/users/{user_id}", summary="Superadmin permanently delete user")
def api_admin_delete_user(
    user_id: int,
    admin=Depends(auth_service.require_superadmin_user),
):
    auth_service.admin_delete_user(user_id, admin["id"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Redeem keys
# ---------------------------------------------------------------------------

@router.post("/subscription/keys/batch", summary="Admin issue redeem keys")
def api_admin_issue_redeem_keys(
    body: AdminIssueRedeemKeysBody,
    admin=Depends(auth_service.require_admin_user),
):
    result = auth_service.issue_redeem_keys(
        plan_tier=body.plan_tier,
        duration_days=body.duration_days,
        key_count=body.key_count,
        valid_days=body.valid_days,
        max_uses=body.max_uses,
        created_by_user_id=admin["id"],
        note=body.note,
    )
    return {"ok": True, **result}


@router.get("/subscription/keys", summary="Admin list redeem keys")
def api_admin_list_redeem_keys(
    batch_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    _admin=Depends(auth_service.require_admin_user),
):
    rows = auth_service.list_redeem_keys(batch_id=batch_id, limit=limit)
    return {"ok": True, "keys": rows}


@router.patch("/subscription/keys/{key_id}/disable", summary="Admin disable redeem key")
def api_admin_disable_redeem_key(key_id: int, _admin=Depends(auth_service.require_admin_user)):
    ok = auth_service.disable_redeem_key(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="兑换码不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Analytics (admin read)
# ---------------------------------------------------------------------------

@router.get("/analytics/overview", summary="Admin analytics overview")
def api_admin_analytics_overview(_admin=Depends(auth_service.require_admin_user)):
    return {"ok": True, **analytics_service.get_overview_stats()}


@router.get("/analytics/users", summary="Admin analytics user activity")
def api_admin_analytics_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_user_activity_stats(limit=limit, offset=offset)}


@router.get("/analytics/papers", summary="Admin analytics paper popularity")
def api_admin_analytics_papers(
    limit: int = Query(30, ge=1, le=100),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_paper_popularity_stats(limit=limit)}


@router.get("/analytics/trends", summary="Admin analytics trends")
def api_admin_analytics_trends(
    days: int = Query(30, ge=7, le=365),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_trend_data(days=days)}


@router.get("/analytics/features", summary="Admin analytics feature usage")
def api_admin_analytics_features(_admin=Depends(auth_service.require_admin_user)):
    return {"ok": True, **analytics_service.get_feature_usage_stats()}


@router.get("/analytics/retention", summary="Admin analytics retention")
def api_admin_analytics_retention(
    weeks: int = Query(8, ge=2, le=24),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_retention_data(weeks=weeks)}


@router.get("/analytics/engagement-signin", summary="Admin analytics for task-signin funnel")
def api_admin_analytics_engagement_signin(
    days: int = Query(14, ge=1, le=90),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_engagement_signin_stats(days=days)}


@router.get("/analytics/activation", summary="Admin analytics: new user 7-day activation funnel")
def api_admin_analytics_activation(
    days: int = Query(30, ge=7, le=180),
    activation_window_days: int = Query(7, ge=1, le=30),
    tier: Optional[str] = Query(None, description="Filter by user tier: free | pro | pro_plus"),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_activation_stats(
        days=days,
        activation_window_days=activation_window_days,
        tier=tier if tier in ("free", "pro", "pro_plus") else None,
    )}


@router.get("/analytics/activated-retention", summary="Admin analytics: retention of activated users only")
def api_admin_analytics_activated_retention(
    weeks: int = Query(8, ge=2, le=24),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_activated_retention(weeks=weeks)}


@router.get("/analytics/content-funnel", summary="Admin analytics: content & feature conversion funnel")
def api_admin_analytics_content_funnel(
    days: int = Query(30, ge=7, le=180),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_content_funnel_stats(days=days)}


@router.get("/analytics/value-retention", summary="Admin analytics: value-action weekly retention of activated users")
def api_admin_analytics_value_retention(
    weeks: int = Query(8, ge=2, le=24),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_value_action_retention(weeks=weeks)}


@router.get("/analytics/content-step-funnel", summary="Admin analytics: step funnel card_view->paper_view->save->deep_action")
def api_admin_analytics_content_step_funnel(
    days: int = Query(30, ge=7, le=180),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_content_step_funnel(days=days)}


@router.get("/analytics/ai-features", summary="Admin analytics: AI feature adoption (research / chat / idea)")
def api_admin_analytics_ai_features(
    days: int = Query(30, ge=7, le=180),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_ai_feature_stats(days=days)}


@router.get("/analytics/engagement-depth", summary="Admin analytics: session & reading engagement depth")
def api_admin_analytics_engagement_depth(
    days: int = Query(30, ge=7, le=90),
    _admin=Depends(auth_service.require_admin_user),
):
    return {"ok": True, **analytics_service.get_engagement_depth(days=days)}


# ---------------------------------------------------------------------------
# Analytics event tracking (user-facing, all logged-in users)
# Note: these routes use /api/analytics prefix, not /api/admin
# ---------------------------------------------------------------------------

# These two routes sit under /api/analytics (not /api/admin).
# We add them here without the admin-guard since they're for all users.
# To keep the prefix correct we need a separate sub-router trick, but
# FastAPI allows explicit full paths on include_router too.
# Easiest: register them with include_in_schema and the literal path.

# We'll handle them in paper_router (which already uses prefix="/api")
# since they don't fit the /api/admin prefix. They are included in paper_router.py.


# ---------------------------------------------------------------------------
# System config
# ---------------------------------------------------------------------------

@router.get("/config", summary="Get system configuration")
def api_admin_get_config(
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        result = config_service.get_config_with_groups()
        return {"ok": True, **result}
    except Exception as e:
        raise _admin_error_response("获取配置", e)


@router.post("/config", summary="Update system configuration")
def api_admin_update_config(
    body: SystemConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        updated = config_service.update_config(body.config)
        return {"ok": True, "config": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _admin_error_response("更新配置", e)


@router.post("/config/reset", summary="Reset system configuration to defaults")
def api_admin_reset_config(
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        config_service.reset_config()
        return {"ok": True, "message": "配置已重置为默认值"}
    except Exception as e:
        raise _admin_error_response("重置配置", e)


@router.post("/config/batch-apply", summary="Batch apply LLM and prompt configs")
def api_admin_batch_apply_configs(
    body: BatchApplyConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        result = config_mapper.batch_apply(
            llm_applies=[item.model_dump() for item in body.llm_applies],
            prompt_applies=[item.model_dump() for item in body.prompt_applies],
        )
        return {
            "ok": True,
            "message": f"批量应用完成，共更新 {result['applied_count']} 项配置",
            "applied_count": result["applied_count"],
            "errors": result["errors"],
            "config": result["config"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _admin_error_response("批量应用", e)


# ---------------------------------------------------------------------------
# LLM config management
# ---------------------------------------------------------------------------

@router.get("/llm-configs", summary="Get all LLM configs")
def api_admin_list_llm_configs(
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        configs = llm_config_service.list_configs()
        return {"ok": True, "configs": configs}
    except Exception as e:
        raise _admin_error_response("获取配置列表", e)


@router.get("/llm-configs/{config_id}", summary="Get LLM config by ID")
def api_admin_get_llm_config(
    config_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        config = llm_config_service.get_config(config_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")
        return {"ok": True, "config": config}
    except HTTPException:
        raise
    except Exception as e:
        raise _admin_error_response("获取配置", e)


@router.post("/llm-configs", summary="Create LLM config")
def api_admin_create_llm_config(
    body: LlmConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        config = llm_config_service.create_config(body.dict())
        return {"ok": True, "config": config}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _admin_error_response("创建配置", e)


@router.put("/llm-configs/{config_id}", summary="Update LLM config")
def api_admin_update_llm_config(
    config_id: int,
    body: LlmConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        config = llm_config_service.update_config(config_id, body.dict(exclude_unset=True))
        if not config:
            raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")
        return {"ok": True, "config": config}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _admin_error_response("更新配置", e)


@router.delete("/llm-configs/{config_id}", summary="Delete LLM config")
def api_admin_delete_llm_config(
    config_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        success = llm_config_service.delete_config(config_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")
        return {"ok": True, "message": "配置已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise _admin_error_response("删除配置", e)


@router.post("/llm-configs/{config_id}/apply", summary="Apply LLM config to config.py")
def api_admin_apply_llm_config(
    config_id: int,
    body: ApplyLlmConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        updated = config_mapper.apply_llm_config(config_id, body.usage_prefix)
        return {"ok": True, "message": f"配置已应用到 {body.usage_prefix} 前缀", "config": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _admin_error_response("应用配置", e)


# ---------------------------------------------------------------------------
# Prompt config management
# ---------------------------------------------------------------------------

@router.get("/prompt-configs", summary="Get all prompt configs")
def api_admin_list_prompt_configs(
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        configs = prompt_config_service.list_configs()
        return {"ok": True, "configs": configs}
    except Exception as e:
        raise _admin_error_response("获取配置列表", e)


@router.get("/prompt-configs/{config_id}", summary="Get prompt config by ID")
def api_admin_get_prompt_config(
    config_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        config = prompt_config_service.get_config(config_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"提示词配置 {config_id} 不存在")
        return {"ok": True, "config": config}
    except HTTPException:
        raise
    except Exception as e:
        raise _admin_error_response("获取配置", e)


@router.post("/prompt-configs", summary="Create prompt config")
def api_admin_create_prompt_config(
    body: PromptConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        config = prompt_config_service.create_config(body.dict())
        return {"ok": True, "config": config}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _admin_error_response("创建配置", e)


@router.put("/prompt-configs/{config_id}", summary="Update prompt config")
def api_admin_update_prompt_config(
    config_id: int,
    body: PromptConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        config = prompt_config_service.update_config(config_id, body.dict(exclude_unset=True))
        if not config:
            raise HTTPException(status_code=404, detail=f"提示词配置 {config_id} 不存在")
        return {"ok": True, "config": config}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _admin_error_response("更新配置", e)


@router.delete("/prompt-configs/{config_id}", summary="Delete prompt config")
def api_admin_delete_prompt_config(
    config_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        success = prompt_config_service.delete_config(config_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"提示词配置 {config_id} 不存在")
        return {"ok": True, "message": "配置已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise _admin_error_response("删除配置", e)


@router.post("/prompt-configs/{config_id}/apply", summary="Apply prompt config to config.py")
def api_admin_apply_prompt_config(
    config_id: int,
    body: ApplyPromptConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        updated = config_mapper.apply_prompt_config(config_id, body.variable_name)
        return {"ok": True, "message": f"配置已应用到变量 {body.variable_name}", "config": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise _admin_error_response("应用配置", e)
