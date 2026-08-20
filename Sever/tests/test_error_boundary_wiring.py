from __future__ import annotations

import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]


class ErrorBoundaryWiringTests(unittest.TestCase):
    def test_all_server_errors_cross_sanitized_fastapi_boundary(self) -> None:
        source = (_SEVER / "api.py").read_text(encoding="utf-8")
        self.assertIn("@app.exception_handler(StarletteHTTPException)", source)
        self.assertIn("@app.exception_handler(Exception)", source)
        self.assertIn("if exc.status_code < 500", source)
        self.assertIn("is_public_error_detail(exc.detail)", source)
        self.assertIn("detail_reference = extract_error_reference(exc.detail)", source)
        self.assertIn("is_error_reference(detail_reference)", source)
        self.assertEqual(source.count('headers={"X-Error-ID": reference}'), 3)
        self.assertEqual(source.count("request_path=request.url.path"), 2)
        self.assertNotIn("request_path=str(request.url)", source)
        self.assertIn('status_code=500,', source)

    def test_admin_error_helper_uses_sanitized_logger(self) -> None:
        source = (_SEVER / "routers" / "_deps.py").read_text(encoding="utf-8")
        self.assertIn("log_internal_error(_logger, action, exc)", source)
        self.assertIn("public_error_detail(reference", source)
        self.assertIn('headers={"X-Error-ID": reference}', source)
        self.assertNotIn("traceback.print_exc()", source)
        self.assertNotIn("{exc!r}", source)


if __name__ == "__main__":
    unittest.main()
