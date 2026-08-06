from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services.user_paper_public_response import (  # noqa: E402
    has_renderable_summary,
    normalize_public_user_paper_state,
)


_ROUTER = _SEVER / "routers" / "user_paper_router.py"


def _function_source(name: str) -> str:
    source = _ROUTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"function {name} not found")


class UserPaperPublicResponseTests(unittest.TestCase):
    def test_completed_empty_summary_becomes_actionable_failure(self) -> None:
        result = normalize_public_user_paper_state(
            {
                "process_status": "completed",
                "process_step": "done",
                "process_error": "",
                "summary": {"short_title": "metadata only", "abstract": "abstract"},
                "translate_status": "none",
            },
            translation_available=False,
        )

        self.assertEqual(result["process_status"], "failed")
        self.assertEqual(result["process_step"], "paper_summary")
        self.assertEqual(result["process_error"], "论文内容暂不可用，请重新处理")

    def test_renderable_current_and_legacy_summaries_remain_completed(self) -> None:
        summaries = (
            {"🛎️文章简介": {"🔸研究问题": "question"}},
            {"📝重点思路": ["idea"]},
            {"summary": "legacy insight"},
            {"one_sentence_summary": "legacy takeaway"},
        )
        for summary in summaries:
            with self.subTest(summary=summary):
                self.assertTrue(has_renderable_summary(summary))
                result = normalize_public_user_paper_state(
                    {
                        "process_status": "completed",
                        "process_error": "",
                        "summary": summary,
                    },
                    translation_available=False,
                )
                self.assertEqual(result["process_status"], "completed")

    def test_in_progress_empty_summary_is_not_reclassified(self) -> None:
        result = normalize_public_user_paper_state(
            {"process_status": "processing", "summary": None},
            translation_available=False,
        )
        self.assertEqual(result["process_status"], "processing")

    def test_completed_translation_without_files_becomes_retryable_failure(self) -> None:
        result = normalize_public_user_paper_state(
            {
                "process_status": "none",
                "translate_status": "completed",
                "translate_error": "",
            },
            translation_available=False,
        )
        self.assertEqual(result["translate_status"], "failed")
        self.assertEqual(result["translate_error"], "翻译文件暂不可用，请重新翻译")

    def test_completed_translation_with_file_remains_completed(self) -> None:
        result = normalize_public_user_paper_state(
            {"process_status": "none", "translate_status": "completed"},
            translation_available=True,
        )
        self.assertEqual(result["translate_status"], "completed")

    def test_all_paper_return_endpoints_use_the_same_enrichment_contract(self) -> None:
        for function_name in (
            "api_user_paper_import_manual",
            "api_user_paper_import_arxiv",
            "api_user_paper_import_pdf",
            "api_user_paper_update",
            "api_user_paper_upload_pdf",
        ):
            with self.subTest(function=function_name):
                self.assertIn("_enrich_user_paper", _function_source(function_name))

    def test_status_and_file_endpoints_use_normalized_availability(self) -> None:
        self.assertIn(
            "paper = _normalize_user_paper_process_state(paper)",
            _function_source("api_user_paper_process_status"),
        )
        self.assertIn(
            "paper = _normalize_user_paper_translate_state(paper)",
            _function_source("api_user_paper_translate_status"),
        )
        files = _function_source("api_user_paper_files")
        self.assertIn('bool(enriched.get("pdf_static_url"))', files)

    def test_status_normalizers_avoid_full_response_enrichment(self) -> None:
        process_status = _function_source("api_user_paper_process_status")
        translate_status = _function_source("api_user_paper_translate_status")
        self.assertNotIn("_enrich_user_paper(", process_status)
        self.assertNotIn("_enrich_user_paper(", translate_status)


if __name__ == "__main__":
    unittest.main()
