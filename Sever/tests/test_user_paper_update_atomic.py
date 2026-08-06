from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import user_paper_service  # noqa: E402


class UserPaperUpdateAtomicTests(unittest.TestCase):
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
            source_type="pdf",
            title="paper",
            pdf_bytes=b"%PDF-old%%EOF",
            pdf_filename="old.pdf",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _absolute(self, relative_path: str) -> Path:
        return self.files_root / relative_path

    def test_success_commits_new_version_then_removes_old_file(self) -> None:
        old_path = self._absolute(self.paper["pdf_path"])
        updated = user_paper_service.update_paper(
            7,
            self.paper["paper_id"],
            pdf_bytes=b"%PDF-new%%EOF",
            pdf_filename="replacement.pdf",
        )

        self.assertIsNotNone(updated)
        new_path = self._absolute(updated["pdf_path"])
        self.assertNotEqual(old_path, new_path)
        self.assertEqual(new_path.read_bytes(), b"%PDF-new%%EOF")
        self.assertFalse(old_path.exists())
        self.assertEqual(
            user_paper_service.get_paper(7, self.paper["paper_id"])["pdf_path"],
            updated["pdf_path"],
        )
        self.assertEqual(list(new_path.parent.glob(".pending-pdf-*")), [])

    def test_database_failure_keeps_old_file_and_removes_new_version(self) -> None:
        old_path = self._absolute(self.paper["pdf_path"])
        connection = user_paper_service._connect()
        try:
            connection.executescript(
                """
                CREATE TRIGGER reject_paper_update
                BEFORE UPDATE ON user_uploaded_papers
                BEGIN
                    SELECT RAISE(ABORT, 'forced update failure');
                END;
                """
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(sqlite3.IntegrityError):
            user_paper_service.update_paper(
                7,
                self.paper["paper_id"],
                pdf_bytes=b"%PDF-new%%EOF",
                pdf_filename="replacement.pdf",
            )

        current = user_paper_service.get_paper(7, self.paper["paper_id"])
        self.assertEqual(current["pdf_path"], self.paper["pdf_path"])
        self.assertEqual(old_path.read_bytes(), b"%PDF-old%%EOF")
        self.assertEqual(list(old_path.parent.glob("replacement.*.pdf")), [])
        self.assertEqual(list(old_path.parent.glob(".pending-pdf-*")), [])

    def test_atomic_replace_failure_keeps_old_file_and_database_path(self) -> None:
        old_path = self._absolute(self.paper["pdf_path"])
        with patch.object(os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                user_paper_service.update_paper(
                    7,
                    self.paper["paper_id"],
                    pdf_bytes=b"%PDF-new%%EOF",
                    pdf_filename="replacement.pdf",
                )

        current = user_paper_service.get_paper(7, self.paper["paper_id"])
        self.assertEqual(current["pdf_path"], self.paper["pdf_path"])
        self.assertEqual(old_path.read_bytes(), b"%PDF-old%%EOF")
        self.assertEqual(list(old_path.parent.glob("replacement.*.pdf")), [])
        self.assertEqual(list(old_path.parent.glob(".pending-pdf-*")), [])


if __name__ == "__main__":
    unittest.main()
