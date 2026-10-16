"""Unified research-asset search routes."""

from fastapi import APIRouter, Depends, Query
from typing import Literal

from services import search_service
from routers._deps import _get_optional_user


router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def api_search_assets(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(30, ge=1, le=50),
    scope: Literal["all", "mine", "uncollected"] = Query("all"),
    user=Depends(_get_optional_user),
):
    return search_service.search_assets(user["id"] if user else None, q, limit, scope)
