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


if __name__ == "__main__":
    unittest.main()
