"""
Pipeline & Scheduler Router.

All routes are prefixed with /api/admin and registered in api.py via
    app.include_router(pipeline_router)

Owns all pipeline global state (threads, locks, runtime JSON) so the
scheduler never pollutes the composition root.
"""

import json
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

router = APIRouter(prefix="/api/admin", tags=["pipeline"])

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


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

_SEVER_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_APP_PY_PATH = os.path.join(_SEVER_DIR, "app.py")
_SCHEDULE_CONFIG_PATH = os.path.join(_SEVER_DIR, "database", "schedule_config.json")
_SCHEDULER_LOCK_PATH = os.path.join(_SEVER_DIR, "database", "scheduler.lock")
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
_SCHEDULER_MAX_RETRIES = 3
_SCHEDULER_RETRY_WINDOW_SECONDS = 1800


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
    with open(_SCHEDULE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


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


def _get_log_tail(log_file: str, n: int = 300) -> list:
    if not log_file or not os.path.isfile(log_file):
        return []
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [ln.rstrip("\n") for ln in lines[-n:]]
    except OSError:
        return []


# ---------------------------------------------------------------------------
# Pipeline thread functions
# ---------------------------------------------------------------------------

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
):
    global _pipeline_state
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
            line = line.rstrip("\n")
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
        err_line = f"[{datetime.now().strftime('%H:%M:%S')}] [ERROR] {exc}"
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
            "trigger": "manual",
            "date_str": date_str,
            "started_at": started_at,
            "finished_at": finished_at,
            "user_count": 1,
            "user_ids": [user_id] if user_id is not None else [0],
            "exit_code": exit_code,
            "success": exit_code == 0,
            "pipeline": pipeline,
        })


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
        )
        with _active_per_user_procs_lock:
            _active_per_user_procs.append(proc)
        for line in proc.stdout:
            line = line.rstrip("\n")
            log_fh.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")
        proc.wait()
        exit_code = proc.returncode
    except Exception as exc:
        exit_code = -1
        if log_fh:
            try:
                log_fh.write(f"[ERROR] {exc}\n")
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


def _run_multiuser_scheduler_thread(cfg: dict, today: str) -> None:
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
        "pid": os.getpid(),
    })

    exit_code = 0
    user_ids_to_run: list = []
    trigger = cfg.get("trigger", "scheduled")
    try:
        _orch_log(f"[SCHEDULER] 开始共享阶段 (shared) for {today}")
        with _pipeline_lock:
            _pipeline_state["current_step"] = "共享阶段运行中..."
        _save_runtime_state({
            "running": True, "current_step": "共享阶段运行中...",
            "started_at": started_at, "finished_at": None, "exit_code": None,
            "params": params, "run_id": run_id, "log_file": orch_log_file,
        })

        shared_log = os.path.join(_ADMIN_LOG_DIR, f"{run_id}_shared.log")
        shared_cmd = [sys.executable, "-u", _APP_PY_PATH, "shared", "--date", today, "--Zo", zo]
        if sllm is not None:
            shared_cmd.extend(["--SLLM", str(sllm)])
        if force:
            shared_cmd.append("--force")
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

        if shared_exit != 0:
            _orch_log(f"[SCHEDULER] 共享阶段失败 (exit={shared_exit})，终止多用户编排")
            exit_code = shared_exit
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
            per_user_cmd = [
                sys.executable, "-u", _APP_PY_PATH, "per_user",
                "--date", today, "--Zo", zo,
                "--user-id", str(uid),
                "--output-mode", "db",
            ]
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

    except Exception as exc:
        _orch_log(f"[SCHEDULER] 编排异常: {exc!r}")
        exit_code = -1

    finally:
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
                        "已释放 lock 文件，将在重试窗口内重新尝试",
                        flush=True,
                    )
                except OSError:
                    pass


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


def _scheduler_loop():
    while not _scheduler_stop_event.is_set():
        try:
            now = datetime.now()
            disk_cfg = _load_schedule_config()
            cfg = {**_scheduler_state, **disk_cfg}
            today = now.date().isoformat()

            cfg_hour = cfg.get("hour", 6)
            cfg_minute = cfg.get("minute", 0)
            scheduled_today = now.replace(
                hour=cfg_hour, minute=cfg_minute, second=0, microsecond=0
            )
            elapsed_since_scheduled = (now - scheduled_today).total_seconds()
            within_retry_window = 0 <= elapsed_since_scheduled <= _SCHEDULER_RETRY_WINDOW_SECONDS

            for _d in list(_scheduler_retry_counts.keys()):
                if _d != today:
                    del _scheduler_retry_counts[_d]

            retry_count_today = _scheduler_retry_counts.get(today, 0)

            if (
                cfg.get("enabled")
                and within_retry_window
                and cfg.get("last_run_date") != today
                and retry_count_today < _SCHEDULER_MAX_RETRIES
            ):
                lock_path = f"{_SCHEDULER_LOCK_PATH}.{today}"
                os.makedirs(os.path.dirname(_SCHEDULER_LOCK_PATH), exist_ok=True)
                try:
                    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.close(fd)
                except FileExistsError:
                    _scheduler_stop_event.wait(30)
                    continue

                _maybe_clear_stale_runtime_state()

                disk_rt = _load_runtime_state()
                if not disk_rt.get("running") and not _pipeline_state["running"]:
                    use_multi_user = cfg.get("multi_user", True)
                    if use_multi_user:
                        t = threading.Thread(
                            target=_run_multiuser_scheduler_thread,
                            args=(cfg, today),
                            daemon=True,
                        )
                    else:
                        t = threading.Thread(
                            target=_run_pipeline_thread,
                            args=(cfg.get("pipeline", "daily"), today, cfg.get("sllm"), cfg.get("zo", "F")),
                            kwargs={"user_id": cfg.get("user_id")},
                            daemon=True,
                        )
                    t.start()

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

    if body.multi_user:
        cfg = {
            "sllm": body.sllm,
            "zo": body.zo or "F",
            "max_concurrent_user_pipelines": body.max_concurrent_user_pipelines,
            "trigger": "manual",
            "force": body.force,
        }
        t = threading.Thread(
            target=_run_multiuser_scheduler_thread,
            args=(cfg, date_str),
            daemon=True,
        )
        t.start()
        return {"ok": True, "message": f"多用户 Pipeline 已启动{force_hint}，日期: {date_str}（shared + per_user × 所有自定义用户）"}
    else:
        pipeline_user_id = body.user_id if body.user_id is not None else _admin.get("id")
        t = threading.Thread(
            target=_run_pipeline_thread,
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
        t.start()
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
        return {
            "running": disk_state.get("running", False),
            "current_step": disk_state.get("current_step"),
            "logs": logs,
            "started_at": disk_state.get("started_at"),
            "finished_at": disk_state.get("finished_at"),
            "exit_code": disk_state.get("exit_code"),
            "params": disk_state.get("params", {}),
            "run_id": disk_state.get("run_id"),
        }
    with _pipeline_lock:
        return {
            "running": _pipeline_state["running"],
            "current_step": _pipeline_state["current_step"],
            "logs": list(_pipeline_state["logs"]),
            "started_at": _pipeline_state["started_at"],
            "finished_at": _pipeline_state["finished_at"],
            "exit_code": _pipeline_state["exit_code"],
            "params": _pipeline_state["params"],
        }


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
