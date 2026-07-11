"""Unified research-asset search routes."""

from fastapi import APIRouter, Depends, Query

from services import auth_service, search_service


router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def api_search_assets(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(30, ge=1, le=50),
    user=Depends(auth_service.require_user),
):
    return search_service.search_assets(user["id"], q, limit)
