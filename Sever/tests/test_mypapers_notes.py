from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from routers import kb_router
from services import auth_service, kb_service, user_paper_service


class MyPapersNoteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for name, value in (
            ("_DB_PATH", str(Path(temp.name) / "kb.db")),
            ("_KB_FILES_DIR", temp.name),
        ):
            patcher = patch.object(kb_service, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        kb_service.init_db()
        app = FastAPI()
        app.include_router(kb_router.router)
        app.dependency_overrides[auth_service.require_user] = lambda: {"id": 7}
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_uploaded_paper_note_round_trip_without_kb_copy(self):
        with patch.object(user_paper_service, "get_paper", return_value={"paper_id": "up_test"}) as get_paper:
            response = self.client.post("/api/kb/papers/up_test/notes", json={"scope": "mypapers"})
            self.assertEqual(response.status_code, 200, response.text)
            get_paper.assert_called_once_with(7, "up_test")
        note = response.json()
        self.assertEqual(note["scope"], "mypapers")
        self.assertFalse(kb_service.is_paper_in_kb(7, "up_test", "mypapers"))
        response = self.client.patch(f"/api/kb/notes/{note['id']}", json={"content": "Research notes"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get(f"/api/kb/notes/{note['id']}").json()["content"], "Research notes")
        self.assertEqual(len(self.client.get("/api/kb/papers/up_test/notes?scope=mypapers").json()["notes"]), 1)
        self.assertEqual(kb_service.list_notes(7, "up_test", "kb"), [])

    def test_upload_and_link_use_uploaded_paper_ownership(self):
        with (
            patch.object(user_paper_service, "get_paper", return_value={"paper_id": "up_test"}),
            patch.object(kb_router.entitlement_service, "check_boolean_gate", return_value=True),
        ):
            link = self.client.post("/api/kb/papers/up_test/notes/link", json={"scope": "mypapers", "title": "Reference", "url": "https://example.com"})
            upload = self.client.post("/api/kb/papers/up_test/notes/upload?scope=mypapers", files={"file": ("note.txt", b"notes", "text/plain")})
        self.assertEqual(link.status_code, 200, link.text)
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(len(kb_service.list_notes(7, "up_test", "mypapers")), 2)

    def test_missing_or_other_users_paper_cannot_receive_notes(self):
        with (
            patch.object(user_paper_service, "get_paper", return_value=None) as get_paper,
            patch.object(kb_router.entitlement_service, "check_boolean_gate", return_value=True),
        ):
            for suffix, kwargs in (
                ("notes", {"json": {"scope": "mypapers"}}),
                ("notes/link", {"json": {"scope": "mypapers", "title": "Reference", "url": "https://example.com"}}),
                ("notes/upload?scope=mypapers", {"files": {"file": ("note.txt", b"notes")}}),
            ):
                response = self.client.post(f"/api/kb/papers/up_foreign/{suffix}", **kwargs)
                self.assertEqual(response.status_code, 404, response.text)
            self.assertEqual(get_paper.call_count, 3)
            get_paper.assert_called_with(7, "up_foreign")
        self.assertEqual(kb_service.list_notes(7, "up_foreign", "mypapers"), [])

    def test_kb_membership_and_note_limit_still_apply(self):
        missing = self.client.post("/api/kb/papers/2609.00001/notes", json={"scope": "kb"})
        self.assertEqual(missing.status_code, 404)
        kb_service.add_paper(7, "2609.00001", {}, scope="kb")
        with patch.object(kb_router.entitlement_service, "check_kb_note_limit", return_value={"allowed": False, "limit": 50}):
            limited = self.client.post("/api/kb/papers/2609.00001/notes", json={"scope": "kb"})
        self.assertEqual(limited.status_code, 403)
        with patch.object(kb_router.entitlement_service, "check_kb_note_limit", return_value={"allowed": True}):
            allowed = self.client.post("/api/kb/papers/2609.00001/notes", json={"scope": "kb"})
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_unsupported_scope_is_rejected(self):
        response = self.client.post("/api/kb/papers/up_test/notes", json={"scope": "unknown"})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
