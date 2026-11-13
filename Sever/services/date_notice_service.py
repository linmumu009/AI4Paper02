"""Audience helpers for daily pipeline status notices."""

from __future__ import annotations

import logging

from services import auth_service, pipeline_db_service
from services.user_settings_service import list_users_with_custom_configs


logger = logging.getLogger(__name__)


def shared_failure_notice(
    exit_code: int,
    *,
    retry_budget_exhausted: bool = False,
) -> tuple[str, str]:
    """Return a truthful shared-stage notice for the current retry state."""
    if exit_code == 2:
        return (
            "source_temporarily_unavailable",
            "arXiv 论文源当前限流，系统正在自动重试。"
            "今日内容尚未生成，请稍后再查看。",
        )
    if exit_code == 4:
        if retry_budget_exhausted:
            return (
                "source_temporarily_unavailable",
                "arXiv 当日独立批次仍未发布，今日自动检查已结束。"
                "当前仍可阅读最近一期内容；管理员可稍后补跑。",
            )
        return (
            "source_temporarily_unavailable",
            "arXiv 当日批次暂未返回论文，系统会在稍后自动重试。"
            "当前仍可阅读最近一期内容。",
        )
    return (
        "pipeline_temporarily_unavailable",
        "今日内容生成暂时失败，系统正在自动恢复，请稍后再查看。",
    )


def list_notice_user_ids() -> list[int]:
    """Return all users who should receive an explicit daily status notice.

    Registered users without custom model settings must still see processing,
    source-unavailable, and empty-day explanations.  User 0 remains the shared
    fallback for anonymous and legacy clients.
    """
    user_ids = {0}
    try:
        user_ids.update(int(user_id) for user_id in auth_service.list_user_ids())
    except Exception as exc:
        logger.warning("Unable to list registered users for date notices: %r", exc)

    # Keep settings-only users covered during migrations or partial auth data.
    try:
        user_ids.update(int(user_id) for user_id in list_users_with_custom_configs())
    except Exception as exc:
        logger.warning("Unable to list configured users for date notices: %r", exc)
    return sorted(user_ids)


def upsert_notice_for_all_users(
    date_str: str,
    notice_type: str,
    message: str,
) -> list[int]:
    """Write one date notice for every registered/configured user."""
    user_ids = list_notice_user_ids()
    for user_id in user_ids:
        pipeline_db_service.upsert_date_notice(
            user_id,
            date_str,
            notice_type,
            message,
        )
    return user_ids
