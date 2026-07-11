"""Regression tests for cumulative session-duration snapshots."""

import os
import sqlite3
import sys
import tempfile
import unittest

_SEVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SEVER_DIR not in sys.path:
    sys.path.insert(0, _SEVER_DIR)

from services import analytics_service  # noqa: E402


class TestSessionDurationAggregation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._original_db_path = analytics_service._AUTH_DB_PATH
        analytics_service._AUTH_DB_PATH = os.path.join(self._tmp.name, "analytics.db")
        analytics_service.init_db()

        conn = sqlite3.connect(analytics_service._AUTH_DB_PATH)
        try:
            conn.execute(
                """
                CREATE TABLE auth_users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    role TEXT,
                    tier TEXT,
                    created_at TEXT,
                    last_login_at TEXT
                )
                """
            )
            now = analytics_service._now_iso()
            conn.execute(
                "INSERT INTO auth_users VALUES (?, ?, ?, ?, ?, ?)",
                (1, "tester", "user", "free", now, now),
            )
            conn.executemany(
                """
                INSERT INTO analytics_events
                    (user_id, event_type, target_type, target_id, value, meta_json, created_at)
                VALUES (?, 'session_duration', 'session', ?, ?, '{}', ?)
                """,
                [
                    (1, "session-a", 300, now),
                    (1, "session-a", 600, now),
                    (1, "session-b", 120, now),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        analytics_service._AUTH_DB_PATH = self._original_db_path
        self._tmp.cleanup()

    def test_periodic_snapshots_are_not_double_counted(self):
        activity = analytics_service.get_user_activity_stats()
        self.assertEqual(activity["users"][0]["total_time_spent_seconds"], 720)

        depth = analytics_service.get_engagement_depth(days=30)
        self.assertEqual(depth["window_avg_session_seconds"], 360.0)
        self.assertEqual(depth["session_duration_distribution"]["m2_10"], 1)
        self.assertEqual(depth["session_duration_distribution"]["gt10m"], 1)


if __name__ == "__main__":
    unittest.main()
