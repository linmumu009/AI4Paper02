from __future__ import annotations

import sys
import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services.llm_request_options import build_thinking_kwargs  # noqa: E402
from services.pipeline_step_config_service import (  # noqa: E402
    get_enabled_steps,
    validate_step_config,
)


class RuntimeModuleCompletenessTests(unittest.TestCase):
    def test_qwen_thinking_option_is_provider_scoped(self) -> None:
        qwen = build_thinking_kwargs(
            {"llm_model": "qwen-plus", "enable_thinking": True}
        )
        other = build_thinking_kwargs(
            {"llm_model": "gpt-compatible", "enable_thinking": True}
        )
        self.assertEqual(qwen, {"extra_body": {"enable_thinking": True}})
        self.assertEqual(other, {})

    def test_pipeline_dependencies_reject_invalid_configuration(self) -> None:
        errors = validate_step_config(
            {"paper_summary": True, "instutions_filter": False}
        )
        self.assertTrue(errors)

    def test_required_pipeline_steps_cannot_be_disabled(self) -> None:
        enabled, disabled = get_enabled_steps(
            "scheduled", ["arxiv_search", "paper_summary"]
        )
        self.assertIn("arxiv_search", enabled)
        self.assertNotIn("arxiv_search", disabled)


if __name__ == "__main__":
    unittest.main()
