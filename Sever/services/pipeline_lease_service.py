"""Cross-process execution lease for the paper pipeline.

The API normally runs one worker, but deployment restarts, accidental extra
workers, and nearly simultaneous admin requests must not start overlapping
pipelines.  The lease is host-local by design: pipeline data and processes all
live on the same server.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional


DEFAULT_STALE_AFTER_SECONDS = 8 * 60 * 60


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, ValueError):
        return False


def read_lease(lock_path: str) -> dict:
    try:
        with open(lock_path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _lease_is_stale(
    lock_path: str,
    lease: dict,
    stale_after_seconds: int,
    pid_checker: Callable[[int], bool],
) -> bool:
    try:
        age_seconds = max(0.0, time.time() - os.path.getmtime(lock_path))
    except OSError:
        return True

    # A writer may have created the file but not finished its small JSON write.
    # Never reclaim a malformed lease immediately.
    if not lease:
        return age_seconds > 30

    try:
        pid = int(lease.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid <= 0 or not pid_checker(pid):
        return True
    return age_seconds > stale_after_seconds


def acquire_pipeline_lease(
    lock_path: str,
    *,
    pipeline: str,
    date_str: str,
    trigger: str,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    pid_checker: Optional[Callable[[int], bool]] = None,
) -> Optional[dict]:
    """Atomically acquire a host-local pipeline lease, or return ``None``.

    A dead owner's lease is reclaimed once.  The random token prevents an old
    worker's ``finally`` block from deleting a newer worker's lease.
    """
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    checker = pid_checker or _pid_is_alive

    for attempt in range(2):
        lease = {
            "token": uuid.uuid4().hex,
            "pid": os.getpid(),
            "pipeline": pipeline,
            "date_str": date_str,
            "trigger": trigger,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            existing = read_lease(lock_path)
            if attempt == 0 and _lease_is_stale(
                lock_path,
                existing,
                stale_after_seconds,
                checker,
            ):
                try:
                    os.unlink(lock_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    return None
                continue
            return None

        try:
            payload = json.dumps(lease, ensure_ascii=False).encode("utf-8")
            os.write(fd, payload)
            os.fsync(fd)
        except Exception:
            try:
                os.close(fd)
            finally:
                try:
                    os.unlink(lock_path)
                except OSError:
                    pass
            raise
        else:
            os.close(fd)
            return lease
    return None


def release_pipeline_lease(lock_path: str, token: Optional[str]) -> bool:
    """Release only the lease owned by ``token``."""
    if not token:
        return False
    current = read_lease(lock_path)
    if current.get("token") != token:
        return False
    try:
        os.unlink(lock_path)
        return True
    except FileNotFoundError:
        return False
