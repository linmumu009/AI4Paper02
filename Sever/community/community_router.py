"""
Community API Router.

All routes are prefixed with /api/community and registered in api.py via
    app.include_router(community_router)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services import auth_service
from community import community_service

router = APIRouter(prefix="/api/community", tags=["community"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class CreatePostBody(BaseModel):
    category: str = Field("discussion", description="question | discussion | sharing | help")
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)


class UpdatePostBody(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)


class CreateReplyBody(BaseModel):
    content: str = Field(..., min_length=1)
    parent_reply_id: Optional[int] = None


class UpdateReplyBody(BaseModel):
    content: str = Field(..., min_length=1)


class LikeBody(BaseModel):
    target_type: str = Field(..., description="'post' or 'reply'")
    target_id: int


class PinBody(BaseModel):
    pinned: bool


class CloseBody(BaseModel):
    closed: bool


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_optional_user(request: Request) -> Optional[dict]:
    """Try to get current user without raising on failure."""
    return auth_service.get_current_user_optional(request)


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

@router.get("/posts", summary="List community posts")
def api_list_posts(
    category: Optional[str] = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("latest", description="latest | hot"),
    request: Request = None,
):
    user = _get_optional_user(request)
    result = community_service.list_posts(
        category=category, page=page, page_size=page_size, sort=sort
    )
    # Annotate liked status if authenticated
    if user:
        post_ids = [p["id"] for p in result["posts"]]
        liked_ids = community_service.get_user_liked_targets(user["id"], "post", post_ids)
        for p in result["posts"]:
            p["user_liked"] = p["id"] in liked_ids
    else:
        for p in result["posts"]:
            p["user_liked"] = False
    return result


@router.post("/posts", summary="Create a post")
def api_create_post(
    body: CreatePostBody,
    user: dict = Depends(auth_service.require_user),
):
    post = community_service.create_post(
        user_id=user["id"],
        category=body.category,
        title=body.title,
        content=body.content,
    )
    return post


@router.get("/posts/{post_id}", summary="Get post detail with replies")
def api_get_post(
    post_id: int,
    request: Request = None,
):
    post = community_service.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="帖子不存在")

    community_service.increment_view_count(post_id)
    post["view_count"] += 1

    user = _get_optional_user(request)
    if user:
        post["user_liked"] = post_id in community_service.get_user_liked_targets(
            user["id"], "post", [post_id]
        )
        reply_ids = [r["id"] for r in post.get("replies", [])]
        liked_reply_ids = community_service.get_user_liked_targets(user["id"], "reply", reply_ids)
        for r in post.get("replies", []):
            r["user_liked"] = r["id"] in liked_reply_ids
    else:
        post["user_liked"] = False
        for r in post.get("replies", []):
            r["user_liked"] = False

    return post


@router.put("/posts/{post_id}", summary="Edit a post")
def api_update_post(
    post_id: int,
    body: UpdatePostBody,
    user: dict = Depends(auth_service.require_user),
):
    existing = community_service.get_post(post_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="帖子不存在")

    if existing["user_id"] != user["id"] and user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="无权编辑此帖子")

    updated = community_service.update_post(
        post_id=post_id,
        title=body.title,
        content=body.content,
        category=body.category,
    )
    return updated


@router.delete("/posts/{post_id}", summary="Delete a post")
def api_delete_post(
    post_id: int,
    user: dict = Depends(auth_service.require_user),
):
    existing = community_service.get_post(post_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="帖子不存在")

    if existing["user_id"] != user["id"] and user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="无权删除此帖子")

    community_service.delete_post(post_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Replies
# ---------------------------------------------------------------------------

@router.post("/posts/{post_id}/replies", summary="Add a reply to a post")
def api_create_reply(
    post_id: int,
    body: CreateReplyBody,
    user: dict = Depends(auth_service.require_user),
):
    post = community_service.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if post.get("is_closed"):
        raise HTTPException(status_code=403, detail="该帖子已关闭，无法回复")

    reply = community_service.create_reply(
        post_id=post_id,
        user_id=user["id"],
        content=body.content,
        parent_reply_id=body.parent_reply_id,
    )
    if reply is None:
        raise HTTPException(status_code=404, detail="帖子不存在")
    reply["user_liked"] = False
    return reply


@router.put("/replies/{reply_id}", summary="Edit a reply")
def api_update_reply(
    reply_id: int,
    body: UpdateReplyBody,
    user: dict = Depends(auth_service.require_user),
):
    existing = community_service.get_reply(reply_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="回复不存在")

    if existing["user_id"] != user["id"] and user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="无权编辑此回复")

    updated = community_service.update_reply(reply_id=reply_id, content=body.content)
    return updated


@router.delete("/replies/{reply_id}", summary="Delete a reply")
def api_delete_reply(
    reply_id: int,
    user: dict = Depends(auth_service.require_user),
):
    existing = community_service.get_reply(reply_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="回复不存在")

    if existing["user_id"] != user["id"] and user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="无权删除此回复")

    community_service.delete_reply(reply_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Likes
# ---------------------------------------------------------------------------

@router.post("/like", summary="Toggle like for a post or reply")
def api_toggle_like(
    body: LikeBody,
    user: dict = Depends(auth_service.require_user),
):
    if body.target_type not in ("post", "reply"):
        raise HTTPException(status_code=400, detail="target_type 必须是 'post' 或 'reply'")

    try:
        result = community_service.toggle_like(
            user_id=user["id"],
            target_type=body.target_type,
            target_id=body.target_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


# ---------------------------------------------------------------------------
# Admin: pin / close
# ---------------------------------------------------------------------------

@router.put("/posts/{post_id}/pin", summary="Pin or unpin a post (admin only)")
def api_pin_post(
    post_id: int,
    body: PinBody,
    user: dict = Depends(auth_service.require_admin_user),
):
    ok = community_service.set_pinned(post_id, body.pinned)
    if not ok:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return {"ok": True, "is_pinned": body.pinned}


@router.put("/posts/{post_id}/close", summary="Close or reopen a post (admin only)")
def api_close_post(
    post_id: int,
    body: CloseBody,
    user: dict = Depends(auth_service.require_admin_user),
):
    ok = community_service.set_closed(post_id, body.closed)
    if not ok:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return {"ok": True, "is_closed": body.closed}
