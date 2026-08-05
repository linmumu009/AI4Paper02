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

    def _healthy_patches(self):
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
                return_value={
                    "state": "healthy",
                    "used_percent": 79.0,
                    "free_bytes": 8_000_000_000,
                },
            ),
            patch.object(
                service.pipeline_db_service,
                "get_runs_recent",
                return_value=[{"user_id": 0}, {"user_id": 3}],
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
            patch.object(service, "_systemd_active", return_value=True),
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
                service.pipeline_db_service,
                "get_digest_publication_readiness",
                return_value={"user_id": 0, "ready": False, "reason": "no_result"},
            ),
            patch.object(service, "_systemd_active", return_value=True),
        ):
            report = service.build_health_report(now=self._now())

        self.assertEqual(report["status"], "degraded")
        self.assertIn("public_digest_fallback", report["issues"])
        self.assertIn("default_digest_not_ready", report["issues"])

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
            patch.object(service.pipeline_db_service, "get_runs_recent", return_value=[]),
            patch.object(
                service.pipeline_db_service,
                "get_digest_publication_readiness",
                return_value={"user_id": 0, "ready": False, "reason": "no_result"},
            ),
            patch.object(service, "_systemd_active", return_value=True),
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
            patch.object(service, "_systemd_active", side_effect=OSError("systemd")),
        ):
            report = service.build_health_report(now=self._now())

        self.assertEqual(report["status"], "degraded")
        self.assertIn("api_unreachable", report["issues"])
        self.assertIn("storage_check_failed", report["issues"])
        self.assertIn("digest_check_failed", report["issues"])
        self.assertIn("backup_timer_inactive", report["issues"])


if __name__ == "__main__":
    unittest.main()
