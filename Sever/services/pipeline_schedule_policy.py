"""Pure scheduling policy shared by the API router and regression tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping


def count_scheduled_attempts(
    records: Iterable[Mapping[str, object]], date_str: str
) -> int:
    """Count persisted scheduled attempts for a specific pipeline date."""
    return sum(
        1
        for record in records
        if record.get("date_str") == date_str
        and record.get("trigger") == "scheduled"
    )


def scheduled_attempt_is_due(
    now: datetime,
    cfg: Mapping[str, object],
    attempt_count: int,
    *,
    max_retries: int,
) -> bool:
    """Return whether today's job needs its normal start or a same-day catch-up."""
    try:
        hour = int(cfg.get("hour", 6))
        minute = int(cfg.get("minute", 0))
    except (TypeError, ValueError):
        hour, minute = 6, 0
    if not 0 <= hour <= 23:
        hour = 6
    if not 0 <= minute <= 59:
        minute = 0

    today = now.date().isoformat()
    scheduled_today = now.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    return bool(
        cfg.get("enabled")
        and now >= scheduled_today
        and cfg.get("last_run_date") != today
        and attempt_count < max_retries
    )


def rate_limit_cooldown_remaining(
    records: Iterable[Mapping[str, object]],
    date_str: str,
    now: datetime,
    *,
    cooldown_seconds: int,
    max_cooldown_seconds: int | None = None,
) -> float:
    """Recover an exponential rate-limit cooldown from persisted history.

    A fixed retry cap can turn a temporary upstream throttle into a full day of
    missing content.  Persisted exponential cooldowns let the scheduler keep
    trying at a respectful, bounded rate even after a process restart.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    finished_times: list[datetime] = []
    for record in records:
        if (
            record.get("date_str") != date_str
            or record.get("trigger") != "scheduled"
            or record.get("exit_code") != 2
        ):
            continue
        raw_finished = record.get("finished_at")
        if not isinstance(raw_finished, str) or not raw_finished.strip():
            continue
        try:
            finished = datetime.fromisoformat(
                raw_finished.strip().replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        else:
            finished = finished.astimezone(timezone.utc)
        finished_times.append(finished)

    if not finished_times:
        return 0.0

    base = max(1.0, float(cooldown_seconds))
    cap = max(base, float(max_cooldown_seconds or cooldown_seconds))
    delay = min(cap, base * (2 ** max(0, len(finished_times) - 1)))
    elapsed = (now - max(finished_times)).total_seconds()
    return max(0.0, delay - elapsed)
