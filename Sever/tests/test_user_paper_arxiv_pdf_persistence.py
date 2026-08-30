from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import user_paper_pipeline_service, user_paper_service  # noqa: E402


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.chunk_size: int | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        self.chunk_size = chunk_size
        for offset in range(0, len(self.payload), chunk_size):
            yield self.payload[offset:offset + chunk_size]


class _Session:
    def __init__(self, response: _Response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def get(self, *_args, **_kwargs):
        return self.response


class UserPaperArxivPdfPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.files_root = self.root / "kb_files"
        self.user_papers_root = self.files_root / "user_papers"
        self.patches = (
            patch.object(user_paper_service, "_DB_PATH", str(self.root / "papers.db")),
            patch.object(user_paper_service, "_KB_DB_PATH", str(self.root / "analysis.db")),
            patch.object(user_paper_service, "_KB_FILES_DIR", str(self.files_root)),
            patch.object(user_paper_service, "_USER_PAPERS_DIR", str(self.user_papers_root)),
        )
        for active_patch in self.patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        user_paper_service.init_db()
        self.paper = user_paper_service.create_paper(
            7,
            source_type="arxiv",
            source_ref="2608.00001",
            title="paper",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _valid_pdf() -> bytes:
        import fitz

        document = fitz.open()
        try:
            document.new_page()
            return document.tobytes()
        finally:
            document.close()

    def test_download_read_is_bounded_and_oversize_is_rejected(self) -> None:
        response = _Response(b"123456")
        with (
            patch(
                "Controller.http_session.build_session",
                return_value=_Session(response),
            ),
            patch("services.arxiv_rate_limit.wait_before_request"),
        ):
            result = user_paper_pipeline_service._download_arxiv_pdf(
                "2608.00001",
                max_bytes=5,
            )

        self.assertIsNone(result)
        self.assertEqual(response.chunk_size, 64 * 1024)

    def test_invalid_response_is_never_persisted(self) -> None:
        with (
            patch.object(
                user_paper_pipeline_service,
                "_download_arxiv_pdf",
                return_value=b"<html>temporary upstream error</html>" * 100,
            ),
            patch.object(user_paper_service, "update_paper") as update,
        ):
            result = user_paper_pipeline_service._download_and_attach_arxiv_pdf(
                7,
                self.paper["paper_id"],
                "2608.00001",
            )

        self.assertIsNone(result)
        update.assert_not_called()
        self.assertIsNone(
            user_paper_service.get_paper(7, self.paper["paper_id"])["pdf_path"]
        )

    def test_valid_response_is_attached_through_transactional_service(self) -> None:
        payload = self._valid_pdf()
        with patch.object(
            user_paper_pipeline_service,
            "_download_arxiv_pdf",
            return_value=payload,
        ):
            path = user_paper_pipeline_service._download_and_attach_arxiv_pdf(
                7,
                self.paper["paper_id"],
                "2608.00001",
            )

        self.assertIsNotNone(path)
        self.assertEqual(Path(path).read_bytes(), payload)
        stored = user_paper_service.get_paper(7, self.paper["paper_id"])
        self.assertIsNotNone(stored["pdf_path"])
        self.assertEqual(
            Path(path).resolve(),
            (self.files_root / stored["pdf_path"]).resolve(),
        )

    def test_pipeline_stops_before_llm_when_pdf_cannot_be_prepared(self) -> None:
        with (
            patch.object(
                user_paper_pipeline_service,
                "_download_and_attach_arxiv_pdf",
                return_value=None,
            ),
            patch.object(
                user_paper_pipeline_service,
                "_run_pdf_info",
                Mock(side_effect=AssertionError("LLM should not run")),
            ),
        ):
            user_paper_pipeline_service.process_single_paper(
                7,
                self.paper["paper_id"],
            )

        stored = user_paper_service.get_paper(7, self.paper["paper_id"])
        self.assertEqual(stored["process_status"], "failed")
        self.assertEqual(stored["process_step"], "pdf_prepare")
        self.assertIn("无法获取 PDF", stored["process_error"])
        self.assertIsNone(stored["pdf_path"])


if __name__ == "__main__":
    unittest.main()
