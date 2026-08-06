from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import (  # noqa: E402
    background_task_recovery_service,
    kb_service,
    research_service,
    user_paper_service,
)


class BackgroundTaskRecoveryTests(unittest.TestCase):
    def test_startup_reconciles_only_orphaned_active_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            user_db = root / "user_papers.db"
            kb_db = root / "kb.db"
            research_db = root / "research.db"
            with (
                patch.object(user_paper_service, "_DB_PATH", str(user_db)),
                patch.object(kb_service, "_DB_PATH", str(kb_db)),
                patch.object(research_service, "_DB_PATH", str(research_db)),
            ):
                user_paper_service.init_db()
                kb_service.init_db()
                research_service.init_db()

                user_paper = user_paper_service.create_paper(
                    7, source_type="url", title="Interrupted user paper"
                )
                completed_user = user_paper_service.create_paper(
                    7, source_type="url", title="Completed user paper"
                )
                user_paper_service.set_process_status(
                    user_paper["paper_id"], status="processing", step="paper_assets"
                )
                user_paper_service.set_translate_status(
                    user_paper["paper_id"], status="processing", progress=40
                )
                user_paper_service.set_process_status(
                    completed_user["paper_id"], status="completed", step="done"
                )

                kb_service.add_paper(7, "2608.00001", {"title": "Interrupted KB"})
                kb_service.add_paper(7, "2608.00002", {"title": "Completed KB"})
                kb_service.set_kb_paper_process_status(
                    7, "2608.00001", "pending", step="queued"
                )
                kb_service.set_kb_paper_translate_status(
                    7, "2608.00001", "processing", progress=30
                )
                kb_service.set_kb_paper_process_status(
                    7, "2608.00002", "completed", step="done"
                )
                interrupted_session_id = research_service.create_session(
                    7, "Interrupted research", ["2608.00001"], {}
                )
                completed_session_id = research_service.create_session(
                    8, "Completed research", ["2608.00002"], {}
                )
                research_service.update_session_status(completed_session_id, "done")

                counts = background_task_recovery_service.reconcile_interrupted_tasks()

                interrupted_user = user_paper_service.get_paper(
                    7, user_paper["paper_id"]
                )
                untouched_user = user_paper_service.get_paper(
                    7, completed_user["paper_id"]
                )
                interrupted_kb = kb_service.get_kb_paper(7, "2608.00001")
                untouched_kb = kb_service.get_kb_paper(7, "2608.00002")
                interrupted_session = research_service.get_session(
                    7, interrupted_session_id
                )
                untouched_session = research_service.get_session(8, completed_session_id)

        self.assertEqual(counts["total"], 5)
        self.assertEqual(interrupted_user["process_status"], "failed")
        self.assertEqual(interrupted_user["process_step"], "interrupted")
        self.assertEqual(interrupted_user["translate_status"], "failed")
        self.assertIn("请重新尝试", interrupted_user["process_error"])
        self.assertEqual(untouched_user["process_status"], "completed")
        self.assertEqual(interrupted_kb["process_status"], "failed")
        self.assertEqual(interrupted_kb["translate_status"], "failed")
        self.assertEqual(untouched_kb["process_status"], "completed")
        self.assertEqual(interrupted_session["status"], "error")
        self.assertEqual(untouched_session["status"], "done")

    def test_api_startup_wires_background_task_reconciliation(self) -> None:
        source = (_SEVER / "api.py").read_text(encoding="utf-8")
        self.assertIn("reconcile_interrupted_tasks()", source)
        self.assertLess(
            source.index("reconcile_interrupted_tasks()"),
            source.index("recover_all_stalled_jobs()"),
        )


if __name__ == "__main__":
    unittest.main()
