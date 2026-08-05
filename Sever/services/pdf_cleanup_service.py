"""
PDF 缓存清理服务。

清理对象：推荐卡片使用的共享 PDF 缓存
  - data/raw_pdf/<date>/<paper_id>.pdf
  - data/file_collect/<date>/<paper_id>/<paper_id>.pdf（兼容历史布局）

保护条件：只要 paper_id 出现在任意用户的 kb_papers 中，就视为"有人收藏"，
跳过清理。不触碰 kb_files/ 下的用户知识库副本，也不触碰 user_papers/ 下的用户上传文件。

清理触发：
  - 手动：通过管理 API 触发（支持 dry_run 预览）
  - 自动：后台线程每日定时检查，当 auto_enabled=True 时执行
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.safe_logging_service import redact_sensitive_text

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_ROOT = Path(_BASE_DIR) / "data"
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")
_STATE_PATH = os.path.join(_BASE_DIR, "database", "pdf_cleanup_state.json")


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if os.path.isfile(_STATE_PATH):
        try:
            with open(_STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _get_saved_paper_ids() -> set[str]:
    """返回所有用户已收藏到知识库的 paper_id 集合（任意 scope）。"""
    try:
        conn = sqlite3.connect(_DB_PATH)
        try:
            rows = conn.execute("SELECT DISTINCT paper_id FROM kb_papers").fetchall()
            return {r[0] for r in rows}
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("pdf_cleanup_service: 查询 kb_papers 失败: %r", exc)
        return set()


def _date_from_dir_name(name: str) -> datetime | None:
    """解析 YYYY-MM-DD 格式的目录名，返回 date 或 None。"""
    if len(name) == 10 and name[4] == "-" and name[7] == "-":
        try:
            return datetime.strptime(name, "%Y-%m-%d")
        except ValueError:
            pass
    return None


def run_cleanup(
    retention_days: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """执行 PDF 缓存清理。

    Parameters
    ----------
    retention_days:
        N天。若为 None 则读取配置中的 PDF_CLEANUP_RETENTION_DAYS（默认 14）。
    dry_run:
        True = 只统计不删除。

    Returns
    -------
    dict 包含：
        scanned / deletable / deleted / skipped_saved / skipped_recent /
        freed_bytes / errors / dry_run / started_at / finished_at
    """
    started_at = datetime.now(timezone.utc).isoformat()

    if retention_days is None:
        try:
            import config.config as _cfg
            retention_days = getattr(_cfg, "PDF_CLEANUP_RETENTION_DAYS", 14)
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
    freed_bytes = 0
    errors: list[str] = []

    def _try_delete(pdf_path: Path) -> int:
        """删除文件，返回释放字节数。"""
        try:
            size = pdf_path.stat().st_size
            if not dry_run:
                pdf_path.unlink()
            return size
        except Exception as exc:
            errors.append(redact_sensitive_text(f"{pdf_path}: {exc}"))
            return 0

    # ── 1. raw_pdf/<date>/<paper_id>.pdf ──────────────────────────────────
    raw_pdf_root = _DATA_ROOT / "raw_pdf"
    if raw_pdf_root.is_dir():
        for date_entry in raw_pdf_root.iterdir():
            if not date_entry.is_dir():
                continue
            dt = _date_from_dir_name(date_entry.name)
            if dt is None:
                continue
            for pdf_file in date_entry.iterdir():
                if not pdf_file.is_file():
                    continue
                if not pdf_file.suffix.lower() == ".pdf":
                    continue
                if pdf_file.name == "_manifest.json":
                    continue
                scanned += 1
                paper_id = pdf_file.stem
                if paper_id in saved_ids:
                    skipped_saved += 1
                    continue
                if dt >= cutoff:
                    skipped_recent += 1
                    continue
                deletable += 1
                freed = _try_delete(pdf_file)
                if freed >= 0 and not dry_run:
                    deleted += 1
                freed_bytes += freed

    # ── 2. file_collect/<date>/<paper_id>/<paper_id>.pdf（历史布局）──────
    file_collect_root = _DATA_ROOT / "file_collect"
    if file_collect_root.is_dir():
        for date_entry in file_collect_root.iterdir():
            if not date_entry.is_dir():
                continue
            dt = _date_from_dir_name(date_entry.name)
            if dt is None:
                continue
            for paper_dir in date_entry.iterdir():
                if not paper_dir.is_dir():
                    continue
                paper_id = paper_dir.name
                pdf_file = paper_dir / f"{paper_id}.pdf"
                if not pdf_file.is_file():
                    continue
                scanned += 1
                if paper_id in saved_ids:
                    skipped_saved += 1
                    continue
                if dt >= cutoff:
                    skipped_recent += 1
                    continue
                deletable += 1
                freed = _try_delete(pdf_file)
                if freed >= 0 and not dry_run:
                    deleted += 1
                freed_bytes += freed

    finished_at = datetime.now(timezone.utc).isoformat()

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "retention_days": retention_days,
        "scanned": scanned,
        "deletable": deletable,
        "deleted": deleted if not dry_run else 0,
        "skipped_saved": skipped_saved,
        "skipped_recent": skipped_recent,
        "freed_bytes": freed_bytes if not dry_run else 0,
        "freed_mb": round(freed_bytes / 1024 / 1024, 2) if not dry_run else 0.0,
        "errors": errors[:50],
        "started_at": started_at,
        "finished_at": finished_at,
    }

    if not dry_run:
        state = _load_state()
        state["last_run_at"] = finished_at
        state["last_result"] = result
        _save_state(state)
        logger.info(
            "pdf_cleanup_service: 完成清理 scanned=%d deleted=%d freed=%.2f MB errors=%d",
            scanned, deleted, result["freed_mb"], len(errors),
        )
    else:
        logger.info(
            "pdf_cleanup_service: dry-run scanned=%d deletable=%d skipped_saved=%d",
            scanned, deletable, skipped_saved,
        )

    return result


# ---------------------------------------------------------------------------
# Auto-scheduler
# ---------------------------------------------------------------------------

_auto_thread: threading.Thread | None = None
_auto_stop = threading.Event()


def _auto_loop() -> None:
    """后台线程：每分钟检查一次，到达配置时间时执行清理（每天最多一次）。"""
    last_run_date = ""
    while not _auto_stop.is_set():
        try:
            import config.config as _cfg
            if not getattr(_cfg, "PDF_CLEANUP_AUTO_ENABLED", False):
                _auto_stop.wait(60)
                continue

            now = datetime.now()
            today = now.date().isoformat()
            cfg_hour = getattr(_cfg, "PDF_CLEANUP_HOUR", 3)
            cfg_minute = getattr(_cfg, "PDF_CLEANUP_MINUTE", 0)

            if (
                now.hour == cfg_hour
                and now.minute == cfg_minute
                and last_run_date != today
            ):
                last_run_date = today
                logger.info("pdf_cleanup_service: 自动清理开始 date=%s", today)
                try:
                    run_cleanup(dry_run=False)
                except Exception as exc:
                    logger.error("pdf_cleanup_service: 自动清理失败: %r", exc)
        except Exception as exc:
            logger.error("pdf_cleanup_service: _auto_loop 异常: %r", exc)

        _auto_stop.wait(60)


def start_auto_scheduler() -> None:
    global _auto_thread
    if _auto_thread is not None and _auto_thread.is_alive():
        return
    _auto_stop.clear()
    _auto_thread = threading.Thread(
        target=_auto_loop, daemon=True, name="pdf_cleanup_scheduler"
    )
    _auto_thread.start()
    logger.info("pdf_cleanup_service: 自动清理调度线程已启动")


def stop_auto_scheduler() -> None:
    _auto_stop.set()


def get_status() -> dict[str, Any]:
    """返回清理服务当前状态。"""
    import config.config as _cfg
    state = _load_state()
    scheduler_alive = _auto_thread is not None and _auto_thread.is_alive()
    return {
        "auto_enabled": getattr(_cfg, "PDF_CLEANUP_AUTO_ENABLED", False),
        "retention_days": getattr(_cfg, "PDF_CLEANUP_RETENTION_DAYS", 14),
        "auto_hour": getattr(_cfg, "PDF_CLEANUP_HOUR", 3),
        "auto_minute": getattr(_cfg, "PDF_CLEANUP_MINUTE", 0),
        "scheduler_alive": scheduler_alive,
        "last_run_at": state.get("last_run_at"),
        "last_result": state.get("last_result"),
    }
