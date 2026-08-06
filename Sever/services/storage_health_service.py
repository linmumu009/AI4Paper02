"""Disk-capacity health checks used by pipeline preflight and admin status."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

_SEVER_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_DIRECTORY_NAMES = ("data", "database", "logs")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _probe_writable_directory(path: Path) -> dict[str, Any]:
    """Prove that the current service account can create and remove a file."""
    probe_path: str | None = None
    try:
        if not path.is_dir():
            return {"ok": False, "error_type": "DirectoryMissing"}
        descriptor, probe_path = tempfile.mkstemp(
            prefix=".ai4papers-write-probe-",
            dir=path,
        )
        os.close(descriptor)
        os.unlink(probe_path)
        probe_path = None
        return {"ok": True, "error_type": None}
    except (OSError, ValueError, TypeError) as exc:
        return {"ok": False, "error_type": type(exc).__name__}
    finally:
        if probe_path:
            try:
                os.unlink(probe_path)
            except OSError:
                pass


def get_runtime_write_health(
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Return content-free write probes for every pipeline runtime directory."""
    root = Path(path or _SEVER_ROOT)
    checks = {
        name: _probe_writable_directory(root / name)
        for name in _RUNTIME_DIRECTORY_NAMES
    }
    failed = [name for name, check in checks.items() if not check["ok"]]
    return {
        "ok": not failed,
        "checked": list(_RUNTIME_DIRECTORY_NAMES),
        "failed": failed,
        "checks": checks,
    }


def get_storage_health(
    path: str | os.PathLike[str] | None = None,
    *,
    check_runtime_writes: bool = False,
) -> dict[str, Any]:
    target = Path(path or os.environ.get("AI4PAPERS_STORAGE_PATH") or _SEVER_ROOT)
    usage = shutil.disk_usage(target)
    used_percent = round((usage.used / usage.total) * 100, 2) if usage.total else 100.0

    warning_percent = _env_float("AI4PAPERS_DISK_WARNING_PERCENT", 85.0)
    critical_percent = _env_float("AI4PAPERS_DISK_CRITICAL_PERCENT", 95.0)
    minimum_free_bytes = _env_int(
        "AI4PAPERS_DISK_MIN_FREE_BYTES", 2 * 1024 * 1024 * 1024
    )

    if used_percent >= critical_percent or usage.free < minimum_free_bytes:
        capacity_state = "critical"
    elif used_percent >= warning_percent:
        capacity_state = "warning"
    else:
        capacity_state = "healthy"

    runtime_write = (
        get_runtime_write_health(target) if check_runtime_writes else None
    )
    write_access_ok = runtime_write is None or runtime_write["ok"]
    capacity_ok = capacity_state != "critical"
    can_start_pipeline = capacity_ok and write_access_ok
    state = "critical" if not write_access_ok else capacity_state
    if not write_access_ok:
        reason = "required runtime paths are not writable"
    elif not capacity_ok:
        reason = "disk capacity is below the safe pipeline threshold"
    else:
        reason = "ok"
    return {
        "path": str(target.resolve()),
        "state": state,
        "capacity_state": capacity_state,
        "can_start_pipeline": can_start_pipeline,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": used_percent,
        "warning_percent": warning_percent,
        "critical_percent": critical_percent,
        "minimum_free_bytes": minimum_free_bytes,
        "runtime_write": runtime_write,
        "reason": reason,
    }


def require_pipeline_capacity(
    path: str | os.PathLike[str] | None = None,
    *,
    check_runtime_writes: bool = False,
) -> dict[str, Any]:
    health = get_storage_health(
        path,
        check_runtime_writes=check_runtime_writes,
    )
    if not health["can_start_pipeline"]:
        raise RuntimeError(
            "Pipeline blocked by storage preflight: "
            f"reason={health['reason']} "
            f"used={health['used_percent']}% free={health['free_bytes']} "
            f"minimum_free={health['minimum_free_bytes']}"
        )
    return health
