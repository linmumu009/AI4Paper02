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
from services import pipeline_db_service, user_settings_service  # noqa: E402


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

    def test_pdf_info_requires_only_theme_passed_papers(self) -> None:
        pipeline_db_service.bulk_upsert_theme_scores(
            3,
            self.date_str,
            {"2608.00001": 0.95, "2608.00002": 0.20, "2608.00003": 0.10},
        )
        pipeline_db_service.bulk_upsert_selected_papers(
            3,
            self.date_str,
            [
                {
                    "paper_arxiv_id": "2608.00001",
                    "theme_score": 0.95,
                    "passed_theme_filter": 1,
                },
                {
                    "paper_arxiv_id": "2608.00002",
                    "theme_score": 0.20,
                    "passed_theme_filter": 0,
                },
                {
                    "paper_arxiv_id": "2608.00003",
                    "theme_score": 0.10,
                    "passed_theme_filter": 0,
                },
            ],
        )
        pipeline_db_service.upsert_paper_info(
            3,
            self.date_str,
            "2608.00001",
            title="One",
            abstract="Abstract",
        )

        coverage = pipeline_db_service.get_db_step_coverage(
            "pdf_info", 3, self.date_str
        )

        self.assertTrue(coverage["complete"])
        self.assertEqual(coverage["expected_count"], 1)
        self.assertEqual(coverage["valid_count"], 1)

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

    def test_digest_is_not_publishable_until_every_user_facing_output_is_complete(self) -> None:
        self._select_final(3, ["2608.00001"])
        pipeline_db_service.upsert_summary_raw(
            3, self.date_str, "2608.00001", "complete raw summary"
        )
        pipeline_db_service.upsert_summary_limit(
            3, self.date_str, "2608.00001", "complete limited summary"
        )

        incomplete = pipeline_db_service.get_digest_publication_readiness(
            3, self.date_str
        )
        self.assertFalse(incomplete["ready"])
        self.assertEqual(incomplete["reason"], "incomplete_coverage")
        self.assertFalse(incomplete["coverage"]["paper_assets"]["complete"])

        pipeline_db_service.upsert_paper_assets(
            3,
            self.date_str,
            "2608.00001",
            blocks={"summary": {"one_sentence_summary": "A real finding"}},
        )
        complete = pipeline_db_service.get_digest_publication_readiness(
            3, self.date_str
        )
        self.assertTrue(complete["ready"])
        self.assertEqual(complete["reason"], "complete")

    def test_empty_digest_requires_an_explicit_date_notice_to_publish(self) -> None:
        self.assertFalse(
            pipeline_db_service.is_digest_ready_for_publication(3, self.date_str)
        )

        pipeline_db_service.upsert_date_notice(
            3,
            self.date_str,
            "no_papers_empty",
            "今天暂无符合条件的论文。",
        )

        self.assertTrue(
            pipeline_db_service.is_digest_ready_for_publication(3, self.date_str)
        )

    def test_transient_failure_notice_is_visible_and_cleared_after_recovery(self) -> None:
        pipeline_db_service.upsert_date_notice(
            3,
            self.date_str,
            "source_temporarily_unavailable",
            "系统正在自动重试。",
        )

        readiness = pipeline_db_service.get_digest_publication_readiness(
            3, self.date_str
        )
        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["reason"], "temporary_unavailable_notice")
        self.assertEqual(
            pipeline_db_service.delete_date_notices_by_type(
                self.date_str, "source_temporarily_unavailable"
            ),
            1,
        )
        self.assertIsNone(pipeline_db_service.get_date_notice(3, self.date_str))

    def test_processing_notice_is_visible_without_claiming_completion(self) -> None:
        pipeline_db_service.upsert_date_notice(
            3,
            self.date_str,
            "pipeline_processing",
            "今日论文正在生成。",
        )

        readiness = pipeline_db_service.get_digest_publication_readiness(
            3, self.date_str
        )
        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["reason"], "processing_notice")

    def test_per_user_pipeline_never_runs_destructive_cleanup(self) -> None:
        self.assertNotIn("cleanup", app.PER_USER_STEPS)
        self.assertEqual(app.POST_USERS_CLEANUP_STEPS, ["cleanup"])
        self.assertFalse(app._db_step_done("paper_theme_filter", 3, self.date_str))
        self.assertFalse(app._db_step_done("instutions_filter", 3, self.date_str))

    def test_failed_idea_manifest_never_suppresses_retry(self) -> None:
        manifest = self.tmp_path / "idea_combine.jsonl"
        with patch.object(
            app,
            "STEP_OUTPUT_PATHS",
            {"idea_combine": lambda _date: str(manifest)},
        ):
            manifest.write_text('{"status":"failed"}\n', encoding="utf-8")
            self.assertFalse(app.step_output_exists("idea_combine", self.date_str))

            manifest.write_text('{"status":"done"}\n', encoding="utf-8")
            self.assertTrue(app.step_output_exists("idea_combine", self.date_str))

            manifest.write_text("not json\n", encoding="utf-8")
            self.assertFalse(app.step_output_exists("idea_combine", self.date_str))

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

    def test_slim_mineru_requires_complete_summaries_for_all_users(self) -> None:
        for user_id in (0, 3):
            self._select_final(user_id, ["2608.00001"])
            pipeline_db_service.upsert_summary_limit(
                user_id, self.date_str, "2608.00001", "complete limited summary"
            )

        paper_dir = (
            self.tmp_path
            / "full_mineru_cache"
            / self.date_str
            / "2608.00001"
        )
        paper_dir.mkdir(parents=True)
        (paper_dir / "2608.00001.md").write_text("markdown", encoding="utf-8")
        (paper_dir / "origin.pdf").write_bytes(b"pdf")

        with (
            patch.object(cleanup, "_DATA_ROOT", self.tmp_path),
            patch.object(user_settings_service, "list_users_with_custom_configs", return_value=[3]),
            patch.object(cleanup, "_pre_copy_kb_mineru_for_date"),
        ):
            cleanup.cleanup_slim_mineru(self.date_str)

        self.assertTrue((paper_dir / "2608.00001.md").exists())
        self.assertFalse((paper_dir / "origin.pdf").exists())


if __name__ == "__main__":
    unittest.main()
