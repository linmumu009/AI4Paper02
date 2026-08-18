from __future__ import annotations

import argparse
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from Controller import pdf_info  # noqa: E402
from services import pipeline_db_service  # noqa: E402


class PdfInfoDbContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.date_str = "2026-08-05"
        self.preview = self.root / "preview" / self.date_str
        self.preview.mkdir(parents=True)
        (self.preview / "paper-a.md").write_text("PDF text A", encoding="utf-8")
        (self.preview / "paper-b.md").write_text("PDF text B", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            output_mode="db",
            user_id=34,
            in_md_root=str(self.root / "preview"),
            arxiv_json="",
            outdir=str(self.root / "out"),
            limit=None,
            concurrency=1,
            max_chars=120000,
        )

    def test_db_mode_processes_only_theme_passed_and_uses_arxiv_metadata(self) -> None:
        selected = [
            {"paper_arxiv_id": "paper-a", "passed_theme_filter": 1},
            {"paper_arxiv_id": "paper-b", "passed_theme_filter": 0},
        ]
        arxiv_rows = [
            {
                "paper_arxiv_id": "paper-a",
                "title": "Authoritative title",
                "abstract_text": "Authoritative abstract",
                "published_utc": "2026-08-05T00:00:00Z",
            },
            {
                "paper_arxiv_id": "paper-b",
                "title": "Filtered out",
                "abstract_text": "Filtered abstract",
                "published_utc": "2026-08-05T00:00:00Z",
            },
        ]
        cfg = {
            "system_prompt": "classify",
            "api_key": "test",
            "base_url": "https://example.invalid",
            "model": "test",
            "temperature": 0,
            "max_tokens": 20,
            "use_openrouter_free_pool": False,
        }
        with (
            patch.dict(os.environ, {"RUN_DATE": self.date_str}),
            patch.object(pipeline_db_service, "get_selected_papers", return_value=selected),
            patch.object(pipeline_db_service, "get_arxiv_list", return_value=arxiv_rows),
            patch.object(pipeline_db_service, "get_paper_info_map", return_value={}),
            patch.object(pipeline_db_service, "upsert_paper_info") as upsert,
            patch.object(pdf_info, "_resolve_llm_for_user", return_value=cfg),
            patch.object(
                pdf_info,
                "call_qwen",
                return_value='{"instution":"","is_large":false,"abstract":""}',
            ) as call_llm,
        ):
            pdf_info.run(self._args())

        call_llm.assert_called_once()
        self.assertEqual(upsert.call_count, 1)
        kwargs = upsert.call_args.kwargs
        self.assertEqual(kwargs["title"], "Authoritative title")
        self.assertEqual(kwargs["abstract"], "Authoritative abstract")
        self.assertFalse(kwargs["is_large"])

    def test_missing_preview_directory_fails_when_theme_passed_input_exists(self) -> None:
        missing_root = self.root / "missing"
        args = self._args()
        args.in_md_root = str(missing_root)
        selected = [{"paper_arxiv_id": "paper-a", "passed_theme_filter": 1}]
        with (
            patch.dict(os.environ, {"RUN_DATE": self.date_str}),
            patch.object(pipeline_db_service, "get_selected_papers", return_value=selected),
        ):
            with self.assertRaises(SystemExit):
                pdf_info.run(args)

    def test_partial_missing_preview_uses_arxiv_metadata_fallback(self) -> None:
        selected = [
            {"paper_arxiv_id": "paper-a", "passed_theme_filter": 1},
            {"paper_arxiv_id": "paper-missing", "passed_theme_filter": 1},
        ]
        arxiv_rows = [
            {
                "paper_arxiv_id": "paper-a",
                "title": "Available title",
                "abstract_text": "Available abstract",
                "published_utc": "2026-08-05T00:00:00Z",
            },
            {
                "paper_arxiv_id": "paper-missing",
                "title": "Fallback title",
                "abstract_text": "Fallback abstract",
                "published_utc": "2026-08-05T00:00:00Z",
            },
        ]
        cfg = {
            "system_prompt": "classify",
            "api_key": "test",
            "base_url": "https://example.invalid",
            "model": "test",
            "temperature": 0,
            "max_tokens": 20,
            "use_openrouter_free_pool": False,
        }
        with (
            patch.dict(os.environ, {"RUN_DATE": self.date_str}),
            patch.object(pipeline_db_service, "get_selected_papers", return_value=selected),
            patch.object(pipeline_db_service, "get_arxiv_list", return_value=arxiv_rows),
            patch.object(pipeline_db_service, "get_paper_info_map", return_value={}),
            patch.object(pipeline_db_service, "upsert_paper_info") as upsert,
            patch.object(pdf_info, "_resolve_llm_for_user", return_value=cfg),
            patch.object(
                pdf_info,
                "call_qwen",
                return_value='{"instution":"Lab","is_large":true,"abstract":""}',
            ) as call_llm,
        ):
            pdf_info.run(self._args())

        call_llm.assert_called_once()
        self.assertEqual(upsert.call_count, 2)
        fallback_call = next(
            call
            for call in upsert.call_args_list
            if call.args[2] == "paper-missing"
        )
        self.assertFalse(fallback_call.kwargs["is_large"])
        self.assertEqual(fallback_call.kwargs["institution_tier"], 4)
        self.assertEqual(
            fallback_call.kwargs["extra"]["source_status"],
            "preview_unavailable",
        )


if __name__ == "__main__":
    unittest.main()
