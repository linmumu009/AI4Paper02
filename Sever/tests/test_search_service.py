import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import search_service
from services import pipeline_db_service as pipeline_db


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

    def _analysis(self, paper_id="2610.10001", title="Uncollected Graph Analysis", user_id=0,
                  date="2026-10-14", authors=None, complete=True):
        with patch.object(pipeline_db, "_DB_PATH", self.paper_db):
            pipeline_db.init_db()
            pipeline_db.bulk_upsert_arxiv_list(date, [{
                "paper_arxiv_id": paper_id, "title": title,
                "authors": authors or ["First Author"],
            }])
            pipeline_db.bulk_upsert_selected_papers(user_id, date, [
                {"paper_arxiv_id": paper_id, "is_final_selected": 1},
            ])
            pipeline_db.upsert_summary_raw(user_id, date, paper_id, "笔记标题：图记忆\n🛎️文章简介\n研究图记忆。")
            pipeline_db.upsert_summary_limit(user_id, date, paper_id, "精简摘要")
            if complete:
                pipeline_db.upsert_paper_assets(user_id, date, paper_id, blocks={"text": "Evidence"})

    def _search(self, query, user_id=1, limit=30, scope="all"):
        with patch.object(search_service, "_PAPER_DB_PATH", self.paper_db), patch.object(
            search_service, "_USER_PAPERS_DB_PATH", self.user_db
        ):
            return search_service.search_assets(user_id, query, limit, scope)

    def test_search_finds_uncollected_historical_analysis_by_id_title_and_late_author(self):
        authors = ["First", "Second", "Third", "Fourth", "Fifth Researcher"]
        self._analysis(authors=authors)
        for query in ("2610.10001", "Uncollected Graph Analysis", "Fifth Researcher", "图记忆"):
            with self.subTest(query=query):
                found = [r for r in self._search(query)["results"] if r["id"] == "2610.10001"]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["collection_status"], "uncollected")
                self.assertEqual(found[0]["route"], "/papers/2610.10001")

    def test_arxiv_links_prefixes_and_versions_find_same_paper(self):
        self._analysis()
        for query in ("arXiv:2610.10001v2", "https://arxiv.org/abs/2610.10001v3",
                      "https://arxiv.org/pdf/2610.10001.pdf", "https://arxiv.org/html/2610.10001v1"):
            with self.subTest(query=query):
                self.assertEqual(self._search(query)["results"][0]["id"], "2610.10001")

    def test_same_analysis_is_deduplicated_and_collection_flag_belongs_to_current_user(self):
        self._analysis(paper_id="2401.00001", title="Graph Memory")
        self._analysis(paper_id="2401.00001", title="Graph Memory", date="2026-10-12")
        found = [r for r in self._search("Graph Memory")["results"] if r["id"] == "2401.00001"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["collection_status"], "collected")
        other = [r for r in self._search("Graph Memory", user_id=2)["results"] if r["id"] == "2401.00001"]
        self.assertEqual(other[0]["collection_status"], "uncollected")

    def test_public_search_excludes_incomplete_and_other_users_private_analyses(self):
        self._analysis("2610.10001", "Shared Good Graph")
        self._analysis("2610.10002", "Incomplete Graph", complete=False)
        self._analysis("2610.10003", "Private Graph", user_id=2)
        self.assertEqual(self._search("Graph", user_id=None)["results"], [])
        with patch.object(pipeline_db, "_DB_PATH", self.paper_db):
            pipeline_db.publish_digest(0, "2026-10-14")
        public = self._search("Graph", user_id=None)["results"]
        self.assertEqual([r["id"] for r in public], ["2610.10001"])
        owner_ids = {r["id"] for r in self._search("Graph", user_id=2)["results"]}
        self.assertIn("2610.10003", owner_ids)
        self.assertNotIn("up_graph", owner_ids)

    def test_filters_apply_before_result_limit(self):
        self._analysis("2401.00001", "Graph Memory")
        self._analysis("2610.10001", "Graph New")
        mine = self._search("Graph", limit=50, scope="mine")["results"]
        self.assertIn("2401.00001", {r["id"] for r in mine})
        self.assertNotIn("2610.10001", {r["id"] for r in mine})
        uncollected = self._search("Graph", limit=1, scope="uncollected")["results"]
        self.assertEqual([r["id"] for r in uncollected], ["2610.10001"])

    def test_original_title_and_all_authors_in_saved_snapshot_are_searchable(self):
        conn = sqlite3.connect(self.paper_db)
        conn.execute("UPDATE kb_papers SET paper_data=? WHERE user_id=1", (
            json.dumps({"short_title": "中文简称", "title": "Original Long English Title",
                        "authors": ["A", "B", "C", "D", "Fifth Person"]}),
        ))
        conn.commit()
        conn.close()
        for query in ("Original Long English Title", "Fifth Person"):
            self.assertEqual(self._search(query)["results"][0]["id"], "2401.00001")

    def test_title_punctuation_and_whitespace_are_tolerated(self):
        self._analysis(title="Graph Memory: Learning for Agents")
        self.assertEqual(self._search("Graph Memory — Learning\nfor Agents")["results"][0]["id"], "2610.10001")

    def test_exact_old_title_outranks_recent_partial_matches(self):
        self._analysis(title="Graph Memory", date="2026-01-01")
        for index in range(6):
            self._analysis(paper_id=f"2610.1001{index}", title=f"Graph Memory Extension {index}")
        self.assertEqual(self._search("Graph Memory", limit=1)["results"][0]["id"], "2610.10001")

    def test_guest_endpoint_searches_public_papers_without_private_assets(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.search_router import router
        app = FastAPI()
        app.include_router(router)
        self._analysis()
        with patch.object(search_service, "_PAPER_DB_PATH", self.paper_db), patch.object(
            search_service, "_USER_PAPERS_DB_PATH", self.user_db
        ):
            response = TestClient(app).get("/api/search", params={"q": "Graph"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r["id"] for r in response.json()["results"]], ["2610.10001"])

    def test_uploaded_papers_match_authors_and_original_arxiv_reference(self):
        conn = sqlite3.connect(self.user_db)
        conn.execute("ALTER TABLE user_uploaded_papers ADD COLUMN authors_json TEXT DEFAULT '[]'")
        conn.execute("ALTER TABLE user_uploaded_papers ADD COLUMN source_ref TEXT DEFAULT ''")
        conn.execute("UPDATE user_uploaded_papers SET authors_json=?,source_ref=? WHERE user_id=1", (
            json.dumps(["Uploaded Author"]), "https://arxiv.org/abs/2610.10001v2",
        ))
        conn.commit()
        conn.close()
        for query in ("Uploaded Author", "arXiv:2610.10001"):
            found = self._search(query)["results"]
            self.assertEqual(found[0]["id"], "up_graph")
            self.assertEqual(found[0]["collection_status"], "uploaded")

    def test_old_analysis_without_metadata_uses_its_saved_summary_title(self):
        self._analysis()
        conn = sqlite3.connect(self.paper_db)
        conn.execute("DELETE FROM pipeline_arxiv_list")
        conn.commit()
        conn.close()
        found = self._search("2610.10001")["results"][0]
        self.assertEqual(found["title"], "图记忆")

    def test_keyword_search_includes_archived_original_abstract(self):
        self._analysis()
        with patch.object(pipeline_db, "_DB_PATH", self.paper_db):
            pipeline_db.upsert_paper_info(0, "2026-10-14", "2610.10001", abstract="Different paraphrase")
        conn = sqlite3.connect(self.paper_db)
        conn.execute("UPDATE pipeline_arxiv_list SET abstract_text='Rare archived concept'")
        conn.commit()
        conn.close()
        self.assertEqual(self._search("archived concept")["results"][0]["id"], "2610.10001")


if __name__ == "__main__":
    unittest.main()
