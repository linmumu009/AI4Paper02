from __future__ import annotations

import ast
import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]


class StreamQuotaWiringTests(unittest.TestCase):
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

    def test_stream_routes_reserve_and_guard_quota(self) -> None:
        routes = (
            ("routers/paper_router.py", "api_post_paper_chat", "chat"),
            ("routers/paper_router.py", "api_post_general_chat", "chat"),
            ("routers/kb_router.py", "api_kb_compare", "compare"),
            ("routers/research_router.py", "api_start_research", "research"),
            ("routers/research_router.py", "api_continue_round3", "research"),
            ("routers/research_router.py", "api_followup_research", "research"),
        )
        for relative, function_name, feature in routes:
            function = self._function_source(relative, function_name)
            self.assertIn(f'reserve_quota(', function, function_name)
            self.assertIn(f'"{feature}"', function, function_name)
            self.assertIn("guard_quota_stream(", function, function_name)
            self.assertNotIn("consume_quota", function, function_name)

    def test_stream_services_signal_only_after_validation_guards(self) -> None:
        services = (
            ("services/chat_service.py", "stream_chat"),
            ("services/compare_service.py", "stream_compare"),
            ("services/research_service.py", "stream_research"),
            ("services/research_service.py", "stream_continue_round3"),
            ("services/research_service.py", "stream_followup"),
        )
        for relative, function_name in services:
            function = self._function_source(relative, function_name)
            signal_at = function.index("yield STREAM_QUOTA_COMMIT")
            first_return = function.index("return")
            self.assertGreater(signal_at, first_return, function_name)

    def test_reward_consumption_is_deferred_until_stream_commit(self) -> None:
        for relative, function_name in (
            ("routers/paper_router.py", "api_post_paper_chat"),
            ("routers/paper_router.py", "api_post_general_chat"),
            ("routers/kb_router.py", "api_kb_compare"),
            ("routers/research_router.py", "api_start_research"),
        ):
            function = self._function_source(relative, function_name)
            callback_at = function.index("def _commit_reward")
            use_reward_at = function.index("engagement_service.use_reward")
            guard_at = function.index("guard_quota_stream")
            self.assertGreater(use_reward_at, callback_at, function_name)
            self.assertGreater(guard_at, use_reward_at, function_name)


if __name__ == "__main__":
    unittest.main()
