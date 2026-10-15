"""Isolated output failures must not hide complete papers or publish half cards."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from services import pipeline_db_service as db
from Controller import paper_summary


class TestPartialDigestPublication(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(db, "_DB_PATH", str(Path(self.temp.name) / "test.db"))
        patcher.start()
        self.addCleanup(patcher.stop)
        db.init_db()
        self.date = "2026-10-14"
        db.bulk_upsert_selected_papers(0, self.date, [
            {"paper_arxiv_id": p, "is_final_selected": 1} for p in ("good", "bad")
        ])

    def ready(self, paper="good", user=0):
        db.upsert_summary_raw(user, self.date, paper, "raw")
        db.upsert_summary_limit(user, self.date, paper, "short")
        db.upsert_paper_assets(user, self.date, paper, blocks={"text": "evidence"})

    def test_only_complete_explicitly_published_papers_are_visible(self):
        self.ready()
        self.assertFalse(db.is_digest_ready_for_publication(0, self.date))
        self.assertNotIn(self.date, db.list_publishable_dates(0))
        db.upsert_date_notice(0, self.date, "pipeline_temporarily_unavailable", "failed")
        published = db.publish_digest(0, self.date)
        self.assertEqual(published, {"paper_ids": ["good"], "excluded_ids": ["bad"]})
        self.assertEqual(db.get_digest_publication_readiness(0, self.date)["reason"], "partial")
        self.assertIn(self.date, db.list_publishable_dates(0))
        self.assertEqual([p["paper_id"] for p in db.get_digest_papers(0, self.date)], ["good"])
        self.assertIsNone(db.get_date_notice(0, self.date))
        # Original selections and strict completion checks still drive retries.
        self.assertEqual(set(db.get_final_arxiv_ids(0, self.date)), {"good", "bad"})
        self.assertFalse(app._db_step_done("paper_summary", 0, self.date))

    def test_retry_expands_publication_without_exposing_incomplete_new_items(self):
        self.ready()
        db.publish_digest(0, self.date)
        db.upsert_summary_raw(0, self.date, "bad", "new raw")
        self.assertEqual([p["paper_id"] for p in db.get_digest_papers(0, self.date)], ["good"])
        self.ready("bad")
        db.publish_digest(0, self.date)
        self.assertEqual(set(db.get_digest_publication(0, self.date)["paper_ids"]), {"good", "bad"})
        self.assertTrue(app._db_step_done("paper_summary", 0, self.date))

    def test_empty_output_cannot_be_published_or_complete_another_users_batch(self):
        with self.assertRaisesRegex(RuntimeError, "No complete papers"):
            db.publish_digest(0, self.date)
        self.ready(user=3)
        with self.assertRaises(RuntimeError):
            db.publish_digest(0, self.date)
        self.assertIsNone(db.get_digest_publication(0, self.date))

    def test_corruption_after_publication_is_not_served(self):
        self.ready()
        db.publish_digest(0, self.date)
        conn = db._connect()
        conn.execute("UPDATE pipeline_paper_assets SET blocks_json='{}'")
        conn.commit()
        conn.close()
        self.assertFalse(db.is_digest_ready_for_publication(0, self.date))
        self.assertNotIn(self.date, db.list_publishable_dates(0))
        self.assertEqual(db.get_digest_papers(0, self.date), [])

    def test_pipeline_continues_after_one_failed_summary_and_publishes_good_paper(self):
        called = []
        def run_step(step, *args, **kwargs):
            called.append(step)
            if step == "paper_summary":
                db.upsert_summary_raw(0, self.date, "good", "raw")
                raise subprocess.CalledProcessError(db.PARTIAL_OUTPUT_EXIT_CODE, [step])
            if step == "summary_limit":
                db.upsert_summary_limit(0, self.date, "good", "short")
            if step == "paper_assets":
                db.upsert_paper_assets(0, self.date, "good", blocks={"text": "evidence"})
        with patch.dict(app.PIPELINES, {"per_user": ["paper_summary", "summary_limit", "paper_assets"]}), \
             patch.object(app, "run_step", side_effect=run_step), patch.dict(os.environ, {}, clear=True):
            app.main(["per_user", "--date", self.date, "--output-mode", "db",
                      "--user-id", "0", "--from-step", "paper_summary"])
        self.assertEqual(called, ["paper_summary", "summary_limit", "paper_assets"])
        self.assertEqual(db.get_digest_publication(0, self.date)["excluded_ids"], ["bad"])

    def test_unexpected_process_failure_still_aborts(self):
        with patch.dict(app.PIPELINES, {"per_user": ["paper_summary", "summary_limit"]}), \
             patch.object(app, "run_step", side_effect=subprocess.CalledProcessError(1, ["failed"])), \
             patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(subprocess.CalledProcessError):
                app.main(["per_user", "--date", self.date, "--output-mode", "db",
                          "--from-step", "paper_summary"])
        self.assertIsNone(db.get_digest_publication(0, self.date))

    def test_summary_controller_keeps_good_output_and_reports_isolated_failure(self):
        cache = Path(self.temp.name) / "full_mineru_cache" / self.date
        cache.mkdir(parents=True)
        for paper in ("good", "bad"):
            (cache / f"{paper}.md").write_text("input", encoding="utf-8")
        def summarize(_client, path, **kwargs):
            if path.stem == "bad":
                raise RuntimeError("one paper rejected")
            return path, "valid summary"
        args = ["paper_summary", "--date", self.date, "--output-mode", "db",
                "--out-root", str(Path(self.temp.name) / "summaries")]
        with patch.object(paper_summary, "DATA_ROOT", self.temp.name), \
             patch.object(paper_summary, "make_client_for_user", return_value=(object(), {})), \
             patch.object(paper_summary, "summarize_one", side_effect=summarize), \
             patch.object(sys, "argv", args):
            with self.assertRaises(SystemExit) as raised:
                paper_summary.run()
        self.assertEqual(raised.exception.code, db.PARTIAL_OUTPUT_EXIT_CODE)
        self.assertEqual(db.get_summaries_map(0, self.date)["good"]["summary_raw"], "valid summary")


if __name__ == "__main__":
    unittest.main()
