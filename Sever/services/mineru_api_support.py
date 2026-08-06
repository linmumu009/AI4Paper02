"""Shared MinerU API retry and resumable batch-state helpers."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Optional


def parse_retry_after(value: Optional[str], *, now: Optional[datetime] = None) -> Optional[float]:
    """Parse Retry-After seconds or an HTTP date into a non-negative delay."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except (TypeError, ValueError):
        pass
    try:
        retry_at = parsedate_to_datetime(text)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - current).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def compute_retry_delay(
    retry_after: Optional[str],
    attempt: int,
    *,
    base_seconds: float = 15.0,
    cap_seconds: float = 300.0,
) -> float:
    """Prefer Retry-After, otherwise use capped exponential backoff."""
    parsed = parse_retry_after(retry_after)
    if parsed is not None:
        return min(cap_seconds, parsed)
    exponent = max(0, int(attempt) - 1)
    return min(cap_seconds, base_seconds * (2 ** exponent))


def request_json_with_rate_limit_retry(
    session: Any,
    method: str,
    url: str,
    *,
    payload: Optional[dict] = None,
    timeout: tuple[int, int] = (20, 120),
    max_attempts: int = 6,
    sleep_fn: Callable[[float], None] = time.sleep,
    on_retry: Optional[Callable[[int, int, float], None]] = None,
) -> dict:
    """Issue a JSON request and retry HTTP 429 responses safely."""
    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        kwargs: dict[str, Any] = {"timeout": timeout}
        if payload is not None:
            kwargs["json"] = payload
        response = session.request(method.upper(), url, **kwargs)
        if response.status_code == 429 and attempt < attempts:
            delay = compute_retry_delay(response.headers.get("Retry-After"), attempt)
            if on_retry:
                on_retry(attempt, attempts, delay)
            sleep_fn(delay)
            continue
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"MinerU API error: {data}")
        return data
    raise RuntimeError("unreachable")


def load_batch_journal(path: Path, date_str: str) -> dict:
    """Load a batch journal, returning a clean default if it is absent/corrupt."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        data = {}
    if not isinstance(data, dict) or data.get("date") != date_str:
        data = {"version": 1, "date": date_str, "batches": []}
    if not isinstance(data.get("batches"), list):
        data["batches"] = []
    return data


def save_batch_journal(path: Path, journal: dict) -> None:
    """Atomically persist a journal so a killed process can resume by batch_id."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def find_resumable_batch(journal: dict, file_ids: list[str]) -> Optional[dict]:
    """Find the newest unfinished batch containing every currently missing file."""
    wanted = set(file_ids)
    if not wanted:
        return None
    batches = journal.get("batches") if isinstance(journal, dict) else []
    if not isinstance(batches, list):
        return None
    for record in reversed(batches):
        if not isinstance(record, dict) or not record.get("batch_id"):
            continue
        if record.get("status") in {"completed", "fallback"}:
            continue
        recorded = set(str(item) for item in (record.get("file_ids") or []))
        if wanted.issubset(recorded):
            return record
    return None


def update_batch_journal(
    journal: dict,
    path: Path,
    *,
    batch_id: str,
    file_ids: list[str],
    status: str,
    written_ids: Optional[list[str]] = None,
) -> dict:
    """Insert/update one batch record and persist it immediately."""
    batches = journal.setdefault("batches", [])
    record = next(
        (item for item in batches if isinstance(item, dict) and item.get("batch_id") == batch_id),
        None,
    )
    if record is None:
        record = {"batch_id": batch_id}
        batches.append(record)
    record.update(
        {
            "file_ids": list(file_ids),
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    if written_ids is not None:
        record["written_ids"] = list(written_ids)
    save_batch_journal(path, journal)
    return record
