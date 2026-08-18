from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


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

    def test_deepseek_thinking_option_is_explicit_for_official_endpoint(self) -> None:
        disabled = build_thinking_kwargs(
            {
                "llm_base_url": "https://api.deepseek.com",
                "llm_model": "deepseek-v4-flash",
            }
        )
        enabled = build_thinking_kwargs(
            {
                "llm_base_url": "https://api.deepseek.com/beta",
                "llm_model": "deepseek-v4-pro",
                "enable_thinking": True,
            }
        )
        proxied = build_thinking_kwargs(
            {
                "llm_base_url": "https://openrouter.ai/api/v1",
                "llm_model": "deepseek/deepseek-v4-flash",
            }
        )
        self.assertEqual(
            disabled,
            {"extra_body": {"thinking": {"type": "disabled"}}},
        )
        self.assertEqual(
            enabled,
            {"extra_body": {"thinking": {"type": "enabled"}}},
        )
        self.assertEqual(proxied, {})

    def test_pdf_info_forwards_deepseek_non_thinking_request(self) -> None:
        from Controller import pdf_info

        client = MagicMock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"is_large": false}')
                )
            ]
        )
        with patch(
            "services.llm_client_factory.build_llm_client",
            return_value=client,
        ):
            content = pdf_info.call_qwen(
                api_key="test-key",
                base_url="https://api.deepseek.com",
                model="deepseek-v4-flash",
                system_prompt="system",
                user_content="paper",
                temperature=1.0,
                max_tokens=2048,
            )

        self.assertEqual(content, '{"is_large": false}')
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(
            request["extra_body"],
            {"thinking": {"type": "disabled"}},
        )

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
