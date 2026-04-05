"""
Auth / Subscription / Announcements / User Settings & Presets Router.

Registered in api.py via app.include_router(auth_router)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from services import announcement_service, auth_service, sms_service, user_presets_service, user_settings_service
from routers._deps import (
    _clear_session_cookie,
    _login_limiter,
    _register_limiter,
    _set_session_cookie,
)

router = APIRouter(prefix="/api", tags=["auth"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AuthCredentialBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)


class AuthRegisterBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    phone: str = Field(..., description="中国大陆手机号，注册时必填")
    sms_code: str = Field(..., min_length=4, max_length=8, description="短信验证码")


class SmsSendBody(BaseModel):
    phone: str = Field(..., description="中国大陆手机号")


class SmsLoginBody(BaseModel):
    phone: str = Field(..., description="中国大陆手机号")
    code: str = Field(..., min_length=4, max_length=8, description="短信验证码")


class SmsVerifyBody(BaseModel):
    phone: str = Field(..., description="中国大陆手机号")
    code: str = Field(..., min_length=4, max_length=8, description="短信验证码")


class UpdateProfileBody(BaseModel):
    nickname: Optional[str] = Field(None, max_length=64)
    username: Optional[str] = Field(None, min_length=3, max_length=32)


class SetPasswordBody(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordBody(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class SubscriptionRedeemBody(BaseModel):
    code: str = Field(..., min_length=8, max_length=64)
    device_id: Optional[str] = Field(default=None, max_length=128)


class AnnouncementCreateBody(BaseModel):
    title: str
    content: str
    tag: str = "general"
    is_pinned: bool = False


class AnnouncementUpdateBody(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tag: Optional[str] = None
    is_pinned: Optional[bool] = None


class AnnouncementMarkReadBody(BaseModel):
    announcement_ids: Optional[list] = None
    all: bool = False


class UserSettingsBody(BaseModel):
    settings: dict


class UserLlmPresetBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    input_hard_limit: Optional[int] = None
    input_safety_margin: Optional[int] = None


class UserPromptPresetBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    prompt_content: str = ""


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------

@router.post("/auth/sms/send", summary="Send SMS verify code")
def api_auth_sms_send(body: SmsSendBody):
    result = sms_service.send_verify_code(body.phone)
    if not result["success"]:
        raise HTTPException(
            status_code=429 if result.get("wait_seconds", 0) > 0 else 400,
            detail=result["message"],
        )
    return {"ok": True, "message": result["message"]}


@router.post("/auth/sms/verify", summary="Verify SMS code without side effects")
def api_auth_sms_verify(body: SmsVerifyBody):
    result = sms_service.check_verify_code(body.phone, body.code)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"ok": True, "message": result["message"]}


@router.post("/auth/login/sms", summary="Login by phone + SMS code (auto-register if new)")
def api_auth_login_sms(body: SmsLoginBody, request: Request, response: Response):
    client_ip = request.client.host if request.client else "unknown"
    _login_limiter.check(client_ip)

    verify = sms_service.check_verify_code(body.phone, body.code)
    if not verify["success"]:
        raise HTTPException(status_code=401, detail=verify["message"])
    user = auth_service.login_by_phone(body.phone)
    is_new_user = False
    if user is None:
        user = auth_service.auto_register_by_phone(body.phone)
        is_new_user = True
    session = auth_service.create_session(
        user_id=user["id"],
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, session["session_id"], request=request)
    return {"ok": True, "user": user, "is_new_user": is_new_user, "session_id": session["session_id"]}


# ---------------------------------------------------------------------------
# Register / Login / Logout
# ---------------------------------------------------------------------------

@router.post("/auth/register", summary="Register")
def api_auth_register(body: AuthRegisterBody, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _register_limiter.check(client_ip)

    verify = sms_service.check_verify_code(body.phone, body.sms_code)
    if not verify["success"]:
        raise HTTPException(status_code=400, detail=f"手机验证失败：{verify['message']}")
    user = auth_service.register_user(body.username, body.password, phone=body.phone)
    return {"ok": True, "user": user}


@router.post("/auth/login", summary="Login")
def api_auth_login(body: AuthCredentialBody, request: Request, response: Response):
    client_ip = request.client.host if request.client else "unknown"
    _login_limiter.check(client_ip)

    user = auth_service.verify_credentials(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    session = auth_service.create_session(
        user_id=user["id"],
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, session["session_id"], request=request)
    return {"ok": True, "user": user, "session_id": session["session_id"]}


@router.post("/auth/logout", summary="Logout")
def api_auth_logout(request: Request, response: Response):
    session_id = auth_service._extract_session_id(request)
    auth_service.delete_session(session_id)
    _clear_session_cookie(response, request=request)
    return {"ok": True}


@router.get("/auth/me", summary="Current user")
def api_auth_me(request: Request):
    session_id = auth_service._extract_session_id(request)
    user = auth_service.get_user_by_session(session_id)
    return {"authenticated": user is not None, "user": user}


@router.get("/auth/check-username", summary="Check username availability")
def api_auth_check_username(
    username: str = Query(..., min_length=1, max_length=32),
    exclude_user_id: Optional[int] = Query(None),
):
    result = auth_service.check_username_available(username, exclude_user_id=exclude_user_id)
    return result


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@router.get("/auth/profile", summary="Get current user profile")
def api_auth_get_profile(_user=Depends(auth_service.require_user)):
    profile = auth_service.get_user_profile(_user["id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True, "user": profile}


@router.put("/auth/profile", summary="Update current user profile")
def api_auth_update_profile(body: UpdateProfileBody, _user=Depends(auth_service.require_user)):
    if body.nickname is None and body.username is None:
        raise HTTPException(status_code=400, detail="请提供至少一个需要更新的字段")
    updated = auth_service.update_user_profile(
        _user["id"],
        nickname=body.nickname,
        username=body.username,
    )
    return {"ok": True, "user": updated}


@router.post("/auth/profile/set-password", summary="Set password for phone-only account")
def api_auth_set_password(body: SetPasswordBody, _user=Depends(auth_service.require_user)):
    updated = auth_service.set_user_password(_user["id"], body.password)
    return {"ok": True, "user": updated}


@router.post("/auth/profile/change-password", summary="Change password")
def api_auth_change_password(body: ChangePasswordBody, _user=Depends(auth_service.require_user)):
    updated = auth_service.change_user_password(_user["id"], body.old_password, body.new_password)
    return {"ok": True, "user": updated}


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------

@router.get("/subscription/me", summary="Current subscription status")
def api_subscription_me(_user=Depends(auth_service.require_user)):
    status = auth_service.get_subscription_status(_user["id"])
    return {"ok": True, **status}


@router.post("/subscription/redeem", summary="Redeem subscription key")
def api_subscription_redeem(body: SubscriptionRedeemBody, request: Request, _user=Depends(auth_service.require_user)):
    redeemed = auth_service.redeem_subscription_key(
        user_id=_user["id"],
        code=body.code,
        device_id=body.device_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"ok": True, **redeemed}


@router.get("/subscription/history", summary="Get subscription history")
def api_subscription_history(_user=Depends(auth_service.require_user)):
    history = auth_service.get_subscription_history(_user["id"])
    return {"ok": True, "history": history}


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------

@router.get("/announcements", summary="List announcements")
def api_list_announcements(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(auth_service.require_user),
):
    items = announcement_service.list_announcements_with_read(
        user_id=user["id"], limit=limit, offset=offset
    )
    total = announcement_service.count_announcements()
    return {"ok": True, "announcements": items, "total": total}


@router.get("/announcements/unread-count", summary="Get unread announcement count")
def api_announcements_unread_count(user=Depends(auth_service.require_user)):
    count = announcement_service.count_unread(user_id=user["id"])
    return {"ok": True, "count": count}


@router.post("/announcements/mark-read", summary="Mark announcements as read")
def api_announcements_mark_read(
    body: AnnouncementMarkReadBody,
    user=Depends(auth_service.require_user),
):
    if body.all:
        announcement_service.mark_all_read(user_id=user["id"])
    elif body.announcement_ids:
        announcement_service.mark_read(
            user_id=user["id"], announcement_ids=body.announcement_ids
        )
    return {"ok": True}


@router.post("/admin/announcements", summary="Admin create announcement")
def api_admin_create_announcement(
    body: AnnouncementCreateBody,
    admin=Depends(auth_service.require_admin_user),
):
    item = announcement_service.create_announcement(
        title=body.title,
        content=body.content,
        tag=body.tag,
        is_pinned=body.is_pinned,
        created_by=admin["id"],
    )
    return {"ok": True, "announcement": item}


@router.put("/admin/announcements/{announcement_id}", summary="Admin update announcement")
def api_admin_update_announcement(
    announcement_id: int,
    body: AnnouncementUpdateBody,
    _admin=Depends(auth_service.require_admin_user),
):
    item = announcement_service.update_announcement(
        announcement_id=announcement_id,
        title=body.title,
        content=body.content,
        tag=body.tag,
        is_pinned=body.is_pinned,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="公告不存在")
    return {"ok": True, "announcement": item}


@router.delete("/admin/announcements/{announcement_id}", summary="Admin delete announcement")
def api_admin_delete_announcement(
    announcement_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    ok = announcement_service.delete_announcement(announcement_id)
    if not ok:
        raise HTTPException(status_code=404, detail="公告不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------------

@router.get("/user/settings/{feature}", summary="Get user settings for a feature")
def api_get_user_settings(feature: str, _user=Depends(auth_service.require_user)):
    settings = user_settings_service.get_settings(_user["id"], feature)
    defaults = user_settings_service.get_defaults(feature)
    return {"ok": True, "feature": feature, "settings": settings, "defaults": defaults}


@router.put("/user/settings/{feature}", summary="Save user settings for a feature")
def api_save_user_settings(feature: str, body: UserSettingsBody, _user=Depends(auth_service.require_user)):
    merged = user_settings_service.save_settings(_user["id"], feature, body.settings)
    defaults = user_settings_service.get_defaults(feature)
    return {"ok": True, "feature": feature, "settings": merged, "defaults": defaults}


# ---------------------------------------------------------------------------
# User LLM presets
# ---------------------------------------------------------------------------

@router.get("/user/llm-presets", summary="List user LLM presets")
def api_user_list_llm_presets(_user=Depends(auth_service.require_user)):
    presets = user_presets_service.list_llm_presets(_user["id"])
    return {"ok": True, "presets": presets}


@router.post("/user/llm-presets", summary="Create LLM preset")
def api_user_create_llm_preset(body: UserLlmPresetBody, _user=Depends(auth_service.require_user)):
    preset = user_presets_service.create_llm_preset(_user["id"], body.dict())
    return {"ok": True, "preset": preset}


@router.put("/user/llm-presets/{preset_id}", summary="Update LLM preset")
def api_user_update_llm_preset(preset_id: int, body: UserLlmPresetBody, _user=Depends(auth_service.require_user)):
    preset = user_presets_service.update_llm_preset(_user["id"], preset_id, body.dict())
    if preset is None:
        raise HTTPException(status_code=404, detail="预设不存在")
    return {"ok": True, "preset": preset}


@router.delete("/user/llm-presets/{preset_id}", summary="Delete LLM preset")
def api_user_delete_llm_preset(preset_id: int, _user=Depends(auth_service.require_user)):
    ok = user_presets_service.delete_llm_preset(_user["id"], preset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="预设不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# User prompt presets
# ---------------------------------------------------------------------------

@router.get("/user/prompt-presets", summary="List user prompt presets")
def api_user_list_prompt_presets(_user=Depends(auth_service.require_user)):
    presets = user_presets_service.list_prompt_presets(_user["id"])
    return {"ok": True, "presets": presets}


@router.post("/user/prompt-presets", summary="Create prompt preset")
def api_user_create_prompt_preset(body: UserPromptPresetBody, _user=Depends(auth_service.require_user)):
    preset = user_presets_service.create_prompt_preset(_user["id"], body.dict())
    return {"ok": True, "preset": preset}


@router.put("/user/prompt-presets/{preset_id}", summary="Update prompt preset")
def api_user_update_prompt_preset(preset_id: int, body: UserPromptPresetBody, _user=Depends(auth_service.require_user)):
    preset = user_presets_service.update_prompt_preset(_user["id"], preset_id, body.dict())
    if preset is None:
        raise HTTPException(status_code=404, detail="预设不存在")
    return {"ok": True, "preset": preset}


@router.delete("/user/prompt-presets/{preset_id}", summary="Delete prompt preset")
def api_user_delete_prompt_preset(preset_id: int, _user=Depends(auth_service.require_user)):
    ok = user_presets_service.delete_prompt_preset(_user["id"], preset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="预设不存在")
    return {"ok": True}
