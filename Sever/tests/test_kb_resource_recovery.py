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

from services import kb_pipeline_service  # noqa: E402


class KbResourceRecoveryTests(unittest.TestCase):
    def test_invalid_id_is_rejected_before_loading_downloader(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "arXiv"):
            kb_pipeline_service._recover_pdf_from_arxiv(7, "idea_12")

    def test_valid_arxiv_pdf_is_written_to_durable_kb_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session = object()

            def fake_download(_session, paper_id, destination, _logger, **_kwargs):
                self.assertIs(_session, session)
                Path(destination).write_bytes(b"%PDF-test%%EOF")
                return SimpleNamespace(ok=True, out_path=destination, arxiv_id=paper_id)

            with (
                patch.object(kb_pipeline_service, "_SEVER_DIR", temp_dir),
                patch("Controller.http_session.build_session", return_value=session),
                patch("Controller.pdf_download.download_one_pdf", side_effect=fake_download),
            ):
                recovered = kb_pipeline_service._recover_pdf_from_arxiv(7, "2601.00001")

            expected = Path(temp_dir) / "data" / "kb_files" / "7" / "2601.00001" / "2601.00001.pdf"
            self.assertEqual(Path(recovered), expected)
            self.assertTrue(expected.is_file())


if __name__ == "__main__":
    unittest.main()
