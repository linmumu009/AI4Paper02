from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import pdf_cleanup_service  # noqa: E402


class PdfCleanupServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "data"
        self.state_path = Path(self.temp_dir.name) / "state" / "cleanup.json"
        self.root.mkdir(parents=True)
        self.root_patch = patch.object(pdf_cleanup_service, "_DATA_ROOT", self.root)
        self.state_patch = patch.object(
            pdf_cleanup_service,
            "_STATE_PATH",
            str(self.state_path),
        )
        self.root_patch.start()
        self.state_patch.start()

    def tearDown(self) -> None:
        self.state_patch.stop()
        self.root_patch.stop()
        self.temp_dir.cleanup()

    def _write_file(self, relative: str, content: bytes = b"cache") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _write_bundle(self, source: str, paper_id: str, content: bytes = b"bundle") -> Path:
        path = self.root / source / "2000-01-01" / paper_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "result.md").write_bytes(content)
        return path

    def test_preview_counts_pdf_and_mineru_without_deleting(self) -> None:
        raw = self._write_file("raw_pdf/2000-01-01/2601.00001.pdf", b"pdf")
        file_collect = self._write_bundle("file_collect", "2601.00001")
        mineru = self._write_bundle("full_mineru_cache", "2601.00002", b"mineru")
        selected = self._write_bundle("selectedpaper_to_mineru", "2601.00003")

        with patch.object(pdf_cleanup_service, "_get_saved_paper_ids", return_value=set()):
            result = pdf_cleanup_service.run_cleanup(retention_days=14, dry_run=True)

        self.assertEqual(result["scanned"], 4)
        self.assertEqual(result["deletable"], 4)
        self.assertEqual(result["deleted"], 0)
        self.assertGreater(result["reclaimable_bytes"], 0)
        self.assertEqual(result["freed_bytes"], result["reclaimable_bytes"])
        self.assertEqual(result["sources"]["full_mineru_cache"]["deletable"], 1)
        self.assertTrue(raw.exists())
        self.assertTrue(file_collect.exists())
        self.assertTrue(mineru.exists())
        self.assertTrue(selected.exists())

    def test_actual_cleanup_deletes_only_expired_unsaved_targets(self) -> None:
        unsaved_pdf = self._write_file("raw_pdf/2000-01-01/2601.00001.pdf")
        saved_pdf = self._write_file("raw_pdf/2000-01-01/2601.00002.pdf")
        unsaved_mineru = self._write_bundle("full_mineru_cache", "2601.00001")
        saved_mineru = self._write_bundle("full_mineru_cache", "2601.00002")
        recent_mineru = self.root / "file_collect" / "2999-01-01" / "2601.00003"
        recent_mineru.mkdir(parents=True)
        (recent_mineru / "result.md").write_text("recent", encoding="utf-8")

        with patch.object(
            pdf_cleanup_service,
            "_get_saved_paper_ids",
            return_value={"2601.00002"},
        ):
            result = pdf_cleanup_service.run_cleanup(retention_days=14, dry_run=False)

        self.assertEqual(result["scanned"], 5)
        self.assertEqual(result["deletable"], 2)
        self.assertEqual(result["deleted"], 2)
        self.assertEqual(result["skipped_saved"], 2)
        self.assertEqual(result["skipped_recent"], 1)
        self.assertFalse(unsaved_pdf.exists())
        self.assertFalse(unsaved_mineru.exists())
        self.assertTrue(saved_pdf.exists())
        self.assertTrue(saved_mineru.exists())
        self.assertTrue(recent_mineru.exists())
        self.assertEqual(
            pdf_cleanup_service._load_state()["last_success_date"],
            pdf_cleanup_service.datetime.now().date().isoformat(),
        )

    def test_saved_paper_lookup_failure_is_fail_closed(self) -> None:
        target = self._write_file("raw_pdf/2000-01-01/2601.00001.pdf")

        with (
            patch.object(
                pdf_cleanup_service,
                "_get_saved_paper_ids",
                side_effect=pdf_cleanup_service.CleanupSafetyError("database unavailable"),
            ),
            self.assertRaises(pdf_cleanup_service.CleanupSafetyError),
        ):
            pdf_cleanup_service.run_cleanup(retention_days=14, dry_run=False)

        self.assertTrue(target.exists())
        self.assertFalse(self.state_path.exists())

    def test_delete_error_is_not_counted_or_marked_successful(self) -> None:
        target = self._write_file("raw_pdf/2000-01-01/2601.00001.pdf")

        with (
            patch.object(pdf_cleanup_service, "_get_saved_paper_ids", return_value=set()),
            patch.object(pdf_cleanup_service, "_delete_target", side_effect=OSError("locked")),
        ):
            result = pdf_cleanup_service.run_cleanup(retention_days=14, dry_run=False)

        self.assertEqual(result["deletable"], 1)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertTrue(target.exists())
        self.assertNotIn("last_success_date", pdf_cleanup_service._load_state())


if __name__ == "__main__":
    unittest.main()
