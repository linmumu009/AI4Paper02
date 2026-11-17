from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import pipeline_backfill_service as policy  # noqa: E402
from services import pipeline_db_service as db, user_settings_service  # noqa: E402

# The production router starts a scheduler when imported. Tests must never
# start real workers or touch the developer's pipeline runtime state.
with patch("threading.Thread.start"):
    router = importlib.import_module("routers.pipeline_router")


class BackfillPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 10, 0)
        self.cfg = {"enabled": True, "multi_user": True, "pipeline": "daily", "last_run_date": "2026-11-13"}

    def row(self, day="2026-11-16", **updates):
        return {
            "date_str": day,
            "trigger": "scheduled",
            "started_at": "2026-11-16T07:54:00+00:00",
            "finished_at": "2026-11-16T07:54:51+00:00",
            "exit_code": 4,
            **updates,
        }

    def test_yesterdays_exhausted_budget_does_not_block_backfill(self):
        history = [self.row() for _ in range(8)]
        self.assertEqual(policy.next_backfill_date(self.now, self.cfg, history), "2026-11-16")

    def test_missing_day_with_no_attempts_is_detected_after_watermark(self):
        self.assertEqual(policy.next_backfill_date(self.now, self.cfg, []), "2026-11-16")

    def test_newer_success_watermark_does_not_hide_an_unattempted_gap(self):
        cfg = {**self.cfg, "last_run_date": "2026-11-17"}
        history = [self.row("2026-11-13", exit_code=0, arxiv_count=500)]
        self.assertEqual(policy.next_backfill_date(self.now, cfg, history), "2026-11-16")

    def test_completed_day_is_never_repeated(self):
        history = [self.row(exit_code=0, arxiv_count=321)]
        self.assertIsNone(policy.next_backfill_date(self.now, self.cfg, history))

    def test_manual_full_batch_success_closes_the_gap(self):
        history = [self.row(), self.row(trigger="manual", exit_code=0, arxiv_count=321)]
        self.assertIsNone(policy.next_backfill_date(self.now, self.cfg, history))

    def test_partial_success_and_zero_paper_success_are_not_complete(self):
        for extra in ({"arxiv_count": 321, "coverage_complete": False}, {"arxiv_count": 0}):
            with self.subTest(extra=extra):
                self.assertEqual(policy.next_backfill_date(self.now, self.cfg, [self.row(exit_code=0, **extra)]), "2026-11-16")

    def test_today_weekends_and_dates_outside_recent_window_are_excluded(self):
        cfg = {**self.cfg, "last_run_date": None}
        history = [self.row(day) for day in ("2026-11-10", "2026-11-14", "2026-11-15", "2026-11-17", "2026-11-18")]
        history += [self.row(day, exit_code=0, arxiv_count=1) for day in ("2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16")]
        self.assertIsNone(policy.next_backfill_date(self.now, cfg, history))

    def test_oldest_gap_is_selected_first(self):
        cfg = {**self.cfg, "last_run_date": "2026-11-10"}
        self.assertEqual(policy.next_backfill_date(self.now, cfg, []), "2026-11-11")

    def test_new_or_disabled_schedule_does_not_create_historical_work(self):
        for cfg in ({**self.cfg, "last_run_date": None}, {**self.cfg, "enabled": False}, {**self.cfg, "multi_user": False}):
            self.assertIsNone(policy.next_backfill_date(self.now, cfg, []))

    def test_persisted_backfill_cooldown_survives_restart(self):
        recent = self.row(trigger=policy.BACKFILL_TRIGGER, started_at="2026-11-17T01:00:00+00:00", finished_at="2026-11-17T01:10:00+00:00")
        self.assertIsNone(policy.next_backfill_date(self.now, self.cfg, [recent]))
        self.assertEqual(policy.next_backfill_date(datetime(2026, 11, 17, 11, 11), self.cfg, [recent]), "2026-11-16")

    def test_execution_day_budget_resets_on_next_day_not_target_day(self):
        records = [self.row(trigger=policy.BACKFILL_TRIGGER, started_at=stamp, finished_at=stamp) for stamp in ("2026-11-17T00:00:00+00:00", "2026-11-17T03:00:00+00:00")]
        self.assertIsNone(policy.next_backfill_date(datetime(2026, 11, 17, 18), self.cfg, records))
        self.assertEqual(policy.next_backfill_date(datetime(2026, 11, 18, 1), self.cfg, records), "2026-11-16")

    def test_execution_day_uses_shanghai_time(self):
        records = [self.row(trigger=policy.BACKFILL_TRIGGER, started_at=stamp, finished_at=stamp) for stamp in ("2026-11-16T16:00:00Z", "2026-11-16T18:00:00Z")]
        self.assertIsNone(policy.next_backfill_date(datetime(2026, 11, 17, 10), self.cfg, records))

    def test_capped_old_gap_does_not_starve_another_gap(self):
        cfg = {**self.cfg, "last_run_date": "2026-11-11"}
        records = [self.row("2026-11-12", trigger=policy.BACKFILL_TRIGGER, started_at=stamp, finished_at=stamp) for stamp in ("2026-11-17T00:00:00Z", "2026-11-17T00:30:00Z")]
        self.assertEqual(policy.next_backfill_date(self.now, cfg, records), "2026-11-13")


class BackfillRouterTests(unittest.TestCase):
    def test_today_has_priority_and_backfill_runs_only_during_idle_or_cooldown(self):
        for due, cooldown, expected_backfill in ((True, 0, False), (True, 300, True), (False, 0, True)):
            with self.subTest(due=due, cooldown=cooldown), tempfile.TemporaryDirectory() as tmp:
                cfg = {"enabled": True, "multi_user": True, "pipeline": "daily"}
                with patch.object(router, "_load_schedule_config", return_value=cfg), patch.object(router, "_load_schedule_history", return_value=[]), patch.object(router, "_scheduled_attempt_count", return_value=0), patch.object(router, "_scheduler_retry_counts", {}), patch.object(router, "_arxiv_rate_limit_last_at", None), patch.object(router, "failure_cooldown_remaining", return_value=cooldown), patch.object(router, "rate_limit_cooldown_remaining", return_value=0), patch.object(router, "_scheduled_attempt_is_due", return_value=due), patch.object(router, "_SCHEDULER_LOCK_PATH", str(Path(tmp) / "schedule.lock")), patch.object(router, "_try_acquire_execution_lease", return_value={"token": "test"}), patch.object(router, "_try_start_scheduled_backfill") as backfill, patch.object(router.threading, "Thread"), patch.object(router._scheduler_stop_event, "is_set", side_effect=[False, True]), patch.object(router._scheduler_stop_event, "wait"):
                    router._scheduler_loop()
                self.assertEqual(backfill.called, expected_backfill)

    def test_busy_lease_never_launches_second_worker(self):
        with patch.object(router, "next_backfill_date", return_value="2026-11-16"), patch.object(db, "get_arxiv_list_ids", return_value=[]), patch.object(router, "_try_acquire_execution_lease", return_value=None), patch.object(router.threading, "Thread") as thread:
            self.assertFalse(router._try_start_scheduled_backfill({"enabled": True}, datetime(2026, 11, 17), []))
        thread.assert_not_called()

    def test_thread_launch_failure_releases_reserved_slot(self):
        with patch.object(router, "next_backfill_date", return_value="2026-11-16"), patch.object(db, "get_arxiv_list_ids", return_value=[]), patch.object(router, "_try_acquire_execution_lease", return_value={"token": "test"}), patch.object(router.threading, "Thread") as thread, patch.object(router, "_release_execution_lease") as release:
            thread.return_value.start.side_effect = RuntimeError("failed")
            with self.assertRaises(RuntimeError):
                router._try_start_scheduled_backfill({"enabled": True}, datetime(2026, 11, 17), [])
        release.assert_called_once_with("test")

    def test_existing_source_keeps_force_off_and_users_serial(self):
        with patch.object(router, "next_backfill_date", return_value="2026-11-16"), patch.object(router, "source_empty_result_needs_retry", return_value=True), patch.object(db, "get_arxiv_list_ids", return_value=["one"]), patch.object(router, "_try_acquire_execution_lease", return_value={"token": "test"}), patch.object(router.threading, "Thread") as thread:
            self.assertTrue(router._try_start_scheduled_backfill({"enabled": True, "max_concurrent_user_pipelines": 3, "deepseek_offpeak_enabled": True}, datetime(2026, 11, 17), []))
        cfg = thread.call_args.kwargs["args"][2]
        self.assertFalse(cfg["force"])
        self.assertEqual(cfg["max_concurrent_user_pipelines"], 1)
        self.assertEqual(cfg["trigger"], policy.BACKFILL_TRIGGER)
        self.assertTrue(cfg["deepseek_offpeak_enabled"])

    def test_backfill_preserves_watermark_offpeak_and_strict_coverage(self):
        for incomplete in (False, True):
            with self.subTest(incomplete=incomplete), tempfile.TemporaryDirectory() as tmp:
                def coverage(_step, uid, _date):
                    return {"complete": not (incomplete and uid == 0), "expected_count": 2, "valid_count": 1 if incomplete and uid == 0 else 2}
                with patch.object(router, "_ADMIN_LOG_DIR", tmp), patch.object(router, "_pipeline_state", {"logs": []}), patch.object(router, "_create_db_run", return_value=0), patch.object(router, "_save_runtime_state"), patch.object(router, "_write_pipeline_processing_notices"), patch.object(router, "_publish_multi_user_run_notices"), patch.object(router, "_append_schedule_history") as history, patch.object(router, "_save_schedule_config") as save_schedule, patch.object(router, "_release_execution_lease"), patch.object(router, "_run_pipeline_subprocess", return_value=0) as run, patch.object(db, "get_arxiv_list_ids", return_value=["one", "two"]), patch.object(db, "get_db_step_coverage", side_effect=coverage), patch.object(user_settings_service, "list_users_with_custom_configs", return_value=[3]), patch.object(user_settings_service, "collect_all_search_categories", return_value=[]):
                    router._run_multiuser_scheduler_thread({"trigger": policy.BACKFILL_TRIGGER, "max_concurrent_user_pipelines": 1, "deepseek_offpeak_enabled": True}, "2026-11-16", lease_token="test")
                save_schedule.assert_not_called()
                record = history.call_args.args[0]
                self.assertEqual(record["success"], not incomplete)
                self.assertEqual(record["coverage_complete"], not incomplete)
                user_calls = [c for c in run.call_args_list if "per_user" in c.args[0]]
                self.assertEqual(len(user_calls), 2)
                self.assertTrue(all(c.args[1]["DEEPSEEK_OFFPEAK_ONLY"] == "1" for c in user_calls))
                cleanup_calls = [c for c in run.call_args_list if "post_users_cleanup" in c.args[0]]
                self.assertEqual(len(cleanup_calls), 0 if incomplete else 1)


if __name__ == "__main__":
    unittest.main()
