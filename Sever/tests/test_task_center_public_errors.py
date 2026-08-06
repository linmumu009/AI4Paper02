from __future__ import annotations

import ast
import unittest
from pathlib import Path


_ROUTER = Path(__file__).resolve().parents[1] / "routers" / "task_center_router.py"


def _function_source(name: str) -> str:
    source = _ROUTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    return ast.get_source_segment(source, function) or ""


class TaskCenterPublicErrorTests(unittest.TestCase):
    def test_retry_and_cancel_hide_internal_exceptions(self) -> None:
        for function_name, operation in (
            ("api_retry_task", "task_center_retry"),
            ("api_cancel_task", "task_center_cancel"),
        ):
            route = _function_source(function_name)
            self.assertIn("safe_failure_detail", route)
            self.assertIn(operation, route)
            self.assertNotIn("detail=str(exc)", route)
            self.assertIn("detail=public_error", route)


if __name__ == "__main__":
    unittest.main()
