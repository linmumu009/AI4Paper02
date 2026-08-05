import os
import tempfile
import time
import unittest
from unittest.mock import patch

from Sever.services.pipeline_lease_service import (
    acquire_pipeline_lease,
    read_lease,
    release_pipeline_lease,
)


class PipelineLeaseServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.lock_path = os.path.join(self.temp_dir.name, "pipeline.lock")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _acquire(self, **kwargs):
        return acquire_pipeline_lease(
            self.lock_path,
            pipeline="multi_user",
            date_str="2026-08-05",
            trigger="manual",
            **kwargs,
        )

    def test_second_owner_cannot_acquire_live_lease(self) -> None:
        first = self._acquire(pid_checker=lambda _pid: True)
        second = self._acquire(pid_checker=lambda _pid: True)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(read_lease(self.lock_path)["token"], first["token"])

    def test_dead_owner_is_reclaimed(self) -> None:
        first = self._acquire(pid_checker=lambda _pid: True)
        second = self._acquire(pid_checker=lambda _pid: False)

        self.assertIsNotNone(second)
        self.assertNotEqual(first["token"], second["token"])
        self.assertEqual(read_lease(self.lock_path)["token"], second["token"])

    def test_old_owner_cannot_release_new_lease(self) -> None:
        first = self._acquire(pid_checker=lambda _pid: True)
        second = self._acquire(pid_checker=lambda _pid: False)

        self.assertFalse(release_pipeline_lease(self.lock_path, first["token"]))
        self.assertTrue(os.path.exists(self.lock_path))
        self.assertTrue(release_pipeline_lease(self.lock_path, second["token"]))
        self.assertFalse(os.path.exists(self.lock_path))

    def test_recent_incomplete_write_is_not_reclaimed(self) -> None:
        with open(self.lock_path, "w", encoding="utf-8") as handle:
            handle.write("")

        self.assertIsNone(self._acquire(pid_checker=lambda _pid: False))

        old = time.time() - 31
        os.utime(self.lock_path, (old, old))
        self.assertIsNotNone(self._acquire(pid_checker=lambda _pid: False))

    def test_excessively_old_live_lease_is_reclaimed(self) -> None:
        first = self._acquire(pid_checker=lambda _pid: True)
        old = time.time() - 11
        os.utime(self.lock_path, (old, old))

        second = self._acquire(
            pid_checker=lambda _pid: True,
            stale_after_seconds=10,
        )

        self.assertIsNotNone(second)
        self.assertNotEqual(first["token"], second["token"])


if __name__ == "__main__":
    unittest.main()
