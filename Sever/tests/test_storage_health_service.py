"""Tests for disk-capacity pipeline preflight."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import storage_health_service  # noqa: E402


class TestStorageHealthService(unittest.TestCase):
    def test_blocks_pipeline_when_disk_is_critical(self) -> None:
        usage = SimpleNamespace(
            total=40 * 1024**3,
            used=39 * 1024**3,
            free=1 * 1024**3,
        )
        with patch.object(storage_health_service.shutil, "disk_usage", return_value=usage):
            health = storage_health_service.get_storage_health(".")
            with self.assertRaisesRegex(RuntimeError, "Pipeline blocked"):
                storage_health_service.require_pipeline_capacity(".")

        self.assertEqual(health["state"], "critical")
        self.assertFalse(health["can_start_pipeline"])

    def test_allows_pipeline_with_safe_headroom(self) -> None:
        usage = SimpleNamespace(
            total=40 * 1024**3,
            used=20 * 1024**3,
            free=20 * 1024**3,
        )
        with patch.object(storage_health_service.shutil, "disk_usage", return_value=usage):
            health = storage_health_service.require_pipeline_capacity(".")

        self.assertEqual(health["state"], "healthy")
        self.assertTrue(health["can_start_pipeline"])

    def test_runtime_write_probe_requires_all_pipeline_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("data", "database", "logs"):
                (root / name).mkdir()

            health = storage_health_service.get_runtime_write_health(root)

        self.assertTrue(health["ok"])
        self.assertEqual(health["failed"], [])
        self.assertTrue(all(item["ok"] for item in health["checks"].values()))

    def test_blocks_pipeline_when_runtime_directory_is_not_writable(self) -> None:
        usage = SimpleNamespace(
            total=40 * 1024**3,
            used=20 * 1024**3,
            free=20 * 1024**3,
        )
        runtime_health = {
            "ok": False,
            "checked": ["data", "database", "logs"],
            "failed": ["logs"],
            "checks": {
                "data": {"ok": True, "error_type": None},
                "database": {"ok": True, "error_type": None},
                "logs": {"ok": False, "error_type": "PermissionError"},
            },
        }
        with (
            patch.object(storage_health_service.shutil, "disk_usage", return_value=usage),
            patch.object(
                storage_health_service,
                "get_runtime_write_health",
                return_value=runtime_health,
            ),
        ):
            health = storage_health_service.get_storage_health(
                ".",
                check_runtime_writes=True,
            )
            with self.assertRaisesRegex(RuntimeError, "not writable"):
                storage_health_service.require_pipeline_capacity(
                    ".",
                    check_runtime_writes=True,
                )

        self.assertEqual(health["state"], "critical")
        self.assertEqual(health["capacity_state"], "healthy")
        self.assertFalse(health["can_start_pipeline"])
        self.assertEqual(health["runtime_write"]["failed"], ["logs"])


if __name__ == "__main__":
    unittest.main()
