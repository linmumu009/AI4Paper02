"""Confirm quota only when a lazy streaming task reaches its real start boundary."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator
from typing import Any, Optional

from services import entitlement_service
from services.safe_logging_service import safe_failure_detail


logger = logging.getLogger(__name__)


class _QuotaCommitSignal:
    __slots__ = ()


STREAM_QUOTA_COMMIT = _QuotaCommitSignal()


def guard_quota_stream(
    stream: Iterable[Any],
    reservation_id: Optional[str],
    *,
    on_commit: Optional[Callable[[], None]] = None,
    operation: str = "quota_stream",
) -> Iterator[Any]:
    """Filter the internal commit signal and release quota if it never arrives.

    Streaming generators are lazy: validation and configuration failures often
    occur only after the HTTP response object has been created. The producer
    yields ``STREAM_QUOTA_COMMIT`` immediately before its first chargeable side
    effect. Until then the quota unit remains refundable.
    """
    committed = False
    try:
        for item in stream:
            if item is STREAM_QUOTA_COMMIT:
                if committed:
                    continue
                committed = True
                if reservation_id:
                    try:
                        entitlement_service.commit_quota_reservation(reservation_id)
                    except Exception as exc:
                        safe_failure_detail(
                            logger,
                            "流式任务额度状态确认失败",
                            exc,
                            operation=f"{operation}_quota_commit",
                        )
                if on_commit is not None:
                    try:
                        on_commit()
                    except Exception as exc:
                        safe_failure_detail(
                            logger,
                            "流式任务启动回调失败",
                            exc,
                            operation=f"{operation}_commit_callback",
                        )
                continue
            yield item
    finally:
        if not committed and reservation_id:
            try:
                entitlement_service.release_quota_reservation(reservation_id)
            except Exception as exc:
                safe_failure_detail(
                    logger,
                    "流式任务额度退还失败",
                    exc,
                    operation=f"{operation}_quota_release",
                )
