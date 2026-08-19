"""Pure scheduling policy shared by the API router and regression tests."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable, Mapping


DEFAULT_SCHEDULED_MAX_ATTEMPTS = 8
DEFAULT_ARXIV_READY_HOUR = 9
DEFAULT_ARXIV_READY_MINUTE = 15
SCHEDULED_SOURCE_EMPTY_EXIT_CODE = 4


def multi_user_notice_action(
    exit_code: int,
    *,
    schedule_outcome: str,
    shared_stage_succeeded: bool,
    per_user_stage_completed: bool,
    has_failed_users: bool,
) -> str:
    """Return ``clear``, ``shared_failure`` or ``user_failures`` for a run."""
    if exit_code == 0:
        return "clear"
    if (
        schedule_outcome == "source_empty_retry"
        or not shared_stage_succeeded
        or not per_user_stage_completed
    ):
        return "shared_failure"
    if has_failed_users:
        return "user_failures"
    # Cleanup failed after all personalized results were published. Keep those
    # results visible while the scheduler retries the maintenance work.
    return "clear"


def _configured_clock(cfg: Mapping[str, object]) -> tuple[int, int]:
    try:
        hour = int(cfg.get("hour", 6))
        minute = int(cfg.get("minute", 0))
    except (TypeError, ValueError):
        hour, minute = 6, 0
    if not 0 <= hour <= 23:
        hour = 6
    if not 0 <= minute <= 59:
        minute = 0
    return hour, minute


def schedule_uses_daily_arxiv(cfg: Mapping[str, object]) -> bool:
    """Return whether a scheduled pipeline depends on the daily arXiv release."""
    if cfg.get("multi_user") is True:
        return True
    return str(cfg.get("pipeline", "daily")).strip().lower() in {"daily", "default"}


def is_arxiv_release_day(date_str: str) -> bool:
    """arXiv publishes a new China-morning batch from Monday to Friday."""
    try:
        return date.fromisoformat(date_str).weekday() < 5
    except (TypeError, ValueError):
        return False


def effective_weekday_schedule_clock(
    cfg: Mapping[str, object],
) -> tuple[int, int]:
    """Apply a safe lower bound for pipelines that need the daily arXiv batch.

    The arXiv announcement lands at 08:00 China time during US daylight saving
    time and 09:00 during US standard time.  A 09:15 lower bound covers both
    seasons plus a small propagation buffer while still allowing admins to
    configure a later time.
    """
    hour, minute = _configured_clock(cfg)
    if not schedule_uses_daily_arxiv(cfg):
        return hour, minute
    configured_minutes = hour * 60 + minute
    ready_minutes = DEFAULT_ARXIV_READY_HOUR * 60 + DEFAULT_ARXIV_READY_MINUTE
    if configured_minutes >= ready_minutes:
        return hour, minute
    return DEFAULT_ARXIV_READY_HOUR, DEFAULT_ARXIV_READY_MINUTE


def effective_scheduled_time(
    now: datetime,
    cfg: Mapping[str, object],
) -> datetime:
    """Return the real start time after applying the weekday source guard."""
    hour, minute = _configured_clock(cfg)
    if is_arxiv_release_day(now.date().isoformat()):
        hour, minute = effective_weekday_schedule_clock(cfg)
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def source_empty_result_needs_retry(
    records: Iterable[Mapping[str, object]],
    date_str: str,
    cfg: Mapping[str, object],
) -> bool:
    """Return whether an unresolved empty weekday result still needs recovery.

    Before the source-ready guard existed, a 06:00 run could find zero papers,
    persist ``last_run_date`` and leave the day permanently stale.  The latest
    empty success and the new retryable-empty outcome are both signals.  A later
    content-bearing success clears them.
    """
    if not schedule_uses_daily_arxiv(cfg) or not is_arxiv_release_day(date_str):
        return False

    attempts: list[Mapping[str, object]] = []
    for record in records:
        if record.get("date_str") != date_str or record.get("trigger") != "scheduled":
            continue
        try:
            exit_code = int(record.get("exit_code"))
        except (TypeError, ValueError):
            continue
        if exit_code in {0, SCHEDULED_SOURCE_EMPTY_EXIT_CODE}:
            attempts.append(record)
    if not attempts:
        return False

    def _finished_at(record: Mapping[str, object]) -> datetime:
        raw = record.get("finished_at") or record.get("started_at")
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                pass
        return datetime.min.replace(tzinfo=timezone.utc)

    latest_content_success: datetime | None = None
    latest_empty_signal: datetime | None = None
    for record in attempts:
        finished = _finished_at(record)
        try:
            exit_code = int(record.get("exit_code"))
        except (TypeError, ValueError):
            continue
        if exit_code == SCHEDULED_SOURCE_EMPTY_EXIT_CODE:
            if latest_empty_signal is None or finished > latest_empty_signal:
                latest_empty_signal = finished
            continue

        arxiv_count = record.get("arxiv_count")
        if arxiv_count is not None:
            try:
                is_empty = int(arxiv_count) == 0
            except (TypeError, ValueError):
                is_empty = False
        else:
            try:
                is_empty = int(record.get("user_count")) == 0
            except (TypeError, ValueError):
                is_empty = False
        if is_empty:
            if latest_empty_signal is None or finished > latest_empty_signal:
                latest_empty_signal = finished
        elif latest_content_success is None or finished > latest_content_success:
            latest_content_success = finished

    if latest_empty_signal is None:
        return False
    return latest_content_success is None or latest_empty_signal > latest_content_success


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
    today = now.date().isoformat()
    if schedule_uses_daily_arxiv(cfg) and not is_arxiv_release_day(today):
        return False
    scheduled_today = effective_scheduled_time(now, cfg)
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


def failure_cooldown_remaining(
    records: Iterable[Mapping[str, object]],
    date_str: str,
    now: datetime,
    *,
    cooldown_seconds: int,
    max_cooldown_seconds: int,
) -> float:
    """Return a persisted exponential cooldown after consecutive failures.

    The retry count is intentionally still capped by ``scheduled_attempt_is_due``.
    This policy only spreads those attempts across the day so a brief dependency
    outage cannot consume the entire retry budget in a few minutes.  A successful
    scheduled record resets the failure streak.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    attempts: list[tuple[datetime, int]] = []
    for record in records:
        if (
            record.get("date_str") != date_str
            or record.get("trigger") != "scheduled"
        ):
            continue
        try:
            exit_code = int(record.get("exit_code"))
        except (TypeError, ValueError):
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
        attempts.append((finished, exit_code))

    if not attempts:
        return 0.0
    attempts.sort(key=lambda item: item[0], reverse=True)
    if attempts[0][1] == 0:
        return 0.0

    consecutive_failures = 0
    for _, exit_code in attempts:
        if exit_code == 0:
            break
        consecutive_failures += 1

    base = max(1.0, float(cooldown_seconds))
    cap = max(base, float(max_cooldown_seconds))
    delay = min(cap, base * (2 ** max(0, consecutive_failures - 1)))
    elapsed = (now - attempts[0][0]).total_seconds()
    return max(0.0, delay - elapsed)
