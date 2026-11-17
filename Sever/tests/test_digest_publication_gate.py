from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import data_service, pipeline_db_service  # noqa: E402


class TestDigestPublicationGate(unittest.TestCase):
    date_str = "2026-08-05"

    def test_malformed_concise_intro_falls_back_to_real_detailed_content(self) -> None:
        raw = (
            "笔记标题：Muon洗牌收敛性\n📖标题：Muon under Shuffling\n"
            "🛎️文章简介\n🔸研究问题：洗牌采样下的收敛速度如何？\n"
            "🔸主要贡献：给出问题依赖的动量选择与收敛界。\n"
        )
        concise = (
            "KTH：Muon收敛性\n📖标题：Muon under Shuffling\n"
            "🛎️文章简介\n本文研究洗牌采样并给出收敛结论。\n"
        )
        row = {"paper_id": "2608.00001", "title": "Muon under Shuffling", "summary_raw": raw, "summary_limit": concise}
        with patch.object(pipeline_db_service, "has_final_selections", return_value=True), patch.object(pipeline_db_service, "get_date_notice", return_value=None), patch.object(pipeline_db_service, "is_digest_ready_for_publication", return_value=True), patch.object(pipeline_db_service, "get_digest_papers", return_value=[row]), patch.object(pipeline_db_service, "get_paper_images", return_value={}):
            cards = data_service._get_papers_from_db(self.date_str)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["🛎️文章简介"]["🔸研究问题"], "洗牌采样下的收敛速度如何？")
        self.assertFalse(cards[0]["has_detailed_summary"])

        bundle = {"date_str": self.date_str, "summary": row, "info": {}, "assets": {}}
        with patch.object(pipeline_db_service, "get_latest_paper_bundle", return_value=bundle), patch.object(pipeline_db_service, "is_digest_ready_for_publication", return_value=True), patch.object(pipeline_db_service, "get_digest_publication", return_value=None), patch.object(data_service, "_list_paper_images_from_select_image", return_value=[]), patch.object(data_service, "_find_local_pdf_url", return_value=None):
            detail = data_service.get_paper_detail("2608.00001")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["summary"]["🛎️文章简介"], cards[0]["🛎️文章简介"])
        self.assertIsNone(detail["summary_variants"]["detailed"])

    def test_two_invalid_summaries_still_cannot_publish_a_blank_card(self) -> None:
        parsed, source = data_service._parse_summary_for_display(
            "笔记标题：只有标题", "KTH：也只有标题", "2608.00001"
        )
        self.assertIsNone(parsed)
        self.assertEqual(source, "")

    def test_valid_concise_summary_remains_preferred(self) -> None:
        raw = "详细标题\n🛎️文章简介\n🔸研究问题：详细问题"
        concise = "简短标题\n🛎️文章简介\n🔸研究问题：简短问题"
        parsed, source = data_service._parse_summary_for_display(raw, concise, "2608.00001")
        self.assertEqual(source, concise)
        self.assertEqual(parsed["🛎️文章简介"]["🔸研究问题"], "简短问题")

    def test_incomplete_db_batch_does_not_fall_back_to_partial_files(self) -> None:
        with (
            patch.object(pipeline_db_service, "has_final_selections", return_value=True),
            patch.object(pipeline_db_service, "get_date_notice", return_value=None),
            patch.object(
                pipeline_db_service,
                "is_digest_ready_for_publication",
                return_value=False,
            ),
            patch.object(pipeline_db_service, "get_digest_papers") as get_digest,
        ):
            result = data_service._get_papers_from_db(self.date_str, user_id=3)

        self.assertEqual(result, [])
        get_digest.assert_not_called()

    def test_incomplete_personalized_batch_uses_complete_default_batch(self) -> None:
        digest_row = {
            "paper_id": "2608.00001",
            "title": "Complete default paper",
            "summary_raw": "",
            "summary_limit": (
                "📖标题：Complete default paper\n\n"
                "🛎️文章简介\n"
                "🔸研究问题：测试问题\n"
                "🔸主要贡献：测试贡献\n"
            ),
            "institution": "",
            "is_large_institution": False,
            "institution_tier": 4,
            "abstract": "abstract",
            "relevance_score": 0.9,
            "headline": "headline",
            "paper_assets": {"blocks": {"summary": "ready"}},
            "is_personalized": False,
            "pipeline_user_id": 0,
            "authors": [],
            "categories": [],
        }

        def ready(user_id: int, _date: str) -> bool:
            return user_id == 0

        with (
            patch.object(pipeline_db_service, "has_final_selections", return_value=True),
            patch.object(pipeline_db_service, "get_date_notice", return_value=None),
            patch.object(
                pipeline_db_service,
                "is_digest_ready_for_publication",
                side_effect=ready,
            ),
            patch.object(
                pipeline_db_service,
                "get_digest_papers",
                return_value=[digest_row],
            ) as get_digest,
            patch.object(pipeline_db_service, "get_paper_images", return_value={}),
        ):
            result = data_service._get_papers_from_db(self.date_str, user_id=3)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pipeline_user_id"], 0)
        get_digest.assert_called_once_with(0, self.date_str, fallback_user_id=0)

    def test_explicit_personalized_empty_notice_does_not_fall_back_to_default(self) -> None:
        def has_final(user_id: int, _date: str) -> bool:
            return user_id == 0

        def notice(user_id: int, _date: str):
            return {"type": "no_papers_empty"} if user_id == 3 else None

        with (
            patch.object(
                pipeline_db_service,
                "has_final_selections",
                side_effect=has_final,
            ),
            patch.object(
                pipeline_db_service,
                "get_date_notice",
                side_effect=notice,
            ),
            patch.object(
                pipeline_db_service,
                "is_digest_ready_for_publication",
                return_value=True,
            ),
            patch.object(pipeline_db_service, "get_digest_papers") as get_digest,
        ):
            result = data_service._get_papers_from_db(self.date_str, user_id=3)

        self.assertEqual(result, [])
        get_digest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
