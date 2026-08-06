from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


_ROOT = Path(__file__).resolve().parents[1]
_ROUTER = _ROOT / "routers" / "idea_router.py"
_SERVICE = _ROOT / "services" / "idea_pipeline_service.py"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services import idea_pipeline_service  # noqa: E402
from services.quota_stream_service import STREAM_QUOTA_COMMIT  # noqa: E402


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )
    return ast.get_source_segment(source, function) or ""


class IdeaGenerationQuotaContractTests(unittest.TestCase):
    def test_streaming_generation_confirms_quota_at_llm_boundary(self) -> None:
        route = _function_source(_ROUTER, "api_idea_generate_candidates")
        stream = _function_source(_SERVICE, "stream_generate_candidates")

        self.assertNotIn("consume_quota", route)
        self.assertEqual(route.count('reserve_quota(_user["id"], "idea_gen")'), 1)
        self.assertIn("guard_quota_stream", route)
        self.assertIn("on_commit=_commit_reward", route)
        self.assertLess(
            stream.index("yield STREAM_QUOTA_COMMIT"),
            stream.index("yield from _sse_stream_llm"),
        )
        self.assertGreater(
            stream.index("yield STREAM_QUOTA_COMMIT"),
            stream.index("atoms_context ="),
        )

    def test_paper_generation_refunds_errors_and_cached_results(self) -> None:
        route = _function_source(_ROUTER, "api_idea_generate_candidates_for_paper")
        service = _function_source(_SERVICE, "generate_candidates_for_paper")

        self.assertNotIn("consume_quota", route)
        self.assertIn('reserve_quota(_user["id"], "idea_gen")', route)
        self.assertGreaterEqual(
            route.count("_finalize_idea_quota(reservation_id, commit=False)"),
            2,
        )
        self.assertIn(
            '_finalize_idea_quota(reservation_id, commit=bool(result.get("generated")))',
            route,
        )
        self.assertIn('"generated": False', service)
        self.assertIn('"generated": True', service)

    def test_stream_does_not_commit_before_preflight_succeeds(self) -> None:
        idea_store = Mock()
        with (
            patch.object(idea_pipeline_service, "_get_idea_service", return_value=idea_store),
            patch.object(idea_pipeline_service, "_get_llm_config", return_value={}),
            patch.object(
                idea_pipeline_service,
                "_check_credentials",
                return_value="请先配置模型",
            ),
        ):
            output = list(
                idea_pipeline_service.stream_generate_candidates(
                    7,
                    custom_question="一个研究问题",
                )
            )

        self.assertNotIn(STREAM_QUOTA_COMMIT, output)
        self.assertTrue(any("请先配置模型" in str(item) for item in output))

    def test_stream_commits_immediately_before_llm_generation(self) -> None:
        idea_store = Mock()
        idea_store.search_atoms_fts.return_value = [
            {
                "id": 3,
                "atom_type": "method",
                "paper_id": "paper-1",
                "content": "atom content",
            }
        ]
        with (
            patch.object(idea_pipeline_service, "_get_idea_service", return_value=idea_store),
            patch.object(
                idea_pipeline_service,
                "_get_llm_config",
                return_value={"system_prompt": "system"},
            ),
            patch.object(idea_pipeline_service, "_check_credentials", return_value=None),
            patch.object(idea_pipeline_service, "_make_client", return_value=Mock()),
            patch.object(
                idea_pipeline_service,
                "_sse_stream_llm",
                return_value=iter(("data: answer\n\n", "data: [DONE]\n\n")),
            ),
        ):
            output = list(
                idea_pipeline_service.stream_generate_candidates(
                    7,
                    custom_question="一个研究问题",
                )
            )

        self.assertIs(output[0], STREAM_QUOTA_COMMIT)
        self.assertEqual(output[1], "data: answer\n\n")


if __name__ == "__main__":
    unittest.main()
