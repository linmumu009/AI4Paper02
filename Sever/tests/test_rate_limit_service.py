from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services.rate_limit_service import (  # noqa: E402
    PersistentRateLimiter,
    RateLimitExceeded,
)


class RateLimitServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "limits.db")
        self.now = 1_000.0

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _limiter(self, bucket: str = "login") -> PersistentRateLimiter:
        return PersistentRateLimiter(
            bucket=bucket,
            max_attempts=2,
            window_seconds=60,
            db_path=self.db_path,
            clock=lambda: self.now,
        )

    def test_limit_persists_across_instances(self) -> None:
        self._limiter().check("203.0.113.4")
        self._limiter().check("203.0.113.4")

        with self.assertRaises(RateLimitExceeded) as caught:
            self._limiter().check("203.0.113.4")

        self.assertEqual(caught.exception.retry_after_seconds, 60)

    def test_window_expiry_and_keys_are_isolated(self) -> None:
        limiter = self._limiter()
        limiter.check("first")
        limiter.check("first")
        limiter.check("second")
        self.now += 61
        limiter.check("first")

    def test_buckets_are_isolated(self) -> None:
        self._limiter("login").check("same")
        self._limiter("login").check("same")
        self._limiter("register").check("same")

    def test_raw_rate_limit_key_is_not_stored(self) -> None:
        raw_key = "sensitive-user@example.com"
        self._limiter().check(raw_key)
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT key_hash FROM rate_limit_events LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertNotEqual(row[0], raw_key)
        self.assertEqual(len(row[0]), 64)


if __name__ == "__main__":
    unittest.main()
