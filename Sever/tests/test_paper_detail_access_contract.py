import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import data_service, kb_service, pipeline_db_service  # noqa: E402


class TestPaperDetailAccessContract(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "paper_analysis.db")
        self.data_root = str(Path(self.tmp.name) / "data")
        Path(self.data_root).mkdir(parents=True, exist_ok=True)
        self.patchers = [
            patch.object(kb_service, "_DB_PATH", self.db_path),
            patch.object(pipeline_db_service, "_DB_PATH", self.db_path),
            patch.object(data_service, "_DATA_ROOT", self.data_root),
        ]
        for patcher in self.patchers:
            patcher.start()
        kb_service.init_db()
        pipeline_db_service.init_db()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tmp.cleanup()

    def test_saved_snapshot_remains_accessible_without_publishable_pipeline_rows(self) -> None:
        paper_id = "2999.00001"
        kb_service.add_paper(
            7,
            paper_id,
            {
                "paper_id": paper_id,
                "short_title": "历史收藏论文",
                "📖标题": "A Saved Historical Paper",
                "🛎️文章简介": {"🔸研究问题": "保存内容是否仍可访问？", "🔸主要贡献": "是。"},
            },
        )

        detail = data_service.get_paper_detail(paper_id, user_id=7)

        self.assertIsNotNone(detail)
        self.assertEqual(detail["summary"]["paper_id"], paper_id)
        self.assertEqual(detail["summary"]["short_title"], "历史收藏论文")
        self.assertTrue(detail["summary"]["is_personalized"])

    def test_incomplete_saved_snapshot_gets_professional_nonempty_fallback(self) -> None:
        paper_id = "2999.00002"
        kb_service.add_paper(7, paper_id, {})

        detail = data_service.get_paper_detail(paper_id, user_id=7)

        self.assertIsNotNone(detail)
        self.assertEqual(detail["summary"]["short_title"], paper_id)
        intro = detail["summary"]["🛎️文章简介"]
        self.assertIn("历史摘要数据不完整", intro["🔸研究问题"])

    def test_latest_pipeline_bundle_uses_direct_paper_lookup(self) -> None:
        paper_id = "2999.00003"
        for date_str, score in (("2026-08-01", 0.5), ("2026-08-05", 0.9)):
            pipeline_db_service.upsert_selected_paper(
                0,
                date_str,
                paper_id,
                passed_theme=True,
                passed_institution=True,
                is_final=True,
                theme_score=score,
            )
            pipeline_db_service.upsert_summary_limit(
                0,
                date_str,
                paper_id,
                f"短标题\n\n📖标题：Paper {date_str}\n\n🛎️文章简介\n🔸研究问题：问题\n🔸主要贡献：贡献",
            )

        bundle = pipeline_db_service.get_latest_paper_bundle(0, paper_id)

        self.assertIsNotNone(bundle)
        self.assertEqual(bundle["date_str"], "2026-08-05")
        self.assertEqual(bundle["theme_score"], 0.9)

    def test_unknown_paper_does_not_enumerate_pipeline_dates(self) -> None:
        with patch.object(
            pipeline_db_service,
            "list_dates_with_data",
            side_effect=AssertionError("detail lookup must not enumerate dates"),
        ):
            detail = data_service.get_paper_detail("2999.99999", user_id=7)

        self.assertIsNone(detail)

    def test_incomplete_newer_public_batch_does_not_hide_older_valid_detail(self) -> None:
        paper_id = "2999.00004"
        for date_str in ("2026-08-01", "2026-08-05"):
            pipeline_db_service.upsert_selected_paper(
                0,
                date_str,
                paper_id,
                passed_theme=True,
                passed_institution=True,
                is_final=True,
                theme_score=0.8,
            )
            pipeline_db_service.upsert_summary_limit(
                0,
                date_str,
                paper_id,
                f"短标题\n\n📖标题：Paper {date_str}\n\n🛎️文章简介\n🔸研究问题：问题\n🔸主要贡献：贡献",
            )

        with patch.object(
            pipeline_db_service,
            "is_digest_ready_for_publication",
            side_effect=lambda _uid, date_str: date_str == "2026-08-01",
        ):
            detail = data_service.get_paper_detail(paper_id)

        self.assertIsNotNone(detail)
        self.assertEqual(detail["date"], "2026-08-01")
        self.assertEqual(detail["summary"]["📖标题"], "Paper 2026-08-01")


if __name__ == "__main__":
    unittest.main()
