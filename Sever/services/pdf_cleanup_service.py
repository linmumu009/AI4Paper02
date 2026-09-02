"""Shared recommendation-resource cleanup service.

Managed caches:
  - ``data/raw_pdf/<date>/<paper_id>.pdf``
  - ``data/file_collect/<date>/<paper_id>/``
  - ``data/full_mineru_cache/<date>/<paper_id>/``
  - ``data/selectedpaper_to_mineru/<date>/<paper_id>/``

The service never touches ``kb_files`` or ``user_papers``. A paper present in
any user's knowledge base is protected across every managed cache. If the
protection query fails, cleanup aborts instead of assuming nothing is saved.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from services.safe_logging_service import redact_sensitive_text

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_ROOT = Path(_BASE_DIR) / "data"
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")
_STATE_PATH = os.path.join(_BASE_DIR, "database", "pdf_cleanup_state.json")

_MANAGED_DIRECTORY_SOURCES = (
    "file_collect",
    "full_mineru_cache",
    "selectedpaper_to_mineru",
)
_MANAGED_SOURCES = ("raw_pdf", *_MANAGED_DIRECTORY_SOURCES)
_PRESSURE_COOLDOWN_SECONDS = 15 * 60


class CleanupSafetyError(RuntimeError):
    """Raised when cleanup cannot prove that a deletion is safe."""


def _load_state() -> dict:
    if os.path.isfile(_STATE_PATH):
        try:
            with open(_STATE_PATH, encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_STATE_PATH, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


def _get_saved_paper_ids() -> set[str]:
    """Return all saved paper IDs or abort when the protection query fails."""
    try:
        conn = sqlite3.connect(_DB_PATH)
        try:
            rows = conn.execute("SELECT DISTINCT paper_id FROM kb_papers").fetchall()
            return {str(row[0]) for row in rows if row and row[0]}
        finally:
            conn.close()
    except Exception as exc:
        logger.error(
            "pdf_cleanup_service: 无法确认知识库保护清单，已取消清理: %r",
            exc,
        )
        raise CleanupSafetyError("无法确认已收藏论文，已安全取消本次清理") from exc


def _date_from_dir_name(name: str) -> datetime | None:
    """Parse a YYYY-MM-DD cache directory name."""
    if len(name) == 10 and name[4] == "-" and name[7] == "-":
        try:
            return datetime.strptime(name, "%Y-%m-%d")
        except ValueError:
            pass
    return None


def _iter_targets() -> Iterator[tuple[str, datetime, str, Path]]:
    """Yield ``(source, date, paper_id, path)`` for managed cache entries."""
    raw_pdf_root = _DATA_ROOT / "raw_pdf"
    if raw_pdf_root.is_dir():
        for date_entry in raw_pdf_root.iterdir():
            if not date_entry.is_dir() or date_entry.is_symlink():
                continue
            cache_date = _date_from_dir_name(date_entry.name)
            if cache_date is None:
                continue
            for pdf_file in date_entry.iterdir():
                if (
                    pdf_file.is_file()
                    and not pdf_file.is_symlink()
                    and pdf_file.suffix.lower() == ".pdf"
                ):
                    yield "raw_pdf", cache_date, pdf_file.stem, pdf_file

    for source in _MANAGED_DIRECTORY_SOURCES:
        root = _DATA_ROOT / source
        if not root.is_dir():
            continue
        for date_entry in root.iterdir():
            if not date_entry.is_dir() or date_entry.is_symlink():
                continue
            cache_date = _date_from_dir_name(date_entry.name)
            if cache_date is None:
                continue
            for paper_dir in date_entry.iterdir():
                if paper_dir.is_dir() and not paper_dir.is_symlink():
                    yield source, cache_date, paper_dir.name, paper_dir


def _path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            total += child.stat().st_size
    return total


def _delete_target(path: Path) -> None:
    """Delete one validated cache target without following symlinks."""
    data_root = _DATA_ROOT.resolve()
    resolved = path.resolve()
    if resolved == data_root or data_root not in resolved.parents:
        raise CleanupSafetyError("清理目标超出允许的数据缓存目录")
    if path.is_symlink():
        raise CleanupSafetyError("拒绝清理符号链接目标")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _get_disk_status() -> dict[str, Any]:
    """Return cache-volume capacity and the configured low-space threshold."""
    import config.config as config

    min_free_gb = max(
        1.0,
        float(getattr(config, "PDF_CLEANUP_MIN_FREE_GB", 10.0)),
    )
    min_free_bytes = int(min_free_gb * 1024 ** 3)
    try:
        usage = shutil.disk_usage(_DATA_ROOT)
    except OSError as exc:
        return {
            "available": False,
            "error": redact_sensitive_text(str(exc)),
            "min_free_gb": min_free_gb,
            "min_free_bytes": min_free_bytes,
            "pressure_active": False,
        }
    return {
        "available": True,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": round(usage.used / usage.total * 100, 1) if usage.total else 0.0,
        "min_free_gb": min_free_gb,
        "min_free_bytes": min_free_bytes,
        "pressure_active": usage.free < min_free_bytes,
    }


def run_cleanup(
    retention_days: int | None = None,
    dry_run: bool = False,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Preview or remove expired, unsaved shared recommendation resources."""
    started_at = datetime.now(timezone.utc).isoformat()
    disk_before = _get_disk_status()

    if retention_days is None:
        try:
            import config.config as config
            retention_days = getattr(config, "PDF_CLEANUP_RETENTION_DAYS", 14)
        except Exception:
            retention_days = 14
    retention_days = max(1, int(retention_days))

    cutoff = datetime.now() - timedelta(days=retention_days)
    saved_ids = _get_saved_paper_ids()

    scanned = 0
    deletable = 0
    deleted = 0
    skipped_saved = 0
    skipped_recent = 0
    reclaimable_bytes = 0
    freed_bytes = 0
    errors: list[str] = []
    source_stats: dict[str, dict[str, int]] = {
        source: {
            "scanned": 0,
            "deletable": 0,
            "deleted": 0,
            "reclaimable_bytes": 0,
            "freed_bytes": 0,
        }
        for source in _MANAGED_SOURCES
    }

    for source, cache_date, paper_id, target in _iter_targets():
        scanned += 1
        source_stats[source]["scanned"] += 1
        if paper_id in saved_ids:
            skipped_saved += 1
            continue
        if cache_date >= cutoff:
            skipped_recent += 1
            continue

        try:
            size = _path_size(target)
        except Exception as exc:
            errors.append(redact_sensitive_text(f"{target}: {exc}"))
            continue

        deletable += 1
        reclaimable_bytes += size
        source_stats[source]["deletable"] += 1
        source_stats[source]["reclaimable_bytes"] += size

        if dry_run:
            continue

        try:
            _delete_target(target)
        except Exception as exc:
            errors.append(redact_sensitive_text(f"{target}: {exc}"))
            continue

        deleted += 1
        freed_bytes += size
        source_stats[source]["deleted"] += 1
        source_stats[source]["freed_bytes"] += size

    # In preview mode, report the estimated space that would be released. The
    # UI labels this as an estimate rather than claiming deletion occurred.
    reported_bytes = reclaimable_bytes if dry_run else freed_bytes
    finished_at = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {
        "dry_run": dry_run,
        "trigger": trigger,
        "retention_days": retention_days,
        "managed_sources": list(_MANAGED_SOURCES),
        "sources": source_stats,
        "scanned": scanned,
        "deletable": deletable,
        "deleted": deleted,
        "skipped_saved": skipped_saved,
        "skipped_recent": skipped_recent,
        "reclaimable_bytes": reclaimable_bytes,
        "freed_bytes": reported_bytes,
        "freed_mb": round(reported_bytes / 1024 / 1024, 2),
        "errors": errors[:50],
        "started_at": started_at,
        "finished_at": finished_at,
        "disk_before": disk_before,
        "disk_after": _get_disk_status(),
    }

    if not dry_run:
        state = _load_state()
        state["last_run_at"] = finished_at
        # A partial deletion is not a successful scheduled run. Leaving the
        # date incomplete lets the scheduler retry failed targets later today.
        if not errors:
            state["last_success_date"] = datetime.now().date().isoformat()
        state["last_result"] = result
        _save_state(state)
        logger.info(
            "pdf_cleanup_service: 完成资源清理 scanned=%d deleted=%d freed=%.2f MB errors=%d",
            scanned,
            deleted,
            result["freed_mb"],
            len(errors),
        )
    else:
        logger.info(
            "pdf_cleanup_service: 预览资源清理 scanned=%d deletable=%d reclaimable=%.2f MB",
            scanned,
            deletable,
            result["freed_mb"],
        )

    return result


_auto_thread: threading.Thread | None = None
_auto_stop = threading.Event()
_last_pressure_attempt_monotonic = 0.0


def _auto_loop() -> None:
    """Run at or after the configured time, retrying failures the same day."""
    global _last_pressure_attempt_monotonic
    while not _auto_stop.is_set():
        try:
            import config.config as config
            auto_enabled = bool(getattr(config, "PDF_CLEANUP_AUTO_ENABLED", False))
            pressure_enabled = bool(
                getattr(config, "PDF_CLEANUP_PRESSURE_ENABLED", True)
            )
            if not auto_enabled and not pressure_enabled:
                _auto_stop.wait(60)
                continue

            now = datetime.now()
            monotonic_now = time.monotonic()

            if (
                pressure_enabled
                and monotonic_now - _last_pressure_attempt_monotonic
                >= _PRESSURE_COOLDOWN_SECONDS
            ):
                disk_status = _get_disk_status()
                if disk_status.get("pressure_active"):
                    _last_pressure_attempt_monotonic = monotonic_now
                    regular_retention = max(
                        1,
                        int(getattr(config, "PDF_CLEANUP_RETENTION_DAYS", 14)),
                    )
                    pressure_retention = max(
                        1,
                        int(
                            getattr(
                                config,
                                "PDF_CLEANUP_PRESSURE_RETENTION_DAYS",
                                1,
                            )
                        ),
                    )
                    effective_retention = min(
                        regular_retention,
                        pressure_retention,
                    )
                    logger.warning(
                        "pdf_cleanup_service: 磁盘低空间保护触发 free=%.2f GB "
                        "threshold=%.2f GB retention=%d days",
                        int(disk_status.get("free_bytes", 0)) / 1024 ** 3,
                        float(disk_status.get("min_free_gb", 0)),
                        effective_retention,
                    )
                    try:
                        run_cleanup(
                            retention_days=effective_retention,
                            dry_run=False,
                            trigger="disk_pressure",
                        )
                    except Exception as exc:
                        logger.error(
                            "pdf_cleanup_service: 磁盘低空间保护清理失败: %r",
                            exc,
                        )
                    _auto_stop.wait(60)
                    continue

            if not auto_enabled:
                _auto_stop.wait(60)
                continue

            today = now.date().isoformat()
            scheduled = now.replace(
                hour=int(getattr(config, "PDF_CLEANUP_HOUR", 3)),
                minute=int(getattr(config, "PDF_CLEANUP_MINUTE", 0)),
                second=0,
                microsecond=0,
            )
            last_success_date = str(_load_state().get("last_success_date") or "")

            if now >= scheduled and last_success_date != today:
                logger.info("pdf_cleanup_service: 自动资源清理开始 date=%s", today)
                try:
                    run_cleanup(dry_run=False, trigger="scheduled")
                except Exception as exc:
                    # The day remains incomplete, so the next tick retries.
                    logger.error("pdf_cleanup_service: 自动资源清理失败: %r", exc)
        except Exception as exc:
            logger.error("pdf_cleanup_service: _auto_loop 异常: %r", exc)

        _auto_stop.wait(60)


def start_auto_scheduler() -> None:
    global _auto_thread
    if _auto_thread is not None and _auto_thread.is_alive():
        return
    _auto_stop.clear()
    _auto_thread = threading.Thread(
        target=_auto_loop,
        daemon=True,
        name="pdf_cleanup_scheduler",
    )
    _auto_thread.start()
    logger.info("pdf_cleanup_service: 自动资源清理调度线程已启动")


def stop_auto_scheduler() -> None:
    _auto_stop.set()


def get_status() -> dict[str, Any]:
    """Return cleanup configuration, scheduler health and the last result."""
    import config.config as config
    state = _load_state()
    scheduler_alive = _auto_thread is not None and _auto_thread.is_alive()
    return {
        "auto_enabled": getattr(config, "PDF_CLEANUP_AUTO_ENABLED", False),
        "retention_days": getattr(config, "PDF_CLEANUP_RETENTION_DAYS", 14),
        "auto_hour": getattr(config, "PDF_CLEANUP_HOUR", 3),
        "auto_minute": getattr(config, "PDF_CLEANUP_MINUTE", 0),
        "pressure_enabled": getattr(
            config,
            "PDF_CLEANUP_PRESSURE_ENABLED",
            True,
        ),
        "min_free_gb": getattr(config, "PDF_CLEANUP_MIN_FREE_GB", 10.0),
        "pressure_retention_days": getattr(
            config,
            "PDF_CLEANUP_PRESSURE_RETENTION_DAYS",
            1,
        ),
        "disk": _get_disk_status(),
        "scheduler_alive": scheduler_alive,
        "managed_sources": list(_MANAGED_SOURCES),
        "last_run_at": state.get("last_run_at"),
        "last_success_date": state.get("last_success_date"),
        "last_result": state.get("last_result"),
    }
