from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from routers import kb_router  # noqa: E402
from services import kb_service  # noqa: E402


class KbSaveFastPathTests(unittest.TestCase):
    def test_resource_attachment_runs_after_save_response_is_prepared(self) -> None:
        tasks = BackgroundTasks()
        saved = {
            "id": 11,
            "user_id": 7,
            "scope": "kb",
            "paper_id": "2608.00001",
            "folder_id": None,
            "paper_data": {"title": "Deferred resources"},
        }

        with (
            patch.object(
                kb_router.entitlement_service,
                "check_kb_paper_limit",
                return_value={"allowed": True, "limit": 100},
            ),
            patch.object(kb_router.kb_service, "add_paper", return_value=saved),
            patch.object(kb_router, "_invalidate_tree_cache"),
            patch.object(kb_router, "_prepare_saved_paper_resources") as prepare,
            patch.object(kb_router.auto_classify_service, "enqueue_classify"),
            patch.object(
                kb_router.preference_service,
                "extract_paper_features",
                return_value={
                    "categories": [],
                    "keywords": [],
                    "institution_tier": "unknown",
                },
            ),
            patch.object(kb_router.preference_service, "record_feedback"),
        ):
            result = kb_router.api_kb_add_paper(
                kb_router.AddPaperBody(
                    paper_id="2608.00001",
                    paper_data={"title": "Deferred resources"},
                ),
                tasks,
                _user={"id": 7},
            )

            self.assertEqual(result, saved)
            prepare.assert_not_called()
            asyncio.run(tasks())
            prepare.assert_called_once_with(7, "2608.00001", "kb")


class UnclassifiedCountTests(unittest.TestCase):
    def test_root_skipped_failed_and_none_papers_are_visible_in_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "kb-test.db")
            with patch.object(kb_service, "_DB_PATH", db_path):
                kb_service.init_db()
                conn = kb_service._connect()
                try:
                    now = "2026-09-01T00:00:00+00:00"
                    unclassified_folder = conn.execute(
                        """
                        INSERT INTO kb_folders
                            (user_id, scope, name, parent_id, created_at, updated_at)
                        VALUES (?, ?, ?, NULL, ?, ?)
                        """,
                        (7, "kb", "未分类", now, now),
                    ).lastrowid
                    manual_folder = conn.execute(
                        """
                        INSERT INTO kb_folders
                            (user_id, scope, name, parent_id, created_at, updated_at)
                        VALUES (?, ?, ?, NULL, ?, ?)
                        """,
                        (7, "kb", "我的目录", now, now),
                    ).lastrowid

                    rows = [
                        ("root-none", None, "none"),
                        ("root-skipped", None, "skipped"),
                        ("root-failed", None, "failed"),
                        ("root-done", None, "done"),
                        ("system-unclassified", unclassified_folder, "done"),
                        ("manual-folder", manual_folder, "none"),
                    ]
                    conn.executemany(
                        """
                        INSERT INTO kb_papers
                            (user_id, scope, paper_id, folder_id, paper_data,
                             created_at, classify_status)
                        VALUES (7, 'kb', ?, ?, '{}', ?, ?)
                        """,
                        [(paper_id, folder_id, now, status) for paper_id, folder_id, status in rows],
                    )
                    conn.commit()
                finally:
                    conn.close()

                self.assertEqual(kb_service.count_unclassified_papers(7, "kb"), 4)
                self.assertEqual(kb_service.count_unclassified_papers(8, "kb"), 0)


if __name__ == "__main__":
    unittest.main()
