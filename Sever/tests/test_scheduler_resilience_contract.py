from __future__ import annotations

import logging
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

import app  # noqa: E402
from Controller import arxiv_search04  # noqa: E402
from services.pipeline_schedule_policy import (  # noqa: E402
    count_scheduled_attempts,
    failure_cooldown_remaining,
    rate_limit_cooldown_remaining,
    scheduled_attempt_is_due,
)


MAX_RETRIES = 8


class ArxivStartupResilienceTests(unittest.TestCase):
    def test_file_logging_permission_error_falls_back_to_stdout(self) -> None:
        with (
            patch.object(arxiv_search04.os, "makedirs"),
            patch.object(
                arxiv_search04.logging,
                "FileHandler",
                side_effect=PermissionError(13, "denied"),
            ),
        ):
            logger = arxiv_search04.setup_logging()

        self.assertTrue(
            any(
                isinstance(handler, logging.StreamHandler)
                for handler in logger.handlers
            )
        )
        self.assertFalse(
            any(
                isinstance(handler, logging.FileHandler)
                for handler in logger.handlers
            )
        )

    def test_pipeline_cli_preserves_child_exit_code(self) -> None:
        error = subprocess.CalledProcessError(2, ["arxiv_search"])
        with patch.object(app, "main", side_effect=error):
            with self.assertRaises(SystemExit) as caught:
                app.cli()
        self.assertEqual(caught.exception.code, 2)


class SchedulerCatchUpTests(unittest.TestCase):
    def test_same_day_late_start_is_due(self) -> None:
        cfg = {
            "enabled": True,
            "hour": 6,
            "minute": 0,
            "last_run_date": "2026-08-05",
        }
        self.assertTrue(
            scheduled_attempt_is_due(
                datetime(2026, 8, 6, 20, 0), cfg, 0, max_retries=MAX_RETRIES
            )
        )
        self.assertFalse(
            scheduled_attempt_is_due(
                datetime(2026, 8, 6, 5, 59), cfg, 0, max_retries=MAX_RETRIES
            )
        )

    def test_success_or_retry_cap_suppresses_catch_up(self) -> None:
        now = datetime(2026, 8, 6, 20, 0)
        completed = {
            "enabled": True,
            "hour": 6,
            "minute": 0,
            "last_run_date": "2026-08-06",
        }
        pending = {**completed, "last_run_date": "2026-08-05"}
        self.assertFalse(
            scheduled_attempt_is_due(
                now, completed, 0, max_retries=MAX_RETRIES
            )
        )
        self.assertFalse(
            scheduled_attempt_is_due(
                now, pending, MAX_RETRIES, max_retries=MAX_RETRIES
            )
        )

    def test_retry_count_recovers_from_persistent_history(self) -> None:
        history = [
            {"date_str": "2026-08-06", "trigger": "scheduled"},
            {"date_str": "2026-08-06", "trigger": "scheduled"},
            {"date_str": "2026-08-06", "trigger": "manual"},
            {"date_str": "2026-08-05", "trigger": "scheduled"},
        ]
        self.assertEqual(count_scheduled_attempts(history, "2026-08-06"), 2)

    def test_rate_limit_cooldown_recovers_after_process_restart(self) -> None:
        history = [
            {
                "date_str": "2026-08-06",
                "trigger": "scheduled",
                "exit_code": 2,
                "finished_at": "2026-08-06T02:00:00+00:00",
            }
        ]
        remaining = rate_limit_cooldown_remaining(
            history,
            "2026-08-06",
            datetime(2026, 8, 6, 2, 5, tzinfo=timezone.utc),
            cooldown_seconds=900,
        )
        self.assertEqual(remaining, 600.0)
        self.assertEqual(
            rate_limit_cooldown_remaining(
                history,
                "2026-08-06",
                datetime(2026, 8, 6, 2, 20, tzinfo=timezone.utc),
                cooldown_seconds=900,
            ),
            0.0,
        )

    def test_repeated_rate_limits_back_off_exponentially_but_remain_due(self) -> None:
        history = [
            {
                "date_str": "2026-08-06",
                "trigger": "scheduled",
                "exit_code": 2,
                "finished_at": timestamp,
            }
            for timestamp in (
                "2026-08-06T02:00:00+00:00",
                "2026-08-06T02:45:00+00:00",
                "2026-08-06T04:00:00+00:00",
            )
        ]
        self.assertEqual(
            rate_limit_cooldown_remaining(
                history,
                "2026-08-06",
                datetime(2026, 8, 6, 5, 0, tzinfo=timezone.utc),
                cooldown_seconds=1800,
                max_cooldown_seconds=14400,
            ),
            3600.0,
        )
        cfg = {
            "enabled": True,
            "hour": 6,
            "minute": 0,
            "last_run_date": "2026-08-05",
        }
        self.assertTrue(
            scheduled_attempt_is_due(
                datetime(2026, 8, 6, 20, 0),
                cfg,
                len(history),
                max_retries=MAX_RETRIES,
            )
        )

    def test_generic_failures_use_persisted_exponential_cooldown(self) -> None:
        history = [
            {
                "date_str": "2026-08-06",
                "trigger": "scheduled",
                "exit_code": 1,
                "finished_at": timestamp,
            }
            for timestamp in (
                "2026-08-06T02:00:00+00:00",
                "2026-08-06T02:10:00+00:00",
                "2026-08-06T02:30:00+00:00",
            )
        ]

        self.assertEqual(
            failure_cooldown_remaining(
                reversed(history),
                "2026-08-06",
                datetime(2026, 8, 6, 2, 35, tzinfo=timezone.utc),
                cooldown_seconds=300,
                max_cooldown_seconds=7200,
            ),
            900.0,
        )
        self.assertEqual(
            failure_cooldown_remaining(
                history,
                "2026-08-06",
                datetime(2026, 8, 6, 2, 51, tzinfo=timezone.utc),
                cooldown_seconds=300,
                max_cooldown_seconds=7200,
            ),
            0.0,
        )

    def test_success_resets_generic_failure_cooldown(self) -> None:
        history = [
            {
                "date_str": "2026-08-06",
                "trigger": "scheduled",
                "exit_code": 1,
                "finished_at": "2026-08-06T02:00:00+00:00",
            },
            {
                "date_str": "2026-08-06",
                "trigger": "scheduled",
                "exit_code": 0,
                "finished_at": "2026-08-06T02:10:00+00:00",
            },
        ]

        self.assertEqual(
            failure_cooldown_remaining(
                history,
                "2026-08-06",
                datetime(2026, 8, 6, 2, 11, tzinfo=timezone.utc),
                cooldown_seconds=300,
                max_cooldown_seconds=7200,
            ),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
