"""
Entitlement router — exposes the user's current quota and feature-gate status.
"""

from fastapi import APIRouter, Depends

from services import auth_service, entitlement_service

router = APIRouter(prefix="/api/entitlements", tags=["entitlements"])


@router.get("/me", summary="Get current user's full entitlement status")
def api_get_my_entitlements(user=Depends(auth_service.require_user)):
    """
    Returns tier, all per-feature quotas (limit / used / remaining / period),
    boolean gates, storage usage, per-session caps, and retention policy.

    Frontend should call this once after login and cache in useEntitlements composable.
    """
    data = entitlement_service.get_user_entitlements(user["id"])
    return {"ok": True, **data}
