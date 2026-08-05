"""Periodic production health checks with durable, content-free status output."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from services import pipeline_db_service
from services.storage_health_service import get_storage_health


_SEVER_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_STATE_PATH = _SEVER_ROOT / "database" / "system_health.json"
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
        digest_check = {
            "ok": not deadline_passed or incomplete_count == 0,
            "deadline_hour": deadline_hour,
            "deadline_passed": deadline_passed,
            "users_checked": len(readiness),
            "ready_users": ready_count,
            "incomplete_users": incomplete_count,
            "default_reason": default_state.get("reason", "unknown"),
        }
        if deadline_passed and not default_state.get("ready"):
            issues.append("default_digest_not_ready")
        if deadline_passed and incomplete_count:
            issues.append("user_digest_incomplete")
        if (
            deadline_passed
            and default_state.get("ready")
            and default_state.get("reason") == "complete"
            and api_check.get("paper_count", 0) == 0
        ):
            issues.append("public_digest_empty")
    except Exception as exc:
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
