import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services import search_service


class SearchServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paper_db = os.path.join(self.tmp.name, "paper.db")
        self.user_db = os.path.join(self.tmp.name, "user.db")
        self._create_paper_db()
        self._create_user_db()

    def tearDown(self):
        self.tmp.cleanup()

    def _create_paper_db(self):
        conn = sqlite3.connect(self.paper_db)
        conn.executescript(
            """
            CREATE TABLE kb_papers (
                user_id INTEGER, scope TEXT, paper_id TEXT,
                paper_data TEXT, created_at TEXT
            );
            CREATE TABLE kb_notes (
                id INTEGER, user_id INTEGER, scope TEXT, paper_id TEXT,
                title TEXT, content TEXT, type TEXT, updated_at TEXT
            );
            CREATE TABLE kb_compare_results (
                id INTEGER, user_id INTEGER, title TEXT, markdown TEXT, updated_at TEXT
            );
            CREATE TABLE research_sessions (
                id INTEGER, user_id INTEGER, question TEXT, status TEXT, updated_at TEXT
            );
            CREATE TABLE research_projects (
                id INTEGER, user_id INTEGER, name TEXT, objective TEXT,
                description TEXT, status TEXT, updated_at TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO kb_papers VALUES (1, 'kb', ?, ?, ?)",
            ("2401.00001", json.dumps({"short_title": "Graph Memory", "abstract": "agent memory"}), "2026-01-01"),
        )
        conn.execute(
            "INSERT INTO kb_notes VALUES (1, 1, 'kb', '2401.00001', 'Graph ideas', 'follow-up experiments', 'markdown', '2026-01-02')"
        )
        conn.execute(
            "INSERT INTO kb_compare_results VALUES (1, 1, 'Graph comparison', 'memory methods', '2026-01-03')"
        )
        conn.execute(
            "INSERT INTO research_sessions VALUES (1, 1, 'How does graph memory work?', 'done', '2026-01-04')"
        )
        conn.execute(
            "INSERT INTO research_projects VALUES (1, 1, 'Graph Memory Project', 'agent memory', 'evidence map', 'active', '2026-01-05')"
        )
        conn.execute(
            "INSERT INTO kb_notes VALUES (2, 2, 'kb', 'private', 'Graph secret', 'other user', 'markdown', '2026-01-05')"
        )
        conn.commit()
        conn.close()

    def _create_user_db(self):
        conn = sqlite3.connect(self.user_db)
        conn.executescript(
            """
            CREATE TABLE user_uploaded_papers (
                user_id INTEGER, paper_id TEXT, title TEXT, abstract TEXT,
                institution TEXT, updated_at TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO user_uploaded_papers VALUES (1, 'up_graph', 'Graph Survey', 'survey', 'Lab', '2026-01-06')"
        )
        conn.execute(
            "INSERT INTO user_uploaded_papers VALUES (2, 'up_private', 'Graph Private', 'secret', 'Lab', '2026-01-07')"
        )
        conn.commit()
        conn.close()

    def test_searches_all_asset_types_without_cross_user_leakage(self):
        with patch.object(search_service, "_PAPER_DB_PATH", self.paper_db), patch.object(
            search_service, "_USER_PAPERS_DB_PATH", self.user_db
        ):
            response = search_service.search_assets(1, "graph", 30)

        self.assertEqual(
            {item["type"] for item in response["results"]},
            {"paper", "note", "compare", "research", "project", "user_paper"},
        )
        self.assertTrue(all("Private" not in item["title"] and "secret" not in item["title"] for item in response["results"]))
        routes = {item["type"]: item["route"] for item in response["results"]}
        self.assertEqual(routes["paper"], "/papers/2401.00001")
        self.assertEqual(routes["note"], "/notes/1")
        self.assertIn("result=1", routes["compare"])
        self.assertIn("session=1", routes["research"])
        self.assertEqual(routes["project"], "/projects/1")
        self.assertIn("paper=up_graph", routes["user_paper"])

    def test_empty_query_returns_no_results(self):
        response = search_service.search_assets(1, "   ")
        self.assertEqual(response, {"query": "", "results": [], "total": 0})


if __name__ == "__main__":
    unittest.main()
