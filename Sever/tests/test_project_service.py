import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services import project_service, research_service


class ProjectServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "paper_analysis.db")
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE kb_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                scope TEXT NOT NULL,
                name TEXT NOT NULL,
                parent_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE research_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                paper_ids_json TEXT NOT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                parent_session_id INTEGER,
                status TEXT NOT NULL,
                saved INTEGER NOT NULL DEFAULT 0,
                folder_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE kb_papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                scope TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                folder_id INTEGER,
                paper_data TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE kb_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                paper_id TEXT NOT NULL,
                title TEXT NOT NULL
            );
            CREATE TABLE kb_compare_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL
            );
            CREATE TABLE idea_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO kb_folders VALUES (1, 1, 'research', 'Agent Memory', NULL, '2026-01-01', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO kb_folders VALUES (2, 1, 'research', 'Experiments', 1, '2026-01-01', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO kb_folders VALUES (3, 2, 'research', 'Private', NULL, '2026-01-01', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO research_sessions "
            "(id,user_id,question,paper_ids_json,config_json,status,saved,folder_id,created_at,updated_at) "
            "VALUES (1,1,'Compare memory methods','[\"2401.00001\"]','{}','done',0,2,'2026-01-02','2026-01-02')"
        )
        conn.execute(
            "INSERT INTO kb_papers "
            "(user_id,scope,paper_id,paper_data,created_at) VALUES (1,'kb','2401.00001',?,'2026-01-02')",
            (json.dumps({"short_title": "Graph Memory"}),),
        )
        conn.execute("INSERT INTO kb_compare_results VALUES (1,1,'Memory comparison')")
        conn.execute("INSERT INTO idea_candidates VALUES (1,1,'Intervention memory','draft')")
        conn.commit()
        conn.close()
        self.patch_db = patch.object(project_service, "_DB_PATH", self.db_path)
        self.patch_db.start()
        self.patch_research_db = patch.object(research_service, "_DB_PATH", self.db_path)
        self.patch_research_db.start()

    def tearDown(self):
        self.patch_research_db.stop()
        self.patch_db.stop()
        self.tmp.cleanup()

    def test_migration_is_idempotent_and_connects_nested_sessions(self):
        project_service.init_db()
        project_service.init_db()

        conn = sqlite3.connect(self.db_path)
        project_count = conn.execute("SELECT COUNT(*) FROM research_projects").fetchone()[0]
        project_id = conn.execute(
            "SELECT id FROM research_projects WHERE user_id=1 AND legacy_folder_id=1"
        ).fetchone()[0]
        linked_project = conn.execute(
            "SELECT project_id FROM research_sessions WHERE id=1"
        ).fetchone()[0]
        conn.close()

        self.assertEqual(project_count, 2)
        self.assertEqual(linked_project, project_id)

    def test_project_assets_are_deduplicated_and_user_isolated(self):
        project_service.init_db()
        project = project_service.list_projects(1)[0]
        first = project_service.add_asset(1, project["id"], "paper", "2401.00001", "kb")
        second = project_service.add_asset(1, project["id"], "paper", "2401.00001", "kb")

        self.assertEqual(first["id"], second["id"])
        detail = project_service.get_project(1, project["id"])
        self.assertEqual(detail["counts"]["paper"], 1)
        self.assertEqual(detail["assets"][0]["title"], "Graph Memory")
        self.assertIsNone(project_service.get_project(2, project["id"]))
        with self.assertRaises(LookupError):
            project_service.add_asset(2, project["id"], "paper", "2401.00001", "kb")

    def test_removing_or_deleting_project_does_not_delete_source_assets(self):
        project_service.init_db()
        project = project_service.list_projects(1)[0]
        project_service.add_asset(1, project["id"], "compare_result", "1")
        self.assertTrue(
            project_service.remove_asset(1, project["id"], "compare_result", "1")
        )
        self.assertTrue(project_service.set_project_status(1, project["id"], "deleted"))

        conn = sqlite3.connect(self.db_path)
        compare_count = conn.execute("SELECT COUNT(*) FROM kb_compare_results").fetchone()[0]
        session_count = conn.execute("SELECT COUNT(*) FROM research_sessions").fetchone()[0]
        session_project = conn.execute(
            "SELECT project_id FROM research_sessions WHERE id=1"
        ).fetchone()[0]
        conn.close()

        self.assertEqual(compare_count, 1)
        self.assertEqual(session_count, 1)
        self.assertIsNone(session_project)

    def test_project_sessions_ignore_retention_and_moves_sync_project(self):
        research_service.init_db()
        project_service.init_db()
        projects = {item["name"]: item for item in project_service.list_projects(1)}
        sessions = research_service.list_sessions(1, retention_days=3)
        self.assertEqual([item["id"] for item in sessions], [1])
        self.assertEqual(sessions[0]["project_id"], projects["Agent Memory"]["id"])

        research_service.move_sessions(1, [1], None)
        moved = research_service.get_session(1, 1)
        self.assertIsNone(moved["folder_id"])
        self.assertIsNone(moved["project_id"])

        research_service.move_sessions(1, [1], 2)
        moved_back = research_service.get_session(1, 1)
        self.assertEqual(moved_back["folder_id"], 2)
        self.assertEqual(moved_back["project_id"], projects["Agent Memory"]["id"])


if __name__ == "__main__":
    unittest.main()
