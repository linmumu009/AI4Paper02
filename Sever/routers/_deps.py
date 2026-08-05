"""
Shared utilities for all routers.

Provides:
- Common path constants (_SEVER_DIR, _DATA_DIR, _KB_FILES_DIR, _EXE_RELEASE_DIR)
- Security helpers (_admin_error_response)
- Durable rate limiter (_RateLimiter, _login_limiter, _register_limiter)
- Cookie / session helpers (_is_request_https, _cookie_secure_flag,
  _set_session_cookie, _clear_session_cookie, _get_optional_user)
- Tier quota helpers (_tier_quota_limit, _tier_label)
"""

import logging
import os
from typing import Optional

from fastapi import HTTPException, Request, Response

from services import auth_service, entitlement_service, rate_limit_service
from services.safe_logging_service import log_internal_error, public_error_detail

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

# routers/ is one level below Sever/
_SEVER_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_DATA_DIR = os.path.join(_SEVER_DIR, "data")
_KB_FILES_DIR = os.path.join(_DATA_DIR, "kb_files")
_EXE_RELEASE_DIR = os.path.abspath(
    os.path.normpath(
        os.environ.get("EXE_RELEASE_DIR", os.path.join(_SEVER_DIR, "..", "exe_release"))
    )
)


# ---------------------------------------------------------------------------
# Security: sanitized error responses for admin endpoints
# ---------------------------------------------------------------------------

def _admin_error_response(action: str, exc: Exception, status_code: int = 500) -> HTTPException:
    """Log the real error server-side and return a sanitized HTTPException."""
    reference = log_internal_error(_logger, action, exc)
    return HTTPException(
        status_code=status_code,
        detail=public_error_detail(reference, f"{action}失败"),
        headers={"X-Error-ID": reference},
    )


# ---------------------------------------------------------------------------
# Rate limiting for authentication endpoints (anti brute-force)
# ---------------------------------------------------------------------------

class _RateLimiter:
    """FastAPI adapter around the durable sliding-window limiter."""

    def __init__(self, bucket: str, max_attempts: int, window_seconds: int):
        self._limiter = rate_limit_service.PersistentRateLimiter(
            bucket=bucket,
            max_attempts=max_attempts,
            window_seconds=window_seconds,
        )

    def check(self, key: str) -> None:
        try:
            self._limiter.check(key)
        except rate_limit_service.RateLimitExceeded as exc:
            raise HTTPException(
                status_code=429,
                detail="请求过于频繁，请稍后再试",
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc


# 10 attempts per 5 minutes per IP for login
_login_limiter = _RateLimiter("auth_login", max_attempts=10, window_seconds=300)
# Also cap attempts per account so rotating source IPs cannot brute-force one user.
_login_account_limiter = _RateLimiter(
    "auth_login_account", max_attempts=10, window_seconds=300
)
# 5 attempts per 10 minutes per IP for registration
_register_limiter = _RateLimiter("auth_register", max_attempts=5, window_seconds=600)
# 5 SMS sends per 10 minutes per IP (to prevent SMS cost abuse)
_sms_send_limiter = _RateLimiter("sms_send", max_attempts=5, window_seconds=600)
_sms_send_phone_limiter = _RateLimiter(
    "sms_send_phone", max_attempts=3, window_seconds=600
)
# 10 SMS verify attempts per 5 minutes per IP (to prevent brute-force)
_sms_verify_limiter = _RateLimiter("sms_verify", max_attempts=10, window_seconds=300)
_sms_verify_phone_limiter = _RateLimiter(
    "sms_verify_phone", max_attempts=10, window_seconds=300
)
# 120 analytics events per minute per IP (generous but bounded)
_analytics_limiter = _RateLimiter("analytics", max_attempts=120, window_seconds=60)


# ---------------------------------------------------------------------------
# Cookie 安全配置
# ---------------------------------------------------------------------------

_COOKIE_SECURE_RAW = os.environ.get("COOKIE_SECURE", "false").strip().lower()
_COOKIE_SAMESITE_RAW = os.environ.get("COOKIE_SAMESITE", "lax").strip().lower()
_COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", "").strip() or None

_VALID_SAMESITE = {"lax", "strict", "none"}
if _COOKIE_SAMESITE_RAW not in _VALID_SAMESITE:
    print(
        f"[WARN] Invalid COOKIE_SAMESITE={_COOKIE_SAMESITE_RAW!r}; fallback to 'lax'. "
        "Allowed values: lax / strict / none",
        flush=True,
    )
    _COOKIE_SAMESITE_RAW = "lax"


def _is_request_https(request: Optional[Request]) -> bool:
    if request is None:
        return False
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if proto:
        return proto == "https"
    return request.url.scheme == "https"


def _cookie_secure_flag(request: Optional[Request]) -> bool:
    if _COOKIE_SECURE_RAW in ("auto",):
        secure = _is_request_https(request)
    else:
        secure = _COOKIE_SECURE_RAW in ("1", "true", "yes")
    if _COOKIE_SAMESITE_RAW == "none" and not secure:
        print(
            "[WARN] COOKIE_SAMESITE=none requires Secure cookie; force secure=True for session cookie.",
            flush=True,
        )
        secure = True
    return secure


def _set_session_cookie(resp: Response, session_id: str, request: Optional[Request] = None) -> None:
    secure = _cookie_secure_flag(request)
    resp.set_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite=_COOKIE_SAMESITE_RAW,
        secure=secure,
        max_age=auth_service.SESSION_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
        domain=_COOKIE_DOMAIN,
    )


def _clear_session_cookie(resp: Response, request: Optional[Request] = None) -> None:
    secure = _cookie_secure_flag(request)
    resp.delete_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=_COOKIE_SAMESITE_RAW,
        secure=secure,
        domain=_COOKIE_DOMAIN,
    )


def _get_optional_user(request: Request) -> Optional[dict]:
    session_id = auth_service._extract_session_id(request)
    return auth_service.get_user_by_session(session_id)


def _tier_quota_limit(user: Optional[dict]) -> Optional[int]:
    uid = user["id"] if user else None
    return entitlement_service.get_browse_limit(uid)


def _tier_label(user: Optional[dict]) -> str:
    if not user:
        return "anonymous"
    role = user.get("role", "user")
    if role in ("admin", "superadmin"):
        return "pro_plus"
    return user.get("tier", "free")
