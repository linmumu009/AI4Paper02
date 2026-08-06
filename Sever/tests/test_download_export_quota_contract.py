from __future__ import annotations

import ast
import unittest
from pathlib import Path


_ROUTER = Path(__file__).resolve().parents[1] / "routers" / "download_router.py"


class DownloadExportQuotaContractTests(unittest.TestCase):
    def test_export_quota_is_reserved_only_after_source_validation(self) -> None:
        source = _ROUTER.read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "api_download_paper_file"
        )
        route = ast.get_source_segment(source, function) or ""

        self.assertNotIn("consume_quota", route)
        self.assertEqual(route.count("reserve_quota(user_id, \"export\")"), 1)
        self.assertLess(route.index("if not os.path.isfile(md_path)"), route.index("reserve_quota"))
        self.assertLess(route.index('if fmt == "md"'), route.index("reserve_quota"))
        self.assertGreaterEqual(route.count("_release_export_reservation"), 2)

    def test_original_pdf_download_is_not_an_export_charge(self) -> None:
        source = _ROUTER.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count('if file_type == "pdf"'), 2)
        self.assertGreaterEqual(source.count('detail="PDF 文件不存在"'), 2)

    def test_generated_exports_are_deleted_and_errors_are_sanitized(self) -> None:
        source = _ROUTER.read_text(encoding="utf-8")
        self.assertEqual(
            source.count("background=BackgroundTask(_remove_file_quietly, tmp_path)"),
            2,
        )
        self.assertIn("safe_failure_detail", source)
        self.assertNotIn('detail=f"DOCX 转换失败: {exc}"', source)
        self.assertNotIn('detail=f"PDF 转换失败: {exc}"', source)


if __name__ == "__main__":
    unittest.main()
