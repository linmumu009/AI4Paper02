from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import kb_router
from services import auth_service, kb_service, reading_excerpt_service


class ReadingExcerptTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patched = patch.object(kb_service, '_DB_PATH', str(Path(temp.name) / 'kb.db'))
        patched.start()
        self.addCleanup(patched.stop)
        kb_service.init_db()
        self.note = kb_service.create_note(7, 'paper', 'Existing', '<p>Keep this</p>', scope='mypapers')
        app = FastAPI()
        app.include_router(kb_router.router)
        app.dependency_overrides[auth_service.require_user] = lambda: {'id': 7}
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def payload(self, **extra):
        return dict(paper_id='paper', scope='mypapers', text='<script>quote</script>', source_path='/reading-source/paper?mode=zh&clip=one#anchor', **extra)

    def test_append_retains_content_escapes_quote_and_is_retry_safe(self):
        for _ in range(2):
            response = self.client.post(f"/api/kb/notes/{self.note['id']}/excerpt", json=self.payload())
            self.assertEqual(response.status_code, 200, response.text)
        content = response.json()['content']
        self.assertTrue(content.startswith('<p>Keep this</p>'))
        self.assertNotIn('<script>', content)
        self.assertEqual(content.count('<blockquote>'), 1)
        self.assertIn('&lt;script&gt;', content)

    def test_rejects_cross_user_paper_scope_and_external_sources(self):
        foreign = kb_service.create_note(8, 'paper', 'Other', 'Other', scope='mypapers')
        self.assertEqual(self.client.post(f"/api/kb/notes/{foreign['id']}/excerpt", json=self.payload()).status_code, 404)
        for changes, code in [({'scope': 'kb'}, 404), ({'paper_id': 'other', 'source_path': '/reading-source/other'}, 404), ({'source_path': 'https://example.com/reading-source/paper'}, 422)]:
            payload = self.payload()
            payload.update(changes)
            self.assertEqual(self.client.post(f"/api/kb/notes/{self.note['id']}/excerpt", json=payload).status_code, code)

    def test_concurrent_appends_keep_both_excerpts(self):
        def append(index):
            return reading_excerpt_service.append_excerpt(7, self.note['id'], 'paper', 'mypapers', f'quote {index}', f'/reading-source/paper?clip={index}')
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(append, [1, 2]))
        content = kb_service.get_note(7, self.note['id'])['content']
        self.assertIn('quote 1', content)
        self.assertIn('quote 2', content)


if __name__ == '__main__':
    unittest.main()
