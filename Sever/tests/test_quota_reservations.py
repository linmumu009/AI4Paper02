from __future__ import annotations

import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import entitlement_service  # noqa: E402


class QuotaReservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "quota.db")
        self._db_patch = patch.object(entitlement_service, "_DB_PATH", self.db_path)
        self._db_patch.start()
        entitlement_service.init_db()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE auth_users (
                    id INTEGER PRIMARY KEY,
                    role TEXT,
                    tier TEXT,
                    tier_expires_at TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO auth_users (id, role, tier) VALUES (7, 'user', 'free')"
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        self._db_patch.stop()
        self._tmp.cleanup()

    def test_release_refunds_reserved_quota_exactly_once(self) -> None:
        receipt = entitlement_service.reserve_quota(7, "translate")
        reservation_id = receipt["reservation_id"]
        self.assertIsNotNone(reservation_id)
        self.assertEqual(entitlement_service.check_quota(7, "translate")["used"], 1)

        self.assertTrue(entitlement_service.release_quota_reservation(reservation_id))
        self.assertFalse(entitlement_service.release_quota_reservation(reservation_id))
        self.assertEqual(entitlement_service.check_quota(7, "translate")["used"], 0)

    def test_committed_reservation_cannot_be_refunded(self) -> None:
        receipt = entitlement_service.reserve_quota(7, "translate")
        reservation_id = receipt["reservation_id"]

        self.assertTrue(entitlement_service.commit_quota_reservation(reservation_id))
        self.assertTrue(entitlement_service.commit_quota_reservation(reservation_id))
        self.assertFalse(entitlement_service.release_quota_reservation(reservation_id))
        self.assertEqual(entitlement_service.check_quota(7, "translate")["used"], 1)

    def test_reservation_limit_is_enforced_without_partial_increment(self) -> None:
        class FakeHttpException(Exception):
            def __init__(self, status_code: int, detail: str):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        fake_fastapi = types.ModuleType("fastapi")
        fake_fastapi.HTTPException = FakeHttpException
        entitlement_service.reserve_quota(7, "translate")
        entitlement_service.reserve_quota(7, "translate")

        with patch.dict("sys.modules", {"fastapi": fake_fastapi}):
            with self.assertRaises(FakeHttpException) as ctx:
                entitlement_service.reserve_quota(7, "translate")

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(entitlement_service.check_quota(7, "translate")["used"], 2)
        conn = sqlite3.connect(self.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM quota_reservations").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 2)

    def test_init_releases_reservation_abandoned_by_crashed_process(self) -> None:
        receipt = entitlement_service.reserve_quota(7, "translate")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE quota_reservations SET created_at='2000-01-01T00:00:00+00:00' "
                "WHERE reservation_id=?",
                (receipt["reservation_id"],),
            )
            conn.commit()
        finally:
            conn.close()

        entitlement_service.init_db()

        self.assertEqual(entitlement_service.check_quota(7, "translate")["used"], 0)
        conn = sqlite3.connect(self.db_path)
        try:
            status = conn.execute(
                "SELECT status FROM quota_reservations WHERE reservation_id=?",
                (receipt["reservation_id"],),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(status, "released")


if __name__ == "__main__":
    unittest.main()
