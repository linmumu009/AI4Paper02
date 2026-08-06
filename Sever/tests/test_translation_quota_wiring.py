from __future__ import annotations

import ast
import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]


class TranslationQuotaWiringTests(unittest.TestCase):
    def _function_source(self, relative: str, function_name: str) -> str:
        source = (_SEVER / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        )
        return ast.get_source_segment(source, function) or ""

    def test_translation_routes_delegate_quota_after_task_claim(self) -> None:
        routes = (
            ("routers/user_paper_router.py", "api_user_paper_translate"),
            ("routers/user_paper_router.py", "api_user_paper_retranslate"),
            ("routers/kb_router.py", "api_kb_paper_translate"),
            ("routers/kb_router.py", "api_kb_paper_retranslate"),
        )
        for relative, function_name in routes:
            function = self._function_source(relative, function_name)
            self.assertIn("charge_quota=True", function, function_name)
            self.assertNotIn("consume_quota", function, function_name)

    def test_retranslate_routes_do_not_delete_existing_outputs_before_launch(self) -> None:
        for relative, function_name in (
            ("routers/user_paper_router.py", "api_user_paper_retranslate"),
            ("routers/kb_router.py", "api_kb_paper_retranslate"),
        ):
            function = self._function_source(relative, function_name)
            self.assertNotIn("os.remove", function, function_name)
            self.assertNotIn("set_translate_status", function, function_name)
            self.assertNotIn("set_kb_paper_translate_status", function, function_name)


if __name__ == "__main__":
    unittest.main()
