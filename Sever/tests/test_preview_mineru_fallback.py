from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from Controller import pdfsplite_to_minerU, selectedpaper_to_mineru  # noqa: E402


class PreviewMineruFallbackTests(unittest.TestCase):
    @staticmethod
    def _write_pdf(path: Path, text: str) -> None:
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), text)
        doc.save(str(path))
        doc.close()

    def test_api_start_failure_falls_back_to_pymupdf_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preview_root = root / "preview"
            output_root = root / "output"
            date_dir = preview_root / "2026-08-06"
            date_dir.mkdir(parents=True)
            pdf_path = date_dir / "2608.00001.pdf"

            self._write_pdf(pdf_path, "Fallback abstract text")

            manifest_path = date_dir / "_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "date": "2026-08-06",
                        "items": [
                            {
                                "status": "created",
                                "preview_pdf": str(pdf_path),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(pdfsplite_to_minerU, "PDF_PREVIEW_DIR", str(preview_root)),
                patch.object(pdfsplite_to_minerU, "PREVIEW_MINERU_DIR", str(output_root)),
                patch.object(pdfsplite_to_minerU, "minerU_Token", ""),
                patch.object(
                    pdfsplite_to_minerU.MinerUClient,
                    "apply_upload_urls",
                    side_effect=RuntimeError("private upstream detail"),
                ) as apply_upload_urls,
                patch.object(sys, "argv", ["pdfsplite_to_minerU.py"]),
            ):
                pdfsplite_to_minerU.run()

            apply_upload_urls.assert_not_called()
            markdown_path = output_root / "2026-08-06" / "2608.00001.md"
            self.assertIn(
                "Fallback abstract text", markdown_path.read_text(encoding="utf-8")
            )
            output_manifest = json.loads(
                (output_root / "2026-08-06" / "_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(output_manifest["total"], 1)
            self.assertEqual(output_manifest["items"][0]["status"], "fallback_pymupdf")

    def test_resumed_batch_wait_failure_falls_back_to_pymupdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preview_root = root / "preview"
            output_root = root / "output"
            date_dir = preview_root / "2026-08-06"
            date_dir.mkdir(parents=True)
            pdf_path = date_dir / "2608.00003.pdf"
            self._write_pdf(pdf_path, "Recovered after stale MinerU batch")
            (date_dir / "_manifest.json").write_text(
                json.dumps(
                    {
                        "date": "2026-08-06",
                        "items": [
                            {"status": "created", "preview_pdf": str(pdf_path)}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(pdfsplite_to_minerU, "PDF_PREVIEW_DIR", str(preview_root)),
                patch.object(pdfsplite_to_minerU, "PREVIEW_MINERU_DIR", str(output_root)),
                patch.object(pdfsplite_to_minerU, "minerU_Token", "configured-token"),
                patch.object(
                    pdfsplite_to_minerU,
                    "find_resumable_batch",
                    return_value={"batch_id": "stale-batch"},
                ),
                patch.object(
                    pdfsplite_to_minerU,
                    "wait_batch_done",
                    side_effect=RuntimeError("private upstream detail"),
                ),
                patch.object(sys, "argv", ["pdfsplite_to_minerU.py"]),
            ):
                pdfsplite_to_minerU.run()

            markdown_path = output_root / "2026-08-06" / "2608.00003.md"
            self.assertIn(
                "Recovered after stale MinerU batch",
                markdown_path.read_text(encoding="utf-8"),
            )
            output_manifest = json.loads(
                (output_root / "2026-08-06" / "_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(output_manifest["items"][0]["status"], "fallback_pymupdf")

    def test_presigned_upload_failure_marks_batch_terminal_and_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preview_root = root / "preview"
            output_root = root / "output"
            date_dir = preview_root / "2026-08-06"
            date_dir.mkdir(parents=True)
            pdf_path = date_dir / "2608.00005.pdf"
            self._write_pdf(pdf_path, "Recovered after upload failure")
            (date_dir / "_manifest.json").write_text(
                json.dumps(
                    {
                        "date": "2026-08-06",
                        "items": [
                            {"status": "created", "preview_pdf": str(pdf_path)}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(pdfsplite_to_minerU, "PDF_PREVIEW_DIR", str(preview_root)),
                patch.object(pdfsplite_to_minerU, "PREVIEW_MINERU_DIR", str(output_root)),
                patch.object(pdfsplite_to_minerU, "minerU_Token", "configured-token"),
                patch.object(
                    pdfsplite_to_minerU.MinerUClient,
                    "apply_upload_urls",
                    return_value={
                        "code": 0,
                        "data": {
                            "batch_id": "upload-failed-batch",
                            "file_urls": ["https://example.invalid/upload"],
                        },
                    },
                ),
                patch.object(
                    pdfsplite_to_minerU,
                    "upload_to_presigned_url",
                    side_effect=RuntimeError("private upstream detail"),
                ),
                patch.object(sys, "argv", ["pdfsplite_to_minerU.py"]),
            ):
                pdfsplite_to_minerU.run()

            markdown_path = output_root / "2026-08-06" / "2608.00005.md"
            self.assertIn(
                "Recovered after upload failure",
                markdown_path.read_text(encoding="utf-8"),
            )
            batch_state = json.loads(
                (output_root / "2026-08-06" / "_batch_state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(batch_state["batches"][0]["status"], "fallback")

    def test_full_text_api_start_failure_preserves_cache_directory_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected_root = root / "selected"
            output_root = root / "full_cache"
            date_dir = selected_root / "2026-08-06"
            date_dir.mkdir(parents=True)
            pdf_path = date_dir / "2608.00002.pdf"
            self._write_pdf(pdf_path, "Fallback full paper text")

            with (
                patch.object(selectedpaper_to_mineru, "minerU_Token", "configured-token"),
                patch.object(
                    selectedpaper_to_mineru.MinerUClient,
                    "apply_upload_urls",
                    side_effect=RuntimeError("private upstream detail"),
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        "selectedpaper_to_mineru.py",
                        "--in-root",
                        str(selected_root),
                        "--outdir",
                        str(output_root),
                    ],
                ),
            ):
                selectedpaper_to_mineru.run()

            markdown_path = (
                output_root / "2026-08-06" / "2608.00002" / "2608.00002.md"
            )
            self.assertIn(
                "Fallback full paper text", markdown_path.read_text(encoding="utf-8")
            )
            output_manifest = json.loads(
                (output_root / "2026-08-06" / "_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(output_manifest["items"][0]["status"], "fallback_pymupdf")

    def test_full_text_resumed_batch_wait_failure_uses_local_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected_root = root / "selected"
            output_root = root / "full_cache"
            date_dir = selected_root / "2026-08-06"
            date_dir.mkdir(parents=True)
            pdf_path = date_dir / "2608.00004.pdf"
            self._write_pdf(pdf_path, "Recovered full paper text")

            with (
                patch.object(selectedpaper_to_mineru, "minerU_Token", "configured-token"),
                patch.object(
                    selectedpaper_to_mineru,
                    "find_resumable_batch",
                    return_value={"batch_id": "stale-batch"},
                ),
                patch.object(
                    selectedpaper_to_mineru,
                    "wait_batch_done",
                    side_effect=RuntimeError("private upstream detail"),
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        "selectedpaper_to_mineru.py",
                        "--in-root",
                        str(selected_root),
                        "--outdir",
                        str(output_root),
                    ],
                ),
            ):
                selectedpaper_to_mineru.run()

            markdown_path = (
                output_root / "2026-08-06" / "2608.00004" / "2608.00004.md"
            )
            self.assertIn(
                "Recovered full paper text", markdown_path.read_text(encoding="utf-8")
            )
            output_manifest = json.loads(
                (output_root / "2026-08-06" / "_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(output_manifest["items"][0]["status"], "fallback_pymupdf")

    def test_full_text_result_download_failure_uses_local_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected_root = root / "selected"
            output_root = root / "full_cache"
            date_dir = selected_root / "2026-08-06"
            date_dir.mkdir(parents=True)
            pdf_path = date_dir / "2608.00006.pdf"
            self._write_pdf(pdf_path, "Recovered after result download failure")

            with (
                patch.object(selectedpaper_to_mineru, "minerU_Token", "configured-token"),
                patch.object(
                    selectedpaper_to_mineru,
                    "find_resumable_batch",
                    return_value={"batch_id": "ready-batch"},
                ),
                patch.object(
                    selectedpaper_to_mineru,
                    "wait_batch_done",
                    return_value=[
                        {
                            "data_id": "2608.00006",
                            "state": "done",
                            "full_zip_url": "https://example.invalid/result.zip",
                        }
                    ],
                ),
                patch.object(
                    selectedpaper_to_mineru,
                    "download_zip",
                    side_effect=RuntimeError("private upstream detail"),
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        "selectedpaper_to_mineru.py",
                        "--in-root",
                        str(selected_root),
                        "--outdir",
                        str(output_root),
                    ],
                ),
            ):
                selectedpaper_to_mineru.run()

            markdown_path = (
                output_root / "2026-08-06" / "2608.00006" / "2608.00006.md"
            )
            self.assertIn(
                "Recovered after result download failure",
                markdown_path.read_text(encoding="utf-8"),
            )
            output_manifest = json.loads(
                (output_root / "2026-08-06" / "_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(output_manifest["items"][0]["status"], "fallback_pymupdf")


if __name__ == "__main__":
    unittest.main()
