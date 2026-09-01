from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

import app  # noqa: E402
from Controller import arxiv_search04  # noqa: E402
from services.pipeline_schedule_policy import (  # noqa: E402
    count_scheduled_attempts,
    failure_cooldown_remaining,
    multi_user_notice_action,
    rate_limit_cooldown_remaining,
    scheduled_attempt_is_due,
    scheduled_failure_retry_metadata,
    source_empty_result_needs_retry,
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

    def test_source_not_ready_step_is_recorded_as_waiting_not_failed(self) -> None:
        recorder = Mock()
        with patch.object(
            app.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=app.ARXIV_EXIT_BATCH_NOT_READY),
        ):
            with self.assertRaises(app.ArxivBatchNotReadyError):
                app.run_step("arxiv_search", recorder=recorder)

        recorder.finish_step.assert_called_once_with(
            "arxiv_search",
            status="pending",
            exit_code=None,
            skip_reason="arXiv 当日批次尚未发布，等待自动重试",
            metrics={"retryable_exit_code": app.ARXIV_EXIT_BATCH_NOT_READY},
        )
        recorder.emit.assert_called_once()
        self.assertEqual(recorder.emit.call_args.kwargs["level"], "warning")

    def test_source_not_ready_run_is_recorded_as_waiting_not_failed(self) -> None:
        error = app.ArxivBatchNotReadyError(
            app.ARXIV_EXIT_BATCH_NOT_READY,
            ["arxiv_search"],
        )
        with (
            patch.dict(app.PIPELINES, {"wait_probe": ["arxiv_search"]}),
            patch.object(app, "step_output_exists", return_value=False),
            patch.object(app, "run_step", side_effect=error),
            patch.object(app.PipelineRecorder, "end_run") as end_run,
        ):
            with self.assertRaises(app.ArxivBatchNotReadyError):
                app.main([
                    "wait_probe",
                    "--date",
                    "2026-08-17",
                    "--run-id",
                    "42",
                ])

        self.assertEqual(end_run.call_args.args[:2], (42,))
        self.assertFalse(end_run.call_args.kwargs["success"])
        self.assertEqual(end_run.call_args.kwargs["status"], "pending")

    def test_pipeline_date_is_forwarded_to_arxiv_announcement_anchor(self) -> None:
        captured_args = []

        def fake_run_step(step, args, **_kwargs):
            self.assertEqual(step, "arxiv_search")
            captured_args.extend(args)
            return 0

        with (
            patch.dict(app.PIPELINES, {"date_probe": ["arxiv_search"]}),
            patch.object(app, "step_output_exists", return_value=False),
            patch.object(app, "run_step", side_effect=fake_run_step),
            patch.object(app, "detect_selected_count", return_value=1) as selected,
        ):
            app.main([
                "date_probe",
                "--date",
                "2026-08-17",
                "--only-step",
                "arxiv_search",
            ])

        self.assertIn("--anchor-date", captured_args)
        anchor_index = captured_args.index("--anchor-date")
        self.assertEqual(captured_args[anchor_index + 1], "2026-08-17")
        selected.assert_called_once_with("2026-08-17")

    def test_selected_count_is_read_from_requested_date_not_latest_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            md_dir = Path(tmp) / "data" / "arxivList" / "md"
            md_dir.mkdir(parents=True)
            (md_dir / "2026-08-17.md").write_text(
                "- Selected: **17**\n", encoding="utf-8"
            )
            (md_dir / "2026-08-18.md").write_text(
                "- Selected: **99**\n", encoding="utf-8"
            )
            with patch.object(app, "ROOT", tmp):
                selected = app.detect_selected_count("2026-08-17")

        self.assertEqual(selected, 17)


class SchedulerCatchUpTests(unittest.TestCase):
    def test_partial_user_failure_only_notifies_failed_users(self) -> None:
        self.assertEqual(
            multi_user_notice_action(
                1,
                schedule_outcome="failed",
                shared_stage_succeeded=True,
                per_user_stage_completed=True,
                has_failed_users=True,
            ),
            "user_failures",
        )

    def test_shared_failure_keeps_shared_notice(self) -> None:
        self.assertEqual(
            multi_user_notice_action(
                2,
                schedule_outcome="failed",
                shared_stage_succeeded=False,
                per_user_stage_completed=False,
                has_failed_users=False,
            ),
            "shared_failure",
        )

    def test_source_empty_retry_keeps_shared_notice_after_shared_step(self) -> None:
        self.assertEqual(
            multi_user_notice_action(
                4,
                schedule_outcome="source_empty_retry",
                shared_stage_succeeded=True,
                per_user_stage_completed=False,
                has_failed_users=False,
            ),
            "shared_failure",
        )

    def test_cleanup_failure_keeps_completed_user_results_visible(self) -> None:
        self.assertEqual(
            multi_user_notice_action(
                1,
                schedule_outcome="failed",
                shared_stage_succeeded=True,
                per_user_stage_completed=True,
                has_failed_users=False,
            ),
            "clear",
        )

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

    def test_weekday_daily_schedule_waits_for_arxiv_release_window(self) -> None:
        cfg = {
            "enabled": True,
            "hour": 6,
            "minute": 0,
            "pipeline": "daily",
            "last_run_date": "2026-08-05",
        }
        self.assertFalse(
            scheduled_attempt_is_due(
                datetime(2026, 8, 6, 9, 14), cfg, 0, max_retries=MAX_RETRIES
            )
        )
        self.assertTrue(
            scheduled_attempt_is_due(
                datetime(2026, 8, 6, 9, 15), cfg, 0, max_retries=MAX_RETRIES
            )
        )

    def test_later_admin_schedule_is_preserved_and_daily_weekends_are_skipped(self) -> None:
        later_cfg = {
            "enabled": True,
            "hour": 10,
            "minute": 5,
            "pipeline": "daily",
            "last_run_date": "2026-08-05",
        }
        self.assertFalse(
            scheduled_attempt_is_due(
                datetime(2026, 8, 6, 10, 4), later_cfg, 0, max_retries=MAX_RETRIES
            )
        )
        self.assertTrue(
            scheduled_attempt_is_due(
                datetime(2026, 8, 6, 10, 5), later_cfg, 0, max_retries=MAX_RETRIES
            )
        )

        weekend_cfg = {**later_cfg, "hour": 6, "minute": 0}
        self.assertFalse(
            scheduled_attempt_is_due(
                datetime(2026, 8, 8, 6, 0), weekend_cfg, 0, max_retries=MAX_RETRIES
            )
        )
        non_arxiv_weekend_cfg = {
            **weekend_cfg,
            "pipeline": "idea",
            "multi_user": False,
        }
        self.assertTrue(
            scheduled_attempt_is_due(
                datetime(2026, 8, 8, 6, 0),
                non_arxiv_weekend_cfg,
                0,
                max_retries=MAX_RETRIES,
            )
        )

    def test_legacy_empty_weekday_success_is_recovered_until_content_succeeds(self) -> None:
        cfg = {"pipeline": "daily", "multi_user": True}
        empty_success = {
            "date_str": "2026-08-06",
            "trigger": "scheduled",
            "exit_code": 0,
            "user_count": 0,
            "finished_at": "2026-08-05T22:00:03+00:00",
        }
        self.assertTrue(
            source_empty_result_needs_retry(
                [empty_success], "2026-08-06", cfg
            )
        )
        content_success = {
            **empty_success,
            "user_count": 4,
            "arxiv_count": 25,
            "finished_at": "2026-08-06T02:00:00+00:00",
        }
        self.assertFalse(
            source_empty_result_needs_retry(
                [content_success, empty_success], "2026-08-06", cfg
            )
        )
        self.assertFalse(
            source_empty_result_needs_retry(
                [{**empty_success, "date_str": "2026-08-08"}],
                "2026-08-08",
                cfg,
            )
        )

        retryable_empty = {
            **empty_success,
            "exit_code": 4,
            "finished_at": "2026-08-06T01:15:00+00:00",
        }
        self.assertTrue(
            source_empty_result_needs_retry(
                [retryable_empty], "2026-08-06", cfg
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

    def test_retry_metadata_exposes_next_attempt_and_exhaustion(self) -> None:
        records = [
            {
                "date_str": "2026-08-06",
                "trigger": "scheduled",
                "exit_code": 4,
                "finished_at": timestamp,
            }
            for timestamp in (
                "2026-08-06T02:00:00+00:00",
                "2026-08-06T02:10:00+00:00",
            )
        ]
        metadata = scheduled_failure_retry_metadata(
            records,
            "2026-08-06",
            datetime(2026, 8, 6, 2, 10, tzinfo=timezone.utc),
            cooldown_seconds=300,
            max_cooldown_seconds=7200,
            max_attempts=8,
        )

        self.assertEqual(metadata["attempt"], 2)
        self.assertEqual(metadata["retry_cooldown_seconds"], 600)
        self.assertEqual(metadata["next_retry_at"], "2026-08-06T02:20:00+00:00")
        self.assertFalse(metadata["retry_budget_exhausted"])

        exhausted = scheduled_failure_retry_metadata(
            records * 4,
            "2026-08-06",
            datetime(2026, 8, 6, 2, 10, tzinfo=timezone.utc),
            cooldown_seconds=300,
            max_cooldown_seconds=7200,
            max_attempts=8,
        )
        self.assertTrue(exhausted["retry_budget_exhausted"])
        self.assertIsNone(exhausted["next_retry_at"])

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
