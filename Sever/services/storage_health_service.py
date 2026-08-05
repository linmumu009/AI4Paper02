"""Disk-capacity health checks used by pipeline preflight and admin status."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

_SEVER_ROOT = Path(__file__).resolve().parents[1]


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


def get_storage_health(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    target = Path(path or os.environ.get("AI4PAPERS_STORAGE_PATH") or _SEVER_ROOT)
    usage = shutil.disk_usage(target)
    used_percent = round((usage.used / usage.total) * 100, 2) if usage.total else 100.0

    warning_percent = _env_float("AI4PAPERS_DISK_WARNING_PERCENT", 85.0)
    critical_percent = _env_float("AI4PAPERS_DISK_CRITICAL_PERCENT", 95.0)
    minimum_free_bytes = _env_int(
        "AI4PAPERS_DISK_MIN_FREE_BYTES", 2 * 1024 * 1024 * 1024
    )

    if used_percent >= critical_percent or usage.free < minimum_free_bytes:
        state = "critical"
    elif used_percent >= warning_percent:
        state = "warning"
    else:
        state = "healthy"

    can_start_pipeline = state != "critical"
    return {
        "path": str(target.resolve()),
        "state": state,
        "can_start_pipeline": can_start_pipeline,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": used_percent,
        "warning_percent": warning_percent,
        "critical_percent": critical_percent,
        "minimum_free_bytes": minimum_free_bytes,
        "reason": (
            "ok"
            if can_start_pipeline
            else "disk capacity is below the safe pipeline threshold"
        ),
    }


def require_pipeline_capacity(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    health = get_storage_health(path)
    if not health["can_start_pipeline"]:
        raise RuntimeError(
            "Pipeline blocked by storage preflight: "
            f"used={health['used_percent']}% free={health['free_bytes']} "
            f"minimum_free={health['minimum_free_bytes']}"
        )
    return health
