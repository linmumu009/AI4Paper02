from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import paper_resource_service  # noqa: E402


class PaperResourceServiceTests(unittest.TestCase):
    def _status(
        self,
        *,
        paper_id: str = "2601.00001",
        shared_pdf: bool = False,
        shared_mineru: bool = False,
        private_pdf: bool = False,
        saved: bool = False,
        process_status: str = "none",
    ) -> dict:
        derivative_paths = {
            "mineru": "missing-mineru.md",
            "mineru_normalized": "missing-normalized.md",
        }
        with (
            patch.object(
                paper_resource_service.kb_service,
                "_find_pdf_in_file_collect",
                return_value=Path("shared.pdf") if shared_pdf else None,
            ),
            patch.object(
                paper_resource_service.kb_service,
                "_find_mineru_in_file_collect",
                return_value=Path("shared.md") if shared_mineru else None,
            ),
            patch.object(
                paper_resource_service.kb_service,
                "get_kb_pdf_path",
                return_value="private.pdf" if private_pdf else None,
            ),
            patch.object(
                paper_resource_service.kb_service,
                "get_kb_paper",
                return_value={"process_status": process_status} if saved else None,
            ),
            patch.object(
                paper_resource_service.translate_service,
                "kb_paper_derivative_paths",
                return_value=derivative_paths,
            ),
            patch.object(paper_resource_service.os.path, "isfile", return_value=False),
        ):
            return paper_resource_service.get_resource_status(7, paper_id)

    def test_expired_arxiv_paper_can_be_saved_and_reprocessed(self) -> None:
        status = self._status()

        self.assertEqual(status["state"], "expired")
        self.assertTrue(status["recoverable"])
        self.assertEqual(status["action"], "save_and_reprocess")

    def test_saved_pdf_without_mineru_can_be_reprocessed(self) -> None:
        status = self._status(private_pdf=True, saved=True)

        self.assertEqual(status["state"], "partial")
        self.assertTrue(status["local_pdf_available"])
        self.assertFalse(status["mineru_available"])
        self.assertEqual(status["action"], "reprocess")

    def test_user_created_idea_never_triggers_arxiv_download(self) -> None:
        status = self._status(paper_id="idea_12")

        self.assertFalse(status["recoverable"])
        self.assertEqual(status["action"], "none")
        self.assertFalse(paper_resource_service.is_recoverable_arxiv_id("2601.00001.pdf"))

    def test_running_recovery_is_visible_after_page_reload(self) -> None:
        status = self._status(saved=True, process_status="processing")

        self.assertEqual(status["state"], "recovering")
        self.assertEqual(status["action"], "reprocess")

    def test_existing_non_arxiv_pdf_can_still_be_reparsed(self) -> None:
        status = self._status(
            paper_id="legacy-paper",
            private_pdf=True,
            saved=True,
        )

        self.assertTrue(status["recoverable"])
        self.assertEqual(status["action"], "reprocess")


if __name__ == "__main__":
    unittest.main()
