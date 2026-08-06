from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import system_health_service as service  # noqa: E402


class SystemHealthServiceTests(unittest.TestCase):
    def _now(self, hour: int = 16) -> datetime:
        return datetime(2026, 8, 5, hour, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    def _healthy_patches(self, storage: dict | None = None):
        return (
            patch.object(
                service,
                "_http_json_get",
                return_value=(
                    200,
                    {
                        "papers": [{"paper_id": "hidden"}] * 3,
                        "total_available": 5,
                        "effective_date": "2026-08-05",
                        "is_fallback": False,
                    },
                ),
            ),
            patch.object(
                service,
                "get_storage_health",
                return_value=storage or {
                    "state": "healthy",
                    "used_percent": 79.0,
                    "free_bytes": 8_000_000_000,
                    "runtime_write": {
                        "ok": True,
                        "failed": [],
                    },
                },
            ),
            patch.object(
                service.pipeline_db_service,
                "get_runs_recent",
                return_value=[
                    {
                        "user_id": 0,
                        "trigger": "scheduled",
                        "parent_run_id": None,
                        "status": "completed",
                    },
                    {
                        "user_id": 3,
                        "trigger": "scheduled",
                        "parent_run_id": 1,
                        "status": "completed",
                    },
                ],
            ),
            patch.object(
                service,
                "_load_schedule_config",
                return_value=(
                    {"enabled": True, "hour": 6, "minute": 0, "last_run_date": "2026-08-05"},
                    True,
                ),
            ),
            patch.object(
                service.pipeline_db_service,
                "get_digest_publication_readiness",
                side_effect=lambda uid, _date: {
                    "user_id": uid,
                    "ready": True,
                    "reason": "complete",
                },
            ),
            patch.object(
                service,
                "_backup_health_check",
                return_value=(
                    {
                        "ok": True,
                        "timer_active": True,
                        "last_result": "success",
                        "status_readable": True,
                        "status_valid": True,
                        "max_age_hours": 30,
                        "age_hours": 12.0,
                        "database_count": 4,
                        "recovery_secret_count": 3,
                    },
                    [],
                ),
            ),
        )

    def test_healthy_report_contains_only_operational_counts(self) -> None:
        patches = self._healthy_patches()
        for item in patches:
            item.start()
        try:
            report = service.build_health_report(now=self._now())
        finally:
            for item in reversed(patches):
                item.stop()

        self.assertEqual(report["status"], "healthy")
        self.assertEqual(report["checks"]["api"]["paper_count"], 3)
        self.assertEqual(report["checks"]["digest"]["ready_users"], 2)
        self.assertNotIn("hidden", json.dumps(report))

    def test_runtime_write_failure_is_reported_as_storage_incident(self) -> None:
        patches = self._healthy_patches(
            storage={
                "state": "critical",
                "used_percent": 40.0,
                "free_bytes": 20_000_000_000,
                "runtime_write": {
                    "ok": False,
                    "failed": ["logs"],
                },
            }
        )
        for item in patches:
            item.start()
        try:
            report = service.build_health_report(now=self._now())
        finally:
            for item in reversed(patches):
                item.stop()

        self.assertEqual(report["status"], "degraded")
        self.assertIn("storage_not_writable", report["issues"])
        self.assertIn("storage_critical", report["issues"])
        self.assertFalse(report["checks"]["storage"]["runtime_write_ok"])
        self.assertEqual(
            report["checks"]["storage"]["runtime_write_failures"],
            ["logs"],
        )

    def test_fallback_and_incomplete_digest_fail_after_deadline(self) -> None:
        with (
            patch.object(
                service,
                "_http_json_get",
                return_value=(200, {"papers": [], "effective_date": "2026-08-04", "is_fallback": True}),
            ),
            patch.object(
                service,
                "get_storage_health",
                return_value={"state": "healthy", "used_percent": 70, "free_bytes": 9},
            ),
            patch.object(
                service.pipeline_db_service,
                "get_runs_recent",
                return_value=[],
            ),
            patch.object(
                service,
                "_load_schedule_config",
                return_value=({"enabled": True, "hour": 6, "minute": 0}, True),
            ),
            patch.object(
                service.pipeline_db_service,
                "get_digest_publication_readiness",
                return_value={"user_id": 0, "ready": False, "reason": "no_result"},
            ),
            patch.object(
                service,
                "_backup_health_check",
                return_value=({"ok": True, "timer_active": True}, []),
            ),
        ):
            report = service.build_health_report(now=self._now())

        self.assertEqual(report["status"], "degraded")
        self.assertIn("public_digest_fallback", report["issues"])
        self.assertIn("default_digest_not_ready", report["issues"])
        self.assertFalse(report["checks"]["api"]["ok"])
        self.assertFalse(report["checks"]["digest"]["ok"])

    def test_digest_is_allowed_to_be_pending_before_deadline(self) -> None:
        with (
            patch.object(
                service,
                "_http_json_get",
                return_value=(200, {"papers": [], "effective_date": "2026-08-05"}),
            ),
            patch.object(
                service,
                "get_storage_health",
                return_value={"state": "healthy", "used_percent": 70, "free_bytes": 9},
            ),
            patch.object(
                service.pipeline_db_service,
                "get_runs_recent",
                return_value=[
                    {
                        "user_id": 0,
                        "trigger": "scheduled",
                        "parent_run_id": None,
                        "status": "running",
                        "started_at": "2026-08-05T00:00:00+00:00",
                    }
                ],
            ),
            patch.object(
                service,
                "_load_schedule_config",
                return_value=({"enabled": True, "hour": 6, "minute": 0}, True),
            ),
            patch.object(
                service.pipeline_db_service,
                "get_digest_publication_readiness",
                return_value={"user_id": 0, "ready": False, "reason": "no_result"},
            ),
            patch.object(
                service,
                "_backup_health_check",
                return_value=({"ok": True, "timer_active": True}, []),
            ),
        ):
            report = service.build_health_report(now=self._now(hour=8))

        self.assertEqual(report["status"], "healthy")
        self.assertFalse(report["checks"]["digest"]["deadline_passed"])

    def test_alert_is_deduplicated_and_recovery_is_sent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "health.json"
            degraded = {"status": "degraded", "issues": ["api_unreachable"]}
            healthy = {"status": "healthy", "issues": []}
            with patch.object(service, "_post_alert") as post_alert:
                self.assertTrue(service.persist_report_and_alert(
                    degraded,
                    state_path=state_path,
                    webhook_url="https://example.invalid/hook",
                    now_epoch=1000,
                ))
                self.assertFalse(service.persist_report_and_alert(
                    degraded,
                    state_path=state_path,
                    webhook_url="https://example.invalid/hook",
                    now_epoch=1100,
                ))
                self.assertTrue(service.persist_report_and_alert(
                    healthy,
                    state_path=state_path,
                    webhook_url="https://example.invalid/hook",
                    now_epoch=1200,
                ))
            self.assertEqual(post_alert.call_count, 2)

    def test_check_failures_are_reported_without_aborting_other_checks(self) -> None:
        with (
            patch.object(service, "_http_json_get", side_effect=OSError("offline")),
            patch.object(service, "get_storage_health", side_effect=OSError("disk")),
            patch.object(
                service.pipeline_db_service,
                "get_runs_recent",
                side_effect=RuntimeError("db"),
            ),
            patch.object(
                service,
                "_load_schedule_config",
                return_value=({"enabled": True, "hour": 6, "minute": 0}, True),
            ),
            patch.object(
                service,
                "_backup_health_check",
                return_value=(
                    {"ok": False, "timer_active": False},
                    ["backup_timer_inactive", "backup_status_unreadable"],
                ),
            ),
        ):
            report = service.build_health_report(now=self._now())

        self.assertEqual(report["status"], "degraded")
        self.assertIn("api_unreachable", report["issues"])
        self.assertIn("storage_check_failed", report["issues"])
        self.assertIn("digest_check_failed", report["issues"])
        self.assertIn("pipeline_execution_check_failed", report["issues"])
        self.assertIn("backup_timer_inactive", report["issues"])

    def test_backup_health_requires_fresh_verified_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            status_path = Path(temp_dir) / "backup_health.json"
            status_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "ok": True,
                        "backup_created_at": "2026-08-05T02:20:00+08:00",
                        "verified_at": "2026-08-05T02:21:00+08:00",
                        "database_count": 4,
                        "recovery_secret_count": 3,
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(service, "_BACKUP_STATUS_PATH", status_path),
                patch.object(service, "_systemd_active", return_value=True),
                patch.object(service, "_systemd_property", return_value="success"),
            ):
                check, issues = service._backup_health_check(self._now())

        self.assertTrue(check["ok"])
        self.assertTrue(check["status_valid"])
        self.assertEqual(check["database_count"], 4)
        self.assertEqual(issues, [])

    def test_backup_health_distinguishes_stale_and_failed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            status_path = Path(temp_dir) / "backup_health.json"
            status_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "ok": True,
                        "backup_created_at": "2026-08-03T02:20:00+08:00",
                        "verified_at": "2026-08-03T02:21:00+08:00",
                        "database_count": 4,
                        "recovery_secret_count": 3,
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(service, "_BACKUP_STATUS_PATH", status_path),
                patch.object(service, "_systemd_active", return_value=True),
                patch.object(service, "_systemd_property", return_value="failed"),
            ):
                check, issues = service._backup_health_check(self._now())

        self.assertFalse(check["ok"])
        self.assertIn("backup_last_run_failed", issues)
        self.assertIn("backup_stale", issues)

    def test_missing_scheduled_attempt_is_detected_after_start_grace(self) -> None:
        with patch.object(
            service,
            "_load_schedule_config",
            return_value=({"enabled": True, "hour": 6, "minute": 0}, True),
        ):
            check, issues = service._scheduled_pipeline_check(
                self._now(hour=7),
                [],
            )

        self.assertFalse(check["ok"])
        self.assertTrue(check["start_due"])
        self.assertIn("scheduled_pipeline_not_started", issues)

    def test_fresh_running_attempt_is_healthy(self) -> None:
        with patch.object(
            service,
            "_load_schedule_config",
            return_value=({"enabled": True, "hour": 6, "minute": 0}, True),
        ):
            check, issues = service._scheduled_pipeline_check(
                self._now(hour=8),
                [
                    {
                        "trigger": "scheduled",
                        "parent_run_id": None,
                        "status": "running",
                        "started_at": "2026-08-05T00:00:00+00:00",
                    }
                ],
            )

        self.assertTrue(check["ok"])
        self.assertEqual(check["running"], 1)
        self.assertEqual(issues, [])

    def test_stale_running_attempt_and_terminal_failure_are_distinguished(self) -> None:
        with patch.object(
            service,
            "_load_schedule_config",
            return_value=({"enabled": True, "hour": 6, "minute": 0}, True),
        ):
            stale, stale_issues = service._scheduled_pipeline_check(
                self._now(hour=16),
                [
                    {
                        "trigger": "scheduled",
                        "parent_run_id": None,
                        "status": "running",
                        "started_at": "2026-08-04T22:00:00+00:00",
                    }
                ],
            )
            failed, failed_issues = service._scheduled_pipeline_check(
                self._now(hour=16),
                [
                    {
                        "trigger": "scheduled",
                        "parent_run_id": None,
                        "status": "failed",
                        "finished_at": "2026-08-05T01:00:00+00:00",
                    }
                ],
            )

        self.assertEqual(stale["stale"], 1)
        self.assertIn("scheduled_pipeline_stalled", stale_issues)
        self.assertEqual(failed["failed"], 1)
        self.assertIn("scheduled_pipeline_failed", failed_issues)
        self.assertFalse(failed["retry_budget_exhausted"])

    def test_exhausted_scheduled_retry_budget_is_explicit(self) -> None:
        runs = [
            {
                "trigger": "scheduled",
                "parent_run_id": None,
                "status": "failed",
                "finished_at": f"2026-08-05T01:0{index}:00+00:00",
            }
            for index in range(8)
        ]
        with patch.object(
            service,
            "_load_schedule_config",
            return_value=({"enabled": True, "hour": 6, "minute": 0}, True),
        ):
            check, issues = service._scheduled_pipeline_check(
                self._now(hour=16), runs
            )

        self.assertEqual(check["retry_limit"], 8)
        self.assertTrue(check["retry_budget_exhausted"])
        self.assertIn("scheduled_pipeline_retry_exhausted", issues)

    def test_disabled_or_unreadable_scheduler_is_never_reported_healthy(self) -> None:
        with patch.object(
            service,
            "_load_schedule_config",
            return_value=({"enabled": False}, True),
        ):
            disabled, disabled_issues = service._scheduled_pipeline_check(
                self._now(hour=5),
                [],
            )
        with patch.object(service, "_load_schedule_config", return_value=({}, False)):
            unreadable, unreadable_issues = service._scheduled_pipeline_check(
                self._now(hour=5),
                [],
            )

        self.assertFalse(disabled["ok"])
        self.assertIn("scheduler_disabled", disabled_issues)
        self.assertFalse(unreadable["ok"])
        self.assertIn("scheduler_config_unreadable", unreadable_issues)

    def test_temporary_notice_and_empty_completed_digest_fail_the_digest_check(self) -> None:
        healthy_patches = self._healthy_patches()
        for item in healthy_patches:
            item.start()
        try:
            with patch.object(
                service.pipeline_db_service,
                "get_digest_publication_readiness",
                return_value={
                    "user_id": 0,
                    "ready": True,
                    "reason": "temporary_unavailable_notice",
                },
            ):
                unavailable = service.build_health_report(now=self._now())
            with (
                patch.object(
                    service.pipeline_db_service,
                    "get_digest_publication_readiness",
                    return_value={"user_id": 0, "ready": True, "reason": "complete"},
                ),
                patch.object(
                    service,
                    "_http_json_get",
                    return_value=(
                        200,
                        {
                            "papers": [],
                            "total_available": 0,
                            "effective_date": "2026-08-05",
                            "is_fallback": False,
                        },
                    ),
                ),
            ):
                empty = service.build_health_report(now=self._now())
        finally:
            for item in reversed(healthy_patches):
                item.stop()

        self.assertFalse(unavailable["checks"]["digest"]["ok"])
        self.assertIn("digest_temporarily_unavailable", unavailable["issues"])
        self.assertFalse(empty["checks"]["digest"]["ok"])
        self.assertIn("public_digest_empty", empty["issues"])


if __name__ == "__main__":
    unittest.main()
