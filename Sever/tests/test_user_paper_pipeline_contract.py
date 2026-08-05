from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import user_paper_pipeline_service, user_paper_service
from services.llm_response_guard import EmptyLlmResponseError


class UserPaperPipelineContractTests(unittest.TestCase):
    def test_empty_assets_fail_task_without_persisting_blank_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_path = root / "user_papers" / "7" / "paper-1" / "paper.pdf"
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"test pdf placeholder")
            paper = {
                "paper_id": "paper-1",
                "user_id": 7,
                "source_type": "pdf",
                "source_ref": "",
                "title": "Uploaded paper",
                "abstract": "Existing abstract",
                "institution": "",
                "pdf_path": "user_papers/7/paper-1/paper.pdf",
                "external_url": "",
                "year": 2026,
            }
            status_calls = []
            update_calls = []

            with (
                patch.object(user_paper_service, "_KB_FILES_DIR", str(root)),
                patch.object(user_paper_service, "_USER_PAPERS_DIR", str(root / "user_papers")),
                patch.object(user_paper_service, "get_paper", return_value=paper),
                patch.object(
                    user_paper_service,
                    "set_process_status",
                    side_effect=lambda *args, **kwargs: status_calls.append(kwargs),
                ),
                patch.object(
                    user_paper_service,
                    "update_summary_and_assets",
                    side_effect=lambda *args, **kwargs: update_calls.append(kwargs),
                ),
                patch.object(user_paper_pipeline_service, "_get_mineru_token", return_value=""),
                patch.object(
                    user_paper_pipeline_service,
                    "_extract_text_pymupdf",
                    return_value="Extracted paper text",
                ),
                patch.object(
                    user_paper_pipeline_service,
                    "_run_pdf_info",
                    return_value={
                        "instution": "Example University",
                        "abstract": "Extracted abstract",
                        "is_large": False,
                    },
                ),
                patch.object(
                    user_paper_pipeline_service,
                    "_run_paper_summary",
                    return_value="标题\n\n🛎️文章简介\n🔸研究问题：测试",
                ),
                patch.object(
                    user_paper_pipeline_service,
                    "_run_summary_limit",
                    return_value=("标题\n\n🛎️文章简介\n🔸研究问题：测试", "copied"),
                ),
                patch.object(
                    user_paper_pipeline_service,
                    "_run_paper_assets",
                    side_effect=EmptyLlmResponseError("empty assets"),
                ),
            ):
                user_paper_pipeline_service.process_single_paper(7, "paper-1")

        self.assertEqual(status_calls[-1]["status"], "failed")
        self.assertEqual(status_calls[-1]["step"], "paper_assets")
        self.assertTrue(status_calls[-1]["error"])
        self.assertFalse(
            any("paper_assets_json" in update for update in update_calls)
        )
        self.assertTrue(any("summary_json" in update for update in update_calls))


if __name__ == "__main__":
    unittest.main()
