from __future__ import annotations

import ast
import unittest
from pathlib import Path


_ROUTER = Path(__file__).resolve().parents[1] / "routers" / "research_router.py"


class ResearchExportQuotaContractTests(unittest.TestCase):
    def test_source_and_result_are_validated_before_export_quota(self) -> None:
        source = _ROUTER.read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "api_download_research"
        )
        route = ast.get_source_segment(source, function) or ""

        self.assertNotIn("consume_quota", route)
        self.assertEqual(route.count('reserve_quota(user["id"], "export")'), 1)
        self.assertLess(route.index("session = research_service.get_session"), route.index("reserve_quota"))
        self.assertLess(route.index("if not final_text"), route.index("reserve_quota"))
        self.assertLess(route.index('if format == "md"'), route.index("reserve_quota"))

    def test_conversion_failure_refunds_and_artifacts_are_cleaned(self) -> None:
        source = _ROUTER.read_text(encoding="utf-8")
        route_start = source.index("def api_download_research(")
        route = source[route_start:]

        self.assertIn("_validate_research_export(tmp_path, format)", route)
        self.assertIn("background=BackgroundTask(_remove_research_export_quietly, tmp_path)", route)
        self.assertIn("_finalize_research_export_quota(reservation_id, commit=False)", route)
        self.assertIn("_finalize_research_export_quota(reservation_id, commit=True)", route)
        self.assertIn("safe_failure_detail", route)
        self.assertNotIn('detail=f"{format.upper()} 转换失败', route)

    def test_artifact_validation_checks_format_signatures(self) -> None:
        source = _ROUTER.read_text(encoding="utf-8")
        self.assertIn('signature.startswith(b"%PDF-")', source)
        self.assertIn('signature.startswith(b"PK")', source)
        self.assertIn("os.path.getsize(path) <= 0", source)


if __name__ == "__main__":
    unittest.main()
