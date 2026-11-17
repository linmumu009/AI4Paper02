"""Bounded, restart-safe selection of missed official announcement batches."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

from services.pipeline_schedule_policy import is_arxiv_release_day, schedule_uses_daily_arxiv


BACKFILL_TRIGGER = "scheduled_backfill"
BACKFILL_LOOKBACK_DAYS = 6
BACKFILL_MAX_ATTEMPTS_PER_DAY = 2
BACKFILL_COOLDOWN_SECONDS = 2 * 60 * 60
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _timestamp(record: Mapping[str, object], key: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(record.get(key) or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def next_backfill_date(
    now: datetime,
    cfg: Mapping[str, object],
    records: Iterable[Mapping[str, object]],
) -> str | None:
    """Choose the oldest unresolved recent date, with a separate daily budget.

    Only gaps after an established schedule watermark, or dates previously
    attempted automatically, are eligible. Enabling a new schedule does not
    unexpectedly fetch a week of historical papers. Successful manual full
    batches also close a gap. A partial-publication success does not.
    """
    if not cfg.get("enabled") or not cfg.get("multi_user", True):
        return None
    if not schedule_uses_daily_arxiv(cfg):
        return None
    current = now.replace(tzinfo=_SHANGHAI) if now.tzinfo is None else now.astimezone(_SHANGHAI)
    rows = list(records)
    try:
        watermark = date.fromisoformat(str(cfg.get("last_run_date") or ""))
    except ValueError:
        watermark = None
    established_dates = [watermark] if watermark else []
    for row in rows:
        if row.get("trigger") not in {"scheduled", BACKFILL_TRIGGER}:
            continue
        try:
            established_dates.append(date.fromisoformat(str(row.get("date_str") or "")))
        except ValueError:
            continue
    established = min(established_dates) if established_dates else None

    for offset in range(BACKFILL_LOOKBACK_DAYS, 0, -1):
        target = current.date() - timedelta(days=offset)
        day = target.isoformat()
        if not is_arxiv_release_day(day):
            continue
        attempts = [row for row in rows if row.get("date_str") == day]
        known_gap = any(row.get("trigger") in {"scheduled", BACKFILL_TRIGGER} for row in attempts)
        if not known_gap and (established is None or target <= established):
            continue
        completed = False
        for row in attempts:
            try:
                completed = (
                    int(row.get("exit_code")) == 0
                    and int(row.get("arxiv_count") or 0) > 0
                    and row.get("coverage_complete", True) is not False
                )
            except (TypeError, ValueError):
                continue
            if completed:
                break
        if completed:
            continue

        recent = [row for row in attempts if row.get("trigger") == BACKFILL_TRIGGER]
        today_attempts = [
            row for row in recent
            if (started := _timestamp(row, "started_at")) is not None
            and started.astimezone(_SHANGHAI).date() == current.date()
        ]
        if len(today_attempts) >= BACKFILL_MAX_ATTEMPTS_PER_DAY:
            continue
        finished = [
            value for row in recent
            if (value := _timestamp(row, "finished_at")) is not None
        ]
        if finished and (current - max(finished)).total_seconds() < BACKFILL_COOLDOWN_SECONDS:
            continue
        return day
    return None
