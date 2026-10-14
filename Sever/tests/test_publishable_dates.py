"""Batch date lookup must preserve publication and per-user isolation rules."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import pipeline_db_service as db


class TestPublishableDates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(db, "_DB_PATH", str(Path(self.temp.name) / "test.db"))
        patcher.start()
        self.addCleanup(patcher.stop)
        db.init_db()

    def batch(self, user, date, paper="one", raw="raw", short="short", blocks=None):
        db.bulk_upsert_selected_papers(user, date, [
            {"paper_arxiv_id": paper, "is_final_selected": 1},
        ])
        db.upsert_summary_raw(user, date, paper, raw)
        db.upsert_summary_limit(user, date, paper, short)
        db.upsert_paper_assets(user, date, paper, blocks=blocks or {"text": "content"})

    def test_matches_existing_readiness_for_complete_incomplete_and_notices(self):
        self.batch(3, "2026-10-01")
        self.batch(3, "2026-10-02", short="   ")
        self.batch(3, "2026-10-03", blocks={"text": " "})
        self.batch(3, "2026-10-04")
        self.batch(3, "2026-10-04", paper="missing", raw="")
        for date in ("2026-10-02", "2026-10-05"):
            db.upsert_date_notice(3, date, "pipeline_processing", "Working")
        self.batch(0, "2026-10-06")
        self.batch(99, "2026-10-07")
        candidates = set(db.list_dates_with_data(3) + db.list_dates_with_data(0))
        expected = sorted((date for date in candidates if
            db.is_digest_ready_for_publication(3, date)
            or db.is_digest_ready_for_publication(0, date)), reverse=True)
        self.assertEqual(db.list_publishable_dates(3), expected)
        self.assertEqual(expected, ["2026-10-06", "2026-10-05", "2026-10-01"])
        self.assertEqual(db.list_publishable_dates(0), ["2026-10-06"])

    def test_does_not_combine_outputs_from_different_users(self):
        self.batch(3, "2026-10-01", short="")
        self.batch(0, "2026-10-01", raw="")
        self.assertEqual(db.list_publishable_dates(3), [])
        db.upsert_summary_raw(0, "2026-10-01", "one", "ready")
        self.assertEqual(db.list_publishable_dates(3), ["2026-10-01"])

    def test_corrupt_or_missing_assets_do_not_publish(self):
        self.batch(3, "2026-10-01")
        conn = db._connect()
        conn.execute("UPDATE pipeline_paper_assets SET blocks_json='invalid json'")
        conn.commit()
        self.assertEqual(db.list_publishable_dates(3), [])
        conn.execute("DELETE FROM pipeline_paper_assets")
        conn.commit()
        conn.close()
        self.assertEqual(db.list_publishable_dates(3), [])

    def test_many_dates_use_one_connection_and_no_pipeline_input_reads(self):
        for day in range(1, 21):
            self.batch(3, f"2026-10-{day:02}")
        with patch.object(db, "_connect", wraps=db._connect) as connect, patch.object(
            db, "_get_theme_candidate_ids", side_effect=AssertionError("unneeded inputs")
        ):
            self.assertEqual(len(db.list_publishable_dates(3)), 20)
        self.assertEqual(connect.call_count, 1)


if __name__ == "__main__":
    unittest.main()
