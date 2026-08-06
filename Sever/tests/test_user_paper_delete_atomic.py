from __future__ import annotations

import os
import shutil
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


class UserPaperDeleteAtomicTests(unittest.TestCase):
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
            pdf_bytes=b"%PDF-delete%%EOF",
            pdf_filename="paper.pdf",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @property
    def paper_dir(self) -> Path:
        return Path(user_paper_service._pdf_dir(7, self.paper["paper_id"]))

    @property
    def quarantine_root(self) -> Path:
        return Path(user_paper_service._pending_delete_root())

    def _move_to_quarantine(self) -> Path:
        quarantine = Path(
            user_paper_service._pending_delete_path(7, self.paper["paper_id"])
        )
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.paper_dir, quarantine)
        return quarantine

    def test_success_deletes_record_and_quarantined_files(self) -> None:
        self.assertTrue(user_paper_service.delete_paper(7, self.paper["paper_id"]))

        self.assertIsNone(user_paper_service.get_paper(7, self.paper["paper_id"]))
        self.assertFalse(self.paper_dir.exists())
        self.assertEqual(list(self.quarantine_root.glob("pending-delete-*")), [])

    def test_database_failure_restores_original_directory(self) -> None:
        connection = user_paper_service._connect()
        try:
            connection.executescript(
                """
                CREATE TRIGGER reject_paper_delete
                BEFORE DELETE ON user_uploaded_papers
                BEGIN
                    SELECT RAISE(ABORT, 'forced delete failure');
                END;
                """
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(sqlite3.IntegrityError):
            user_paper_service.delete_paper(7, self.paper["paper_id"])

        self.assertIsNotNone(user_paper_service.get_paper(7, self.paper["paper_id"]))
        self.assertEqual((self.paper_dir / "paper.pdf").read_bytes(), b"%PDF-delete%%EOF")
        self.assertEqual(list(self.quarantine_root.glob("pending-delete-*")), [])

    def test_startup_restores_quarantine_when_database_delete_did_not_commit(self) -> None:
        quarantine = self._move_to_quarantine()

        user_paper_service.init_db()

        self.assertFalse(quarantine.exists())
        self.assertEqual((self.paper_dir / "paper.pdf").read_bytes(), b"%PDF-delete%%EOF")
        self.assertIsNotNone(user_paper_service.get_paper(7, self.paper["paper_id"]))

    def test_startup_removes_quarantine_when_database_delete_committed(self) -> None:
        quarantine = self._move_to_quarantine()
        connection = user_paper_service._connect()
        try:
            connection.execute(
                "DELETE FROM user_uploaded_papers WHERE paper_id = ? AND user_id = ?",
                (self.paper["paper_id"], 7),
            )
            connection.commit()
        finally:
            connection.close()

        user_paper_service.init_db()

        self.assertFalse(quarantine.exists())
        self.assertFalse(self.paper_dir.exists())

    def test_cleanup_failure_is_recovered_on_next_startup(self) -> None:
        with patch.object(shutil, "rmtree", side_effect=OSError("cleanup failed")):
            self.assertTrue(user_paper_service.delete_paper(7, self.paper["paper_id"]))

        quarantines = list(self.quarantine_root.glob("pending-delete-*"))
        self.assertEqual(len(quarantines), 1)
        self.assertIsNone(user_paper_service.get_paper(7, self.paper["paper_id"]))

        user_paper_service.init_db()
        self.assertFalse(quarantines[0].exists())

    def test_recovery_keeps_conflicting_quarantine_for_manual_resolution(self) -> None:
        quarantine = self._move_to_quarantine()
        self.paper_dir.mkdir(parents=True)
        (self.paper_dir / "new.pdf").write_bytes(b"new")

        user_paper_service.init_db()

        self.assertTrue(quarantine.exists())
        self.assertEqual((self.paper_dir / "new.pdf").read_bytes(), b"new")
        self.assertIsNotNone(user_paper_service.get_paper(7, self.paper["paper_id"]))


if __name__ == "__main__":
    unittest.main()
