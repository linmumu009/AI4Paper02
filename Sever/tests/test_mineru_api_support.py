import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


SERVER_ROOT = os.path.dirname(os.path.dirname(__file__))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from services.mineru_api_support import (  # noqa: E402
    find_resumable_batch,
    load_batch_journal,
    parse_retry_after,
    request_json_with_rate_limit_retry,
    update_batch_journal,
)
import app as pipeline_app  # noqa: E402


class _Response:
    def __init__(self, status_code, *, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {"code": 0, "data": {}}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


class MinerUApiSupportTests(unittest.TestCase):
    def test_from_step_without_run_id_does_not_crash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = str(Path(temp_dir) / "missing.json")
            with (
                mock.patch.object(pipeline_app, "PIPELINES", {"test": ["dependency", "target"]}),
                mock.patch.object(pipeline_app, "STEP_OUTPUT_PATHS", {"dependency": lambda _date: missing_path}),
                mock.patch.object(pipeline_app, "run_step", return_value=0) as run_step,
                mock.patch.object(
                    sys,
                    "argv",
                    ["app.py", "test", "--date", "2026-08-05", "--from-step", "target"],
                ),
            ):
                pipeline_app.main()
        run_step.assert_called_once()

    def test_zero_output_mineru_failures_abort_pipeline(self):
        self.assertNotIn("pdfsplite_to_minerU", pipeline_app.SOFT_FAIL_STEPS)
        self.assertNotIn("selectedpaper_to_mineru", pipeline_app.SOFT_FAIL_STEPS)

    def test_parse_retry_after_seconds_and_http_date(self):
        self.assertEqual(parse_retry_after("12"), 12.0)
        now = datetime(2026, 8, 5, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(
            parse_retry_after("Wed, 05 Aug 2026 00:01:00 GMT", now=now),
            60.0,
        )
        self.assertIsNone(parse_retry_after("invalid"))

    def test_request_retries_429_then_returns_json(self):
        session = _Session(
            [
                _Response(429, headers={"Retry-After": "2"}),
                _Response(200, payload={"code": 0, "data": {"batch_id": "b1"}}),
            ]
        )
        sleeps = []
        result = request_json_with_rate_limit_retry(
            session,
            "POST",
            "https://mineru.test/batch",
            payload={"files": []},
            sleep_fn=sleeps.append,
        )
        self.assertEqual(result["data"]["batch_id"], "b1")
        self.assertEqual(session.calls, 2)
        self.assertEqual(sleeps, [2.0])

    def test_batch_journal_is_atomic_and_resumable_for_subset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "_batch_state.json"
            journal = load_batch_journal(path, "2026-08-05")
            update_batch_journal(
                journal,
                path,
                batch_id="batch-1",
                file_ids=["a", "b", "c"],
                status="uploaded",
            )
            loaded = json.loads(path.read_text(encoding="utf-8"))
            record = find_resumable_batch(loaded, ["b", "c"])
            self.assertEqual(record["batch_id"], "batch-1")

            update_batch_journal(
                loaded,
                path,
                batch_id="batch-1",
                file_ids=["a", "b", "c"],
                status="completed",
                written_ids=["a", "b", "c"],
            )
            self.assertIsNone(find_resumable_batch(loaded, ["b"]))

    def test_local_fallback_batch_is_not_resumed(self):
        journal = {
            "batches": [
                {
                    "batch_id": "stale-batch",
                    "file_ids": ["2608.00001"],
                    "status": "fallback",
                }
            ]
        }

        self.assertIsNone(find_resumable_batch(journal, ["2608.00001"]))


if __name__ == "__main__":
    unittest.main()
