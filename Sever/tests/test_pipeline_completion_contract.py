"""Regression tests for DB completion coverage and post-user cleanup safety."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

import app  # noqa: E402
from Controller import cleanup  # noqa: E402
from services import pipeline_db_service  # noqa: E402


class TestPipelineCompletionContract(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.db_path = self.tmp_path / "paper_analysis.db"
        self.db_patch = patch.object(pipeline_db_service, "_DB_PATH", str(self.db_path))
        self.db_patch.start()
        pipeline_db_service.init_db()
        self.date_str = "2026-08-05"
        pipeline_db_service.bulk_upsert_arxiv_list(
            self.date_str,
            [
                {"paper_arxiv_id": "2608.00001", "title": "One"},
                {"paper_arxiv_id": "2608.00002", "title": "Two"},
                {"paper_arxiv_id": "2608.00003", "title": "Three"},
            ],
        )

    def tearDown(self) -> None:
        self.db_patch.stop()
        self._tmp.cleanup()

    def _select_final(self, user_id: int, paper_ids: list[str]) -> None:
        pipeline_db_service.bulk_upsert_selected_papers(
            user_id,
            self.date_str,
            [
                {
                    "paper_arxiv_id": paper_id,
                    "theme_score": 0.95,
                    "passed_theme_filter": 1,
                    "passed_institution_filter": 1,
                    "is_final_selected": 1,
                }
                for paper_id in paper_ids
            ],
        )

    def test_theme_scores_require_full_arxiv_coverage(self) -> None:
        dedup_dir = self.tmp_path / "data" / "paperList_remove_duplications"
        dedup_dir.mkdir(parents=True)
        (dedup_dir / f"{self.date_str}.json").write_text(
            '{"papers": [{"arxiv_id": "2608.00001"}, '
            '{"arxiv_id": "2608.00002"}, {"arxiv_id": "2608.00003"}]}',
            encoding="utf-8",
        )
        pipeline_db_service.bulk_upsert_theme_scores(
            3,
            self.date_str,
            {"2608.00001": 0.9, "2608.00002": 0.8},
        )

        with patch.object(pipeline_db_service, "_BASE_DIR", str(self.tmp_path)):
            coverage = pipeline_db_service.get_db_step_coverage(
                "llm_select_theme", 3, self.date_str
            )

        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["expected_count"], 3)
        self.assertEqual(coverage["valid_count"], 2)
        self.assertEqual(coverage["missing_ids"], ["2608.00003"])

    def test_theme_coverage_uses_real_deduplicated_input_set(self) -> None:
        dedup_dir = self.tmp_path / "data" / "paperList_remove_duplications"
        dedup_dir.mkdir(parents=True)
        (dedup_dir / f"{self.date_str}.json").write_text(
            '{"papers": [{"arxiv_id": "2608.00001"}, '
            '{"arxiv_id": "2608.00002"}]}',
            encoding="utf-8",
        )
        pipeline_db_service.bulk_upsert_theme_scores(
            3,
            self.date_str,
            {"2608.00001": 0.9, "2608.00002": 0.8},
        )

        with patch.object(pipeline_db_service, "_BASE_DIR", str(self.tmp_path)):
            coverage = pipeline_db_service.get_db_step_coverage(
                "llm_select_theme", 3, self.date_str
            )

        self.assertTrue(coverage["complete"])
        self.assertEqual(coverage["expected_count"], 2)
        self.assertEqual(coverage["valid_count"], 2)

    def test_historical_theme_coverage_uses_scores_after_input_cleanup(self) -> None:
        pipeline_db_service.bulk_upsert_theme_scores(
            3,
            self.date_str,
            {"2608.00001": 0.9, "2608.00002": 0.8},
        )

        with patch.object(pipeline_db_service, "_BASE_DIR", str(self.tmp_path)):
            coverage = pipeline_db_service.get_db_step_coverage(
                "llm_select_theme", 3, self.date_str
            )

        self.assertTrue(coverage["complete"])
        self.assertEqual(coverage["expected_count"], 2)

    def test_summaries_require_every_final_selection(self) -> None:
        paper_ids = ["2608.00001", "2608.00002", "2608.00003"]
        self._select_final(3, paper_ids)
        for paper_id in paper_ids[:2]:
            pipeline_db_service.upsert_summary_raw(
                3, self.date_str, paper_id, f"summary for {paper_id}"
            )

        coverage = pipeline_db_service.get_db_step_coverage(
            "paper_summary", 3, self.date_str
        )

        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["missing_ids"], ["2608.00003"])

    def test_empty_asset_skeleton_is_not_complete(self) -> None:
        self._select_final(3, ["2608.00001"])
        empty_blocks = {
            "background": {"text": "", "bullets": []},
            "summary": {"one_sentence_summary": "", "three_takeaways": []},
        }
        pipeline_db_service.upsert_paper_assets(
            3, self.date_str, "2608.00001", blocks=empty_blocks
        )

        incomplete = pipeline_db_service.get_db_step_coverage(
            "paper_assets", 3, self.date_str
        )
        self.assertFalse(incomplete["complete"])
        self.assertEqual(incomplete["invalid_ids"], ["2608.00001"])

        pipeline_db_service.upsert_paper_assets(
            3,
            self.date_str,
            "2608.00001",
            blocks={"summary": {"one_sentence_summary": "A real finding"}},
        )
        complete = pipeline_db_service.get_db_step_coverage(
            "paper_assets", 3, self.date_str
        )
        self.assertTrue(complete["complete"])

    def test_zero_final_recommendations_are_a_valid_completed_result(self) -> None:
        paper_ids = ["2608.00001", "2608.00002", "2608.00003"]
        pipeline_db_service.bulk_upsert_selected_papers(
            3,
            self.date_str,
            [
                {
                    "paper_arxiv_id": paper_id,
                    "theme_score": 0.1,
                    "passed_theme_filter": 0,
                    "passed_institution_filter": 0,
                    "is_final_selected": 0,
                }
                for paper_id in paper_ids
            ],
        )

        summary_coverage = pipeline_db_service.get_db_step_coverage(
            "paper_summary", 3, self.date_str
        )
        assets_coverage = pipeline_db_service.get_db_step_coverage(
            "paper_assets", 3, self.date_str
        )

        self.assertTrue(summary_coverage["complete"])
        self.assertEqual(summary_coverage["expected_count"], 0)
        self.assertTrue(assets_coverage["complete"])
        self.assertEqual(assets_coverage["expected_count"], 0)

    def test_per_user_pipeline_never_runs_destructive_cleanup(self) -> None:
        self.assertNotIn("cleanup", app.PER_USER_STEPS)
        self.assertEqual(app.POST_USERS_CLEANUP_STEPS, ["cleanup"])
        self.assertFalse(app._db_step_done("paper_theme_filter", 3, self.date_str))
        self.assertFalse(app._db_step_done("instutions_filter", 3, self.date_str))

    def test_raw_pdf_cleanup_preserves_selections_from_every_user(self) -> None:
        self._select_final(0, ["2608.00001"])
        self._select_final(3, ["2608.00002"])
        raw_dir = self.tmp_path / "raw_pdf" / self.date_str
        raw_dir.mkdir(parents=True)
        for paper_id in ("2608.00001", "2608.00002", "2608.00003"):
            (raw_dir / f"{paper_id}.pdf").write_bytes(b"pdf")

        with patch.object(cleanup, "_DATA_ROOT", self.tmp_path):
            cleanup.cleanup_raw_pdf(self.date_str)

        self.assertTrue((raw_dir / "2608.00001.pdf").exists())
        self.assertTrue((raw_dir / "2608.00002.pdf").exists())
        self.assertFalse((raw_dir / "2608.00003.pdf").exists())


if __name__ == "__main__":
    unittest.main()
