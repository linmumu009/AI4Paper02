"""
Pipeline & Scheduler Router.

All routes are prefixed with /api/admin and registered in api.py via
    app.include_router(pipeline_router)

Owns all pipeline global state (threads, locks, runtime JSON) so the
scheduler never pollutes the composition root.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import auth_service
from services.pipeline_schedule_policy import (
    DEFAULT_SCHEDULED_MAX_ATTEMPTS,
    count_scheduled_attempts,
    failure_cooldown_remaining,
    rate_limit_cooldown_remaining,
    scheduled_attempt_is_due,
)
from services.safe_logging_service import redact_sensitive_data, redact_sensitive_text
from services.safe_logging_service import safe_failure_detail

router = APIRouter(prefix="/api/admin", tags=["pipeline"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RunPipelineBody(BaseModel):
    pipeline: str = Field(default="default", pattern=r"^[a-zA-Z0-9_-]+$")
    date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    sllm: Optional[int] = None
    zo: Optional[str] = Field(default="F", pattern="^[TF]$")
    user_id: Optional[int] = Field(default=None, description="User ID for per-user config overrides")
    force: bool = Field(default=False, description="强制重新执行：删除已有输出，忽略幂等检查")
    multi_user: bool = Field(default=False, description="启用多用户编排：shared + per_user（含所有自定义配置用户）")
    max_concurrent_user_pipelines: int = Field(default=3, ge=1, le=20)
    days: Optional[int] = Field(default=None, ge=1, le=30)
    categories: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9.,_-]+$")
    extra_query: Optional[str] = Field(default=None, max_length=500)
    max_papers: Optional[int] = Field(default=None, ge=1, le=5000)
    anchor_tz: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9_/+-]+$")


class RerunPipelineBody(BaseModel):
    """Request body for targeted rerun (single step or resume-from)."""
    run_id: int = Field(description="DB run_id to rerun from")
    from_step: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9_-]+$", description="Resume from this step (inclusive)")
    only_step: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9_-]+$", description="Run only this single step")
    force: bool = Field(default=True, description="Force re-execution even if output exists")


class ScheduleConfigBody(BaseModel):
    enabled: bool
    hour: int = Field(default=6, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    pipeline: str = Field(default="daily")
    sllm: Optional[int] = None
    zo: Optional[str] = Field(default="F", pattern="^[TF]$")
    user_id: Optional[int] = Field(default=None)
    multi_user: bool = Field(default=True)
    max_concurrent_user_pipelines: int = Field(default=3, ge=1, le=20)


class StepConfigBody(BaseModel):
    config: dict = Field(..., description="步骤启用/禁用映射 {step_key: bool}")


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_SEVER_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_APP_PY_PATH = os.path.join(_SEVER_DIR, "app.py")
_SCHEDULE_CONFIG_PATH = os.path.join(_SEVER_DIR, "database", "schedule_config.json")
_SCHEDULER_LOCK_PATH = os.path.join(_SEVER_DIR, "database", "scheduler.lock")
_PIPELINE_EXECUTION_LOCK_PATH = os.path.join(_SEVER_DIR, "database", "pipeline_execution.lock")
_RUNTIME_STATE_PATH = os.path.join(_SEVER_DIR, "database", "pipeline_runtime_state.json")
_ADMIN_LOG_DIR = os.path.join(_SEVER_DIR, "logs", "admin_pipeline")
_SCHEDULE_HISTORY_PATH = os.path.join(_SEVER_DIR, "database", "schedule_history.jsonl")

# ---------------------------------------------------------------------------
# Global pipeline state
# ---------------------------------------------------------------------------

_pipeline_state: dict = {
    "running": False,
    "current_step": None,
    "logs": [],
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "params": {},
    "process": None,
    "run_id": None,
    "log_file": None,
}
_pipeline_lock = threading.Lock()
_pipeline_start_lock = threading.Lock()

_active_per_user_procs: list = []
_active_per_user_procs_lock = threading.Lock()

_scheduler_state: dict = {
    "enabled": False,
    "hour": 6,
    "minute": 0,
    "pipeline": "daily",
    "sllm": None,
    "zo": "F",
    "user_id": None,
    "last_run_date": None,
    "multi_user": True,
    "max_concurrent_user_pipelines": 3,
}
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop_event = threading.Event()

_scheduler_retry_counts: dict = {}
_SCHEDULER_MAX_RETRIES = DEFAULT_SCHEDULED_MAX_ATTEMPTS
_SCHEDULER_FAILURE_COOLDOWN_SECONDS = 300
_SCHEDULER_FAILURE_MAX_COOLDOWN_SECONDS = 7200
_SCHEDULER_RATE_LIMIT_COOLDOWN_SECONDS = 1800
_SCHEDULER_RATE_LIMIT_MAX_COOLDOWN_SECONDS = 14400
_TRANSIENT_DATE_NOTICE_TYPES = (
    "pipeline_processing",
    "source_temporarily_unavailable",
    "pipeline_temporarily_unavailable",
)


def _write_pipeline_processing_notices(date_str: str) -> None:
    """Make an in-progress digest visible instead of exposing an unexplained gap."""
    try:
        from services import pipeline_db_service as _pdb
        from services.user_settings_service import list_users_with_custom_configs

        user_ids = {0}
        user_ids.update(int(uid) for uid in list_users_with_custom_configs())
        for user_id in user_ids:
            _pdb.upsert_date_notice(
                user_id,
                date_str,
                "pipeline_processing",
                "今日论文正在生成，完成后会自动显示，请稍后查看。",
            )
    except Exception as exc:
        print(f"[SCHEDULER] 无法写入生成中提示: {exc!r}", flush=True)


def _write_shared_failure_notices(date_str: str, exit_code: int) -> None:
    """Expose a professional empty state while the shared source is unavailable."""
    try:
        from services import pipeline_db_service as _pdb
        from services.user_settings_service import list_users_with_custom_configs

        user_ids = {0}
        user_ids.update(int(uid) for uid in list_users_with_custom_configs())
        if exit_code == 2:
            notice_type = "source_temporarily_unavailable"
            message = (
                "arXiv 论文源当前限流，系统正在自动重试。"
                "今日内容尚未生成，请稍后再查看。"
            )
        else:
            notice_type = "pipeline_temporarily_unavailable"
            message = "今日内容生成暂时失败，系统正在自动恢复，请稍后再查看。"
        for user_id in user_ids:
            _pdb.upsert_date_notice(user_id, date_str, notice_type, message)
    except Exception as exc:
        print(f"[SCHEDULER] 无法写入共享阶段故障提示: {exc!r}", flush=True)


def _clear_shared_failure_notices(date_str: str) -> None:
    """Remove transient notices once the shared stage succeeds."""
    try:
        from services import pipeline_db_service as _pdb

        for notice_type in _TRANSIENT_DATE_NOTICE_TYPES:
            _pdb.delete_date_notices_by_type(date_str, notice_type)
    except Exception as exc:
        print(f"[SCHEDULER] 无法清理过期共享阶段故障提示: {exc!r}", flush=True)
_arxiv_rate_limit_last_at: Optional[float] = None


# ---------------------------------------------------------------------------
# Schedule config helpers
# ---------------------------------------------------------------------------

def _load_schedule_config() -> dict:
    if os.path.isfile(_SCHEDULE_CONFIG_PATH):
        try:
            with open(_SCHEDULE_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_schedule_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(_SCHEDULE_CONFIG_PATH), exist_ok=True)
    tmp = _SCHEDULE_CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, _SCHEDULE_CONFIG_PATH)


# ---------------------------------------------------------------------------
# Runtime state helpers
# ---------------------------------------------------------------------------

def _load_runtime_state() -> dict:
    if os.path.isfile(_RUNTIME_STATE_PATH):
        try:
            with open(_RUNTIME_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_runtime_state(state: dict) -> None:
    os.makedirs(os.path.dirname(_RUNTIME_STATE_PATH), exist_ok=True)
    tmp = _RUNTIME_STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, _RUNTIME_STATE_PATH)


def _admin_pipeline_failure_detail(exc: BaseException, operation: str) -> str:
    return safe_failure_detail(
        logger,
        "流水线管理操作失败，请稍后重试",
        exc,
        operation=operation,
    )


def _rollback_rerun_launch(
    new_run_id: int,
    started_at: str,
    params: dict,
    log_file: str,
    public_error: str,
) -> None:
    """Make a failed rerun launch visible as failed everywhere it was registered."""
    finished_at = datetime.now(timezone.utc).isoformat()
    run_key = f"rerun_{new_run_id}"

    if new_run_id:
        try:
            from services import pipeline_db_service as _pdb
            _pdb.update_run_status(new_run_id, "failed", error=public_error)
        except Exception as rollback_exc:
            logger.error(
                "rerun_launch_db_rollback_failed run_id=%s error=%s",
                new_run_id,
                redact_sensitive_text(rollback_exc),
            )

    owns_runtime_state = False
    with _pipeline_lock:
        if _pipeline_state.get("run_id") == run_key:
            owns_runtime_state = True
            _pipeline_state["running"] = False
            _pipeline_state["process"] = None
            _pipeline_state["current_step"] = "重跑启动失败"
            _pipeline_state["finished_at"] = finished_at
            _pipeline_state["exit_code"] = -1
            _pipeline_state["params"] = params

    if not owns_runtime_state:
        return

    try:
        _save_runtime_state({
            "running": False,
            "pid": None,
            "current_step": "重跑启动失败",
            "started_at": started_at,
            "finished_at": finished_at,
            "exit_code": -1,
            "params": params,
            "run_id": run_key,
            "log_file": log_file,
            "error": public_error,
        })
    except Exception as rollback_exc:
        logger.error(
            "rerun_launch_runtime_rollback_failed run_id=%s error=%s",
            new_run_id,
            redact_sensitive_text(rollback_exc),
        )


# ---------------------------------------------------------------------------
# Schedule history helpers
# ---------------------------------------------------------------------------

def _append_schedule_history(record: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_SCHEDULE_HISTORY_PATH), exist_ok=True)
        with open(_SCHEDULE_HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _load_schedule_history(limit: int = 50) -> list:
    if not os.path.isfile(_SCHEDULE_HISTORY_PATH):
        return []
    records = []
    try:
        with open(_SCHEDULE_HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return records[-limit:][::-1]


def _scheduled_attempt_count(date_str: str) -> int:
    """Restore today's retry count from disk so API restarts cannot reset it."""
    return count_scheduled_attempts(
        _load_schedule_history(limit=200), date_str
    )


def _scheduled_attempt_is_due(now: datetime, cfg: dict, attempt_count: int) -> bool:
    """Return whether today's job still needs a same-day start or catch-up."""
    return scheduled_attempt_is_due(
        now,
        cfg,
        attempt_count,
        max_retries=_SCHEDULER_MAX_RETRIES,
    )


def _get_log_tail(log_file: str, n: int = 300) -> list:
    if not log_file or not os.path.isfile(log_file):
        return []
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [redact_sensitive_text(ln.rstrip("\n")) for ln in lines[-n:]]
    except OSError:
        return []


# ---------------------------------------------------------------------------
# Pipeline thread functions
# ---------------------------------------------------------------------------

def _phase_for_pipeline(pipeline: str) -> str:
    if pipeline == "shared":
        return "shared"
    if pipeline == "per_user":
        return "per_user"
    return pipeline


def _create_db_run(
    pipeline: str,
    date_str: str,
    user_id: int = 0,
    phase: str = "",
    trigger: str = "manual",
    parent_run_id: int = 0,
    requested_by: Optional[int] = None,
    config: Optional[dict] = None,
) -> int:
    """Create a pipeline_runs row and return its id (0 on error)."""
    try:
        from services import pipeline_db_service as _pdb
        run_id = _pdb.create_run(
            run_type=phase or pipeline,
            user_id=user_id,
            date_str=date_str,
            pipeline=pipeline,
            config=config or {},
            parent_run_id=parent_run_id or None,
            trigger=trigger,
            phase=phase,
            requested_by=requested_by,
        )
        _pdb.update_run_status(run_id, "running")
        return run_id
    except Exception:
        return 0


def _run_pipeline_thread(
    pipeline: str,
    date_str: str,
    sllm: Optional[int],
    zo: str,
    user_id: Optional[int] = None,
    force: bool = False,
    days: Optional[int] = None,
    categories: Optional[str] = None,
    extra_query: Optional[str] = None,
    max_papers: Optional[int] = None,
    anchor_tz: Optional[str] = None,
    output_mode_override: Optional[str] = None,
    trigger: str = "manual",
    parent_run_id: int = 0,
    requested_by: Optional[int] = None,
    lease_token: Optional[str] = None,
):
    global _pipeline_state
    # Create DB run record before building the cmd so we can pass --run-id
    uid_int = int(user_id) if user_id is not None else 0
    phase = _phase_for_pipeline(pipeline)
    db_run_id = _create_db_run(
        pipeline=pipeline,
        date_str=date_str,
        user_id=uid_int,
        phase=phase,
        trigger=trigger,
        parent_run_id=parent_run_id,
        requested_by=requested_by,
        config={"sllm": sllm, "zo": zo, "force": force},
    )

    cmd = [sys.executable, "-u", _APP_PY_PATH, pipeline, "--date", date_str, "--Zo", zo]
    if force:
        cmd.append("--force")
    if sllm is not None:
        cmd.extend(["--SLLM", str(sllm)])
    if user_id is not None:
        cmd.extend(["--user-id", str(user_id)])
    if output_mode_override:
        cmd.extend(["--output-mode", output_mode_override])
    if days is not None:
        cmd.extend(["--days", str(days)])
    if categories:
        cmd.extend(["--categories", categories])
    if extra_query:
        cmd.extend(["--query", extra_query])
    if max_papers is not None:
        cmd.extend(["--max-papers", str(max_papers)])
    if anchor_tz:
        cmd.extend(["--anchor-tz", anchor_tz])
    if db_run_id:
        cmd.extend(["--run-id", str(db_run_id)])
    if phase:
        cmd.extend(["--phase", phase])

    env = {**os.environ, "RUN_DATE": date_str, "PYTHONIOENCODING": "utf-8"}
    if sllm is not None:
        env["SLLM"] = str(sllm)
    if user_id is not None:
        env["PIPELINE_USER_ID"] = str(user_id)
    if output_mode_override:
        env["PIPELINE_OUTPUT_MODE"] = output_mode_override

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(_ADMIN_LOG_DIR, exist_ok=True)
    log_file = os.path.join(_ADMIN_LOG_DIR, f"{run_id}.log")
    if db_run_id:
        try:
            from services import pipeline_db_service as _pdb
            _pdb.update_run_log_file(db_run_id, log_file)
        except Exception:
            pass

    params = {
        "pipeline": pipeline,
        "date": date_str,
        "sllm": sllm,
        "zo": zo,
        "user_id": user_id,
        "days": days,
        "categories": categories,
        "extra_query": extra_query,
        "max_papers": max_papers,
        "anchor_tz": anchor_tz,
        "output_mode": output_mode_override or "file",
    }
    started_at = datetime.now(timezone.utc).isoformat()
    init_log_line = f"[{datetime.now().strftime('%H:%M:%S')}] 启动 Pipeline: {pipeline}  日期: {date_str}"

    with _pipeline_lock:
        _pipeline_state["running"] = True
        _pipeline_state["current_step"] = "启动中..."
        _pipeline_state["logs"] = [init_log_line]
        _pipeline_state["started_at"] = started_at
        _pipeline_state["finished_at"] = None
        _pipeline_state["exit_code"] = None
        _pipeline_state["params"] = params
        _pipeline_state["run_id"] = run_id
        _pipeline_state["log_file"] = log_file

    _save_runtime_state({
        "running": True,
        "current_step": "启动中...",
        "started_at": started_at,
        "finished_at": None,
        "exit_code": None,
        "params": params,
        "run_id": run_id,
        "log_file": log_file,
    })

    exit_code = -1
    log_fh = None
    try:
        log_fh = open(log_file, "w", encoding="utf-8", buffering=1)
        log_fh.write(init_log_line + "\n")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_SEVER_DIR,
            env=env,
            start_new_session=(sys.platform != "win32"),
        )
        with _pipeline_lock:
            _pipeline_state["process"] = proc

        try:
            _save_runtime_state({
                "running": True,
                "pid": proc.pid,
                "current_step": "启动中...",
                "started_at": started_at,
                "finished_at": None,
                "exit_code": None,
                "params": params,
                "run_id": run_id,
                "log_file": log_file,
            })
        except OSError:
            pass

        def _is_progress_line(s: str) -> bool:
            return " progress done=" in s or "[PROGRESS] " in s

        current_step = "启动中..."
        for line in proc.stdout:
            line = redact_sensitive_text(line.rstrip("\n"))
            log_line = f"[{datetime.now().strftime('%H:%M:%S')}] {line}"

            step_changed = False
            if line.startswith("RUN step:"):
                current_step = line.replace("RUN step:", "").strip()
                step_changed = True
            elif line.startswith("SKIP step:"):
                current_step = f"跳过: {line.replace('SKIP step:', '').strip()}"
                step_changed = True

            with _pipeline_lock:
                if (
                    _is_progress_line(line)
                    and _pipeline_state["logs"]
                    and _is_progress_line(_pipeline_state["logs"][-1])
                ):
                    _pipeline_state["logs"][-1] = log_line
                else:
                    _pipeline_state["logs"].append(log_line)
                if len(_pipeline_state["logs"]) > 500:
                    _pipeline_state["logs"] = _pipeline_state["logs"][-500:]
                _pipeline_state["current_step"] = current_step

            if log_fh:
                log_fh.write(log_line + "\n")

            if step_changed:
                try:
                    _save_runtime_state({
                        "running": True,
                        "pid": proc.pid,
                        "current_step": current_step,
                        "started_at": started_at,
                        "finished_at": None,
                        "exit_code": None,
                        "params": params,
                        "run_id": run_id,
                        "log_file": log_file,
                    })
                except OSError:
                    pass

        proc.wait()
        exit_code = proc.returncode
    except Exception as exc:
        exit_code = -1
        err_line = redact_sensitive_text(
            f"[{datetime.now().strftime('%H:%M:%S')}] [ERROR] {exc}"
        )
        with _pipeline_lock:
            _pipeline_state["logs"].append(err_line)
        if log_fh:
            try:
                log_fh.write(err_line + "\n")
            except OSError:
                pass
    finally:
        if log_fh:
            try:
                log_fh.close()
            except OSError:
                pass
        finished_at = datetime.now(timezone.utc).isoformat()
        final_step = "已完成" if exit_code == 0 else f"异常退出 (code={exit_code})"
        with _pipeline_lock:
            _pipeline_state["running"] = False
            _pipeline_state["finished_at"] = finished_at
            _pipeline_state["exit_code"] = exit_code
            _pipeline_state["current_step"] = final_step
            _pipeline_state["process"] = None
        try:
            _save_runtime_state({
                "running": False,
                "current_step": final_step,
                "started_at": started_at,
                "finished_at": finished_at,
                "exit_code": exit_code,
                "params": params,
                "run_id": run_id,
                "log_file": log_file,
            })
        except OSError:
            pass
        _append_schedule_history({
            "run_id": run_id,
            "trigger": trigger,
            "date_str": date_str,
            "started_at": started_at,
            "finished_at": finished_at,
            "user_count": 1,
            "user_ids": [user_id] if user_id is not None else [0],
            "exit_code": exit_code,
            "success": exit_code == 0,
            "pipeline": pipeline,
        })
        if trigger == "scheduled":
            lock_path = f"{_SCHEDULER_LOCK_PATH}.{date_str}"
            if exit_code == 0:
                try:
                    new_cfg = {**_load_schedule_config(), "last_run_date": date_str}
                    _save_schedule_config(new_cfg)
                    _scheduler_state["last_run_date"] = date_str
                except OSError:
                    pass
            else:
                try:
                    os.remove(lock_path)
                except OSError:
                    pass
        _release_execution_lease(lease_token)


def _run_pipeline_subprocess(cmd: list, env: dict, log_file: str) -> int:
    exit_code = -1
    log_fh = None
    proc = None
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        log_fh = open(log_file, "w", encoding="utf-8", buffering=1)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_SEVER_DIR,
            env=env,
            start_new_session=(sys.platform != "win32"),
        )
        with _active_per_user_procs_lock:
            _active_per_user_procs.append(proc)
        for line in proc.stdout:
            line = redact_sensitive_text(line.rstrip("\n"))
            log_fh.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")
        proc.wait()
        exit_code = proc.returncode
    except Exception as exc:
        exit_code = -1
        if log_fh:
            try:
                log_fh.write(redact_sensitive_text(f"[ERROR] {exc}") + "\n")
            except OSError:
                pass
    finally:
        with _active_per_user_procs_lock:
            if proc and proc in _active_per_user_procs:
                _active_per_user_procs.remove(proc)
        if log_fh:
            try:
                log_fh.close()
            except OSError:
                pass
    return exit_code


def _run_multiuser_scheduler_thread(
    cfg: dict,
    today: str,
    lease_token: Optional[str] = None,
) -> None:
    import concurrent.futures as _cf

    sllm = cfg.get("sllm")
    zo = cfg.get("zo", "F")
    max_concurrent = int(cfg.get("max_concurrent_user_pipelines") or 3)
    force = bool(cfg.get("force", False))

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_multi"
    os.makedirs(_ADMIN_LOG_DIR, exist_ok=True)
    orch_log_file = os.path.join(_ADMIN_LOG_DIR, f"{run_id}.log")
    started_at = datetime.now(timezone.utc).isoformat()
    params = {"pipeline": "multi_user", "date": today, "sllm": sllm, "zo": zo}

    def _orch_log(msg: str) -> None:
        msg = redact_sensitive_text(msg)
        log_line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        with _pipeline_lock:
            _pipeline_state["logs"].append(log_line)
            if len(_pipeline_state["logs"]) > 500:
                _pipeline_state["logs"] = _pipeline_state["logs"][-500:]
        try:
            with open(orch_log_file, "a", encoding="utf-8") as _f:
                _f.write(log_line + "\n")
        except OSError:
            pass

    with _pipeline_lock:
        _pipeline_state["running"] = True
        _pipeline_state["current_step"] = "初始化多用户编排..."
        _pipeline_state["logs"] = [
            f"[{datetime.now().strftime('%H:%M:%S')}] 启动多用户 Pipeline  日期: {today}"
        ]
        _pipeline_state["started_at"] = started_at
        _pipeline_state["finished_at"] = None
        _pipeline_state["exit_code"] = None
        _pipeline_state["params"] = params
        _pipeline_state["run_id"] = run_id
        _pipeline_state["log_file"] = orch_log_file
        _pipeline_state["process"] = None

    _save_runtime_state({
        "running": True,
        "current_step": "初始化多用户编排...",
        "started_at": started_at,
        "finished_at": None,
        "exit_code": None,
        "params": params,
        "run_id": run_id,
        "log_file": orch_log_file,
        "pid": None,
    })

    exit_code = 0
    user_ids_to_run: list = []
    trigger = cfg.get("trigger", "scheduled")
    db_parent_run_id = 0
    try:
        db_parent_run_id = _create_db_run(
            pipeline="multi_user",
            date_str=today,
            user_id=0,
            phase="orchestrator",
            trigger=trigger,
            config={"sllm": sllm, "zo": zo, "force": force},
        )
        if db_parent_run_id:
            try:
                from services import pipeline_db_service as _pdb
                _pdb.update_run_log_file(db_parent_run_id, orch_log_file)
            except Exception:
                pass
    except Exception:
        pass

    try:
        _orch_log(f"[SCHEDULER] 开始共享阶段 (shared) for {today}")
        _write_pipeline_processing_notices(today)
        with _pipeline_lock:
            _pipeline_state["current_step"] = "共享阶段运行中..."
        _save_runtime_state({
            "running": True, "current_step": "共享阶段运行中...",
            "started_at": started_at, "finished_at": None, "exit_code": None,
            "params": params, "run_id": run_id, "log_file": orch_log_file,
        })

        shared_log = os.path.join(_ADMIN_LOG_DIR, f"{run_id}_shared.log")
        shared_db_run_id = _create_db_run(
            pipeline="shared",
            date_str=today,
            user_id=0,
            phase="shared",
            trigger=trigger,
            parent_run_id=db_parent_run_id,
        )
        if shared_db_run_id:
            try:
                from services import pipeline_db_service as _pdb
                _pdb.update_run_log_file(shared_db_run_id, shared_log)
            except Exception:
                pass
        shared_cmd = [sys.executable, "-u", _APP_PY_PATH, "shared", "--date", today, "--Zo", zo,
                      "--phase", "shared"]
        if shared_db_run_id:
            shared_cmd.extend(["--run-id", str(shared_db_run_id)])
        if sllm is not None:
            shared_cmd.extend(["--SLLM", str(sllm)])
        if force:
            shared_cmd.append("--force")
        if cfg.get("days") is not None:
            shared_cmd.extend(["--days", str(cfg["days"])])
        if cfg.get("extra_query"):
            shared_cmd.extend(["--query", str(cfg["extra_query"])])
        if cfg.get("max_papers") is not None:
            shared_cmd.extend(["--max-papers", str(cfg["max_papers"])])
            _orch_log(f"[SCHEDULER] 最大论文数: {cfg['max_papers']}")
        if cfg.get("anchor_tz"):
            shared_cmd.extend(["--anchor-tz", str(cfg["anchor_tz"])])
        if cfg.get("categories"):
            shared_cmd.extend(["--categories", str(cfg["categories"])])
            _orch_log(f"[SCHEDULER] 使用管理端指定检索分类: {cfg['categories']}")
        else:
            try:
                from services.user_settings_service import collect_all_search_categories
                all_cats = collect_all_search_categories()
                if all_cats:
                    shared_cmd.extend(["--categories", ",".join(all_cats)])
                    _orch_log(f"[SCHEDULER] 合并检索分类: {','.join(all_cats)}")
            except Exception as _cat_exc:
                _orch_log(f"[SCHEDULER] 无法收集检索分类，使用系统默认: {_cat_exc!r}")
        shared_env = {
            **os.environ,
            "RUN_DATE": today,
            "PYTHONIOENCODING": "utf-8",
            "PIPELINE_OUTPUT_MODE": "db",
        }
        if sllm is not None:
            shared_env["SLLM"] = str(sllm)

        shared_exit = _run_pipeline_subprocess(shared_cmd, shared_env, shared_log)
        _orch_log(f"[SCHEDULER] 共享阶段完成 exit={shared_exit}  详细日志: {os.path.basename(shared_log)}")
        try:
            from services import pipeline_db_service as _pdb
            if shared_db_run_id:
                if shared_exit == 0:
                    status = "completed"
                elif shared_exit == 3:
                    status = "partial"
                else:
                    status = "failed"
                _pdb.update_run_status(shared_db_run_id, status)
        except Exception:
            pass

        if shared_exit in (2, 3):
            global _arxiv_rate_limit_last_at
            import time as _time
            _arxiv_rate_limit_last_at = _time.time()
        if shared_exit == 3:
            _orch_log(
                "[SCHEDULER] arxiv_search 因限流仅部分拉取 (exit=3)，"
                "已保存部分列表；后续步骤继续。建议 15–30 分钟后再重跑 arxiv_search。"
            )
            shared_exit = 0

        if shared_exit != 0:
            _orch_log(f"[SCHEDULER] 共享阶段失败 (exit={shared_exit})，终止多用户编排")
            exit_code = shared_exit
            return

        # Short-circuit: if shared phase found 0 papers for today, skip per_user entirely.
        # arxiv_search writes 0 rows to pipeline_arxiv_list when empty, so count=0 is the signal.
        try:
            from services import pipeline_db_service as _pdb
            _arxiv_count = len(_pdb.get_arxiv_list_ids(today))
        except Exception as _cnt_exc:
            _orch_log(f"[SCHEDULER] 无法查询今日论文数量: {_cnt_exc!r}，继续执行每用户阶段")
            _arxiv_count = -1  # unknown; err on side of continuing

        if _arxiv_count == 0:
            _orch_log(f"[SCHEDULER] 今日 arxiv 论文为 0 篇，跳过每用户阶段 (per_user)")
            # Ensure all custom users also see a date notice so the frontend shows the right card
            try:
                from services.user_settings_service import list_users_with_custom_configs as _luc
                _all_uids = [0] + [u for u in _luc() if u != 0]
            except Exception:
                _all_uids = [0]
            try:
                _notice = _pdb.get_date_notice(0, today)
                _notice_type = _notice["type"] if _notice else "no_papers_empty"
                _notice_msg = _notice["message"] if _notice else "今天 ArXiv 在您关注的领域暂无新论文（搜索窗口内无结果）。"
                for _uid in _all_uids:
                    if _uid != 0:
                        _pdb.upsert_date_notice(_uid, today, _notice_type, _notice_msg)
            except Exception as _ne:
                _orch_log(f"[SCHEDULER] 无法写入每用户 date_notice: {_ne!r}")
            return

        try:
            from services.user_settings_service import list_users_with_custom_configs
            custom_user_ids = list_users_with_custom_configs()
        except Exception as exc:
            _orch_log(f"[SCHEDULER] 无法获取自定义用户列表: {exc!r}，仅运行默认用户")
            custom_user_ids = []

        user_ids_to_run = [0] + [uid for uid in custom_user_ids if uid != 0]
        _orch_log(f"[SCHEDULER] 开始每用户阶段 (per_user)，用户列表={user_ids_to_run}")
        with _pipeline_lock:
            _pipeline_state["current_step"] = f"每用户阶段 ({len(user_ids_to_run)} 用户)..."
        _save_runtime_state({
            "running": True,
            "current_step": f"每用户阶段 ({len(user_ids_to_run)} 用户)...",
            "started_at": started_at, "finished_at": None, "exit_code": None,
            "params": params, "run_id": run_id, "log_file": orch_log_file,
        })

        def run_per_user(uid: int) -> tuple:
            per_user_log = os.path.join(_ADMIN_LOG_DIR, f"{run_id}_user{uid}.log")
            per_user_db_run_id = _create_db_run(
                pipeline="per_user",
                date_str=today,
                user_id=uid,
                phase="per_user",
                trigger=trigger,
                parent_run_id=db_parent_run_id,
            )
            if per_user_db_run_id:
                try:
                    from services import pipeline_db_service as _pdb2
                    _pdb2.update_run_log_file(per_user_db_run_id, per_user_log)
                except Exception:
                    pass
            per_user_cmd = [
                sys.executable, "-u", _APP_PY_PATH, "per_user",
                "--date", today, "--Zo", zo,
                "--user-id", str(uid),
                "--output-mode", "db",
                "--phase", "per_user",
            ]
            if per_user_db_run_id:
                per_user_cmd.extend(["--run-id", str(per_user_db_run_id)])
            if sllm is not None:
                per_user_cmd.extend(["--SLLM", str(sllm)])
            if force:
                per_user_cmd.append("--force")
            per_user_env = {
                **os.environ,
                "RUN_DATE": today,
                "PYTHONIOENCODING": "utf-8",
                "PIPELINE_USER_ID": str(uid),
                "PIPELINE_OUTPUT_MODE": "db",
            }
            if sllm is not None:
                per_user_env["SLLM"] = str(sllm)
            _orch_log(f"[SCHEDULER] user={uid} 开始  详细日志: {os.path.basename(per_user_log)}")
            ec = _run_pipeline_subprocess(per_user_cmd, per_user_env, per_user_log)
            _orch_log(f"[SCHEDULER] user={uid} 完成 exit={ec}")
            try:
                from services import pipeline_db_service as _pdb
                if per_user_db_run_id:
                    _pdb.update_run_status(per_user_db_run_id, "completed" if ec == 0 else "failed")
            except Exception:
                pass
            return uid, ec

        with _cf.ThreadPoolExecutor(max_workers=max_concurrent) as pool:
            futures = {pool.submit(run_per_user, uid): uid for uid in user_ids_to_run}
            for fut in _cf.as_completed(futures):
                uid = futures[fut]
                try:
                    _, ec = fut.result()
                    if ec != 0:
                        exit_code = ec
                except Exception as exc:
                    _orch_log(f"[SCHEDULER] user={uid} 运行异常: {exc!r}")
                    exit_code = -1

        _orch_log(f"[SCHEDULER] 所有每用户管线已完成 for {today}")

        # Destructive cleanup is an orchestrator concern, not a per-user step.
        # Run it exactly once and only after every user pipeline has succeeded.
        if exit_code == 0:
            cleanup_log = os.path.join(_ADMIN_LOG_DIR, f"{run_id}_cleanup.log")
            cleanup_db_run_id = _create_db_run(
                pipeline="post_users_cleanup",
                date_str=today,
                user_id=0,
                phase="cleanup",
                trigger=trigger,
                parent_run_id=db_parent_run_id,
            )
            if cleanup_db_run_id:
                try:
                    from services import pipeline_db_service as _pdb3
                    _pdb3.update_run_log_file(cleanup_db_run_id, cleanup_log)
                except Exception:
                    pass
            cleanup_cmd = [
                sys.executable, "-u", _APP_PY_PATH, "post_users_cleanup",
                "--date", today,
                "--phase", "cleanup",
            ]
            if cleanup_db_run_id:
                cleanup_cmd.extend(["--run-id", str(cleanup_db_run_id)])
            cleanup_env = {
                **os.environ,
                "RUN_DATE": today,
                "PYTHONIOENCODING": "utf-8",
                "PIPELINE_PHASE": "cleanup",
            }
            _orch_log(f"[SCHEDULER] 开始全用户完成后清理  详细日志: {os.path.basename(cleanup_log)}")
            cleanup_exit = _run_pipeline_subprocess(cleanup_cmd, cleanup_env, cleanup_log)
            _orch_log(f"[SCHEDULER] 全用户完成后清理结束 exit={cleanup_exit}")
            try:
                from services import pipeline_db_service as _pdb4
                if cleanup_db_run_id:
                    _pdb4.update_run_status(
                        cleanup_db_run_id,
                        "completed" if cleanup_exit == 0 else "failed",
                    )
            except Exception:
                pass
            if cleanup_exit != 0:
                exit_code = cleanup_exit
        else:
            _orch_log("[SCHEDULER] 至少一个用户管线失败，跳过清理以保留可重试输入")

    except Exception as exc:
        _orch_log(f"[SCHEDULER] 编排异常: {exc!r}")
        exit_code = -1

    finally:
        if exit_code == 0:
            _clear_shared_failure_notices(today)
        else:
            _write_shared_failure_notices(today, exit_code)

        # Update parent DB run status
        try:
            if db_parent_run_id:
                from services import pipeline_db_service as _pdb
                _pdb.update_run_status(db_parent_run_id, "completed" if exit_code == 0 else "failed")
        except Exception:
            pass

        finished_at = datetime.now(timezone.utc).isoformat()
        final_step = "已完成" if exit_code == 0 else f"异常退出 (code={exit_code})"
        with _pipeline_lock:
            _pipeline_state["running"] = False
            _pipeline_state["finished_at"] = finished_at
            _pipeline_state["exit_code"] = exit_code
            _pipeline_state["current_step"] = final_step
            _pipeline_state["process"] = None
        try:
            _save_runtime_state({
                "running": False,
                "current_step": final_step,
                "started_at": started_at,
                "finished_at": finished_at,
                "exit_code": exit_code,
                "params": params,
                "run_id": run_id,
                "log_file": orch_log_file,
                "pid": None,
            })
        except OSError:
            pass
        _append_schedule_history({
            "run_id": run_id,
            "trigger": trigger,
            "date_str": today,
            "started_at": started_at,
            "finished_at": finished_at,
            "user_count": len(user_ids_to_run),
            "user_ids": user_ids_to_run,
            "exit_code": exit_code,
            "success": exit_code == 0,
        })

        _lock_path = f"{_SCHEDULER_LOCK_PATH}.{today}"
        if trigger == "scheduled":
            if exit_code == 0:
                new_cfg = {**_load_schedule_config(), "last_run_date": today}
                try:
                    _save_schedule_config(new_cfg)
                    _scheduler_state["last_run_date"] = today
                    print(
                        f"[SCHEDULER] 定时 Pipeline 成功完成，已记录 last_run_date={today}",
                        flush=True,
                    )
                except OSError:
                    pass
            else:
                try:
                    os.remove(_lock_path)
                    print(
                        f"[SCHEDULER] 定时 Pipeline 失败 (exit={exit_code})，"
                        "已释放 lock 文件，将在今日稍后重新尝试",
                        flush=True,
                    )
                except OSError:
                    pass
        _release_execution_lease(lease_token)


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _maybe_clear_stale_runtime_state() -> bool:
    disk_rt = _load_runtime_state()
    if not disk_rt.get("running"):
        return False

    pid = disk_rt.get("pid")
    if pid:
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            pid_int = None
        if pid_int and not _is_pid_alive(pid_int):
            print(
                f"[SCHEDULER] 检测到残留运行状态 (PID={pid_int} 已不存在)，自动重置 running=False",
                flush=True,
            )
            _save_runtime_state({**disk_rt, "running": False, "current_step": "异常退出（进程已消失）", "exit_code": -1})
            with _pipeline_lock:
                _pipeline_state["running"] = False
            return True

    # Multi-user orchestration and targeted reruns are owned by an API thread,
    # not by one stable child PID.  Their cross-process lease is the reliable
    # liveness record.  If the API died, the lease owner is dead and the old
    # runtime JSON must not block the next request for six hours.
    if not pid:
        try:
            from services.pipeline_lease_service import read_lease

            lease = read_lease(_PIPELINE_EXECUTION_LOCK_PATH)
            lease_pid = int(lease.get("pid") or 0)
        except (OSError, TypeError, ValueError):
            lease_pid = 0
        if lease_pid <= 0 or not _is_pid_alive(lease_pid):
            _save_runtime_state({
                **disk_rt,
                "running": False,
                "current_step": "异常退出（执行租约已失效）",
                "exit_code": -1,
            })
            with _pipeline_lock:
                _pipeline_state["running"] = False
            return True

    started_at_str = disk_rt.get("started_at")
    if started_at_str:
        try:
            from datetime import timezone as _tz
            started_at = datetime.fromisoformat(started_at_str)
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=_tz.utc)
            elapsed_hours = (datetime.now(_tz.utc) - started_at).total_seconds() / 3600
            if elapsed_hours > 6:
                print(
                    f"[SCHEDULER] 检测到残留运行状态（已运行 {elapsed_hours:.1f} 小时），自动重置 running=False",
                    flush=True,
                )
                _save_runtime_state({**disk_rt, "running": False, "current_step": "超时自动重置", "exit_code": -1})
                with _pipeline_lock:
                    _pipeline_state["running"] = False
                return True
        except Exception:
            pass

    return False


def _try_acquire_execution_lease(
    pipeline: str,
    date_str: str,
    trigger: str,
) -> Optional[dict]:
    """Atomically reserve the single host-wide pipeline execution slot."""
    from services.pipeline_lease_service import (
        acquire_pipeline_lease,
        release_pipeline_lease,
    )

    with _pipeline_start_lock:
        _maybe_clear_stale_runtime_state()
        lease = acquire_pipeline_lease(
            _PIPELINE_EXECUTION_LOCK_PATH,
            pipeline=pipeline,
            date_str=date_str,
            trigger=trigger,
        )
        if lease is None:
            return None

        disk_rt = _load_runtime_state()
        with _pipeline_lock:
            memory_running = bool(_pipeline_state.get("running"))
        if disk_rt.get("running") or memory_running:
            release_pipeline_lease(_PIPELINE_EXECUTION_LOCK_PATH, lease["token"])
            return None
        return lease


def _release_execution_lease(token: Optional[str]) -> None:
    try:
        from services.pipeline_lease_service import release_pipeline_lease

        release_pipeline_lease(_PIPELINE_EXECUTION_LOCK_PATH, token)
    except OSError:
        pass


def _run_with_execution_lease(target, lease_token: str, *args, **kwargs) -> None:
    """Guarantee lease release even if a worker fails before its own ``try``."""
    try:
        target(*args, lease_token=lease_token, **kwargs)
    finally:
        _release_execution_lease(lease_token)


def _release_current_execution_lease() -> None:
    try:
        from services.pipeline_lease_service import read_lease

        lease = read_lease(_PIPELINE_EXECUTION_LOCK_PATH)
        _release_execution_lease(lease.get("token"))
    except OSError:
        pass


def _scheduler_lock_is_stale(lock_path: str) -> bool:
    """Return true only when a crashed scheduled attempt left its day lock."""
    try:
        with open(lock_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        pid = int(payload.get("pid") or 0)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        try:
            return time.time() - os.path.getmtime(lock_path) > 30
        except OSError:
            return True
    return pid <= 0 or not _is_pid_alive(pid)


def _scheduler_loop():
    while not _scheduler_stop_event.is_set():
        try:
            now = datetime.now()
            disk_cfg = _load_schedule_config()
            cfg = {**_scheduler_state, **disk_cfg}
            today = now.date().isoformat()

            for _d in list(_scheduler_retry_counts.keys()):
                if _d != today:
                    del _scheduler_retry_counts[_d]

            retry_count_today = max(
                _scheduler_retry_counts.get(today, 0),
                _scheduled_attempt_count(today),
            )

            history = _load_schedule_history(limit=200)
            import time as _time
            retry_cooldown_remaining = 0.0
            if _arxiv_rate_limit_last_at is not None:
                since_rl = _time.time() - _arxiv_rate_limit_last_at
                if since_rl < _SCHEDULER_RATE_LIMIT_COOLDOWN_SECONDS:
                    retry_cooldown_remaining = max(
                        retry_cooldown_remaining,
                        _SCHEDULER_RATE_LIMIT_COOLDOWN_SECONDS - since_rl,
                    )
            utc_now = datetime.now(timezone.utc)
            retry_cooldown_remaining = max(
                retry_cooldown_remaining,
                rate_limit_cooldown_remaining(
                    history,
                    today,
                    utc_now,
                    cooldown_seconds=_SCHEDULER_RATE_LIMIT_COOLDOWN_SECONDS,
                    max_cooldown_seconds=_SCHEDULER_RATE_LIMIT_MAX_COOLDOWN_SECONDS,
                ),
                failure_cooldown_remaining(
                    history,
                    today,
                    utc_now,
                    cooldown_seconds=_SCHEDULER_FAILURE_COOLDOWN_SECONDS,
                    max_cooldown_seconds=_SCHEDULER_FAILURE_MAX_COOLDOWN_SECONDS,
                ),
            )

            if _scheduled_attempt_is_due(now, cfg, retry_count_today):
                if retry_cooldown_remaining > 0:
                    _scheduler_stop_event.wait(30)
                    continue

                lock_path = f"{_SCHEDULER_LOCK_PATH}.{today}"
                os.makedirs(os.path.dirname(_SCHEDULER_LOCK_PATH), exist_ok=True)
                try:
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    try:
                        os.write(fd, json.dumps({
                            "pid": os.getpid(),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }).encode("utf-8"))
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                except FileExistsError:
                    if _scheduler_lock_is_stale(lock_path):
                        try:
                            os.remove(lock_path)
                        except OSError:
                            pass
                    _scheduler_stop_event.wait(30)
                    continue

                lease = _try_acquire_execution_lease(
                    "multi_user" if cfg.get("multi_user", True) else cfg.get("pipeline", "daily"),
                    today,
                    "scheduled",
                )
                if lease is not None:
                    use_multi_user = cfg.get("multi_user", True)
                    if use_multi_user:
                        t = threading.Thread(
                            target=_run_with_execution_lease,
                            args=(_run_multiuser_scheduler_thread, lease["token"], cfg, today),
                            daemon=True,
                        )
                    else:
                        t = threading.Thread(
                            target=_run_with_execution_lease,
                            args=(
                                _run_pipeline_thread,
                                lease["token"],
                                cfg.get("pipeline", "daily"),
                                today,
                                cfg.get("sllm"),
                                cfg.get("zo", "F"),
                            ),
                            kwargs={
                                "user_id": cfg.get("user_id"),
                                "trigger": "scheduled",
                            },
                            daemon=True,
                        )
                    try:
                        t.start()
                    except Exception:
                        _release_execution_lease(lease["token"])
                        try:
                            os.remove(lock_path)
                        except OSError:
                            pass
                        raise

                    _scheduler_retry_counts[today] = retry_count_today + 1
                    print(
                        f"[SCHEDULER] 已在 {now.strftime('%H:%M:%S')} 启动定时 Pipeline，"
                        f"日期: {today}（今日第 {retry_count_today + 1}/{_SCHEDULER_MAX_RETRIES} 次尝试）",
                        flush=True,
                    )
                else:
                    try:
                        os.remove(lock_path)
                    except OSError:
                        pass
                    print(
                        f"[SCHEDULER] {today} 触发时 Pipeline 仍在运行中，本次跳过（lock 已释放，下次循环重试）",
                        flush=True,
                    )
        except Exception as exc:
            print(f"[SCHEDULER] 调度循环出现未预期异常（已捕获，线程继续运行）: {exc!r}", flush=True)

        _scheduler_stop_event.wait(30)


def _start_scheduler():
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return
    _scheduler_stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()


# Load saved schedule on module import
_saved_schedule = _load_schedule_config()
if _saved_schedule:
    _scheduler_state.update(_saved_schedule)
    if _scheduler_state.get("enabled"):
        _start_scheduler()


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@router.post("/pipeline/run", summary="Manually run pipeline")
def api_admin_run_pipeline(
    body: RunPipelineBody,
    _admin=Depends(auth_service.require_admin_user),
):
    _maybe_clear_stale_runtime_state()

    disk_state = _load_runtime_state()
    if disk_state.get("running") or _pipeline_state["running"]:
        raise HTTPException(status_code=409, detail="Pipeline 正在运行中，请等待完成")

    date_str = body.date or datetime.now().date().isoformat()
    force_hint = "（强制模式）" if body.force else ""
    lease = _try_acquire_execution_lease(
        "multi_user" if body.multi_user else body.pipeline,
        date_str,
        "manual",
    )
    if lease is None:
        raise HTTPException(status_code=409, detail="Pipeline 正在运行中，请等待完成")

    if body.multi_user:
        cfg = {
            "sllm": body.sllm,
            "zo": body.zo or "F",
            "max_concurrent_user_pipelines": body.max_concurrent_user_pipelines,
            "trigger": "manual",
            "force": body.force,
            "days": body.days,
            "categories": body.categories,
            "extra_query": body.extra_query,
            "max_papers": body.max_papers,
            "anchor_tz": body.anchor_tz,
        }
        t = threading.Thread(
            target=_run_with_execution_lease,
            args=(_run_multiuser_scheduler_thread, lease["token"], cfg, date_str),
            daemon=True,
        )
        try:
            t.start()
        except Exception:
            _release_execution_lease(lease["token"])
            raise
        return {"ok": True, "message": f"多用户 Pipeline 已启动{force_hint}，日期: {date_str}（shared + per_user × 所有自定义用户）"}
    else:
        pipeline_user_id = body.user_id if body.user_id is not None else _admin.get("id")
        t = threading.Thread(
            target=_run_with_execution_lease,
            args=(_run_pipeline_thread, lease["token"]),
            kwargs={
                "pipeline": body.pipeline,
                "date_str": date_str,
                "sllm": body.sllm,
                "zo": body.zo or "F",
                "user_id": pipeline_user_id,
                "force": body.force,
                "days": body.days,
                "categories": body.categories,
                "extra_query": body.extra_query,
                "max_papers": body.max_papers,
                "anchor_tz": body.anchor_tz,
                "output_mode_override": "db",
            },
            daemon=True,
        )
        try:
            t.start()
        except Exception:
            _release_execution_lease(lease["token"])
            raise
        return {"ok": True, "message": f"Pipeline '{body.pipeline}' 已启动{force_hint}，日期: {date_str}"}


@router.get("/pipeline/status", summary="Get pipeline run status")
def api_admin_pipeline_run_status(
    _admin=Depends(auth_service.require_admin_user),
):
    _maybe_clear_stale_runtime_state()

    disk_state = _load_runtime_state()
    if disk_state:
        log_file = disk_state.get("log_file")
        logs = _get_log_tail(log_file, n=300)
        base = {
            "running": disk_state.get("running", False),
            "current_step": disk_state.get("current_step"),
            "logs": logs,
            "started_at": disk_state.get("started_at"),
            "finished_at": disk_state.get("finished_at"),
            "exit_code": disk_state.get("exit_code"),
            "params": disk_state.get("params", {}),
            "run_id": disk_state.get("run_id"),
        }
    else:
        with _pipeline_lock:
            base = {
                "running": _pipeline_state["running"],
                "current_step": _pipeline_state["current_step"],
                "logs": list(_pipeline_state["logs"]),
                "started_at": _pipeline_state["started_at"],
                "finished_at": _pipeline_state["finished_at"],
                "exit_code": _pipeline_state["exit_code"],
                "params": _pipeline_state["params"],
                "run_id": None,
            }

    # Enrich with DB-sourced step summary when a numeric run_id is available
    try:
        from services import pipeline_db_service as _pdb
        db_runs = _pdb.get_runs_recent(limit=5)
        if db_runs:
            latest = db_runs[0]
            base["db_run"] = {
                "id": latest.get("id"),
                "status": latest.get("status"),
                "phase": latest.get("phase"),
                "user_id": latest.get("user_id"),
                "date_str": latest.get("date_str"),
                "started_at": latest.get("started_at"),
                "finished_at": latest.get("finished_at"),
            }
            step_counts_row = _pdb.get_run_summary(latest["id"])
            if step_counts_row:
                base["db_run"]["step_counts"] = step_counts_row.get("step_counts", {})
                base["db_run"]["step_failed"] = step_counts_row.get("step_failed", 0)
                base["db_run"]["step_completed"] = step_counts_row.get("step_completed", 0)
                base["db_run"]["step_skipped"] = step_counts_row.get("step_skipped", 0)
    except Exception:
        pass

    try:
        from services.storage_health_service import get_storage_health

        base["storage"] = get_storage_health(
            _SEVER_DIR,
            check_runtime_writes=True,
        )
    except Exception as exc:
        base["storage"] = {
            "state": "unknown",
            "can_start_pipeline": False,
            "reason": f"storage health check failed: {exc}",
        }

    return base


@router.post("/pipeline/stop", summary="Stop running pipeline")
def api_admin_stop_pipeline(
    _admin=Depends(auth_service.require_admin_user),
):
    pid: Optional[int] = None
    proc_ref = None

    with _pipeline_lock:
        proc_ref = _pipeline_state.get("process")
        if proc_ref is not None and _pipeline_state["running"]:
            pid = proc_ref.pid

    if pid is None:
        disk_state = _load_runtime_state()
        if disk_state.get("running") and disk_state.get("pid"):
            pid = int(disk_state["pid"])

    per_user_procs_snapshot: list = []
    with _active_per_user_procs_lock:
        per_user_procs_snapshot = list(_active_per_user_procs)

    if pid is None and not per_user_procs_snapshot:
        stale_disk = _load_runtime_state()
        if stale_disk.get("running"):
            finished_at = datetime.now(timezone.utc).isoformat()
            _save_runtime_state({
                **stale_disk,
                "running": False,
                "pid": None,
                "current_step": "已手动终止（残留状态已重置）",
                "finished_at": finished_at,
                "exit_code": -9,
            })
            with _pipeline_lock:
                _pipeline_state["running"] = False
                _pipeline_state["process"] = None
                _pipeline_state["current_step"] = "已手动终止（残留状态已重置）"
                _pipeline_state["exit_code"] = -9
            _release_current_execution_lease()
            return {"ok": True, "message": "已重置残留运行状态（进程已不存在）"}
        raise HTTPException(status_code=400, detail="当前没有正在运行的 Pipeline")

    def _kill_pid(p: int) -> bool:
        if sys.platform == "win32":
            try:
                r = subprocess.call(
                    ["taskkill", "/F", "/T", "/PID", str(p)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return r == 0
            except Exception:
                return False
        else:
            import signal as _signal
            try:
                os.killpg(os.getpgid(p), _signal.SIGTERM)
                return True
            except Exception:
                return False

    killed = False
    if pid is not None:
        killed = _kill_pid(pid)

    for pu_proc in per_user_procs_snapshot:
        try:
            if pu_proc.poll() is None:
                if not _kill_pid(pu_proc.pid):
                    pu_proc.kill()
                killed = True
        except Exception:
            pass

    if not killed:
        if proc_ref is not None:
            try:
                proc_ref.kill()
                killed = True
            except Exception:
                pass

    try:
        disk_state = _load_runtime_state()
        if disk_state.get("running"):
            finished_at = datetime.now(timezone.utc).isoformat()
            _save_runtime_state({
                **disk_state,
                "running": False,
                "pid": None,
                "current_step": "已手动终止",
                "finished_at": finished_at,
                "exit_code": -9,
            })
    except OSError:
        pass

    with _pipeline_lock:
        _pipeline_state["running"] = False
        _pipeline_state["process"] = None
        _pipeline_state["current_step"] = "已手动终止"
        _pipeline_state["exit_code"] = -9

    _release_current_execution_lease()
    return {"ok": True, "message": "已发送终止信号（进程树已强制结束）"}


@router.get("/pipeline/data-tracking", summary="Get pipeline data tracking per step")
def api_admin_pipeline_data_tracking(
    user_id: int = Query(0, ge=0, description="User ID (0 = system/default)"),
    days: int = Query(30, ge=1, le=365, description="Number of most recent dates to return"),
    _admin=Depends(auth_service.require_admin_user),
):
    from services import pipeline_db_service
    records = pipeline_db_service.get_pipeline_data_tracking_range(user_id, days)
    return {"records": records}


@router.get("/schedule", summary="Get schedule config")
def api_admin_get_schedule(
    _admin=Depends(auth_service.require_admin_user),
):
    disk_cfg = _load_schedule_config()
    cfg = {**_scheduler_state, **disk_cfg}

    scheduler_alive = _scheduler_thread is not None and _scheduler_thread.is_alive()
    if cfg.get("enabled") and not scheduler_alive:
        print("[SCHEDULER] 检测到调度线程已停止，自动重启", flush=True)
        _start_scheduler()
        scheduler_alive = True

    return {
        "enabled": cfg.get("enabled", False),
        "hour": cfg.get("hour", 6),
        "minute": cfg.get("minute", 0),
        "pipeline": cfg.get("pipeline", "daily"),
        "sllm": cfg.get("sllm"),
        "zo": cfg.get("zo", "F"),
        "user_id": cfg.get("user_id"),
        "last_run_date": cfg.get("last_run_date"),
        "multi_user": cfg.get("multi_user", True),
        "max_concurrent_user_pipelines": cfg.get("max_concurrent_user_pipelines", 3),
        "scheduler_alive": scheduler_alive,
    }


@router.post("/schedule", summary="Update schedule config")
def api_admin_update_schedule(
    body: ScheduleConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    _scheduler_state["enabled"] = body.enabled
    _scheduler_state["hour"] = body.hour
    _scheduler_state["minute"] = body.minute
    _scheduler_state["pipeline"] = body.pipeline
    _scheduler_state["sllm"] = body.sllm
    _scheduler_state["zo"] = body.zo or "F"
    _scheduler_state["user_id"] = body.user_id
    _scheduler_state["multi_user"] = body.multi_user
    _scheduler_state["max_concurrent_user_pipelines"] = body.max_concurrent_user_pipelines

    disk_cfg = _load_schedule_config()
    _save_schedule_config({
        "enabled": body.enabled,
        "hour": body.hour,
        "minute": body.minute,
        "pipeline": body.pipeline,
        "sllm": body.sllm,
        "zo": body.zo or "F",
        "user_id": body.user_id,
        "last_run_date": disk_cfg.get("last_run_date") or _scheduler_state.get("last_run_date"),
        "multi_user": body.multi_user,
        "max_concurrent_user_pipelines": body.max_concurrent_user_pipelines,
    })

    if body.enabled:
        _start_scheduler()

    return {"ok": True, "schedule": {
        "enabled": body.enabled,
        "hour": body.hour,
        "minute": body.minute,
        "pipeline": body.pipeline,
        "sllm": body.sllm,
        "zo": body.zo or "F",
        "user_id": body.user_id,
        "multi_user": body.multi_user,
        "max_concurrent_user_pipelines": body.max_concurrent_user_pipelines,
    }}


@router.get("/schedule/history", summary="Get schedule execution history")
def api_admin_schedule_history(
    limit: int = 50,
    _admin=Depends(auth_service.require_admin_user),
):
    records = _load_schedule_history(limit=min(limit, 200))
    return {"records": records, "total": len(records)}


# ===========================================================================
# Observability API – runs / steps / events / artifacts
# ===========================================================================

@router.get("/pipeline/runs", summary="List recent pipeline runs")
def api_pipeline_runs(
    limit: int = Query(default=20, ge=1, le=100),
    date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user_id: Optional[int] = Query(default=None),
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        from services import pipeline_db_service as _pdb
        runs = _pdb.get_runs_recent_with_summary(limit=limit, date_str=date, user_id=user_id)
        return {"runs": redact_sensitive_data(runs), "total": len(runs)}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_admin_pipeline_failure_detail(exc, "pipeline_runs_list"),
        )


@router.get("/pipeline/runs/{run_id}", summary="Get pipeline run detail with steps")
def api_pipeline_run_detail(
    run_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        from services import pipeline_db_service as _pdb
        run = _pdb.get_run_summary(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return redact_sensitive_data(run)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_admin_pipeline_failure_detail(exc, "pipeline_run_detail"),
        )


@router.get("/pipeline/runs/{run_id}/steps", summary="Get step timeline for a run")
def api_pipeline_run_steps(
    run_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        from services import pipeline_db_service as _pdb
        run = _pdb.get_run_summary(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        steps = _pdb.get_step_runs_for_run(run_id)
        return {
            "run_id": run_id,
            "steps": redact_sensitive_data(steps),
            "total": len(steps),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_admin_pipeline_failure_detail(exc, "pipeline_run_steps"),
        )


@router.get("/pipeline/runs/{run_id}/events", summary="Get structured events for a run")
def api_pipeline_run_events(
    run_id: int,
    step_run_id: Optional[int] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        from services import pipeline_db_service as _pdb
        run = _pdb.get_run_summary(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        events = _pdb.get_events_for_run(run_id, step_run_id=step_run_id, limit=limit)
        return {
            "run_id": run_id,
            "events": redact_sensitive_data(events),
            "total": len(events),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_admin_pipeline_failure_detail(exc, "pipeline_run_events"),
        )


@router.get("/pipeline/runs/{run_id}/artifacts", summary="Get artifacts for a run")
def api_pipeline_run_artifacts(
    run_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    try:
        from services import pipeline_db_service as _pdb
        run = _pdb.get_run_summary(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        artifacts = _pdb.get_artifacts_for_run(run_id)
        return {
            "run_id": run_id,
            "artifacts": redact_sensitive_data(artifacts),
            "total": len(artifacts),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_admin_pipeline_failure_detail(exc, "pipeline_run_artifacts"),
        )


@router.get("/pipeline/runs/{run_id}/log", summary="Get log content for a pipeline run")
def api_pipeline_run_log(
    run_id: int,
    tail: int = Query(default=300, ge=1, le=5000),
    full: bool = Query(default=False),
    _admin=Depends(auth_service.require_admin_user),
):
    """Read the stdout/stderr log for a pipeline run. Only logs inside _ADMIN_LOG_DIR are served."""
    try:
        from services import pipeline_db_service as _pdb
        run = _pdb.get_run_summary(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        log_file = (run.get("log_file") or "").strip()
        if not log_file:
            return {"run_id": run_id, "has_file": False, "lines": [], "total_lines": 0, "log_file": ""}
        # Security: ensure path is strictly inside the admin log directory
        log_norm = os.path.normpath(os.path.abspath(log_file))
        dir_norm = os.path.normpath(os.path.abspath(_ADMIN_LOG_DIR))
        if not (log_norm.startswith(dir_norm + os.sep) or log_norm == dir_norm):
            raise HTTPException(status_code=403, detail="日志路径不在允许范围内")
        if not os.path.isfile(log_file):
            return {
                "run_id": run_id, "has_file": False, "lines": [], "total_lines": 0,
                "log_file": os.path.basename(log_file),
            }
        n_lines = 999999 if full else tail
        lines = _get_log_tail(log_file, n=n_lines)
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as _lf:
                total = sum(1 for _ in _lf)
        except OSError:
            total = len(lines)
        return {
            "run_id": run_id,
            "has_file": True,
            "lines": lines,
            "total_lines": total,
            "log_file": os.path.basename(log_file),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_admin_pipeline_failure_detail(exc, "pipeline_run_log"),
        )


@router.post("/pipeline/rerun", summary="Rerun a pipeline from a specific step")
def api_pipeline_rerun(
    body: RerunPipelineBody,
    admin=Depends(auth_service.require_admin_user),
):
    """
    Restart a previously recorded run from a specific step (from_step) or
    run only a single step (only_step), without re-running the entire pipeline.
    """
    lease_token: Optional[str] = None
    thread_started = False
    new_run_id = 0
    runtime_registered = False
    started_at = ""
    rerun_params: dict = {}
    log_file = ""
    try:
        from services import pipeline_db_service as _pdb

        parent_run = _pdb.get_run_summary(body.run_id)
        if not parent_run:
            raise HTTPException(status_code=404, detail=f"Run {body.run_id} not found")

        pipeline = parent_run.get("pipeline", "default")
        date_str = parent_run.get("date_str", datetime.now().date().isoformat())
        user_id = parent_run.get("user_id", 0)
        phase = parent_run.get("phase", "")
        config = parent_run.get("config") or {}
        sllm = config.get("sllm")
        zo = config.get("zo", "F") or "F"
        output_mode = "db"  # rerun always uses DB mode

        with _pipeline_lock:
            if _pipeline_state.get("running"):
                raise HTTPException(status_code=409, detail="Pipeline is already running")

        lease = _try_acquire_execution_lease(pipeline, date_str, "manual_rerun")
        if lease is None:
            raise HTTPException(status_code=409, detail="Pipeline is already running")
        lease_token = lease["token"]

        new_run_id = _create_db_run(
            pipeline=pipeline,
            date_str=date_str,
            user_id=user_id,
            phase=phase,
            trigger="manual_rerun",
            parent_run_id=body.run_id,
            requested_by=admin.get("id") if isinstance(admin, dict) else getattr(admin, "id", None),
            config={"sllm": sllm, "zo": zo, "force": body.force,
                    "from_step": body.from_step, "only_step": body.only_step},
        )
        if not new_run_id:
            raise RuntimeError("pipeline rerun record could not be created")

        cmd = [sys.executable, "-u", _APP_PY_PATH, pipeline,
               "--date", date_str, "--Zo", zo,
               "--output-mode", output_mode,
               "--phase", phase,
               "--trigger", "manual_rerun",
               "--run-id", str(new_run_id)]
        if user_id:
            cmd.extend(["--user-id", str(user_id)])
        if sllm is not None:
            cmd.extend(["--SLLM", str(sllm)])
        if body.force:
            cmd.append("--force")
        if body.from_step:
            cmd.extend(["--from-step", body.from_step])
        if body.only_step:
            cmd.extend(["--only-step", body.only_step])

        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(_ADMIN_LOG_DIR, f"{run_ts}_rerun{new_run_id}.log")
        os.makedirs(_ADMIN_LOG_DIR, exist_ok=True)
        try:
            from services import pipeline_db_service as _pdb
            _pdb.update_run_log_file(new_run_id, log_file)
        except Exception:
            pass

        env = {**os.environ, "RUN_DATE": date_str, "PYTHONIOENCODING": "utf-8",
               "PIPELINE_OUTPUT_MODE": output_mode}
        if sllm is not None:
            env["SLLM"] = str(sllm)
        if user_id:
            env["PIPELINE_USER_ID"] = str(user_id)

        def _do_rerun():
            exit_code = -1
            try:
                exit_code = _run_pipeline_subprocess(cmd, env, log_file)
            except Exception as exc:
                print(
                    redact_sensitive_text(f"[RERUN] error: {exc!r}"),
                    flush=True,
                )
            finally:
                try:
                    _pdb.update_run_status(
                        new_run_id,
                        "completed" if exit_code == 0 else "failed",
                    )
                except Exception:
                    pass
                finished_at = datetime.now(timezone.utc).isoformat()
                final_step = "重跑已完成" if exit_code == 0 else f"重跑异常退出 (code={exit_code})"
                with _pipeline_lock:
                    _pipeline_state["running"] = False
                    _pipeline_state["process"] = None
                    _pipeline_state["current_step"] = final_step
                    _pipeline_state["finished_at"] = finished_at
                    _pipeline_state["exit_code"] = exit_code
                try:
                    _save_runtime_state({
                        "running": False,
                        "pid": None,
                        "current_step": final_step,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "exit_code": exit_code,
                        "params": {
                            "pipeline": pipeline,
                            "date": date_str,
                            "user_id": user_id,
                            "rerun_of": body.run_id,
                        },
                        "run_id": f"rerun_{new_run_id}",
                        "log_file": log_file,
                    })
                except OSError:
                    pass
                _release_execution_lease(lease_token)

        started_at = datetime.now(timezone.utc).isoformat()
        rerun_params = {
            "pipeline": pipeline,
            "date": date_str,
            "user_id": user_id,
            "rerun_of": body.run_id,
        }
        with _pipeline_lock:
            _pipeline_state["running"] = True
            _pipeline_state["current_step"] = f"重跑 run_id={body.run_id}"
            _pipeline_state["logs"] = [f"[{datetime.now().strftime('%H:%M:%S')}] 重跑 run_id={body.run_id}"]
            _pipeline_state["started_at"] = started_at
            _pipeline_state["finished_at"] = None
            _pipeline_state["exit_code"] = None
            _pipeline_state["params"] = rerun_params
            _pipeline_state["run_id"] = f"rerun_{new_run_id}"
            _pipeline_state["log_file"] = log_file
            runtime_registered = True

        _save_runtime_state({
            "running": True,
            "pid": None,
            "current_step": f"重跑 run_id={body.run_id}",
            "started_at": started_at,
            "finished_at": None,
            "exit_code": None,
            "params": rerun_params,
            "run_id": f"rerun_{new_run_id}",
            "log_file": log_file,
        })

        t = threading.Thread(target=_do_rerun, daemon=True)
        t.start()
        thread_started = True

        return {
            "ok": True,
            "message": f"Rerun started (new run_id={new_run_id})",
            "new_run_id": new_run_id,
            "log_file": log_file,
        }
    except HTTPException as exc:
        if runtime_registered and not thread_started:
            _rollback_rerun_launch(
                new_run_id,
                started_at,
                rerun_params,
                log_file,
                str(exc.detail),
            )
        if lease_token and not thread_started:
            _release_execution_lease(lease_token)
        raise
    except Exception as exc:
        public_error = _admin_pipeline_failure_detail(exc, "pipeline_rerun_start")
        if runtime_registered and not thread_started:
            _rollback_rerun_launch(
                new_run_id,
                started_at,
                rerun_params,
                log_file,
                public_error,
            )
        elif new_run_id and not thread_started:
            try:
                from services import pipeline_db_service as _pdb
                _pdb.update_run_status(new_run_id, "failed", error=public_error)
            except Exception as rollback_exc:
                logger.error(
                    "rerun_launch_db_rollback_failed run_id=%s error=%s",
                    new_run_id,
                    redact_sensitive_text(rollback_exc),
                )
        if lease_token and not thread_started:
            _release_execution_lease(lease_token)
        raise HTTPException(status_code=500, detail=public_error)


# ---------------------------------------------------------------------------
# Pipeline Step Configuration
# ---------------------------------------------------------------------------

@router.get("/pipeline/step-config", summary="Get pipeline step definitions and current config")
def api_get_pipeline_step_config(_admin=Depends(auth_service.require_admin_user)):
    """Return all step definitions plus the current enabled/disabled state."""
    try:
        from services.pipeline_step_config_service import get_step_definitions, get_step_config
        definitions = get_step_definitions()
        config = get_step_config()
        return {"ok": True, "definitions": definitions, "config": config}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_admin_pipeline_failure_detail(exc, "pipeline_step_config_get"),
        )


@router.post("/pipeline/step-config/validate", summary="Validate a proposed step config")
def api_validate_pipeline_step_config(
    body: StepConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """Check whether the proposed config has dependency violations."""
    try:
        from services.pipeline_step_config_service import validate_step_config
        errors = validate_step_config(body.config)
        return {"ok": True, "valid": len(errors) == 0, "errors": errors}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_admin_pipeline_failure_detail(exc, "pipeline_step_config_validate"),
        )


@router.post("/pipeline/step-config", summary="Save pipeline step config")
def api_save_pipeline_step_config(
    body: StepConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """Validate and persist the step enable/disable configuration."""
    try:
        from services.pipeline_step_config_service import save_step_config
        errors = save_step_config(body.config)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        return {"ok": True, "message": "步骤配置已保存"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_admin_pipeline_failure_detail(exc, "pipeline_step_config_save"),
        )


@router.post("/pipeline/step-config/reset", summary="Reset step config to defaults")
def api_reset_pipeline_step_config(_admin=Depends(auth_service.require_admin_user)):
    """Delete the saved config file, reverting all steps to their default state."""
    try:
        from services.pipeline_step_config_service import reset_step_config
        reset_step_config()
        return {"ok": True, "message": "步骤配置已恢复默认"}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_admin_pipeline_failure_detail(exc, "pipeline_step_config_reset"),
        )
