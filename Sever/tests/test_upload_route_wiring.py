from __future__ import annotations

import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]


class UploadRouteWiringTests(unittest.TestCase):
    def test_upload_routes_use_bounded_reader(self) -> None:
        user_paper = (_SEVER / "routers" / "user_paper_router.py").read_text(encoding="utf-8")
        kb = (_SEVER / "routers" / "kb_router.py").read_text(encoding="utf-8")
        self.assertEqual(user_paper.count("read_upload_with_limit(file, _MAX_UPLOAD_SIZE)"), 2)
        self.assertEqual(kb.count("read_upload_with_limit(file, _MAX_UPLOAD_SIZE)"), 1)
        self.assertNotIn("await file.read()", user_paper)
        self.assertNotIn("await file.read()", kb)

    def test_pdf_import_validates_before_consuming_quota(self) -> None:
        source = (_SEVER / "routers" / "user_paper_router.py").read_text(encoding="utf-8")
        start = source.index('async def api_user_paper_import_pdf(')
        end = source.index("\n\n# ---------------------------------------------------------------------------", start)
        route = source[start:end]
        self.assertLess(
            route.index("read_upload_with_limit"),
            route.index('consume_quota(_user["id"], "upload")'),
        )


if __name__ == "__main__":
    unittest.main()
