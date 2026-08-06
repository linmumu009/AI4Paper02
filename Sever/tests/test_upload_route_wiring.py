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

    def test_pdf_import_validates_before_reserving_and_finalizing_quota(self) -> None:
        source = (_SEVER / "routers" / "user_paper_router.py").read_text(encoding="utf-8")
        start = source.index('async def api_user_paper_import_pdf(')
        end = source.index("\n\n# ---------------------------------------------------------------------------", start)
        route = source[start:end]
        self.assertLess(
            route.index("read_upload_with_limit"),
            route.index("validate_pdf_upload"),
        )
        self.assertLess(
            route.index("validate_pdf_upload"),
            route.index("_create_paper_with_quota"),
        )
        self.assertNotIn("consume_quota", route)

    def test_both_user_pdf_routes_validate_content_before_persistence(self) -> None:
        source = (_SEVER / "routers" / "user_paper_router.py").read_text(encoding="utf-8")
        for function_name, persistence_call in (
            ("api_user_paper_import_pdf", "_create_paper_with_quota"),
            ("api_user_paper_upload_pdf", "update_paper"),
        ):
            start = source.index(f"async def {function_name}(")
            end = source.index("\n\n# ---------------------------------------------------------------------------", start)
            route = source[start:end]
            self.assertLess(
                route.index("read_upload_with_limit"),
                route.index("validate_pdf_upload"),
            )
            self.assertLess(
                route.index("validate_pdf_upload"),
                route.index(persistence_call),
            )


if __name__ == "__main__":
    unittest.main()
