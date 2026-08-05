"""Regression tests for publishable summary handling."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import data_service, pipeline_db_service  # noqa: E402
from services.llm_summary_response import create_nonempty_completion  # noqa: E402


def _response(content, *, finish_reason="stop", response_id="resp-test"):
    choices = [] if content is ... else [
        SimpleNamespace(
            message=SimpleNamespace(content=content),
            finish_reason=finish_reason,
        )
    ]
    return SimpleNamespace(choices=choices, id=response_id, model="test-model")


class _Completions:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(*outcomes):
    completions = _Completions(outcomes)
    return SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        completions_spy=completions,
    )


class TestSummaryResponseGuard(unittest.TestCase):
    def test_retries_empty_choices_then_returns_content(self):
        client = _client(_response(...), _response(None), _response("摘要正文"))
        sleeps = []

        result = create_nonempty_completion(
            client,
            request_kwargs={"model": "test"},
            paper_id="2608.02502",
            sleep=sleeps.append,
            logger=lambda _message: None,
        )

        self.assertEqual(result, "摘要正文")
        self.assertEqual(client.completions_spy.calls, 3)
        self.assertEqual(sleeps, [1.0, 2.0])

    def test_retries_non_publishable_content_and_raises(self):
        client = _client(_response("抱歉"), _response("仍然无结构"))

        with self.assertRaisesRegex(RuntimeError, "no publishable content"):
            create_nonempty_completion(
                client,
                request_kwargs={"model": "test"},
                max_attempts=2,
                sleep=lambda _seconds: None,
                logger=lambda _message: None,
                content_validator=lambda text: "🛎️文章简介" in text,
            )


class TestDigestPublicationGuard(unittest.TestCase):
    def test_digest_uses_arxiv_title_when_pdf_info_title_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "paper_analysis.db")
            with patch.object(pipeline_db_service, "_DB_PATH", db_path):
                pipeline_db_service.init_db()
                pipeline_db_service.bulk_upsert_arxiv_list(
                    "2026-08-05",
                    [{
                        "paper_arxiv_id": "2608.02502",
                        "title": "CMuon",
                        "abstract_text": "Abstract fallback",
                        "authors": ["Chuyan Chen"],
                        "categories": ["cs.LG"],
                    }],
                )
                pipeline_db_service.upsert_selected_paper(
                    0,
                    "2026-08-05",
                    "2608.02502",
                    passed_theme=True,
                    passed_institution=True,
                    is_final=True,
                )
                pipeline_db_service.upsert_summary_raw(
                    0, "2026-08-05", "2608.02502", "publishable summary"
                )

                papers = pipeline_db_service.get_digest_papers(0, "2026-08-05")

        self.assertEqual(papers[0]["title"], "CMuon")
        self.assertEqual(papers[0]["abstract"], "Abstract fallback")

    def test_hides_blank_cards_and_fills_title_fallback(self):
        complete = {
            "paper_id": "2608.02508",
            "title": "Fallback arXiv Title",
            "summary_limit": (
                "短标题\n\n🛎️文章简介\n"
                "🔸研究问题：测试问题\n🔸主要贡献：测试贡献\n"
            ),
        }
        blank = {
            "paper_id": "2608.02502",
            "title": "CMuon",
            "summary_limit": "",
            "summary_raw": "",
        }

        with (
            patch.object(pipeline_db_service, "has_final_selections", return_value=True),
            patch.object(pipeline_db_service, "get_digest_papers", return_value=[blank, complete]),
            patch.object(pipeline_db_service, "get_paper_images", return_value={}),
        ):
            result = data_service._get_papers_from_db("2026-08-05", user_id=0)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["paper_id"], "2608.02508")
        self.assertEqual(result[0]["📖标题"], "Fallback arXiv Title")
        self.assertEqual(result[0]["title"], "Fallback arXiv Title")
        self.assertEqual(result[0]["🌐来源"], "arXiv, 2608.02508")


if __name__ == "__main__":
    unittest.main()
