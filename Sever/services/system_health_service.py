"""Periodic production health checks with durable, content-free status output."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from services import pipeline_db_service
from services.storage_health_service import get_storage_health


_SEVER_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_STATE_PATH = _SEVER_ROOT / "database" / "system_health.json"
_SCHEDULE_CONFIG_PATH = _SEVER_ROOT / "database" / "schedule_config.json"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _http_json_get(url: str, timeout: float = 15.0) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "ai4papers-healthcheck/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
        return int(response.status), payload if isinstance(payload, dict) else {}


def _systemd_active(unit: str) -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", unit],
        check=False,
        timeout=10,
    )
    return result.returncode == 0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_schedule_config() -> tuple[dict[str, Any], bool]:
    try:
        value = json.loads(_SCHEDULE_CONFIG_PATH.read_text(encoding="utf-8"))
        return (value, True) if isinstance(value, dict) else ({}, False)
    except (OSError, ValueError, TypeError):
        return {}, False


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _scheduled_pipeline_check(
    current: datetime,
    runs: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    config, config_ok = _load_schedule_config()
    enabled = bool(config.get("enabled")) if config_ok else False
    hour = _safe_int(config.get("hour"), 6)
    minute = _safe_int(config.get("minute"), 0)
    hour = hour if 0 <= hour <= 23 else 6
    minute = minute if 0 <= minute <= 59 else 0
    grace_minutes = max(5, _env_int("PIPELINE_HEALTH_START_GRACE_MINUTES", 45))
    pending_limit = max(10, _env_int("PIPELINE_HEALTH_PENDING_MINUTES", 30))
    running_limit = max(60, _env_int("PIPELINE_HEALTH_RUNNING_MINUTES", 480))
    scheduled_at = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    start_deadline = scheduled_at.timestamp() + grace_minutes * 60
    start_due = current.timestamp() >= start_deadline

    root_attempts = [
        run
        for run in runs
        if run.get("trigger") == "scheduled"
        and not _safe_int(run.get("parent_run_id"))
    ]
    status_counts = {
        status: sum(1 for run in root_attempts if run.get("status") == status)
        for status in ("pending", "running", "completed", "failed")
    }
    now_utc = current.astimezone(timezone.utc)
    stale_count = 0
    for run in root_attempts:
        status = run.get("status")
        if status not in {"pending", "running"}:
            continue
        anchor = _parse_timestamp(run.get("started_at") or run.get("created_at"))
        if anchor is None:
            stale_count += 1
            continue
        age_minutes = max(0.0, (now_utc - anchor).total_seconds() / 60)
        limit = pending_limit if status == "pending" else running_limit
        if age_minutes > limit:
            stale_count += 1

    issues: list[str] = []
    if not config_ok:
        issues.append("scheduler_config_unreadable")
    elif not enabled:
        issues.append("scheduler_disabled")
    elif start_due and not root_attempts:
        issues.append("scheduled_pipeline_not_started")
    if stale_count:
        issues.append("scheduled_pipeline_stalled")
    if (
        start_due
        and status_counts["failed"]
        and not status_counts["completed"]
        and not status_counts["running"]
        and not status_counts["pending"]
    ):
        issues.append("scheduled_pipeline_failed")

    return {
        "ok": not issues,
        "config_readable": config_ok,
        "enabled": enabled,
        "scheduled_time": f"{hour:02d}:{minute:02d}",
        "start_grace_minutes": grace_minutes,
        "start_due": start_due,
        "attempts": len(root_attempts),
        "pending": status_counts["pending"],
        "running": status_counts["running"],
        "completed": status_counts["completed"],
        "failed": status_counts["failed"],
        "stale": stale_count,
        "last_run_date": config.get("last_run_date") if config_ok else None,
    }, issues


def build_health_report(
    *,
    now: Optional[datetime] = None,
    api_origin: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    """Build a report containing counts and states, never paper content."""
    current = now or datetime.now(_SHANGHAI)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_SHANGHAI)
    else:
        current = current.astimezone(_SHANGHAI)
    date_str = current.date().isoformat()
    deadline_hour = max(0, min(23, _env_int("DIGEST_HEALTH_DEADLINE_HOUR", 12)))
    deadline_passed = current.hour >= deadline_hour
    issues: list[str] = []

    api_check: dict[str, Any] = {"ok": False, "status_code": None, "paper_count": 0}
    try:
        status_code, payload = _http_json_get(
            f"{api_origin.rstrip('/')}/api/papers?date={date_str}"
        )
        papers = payload.get("papers") or payload.get("data") or []
        effective_date = str(payload.get("effective_date") or date_str)
        is_fallback = bool(payload.get("is_fallback")) or effective_date != date_str
        api_check.update(
            {
                "ok": status_code == 200,
                "status_code": status_code,
                "paper_count": len(papers) if isinstance(papers, list) else 0,
                "total_available": _safe_int(payload.get("total_available")),
                "is_fallback": is_fallback,
            }
        )
        if status_code != 200:
            issues.append("api_http_error")
        if deadline_passed and is_fallback:
            api_check["ok"] = False
            issues.append("public_digest_fallback")
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        api_check["error_type"] = type(exc).__name__
        issues.append("api_unreachable")

    try:
        storage = get_storage_health(_SEVER_ROOT)
        storage_check = {
            "ok": storage.get("state") == "healthy",
            "state": storage.get("state", "unknown"),
            "used_percent": storage.get("used_percent"),
            "free_bytes": storage.get("free_bytes"),
        }
        if storage_check["state"] == "critical":
            issues.append("storage_critical")
        elif storage_check["state"] == "warning":
            issues.append("storage_warning")
    except Exception as exc:
        storage_check = {
            "ok": False,
            "state": "unknown",
            "error_type": type(exc).__name__,
        }
        issues.append("storage_check_failed")

    try:
        runs = pipeline_db_service.get_runs_recent(limit=500, date_str=date_str)
        pipeline_check, pipeline_issues = _scheduled_pipeline_check(current, runs)
        issues.extend(pipeline_issues)
        user_ids = {0}
        user_ids.update(
            _safe_int(run.get("user_id"))
            for run in runs
            if run.get("user_id") is not None
        )
        readiness = [
            pipeline_db_service.get_digest_publication_readiness(user_id, date_str)
            for user_id in sorted(user_ids)
        ]
        ready_count = sum(1 for item in readiness if item.get("ready"))
        incomplete_count = len(readiness) - ready_count
        default_state = next(
            (item for item in readiness if item.get("user_id") == 0), {}
        )
        default_reason = default_state.get("reason", "unknown")
        default_unavailable = default_reason in {
            "temporary_unavailable_notice",
            "processing_notice",
        }
        public_empty = bool(
            default_state.get("ready")
            and default_reason == "complete"
            and api_check.get("paper_count", 0) == 0
        )
        digest_failed = bool(
            deadline_passed
            and (
                incomplete_count
                or not default_state.get("ready")
                or default_unavailable
                or public_empty
            )
        )
        digest_check = {
            "ok": not digest_failed,
            "deadline_hour": deadline_hour,
            "deadline_passed": deadline_passed,
            "users_checked": len(readiness),
            "ready_users": ready_count,
            "incomplete_users": incomplete_count,
            "default_reason": default_reason,
        }
        if deadline_passed and not default_state.get("ready"):
            issues.append("default_digest_not_ready")
        if (
            deadline_passed
            and default_reason == "temporary_unavailable_notice"
        ):
            issues.append("digest_temporarily_unavailable")
        if deadline_passed and default_reason == "processing_notice":
            issues.append("digest_still_processing")
        if deadline_passed and incomplete_count:
            issues.append("user_digest_incomplete")
        if deadline_passed and public_empty:
            issues.append("public_digest_empty")
    except Exception as exc:
        pipeline_check = {
            "ok": False,
            "error_type": type(exc).__name__,
        }
        issues.append("pipeline_execution_check_failed")
        digest_check = {
            "ok": False,
            "deadline_hour": deadline_hour,
            "deadline_passed": deadline_passed,
            "error_type": type(exc).__name__,
        }
        issues.append("digest_check_failed")

    try:
        backup_active = _systemd_active("ai4papers-db-backup.timer")
    except Exception:
        backup_active = False
    backup_check = {"ok": backup_active, "timer_active": backup_active}
    if not backup_active:
        issues.append("backup_timer_inactive")

    unique_issues = sorted(set(issues))
    return {
        "schema_version": 1,
        "checked_at": current.isoformat(),
        "date_str": date_str,
        "status": "healthy" if not unique_issues else "degraded",
        "issues": unique_issues,
        "checks": {
            "api": api_check,
            "storage": storage_check,
            "digest": digest_check,
            "pipeline": pipeline_check,
            "backup": backup_check,
        },
    }


def _read_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_state(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temp_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _post_alert(webhook_url: str, text: str) -> None:
    payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "ai4papers-healthcheck/1"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if int(response.status) >= 300:
            raise RuntimeError(f"alert webhook returned HTTP {response.status}")


def persist_report_and_alert(
    report: dict,
    *,
    state_path: str | os.PathLike[str] = _DEFAULT_STATE_PATH,
    webhook_url: Optional[str] = None,
    now_epoch: Optional[int] = None,
) -> bool:
    """Persist report and alert only on state change or after the repeat interval."""
    path = Path(state_path)
    previous = _read_state(path)
    previous_status = previous.get("status")
    previous_issues = previous.get("issues") or []
    current_status = report.get("status")
    current_issues = report.get("issues") or []
    current_epoch = int(time.time()) if now_epoch is None else int(now_epoch)
    repeat_seconds = max(900, _env_int("AI4PAPERS_ALERT_REPEAT_SECONDS", 6 * 3600))
    previous_alert_at = _safe_int(previous.get("last_alert_at"))
    changed = previous_status != current_status or previous_issues != current_issues
    repeat_due = current_status != "healthy" and (
        current_epoch - previous_alert_at >= repeat_seconds
    )
    should_alert = bool(webhook_url) and (changed or repeat_due)

    stored = dict(report)
    stored["last_alert_at"] = previous_alert_at
    if should_alert:
        if current_status == "healthy":
            message = "AI4Papers health recovered: all automated checks are healthy."
        else:
            issue_text = ", ".join(current_issues) or "unknown"
            message = f"AI4Papers health degraded: {issue_text}."
        _post_alert(str(webhook_url), message)
        stored["last_alert_at"] = current_epoch
    _write_state(path, stored)
    return should_alert
