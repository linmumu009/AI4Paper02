from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import user_paper_service  # noqa: E402


class UserPaperFileOperationRecoveryTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @property
    def operations_root(self) -> Path:
        return Path(user_paper_service._pending_file_operations_root())

    def _operation(
        self,
        *,
        kind: str,
        user_id: int,
        paper_id: str,
        old_rel_path: str | None,
        new_rel_path: str,
        pending_rel_path: str,
    ) -> Path:
        operation_id = uuid.uuid4().hex
        return Path(
            user_paper_service._write_pending_file_operation(
                operation_id,
                {
                    "kind": kind,
                    "user_id": user_id,
                    "paper_id": paper_id,
                    "old_rel_path": old_rel_path,
                    "new_rel_path": new_rel_path,
                    "pending_rel_path": pending_rel_path,
                },
            )
        )

    def _absolute(self, relative_path: str) -> Path:
        return self.files_root / relative_path

    def test_create_before_commit_removes_unreferenced_files(self) -> None:
        paper_id = f"up_{uuid.uuid4().hex}"
        new_rel = user_paper_service._pdf_rel_path(7, paper_id, "paper.pdf")
        pending_rel = user_paper_service._pdf_rel_path(
            7,
            paper_id,
            ".pending-create-test.tmp",
        )
        marker = self._operation(
            kind="create",
            user_id=7,
            paper_id=paper_id,
            old_rel_path=None,
            new_rel_path=new_rel,
            pending_rel_path=pending_rel,
        )
        self._absolute(new_rel).parent.mkdir(parents=True)
        self._absolute(new_rel).write_bytes(b"new")
        self._absolute(pending_rel).write_bytes(b"pending")

        user_paper_service.init_db()

        self.assertFalse(self._absolute(new_rel).exists())
        self.assertFalse(self._absolute(pending_rel).exists())
        self.assertFalse(marker.exists())
        self.assertFalse(self._absolute(new_rel).parent.exists())

    def test_create_after_commit_keeps_referenced_file(self) -> None:
        paper = user_paper_service.create_paper(7, source_type="manual", title="paper")
        new_rel = user_paper_service._pdf_rel_path(7, paper["paper_id"], "paper.pdf")
        pending_rel = user_paper_service._pdf_rel_path(
            7,
            paper["paper_id"],
            ".pending-create-test.tmp",
        )
        marker = self._operation(
            kind="create",
            user_id=7,
            paper_id=paper["paper_id"],
            old_rel_path=None,
            new_rel_path=new_rel,
            pending_rel_path=pending_rel,
        )
        self._absolute(new_rel).parent.mkdir(parents=True)
        self._absolute(new_rel).write_bytes(b"committed")
        self._absolute(pending_rel).write_bytes(b"pending")
        connection = user_paper_service._connect()
        try:
            connection.execute(
                "UPDATE user_uploaded_papers SET pdf_path = ? WHERE paper_id = ?",
                (new_rel, paper["paper_id"]),
            )
            connection.commit()
        finally:
            connection.close()

        user_paper_service.init_db()

        self.assertEqual(self._absolute(new_rel).read_bytes(), b"committed")
        self.assertFalse(self._absolute(pending_rel).exists())
        self.assertFalse(marker.exists())

    def test_update_before_commit_keeps_old_and_removes_new_version(self) -> None:
        paper = user_paper_service.create_paper(
            7,
            source_type="pdf",
            title="paper",
            pdf_bytes=b"old",
            pdf_filename="old.pdf",
        )
        old_rel = paper["pdf_path"]
        new_rel = user_paper_service._pdf_rel_path(7, paper["paper_id"], "new.pdf")
        pending_rel = user_paper_service._pdf_rel_path(
            7,
            paper["paper_id"],
            ".pending-pdf-test.tmp",
        )
        marker = self._operation(
            kind="update",
            user_id=7,
            paper_id=paper["paper_id"],
            old_rel_path=old_rel,
            new_rel_path=new_rel,
            pending_rel_path=pending_rel,
        )
        self._absolute(new_rel).write_bytes(b"new")
        self._absolute(pending_rel).write_bytes(b"pending")

        user_paper_service.init_db()

        self.assertEqual(self._absolute(old_rel).read_bytes(), b"old")
        self.assertFalse(self._absolute(new_rel).exists())
        self.assertFalse(self._absolute(pending_rel).exists())
        self.assertFalse(marker.exists())

    def test_update_after_commit_keeps_new_and_removes_old_version(self) -> None:
        paper = user_paper_service.create_paper(
            7,
            source_type="pdf",
            title="paper",
            pdf_bytes=b"old",
            pdf_filename="old.pdf",
        )
        old_rel = paper["pdf_path"]
        new_rel = user_paper_service._pdf_rel_path(7, paper["paper_id"], "new.pdf")
        pending_rel = user_paper_service._pdf_rel_path(
            7,
            paper["paper_id"],
            ".pending-pdf-test.tmp",
        )
        marker = self._operation(
            kind="update",
            user_id=7,
            paper_id=paper["paper_id"],
            old_rel_path=old_rel,
            new_rel_path=new_rel,
            pending_rel_path=pending_rel,
        )
        self._absolute(new_rel).write_bytes(b"new")
        self._absolute(pending_rel).write_bytes(b"pending")
        connection = user_paper_service._connect()
        try:
            connection.execute(
                "UPDATE user_uploaded_papers SET pdf_path = ? WHERE paper_id = ?",
                (new_rel, paper["paper_id"]),
            )
            connection.commit()
        finally:
            connection.close()

        user_paper_service.init_db()

        self.assertEqual(self._absolute(new_rel).read_bytes(), b"new")
        self.assertFalse(self._absolute(old_rel).exists())
        self.assertFalse(self._absolute(pending_rel).exists())
        self.assertFalse(marker.exists())

    def test_successful_create_and_update_leave_no_operation_markers(self) -> None:
        paper = user_paper_service.create_paper(
            7,
            source_type="pdf",
            title="paper",
            pdf_bytes=b"old",
            pdf_filename="old.pdf",
        )
        user_paper_service.update_paper(
            7,
            paper["paper_id"],
            pdf_bytes=b"new",
            pdf_filename="new.pdf",
        )

        self.assertEqual(list(self.operations_root.glob("*.json")), [])
        self.assertEqual(list(self.operations_root.glob("*.tmp")), [])

    def test_create_does_not_touch_paper_directory_before_marker_is_durable(self) -> None:
        paper_id = f"up_{uuid.uuid4().hex}"
        with (
            patch.object(user_paper_service, "_new_paper_id", return_value=paper_id),
            patch.object(
                user_paper_service,
                "_write_pending_file_operation",
                side_effect=OSError("marker failed"),
            ),
        ):
            with self.assertRaises(OSError):
                user_paper_service.create_paper(
                    7,
                    source_type="pdf",
                    title="paper",
                    pdf_bytes=b"pdf",
                )

        self.assertFalse(Path(user_paper_service._pdf_dir(7, paper_id)).exists())
        self.assertEqual(user_paper_service.count_papers(7), 0)

    def test_update_does_not_create_directory_before_marker_is_durable(self) -> None:
        paper = user_paper_service.create_paper(7, source_type="manual", title="paper")
        paper_dir = Path(user_paper_service._pdf_dir(7, paper["paper_id"]))
        with patch.object(
            user_paper_service,
            "_write_pending_file_operation",
            side_effect=OSError("marker failed"),
        ):
            with self.assertRaises(OSError):
                user_paper_service.update_paper(
                    7,
                    paper["paper_id"],
                    pdf_bytes=b"pdf",
                )

        self.assertFalse(paper_dir.exists())
        self.assertIsNone(
            user_paper_service.get_paper(7, paper["paper_id"])["pdf_path"]
        )

    def test_malformed_marker_is_retained_without_touching_files(self) -> None:
        self.operations_root.mkdir(parents=True)
        marker = self.operations_root / "broken.json"
        marker.write_text(json.dumps({"version": 999}), encoding="utf-8")

        user_paper_service.init_db()

        self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
