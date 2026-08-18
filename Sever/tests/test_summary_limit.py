"""Unit tests for summary_limit helpers (no network)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from Controller.summary_limit import (  # noqa: E402
    SECTION_PROMPTS_DEFAULT,
    _choice_text,
    build_effective_cfg,
    card_contract_errors,
    card_needs_refinement,
    compress_headline,
    finalize_card_text,
    load_pdf_info_map_for_run,
    process_one,
    process_one_with_fallback,
    refine_full_card_text,
    restructure_to_example,
    rewrite_card,
    split_sections,
    structure_matches_example,
)
from services.llm_response_guard import (  # noqa: E402
    EmptyLlmResponseError,
    InvalidLlmResponseError,
)


def _resp_with_content(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


LONG_CARD = """笔记标题：受控评测智能体运行框架的独立贡献
📖标题：A Controlled Benchmark
🌐来源：arXiv,2608.00001
推荐理由：用受控协议将模型与运行框架分开评估，避免把框架收益误归因给模型，并通过统一预算、隔离数据和完整修改轨迹让不同框架的贡献可复现、可审计、可比较。

🛎️文章简介
🔸研究问题：如何在固定模型和任务的条件下测量运行框架的独立贡献？
🔸主要贡献：构建一套受控评测协议，让模型、任务和运行框架的影响可分离测量。

📝重点思路
🔸固定模型和下游任务，只替换运行框架。
🔸将开发、验证和测试数据隔离，减少适应性过拟合。
🔸在统一预算下记录完整修改轨迹并比较收益。

🔎分析总结
🔸不同运行框架会改变同一模型的任务表现。
🔸框架收益随任务变化，不能用单一任务外推。
🔸受控协议能分开模型能力与框架贡献。

💡个人观点
该协议提高了框架比较的可解释性，但结论仍受任务范围限制。

一句话记忆版：只有固定模型与任务，才能看清运行框架本身对智能体表现的独立贡献。
"""

REFINED_CARD = """笔记标题：分离测量框架贡献
📖标题：A Controlled Benchmark
🌐来源：arXiv,2608.00001
推荐理由：用受控协议分开模型与框架收益。

🛎️文章简介
🔸研究问题：如何测量运行框架的独立贡献？
🔸主要贡献：构建受控协议，分离测量模型、任务与框架影响。

📝重点思路
🔸固定模型和任务，只替换框架。
🔸隔离开发、验证和测试数据。
🔸在统一预算下记录并比较收益。

🔎分析总结
🔸框架会改变同一模型的任务表现。
🔸框架收益随任务变化。
🔸受控协议可分开模型与框架贡献。

💡个人观点
协议提高了框架比较的可解释性，但受任务范围限制。

一句话记忆版：固定模型和任务，才能看清框架贡献。
"""


class TestChoiceText(unittest.TestCase):
    def test_none_content_returns_empty(self):
        self.assertEqual(_choice_text(_resp_with_content(None)), "")

    def test_strips_whitespace(self):
        self.assertEqual(_choice_text(_resp_with_content("  YES  ")), "YES")

    def test_no_choices_returns_empty(self):
        self.assertEqual(_choice_text(SimpleNamespace(choices=[])), "")


class TestStructureMatchesExample(unittest.TestCase):
    def test_prompt_can_be_disabled_per_effective_config(self):
        client = MagicMock()

        result = structure_matches_example(
            client,
            "some text",
            paper_id="x",
            effective_cfg={"structure_check_prompt": ""},
        )

        self.assertTrue(result)
        client.chat.completions.create.assert_not_called()

    def test_none_content_is_not_treated_as_business_no(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _resp_with_content(None)
        with self.assertRaises(EmptyLlmResponseError):
            structure_matches_example(
                client, "笔记标题：测试\n🛎️文章简介", paper_id="2605.20022"
            )

    def test_yes_reply(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _resp_with_content("yes")
        result = structure_matches_example(client, "some text", paper_id="x")
        self.assertTrue(result)

    def test_unrecognized_reply_is_not_treated_as_no(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _resp_with_content("UNKNOWN")
        with self.assertRaises(InvalidLlmResponseError):
            structure_matches_example(client, "some text", paper_id="x")


class TestExplicitLocalFallback(unittest.TestCase):
    def test_model_failure_returns_nonempty_labeled_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "paper.md"
            output = root / "out.md"
            source.write_text("标题\n\n🛎️文章简介\n有效内容", encoding="utf-8")
            with patch(
                "Controller.summary_limit.process_one",
                side_effect=EmptyLlmResponseError("empty model result"),
            ):
                _, status = process_one_with_fallback(
                    MagicMock(),
                    source,
                    output,
                    {},
                )

            self.assertEqual(status, "fallback")
            self.assertTrue(output.read_text(encoding="utf-8").strip())


class TestLoadPdfInfoMapForRun(unittest.TestCase):
    def test_db_mode_maps_institution_to_instution(self):
        pdb = MagicMock()
        pdb.get_paper_info_map.return_value = {
            "2605.20006": {
                "title": "GeoX",
                "source": "arxiv, 2605.20006",
                "institution": "MIT",
            },
        }
        out = load_pdf_info_map_for_run(
            "2026-05-20", user_id=3, output_mode="db", pdb=pdb
        )
        self.assertEqual(out["2605.20006"]["instution"], "MIT")
        self.assertEqual(out["2605.20006"]["title"], "GeoX")


class TestFullCardRefinement(unittest.TestCase):
    def test_frozen_full_card_stage_can_feed_multiple_downstream_configs(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _resp_with_content(
            REFINED_CARD
        )
        full_card_cfg = {
            "card_prompt": "compress",
            "model": "test-model",
            "max_tokens": 2048,
            "input_hard_limit": 129024,
            "input_safety_margin": 4096,
        }

        frozen, rewritten, error = refine_full_card_text(
            client,
            LONG_CARD,
            effective_cfg=full_card_cfg,
        )

        self.assertTrue(rewritten)
        self.assertIsNone(error)
        self.assertEqual(client.chat.completions.create.call_count, 1)
        client.reset_mock()
        common_downstream = {
            **full_card_cfg,
            "headline_prompt": "",
            "structure_check_prompt": "",
            "section_limits": {},
            "section_prompts": {},
        }
        old_text, _ = finalize_card_text(
            client,
            frozen,
            Path("2608.00001.md"),
            {},
            card_rewritten=rewritten,
            effective_cfg=common_downstream,
        )
        new_text, _ = finalize_card_text(
            client,
            frozen,
            Path("2608.00001.md"),
            {},
            card_rewritten=rewritten,
            effective_cfg={**common_downstream, "headline_limit": 16},
        )

        self.assertEqual(old_text, new_text)
        self.assertEqual(client.chat.completions.create.call_count, 0)

    def test_headline_and_structure_rewrite_prompts_are_overridable(self):
        client = MagicMock()

        self.assertEqual(
            compress_headline(
                client,
                "笔记标题：一个很长的标题",
                effective_cfg={"headline_prompt": ""},
            ),
            "笔记标题：一个很长的标题",
        )
        self.assertEqual(
            restructure_to_example(
                client,
                "原文",
                effective_cfg={"structure_rewrite_prompt": ""},
            ),
            "原文",
        )
        client.chat.completions.create.assert_not_called()

    def test_inline_memory_is_available_to_section_fallback(self):
        _, sections = split_sections(
            [
                "🛎️文章简介\n",
                "🔸研究问题：问题？\n",
                "一句话记忆版：这是一个需要继续压缩的很长记忆句\n",
            ]
        )

        memory = [item for item in sections if item[0] == "memory"]
        self.assertEqual(len(memory), 1)
        self.assertEqual(memory[0][1], "一句话记忆版：")
        self.assertIn("需要继续压缩", "".join(memory[0][2]))

    def test_process_can_compress_inline_memory_with_aligned_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "2608.00001.md"
            output = root / "out.md"
            source.write_text(LONG_CARD, encoding="utf-8")
            client = MagicMock()
            client.chat.completions.create.return_value = _resp_with_content(
                "固定模型看框架"
            )

            _, status = process_one(
                client,
                source,
                output,
                {},
                effective_cfg={
                    "card_prompt": "",
                    "headline_prompt": "",
                    "structure_check_prompt": "",
                    "section_limits": {"memory": 10},
                    "section_prompts": {"memory": "compress memory"},
                    "model": "test-model",
                    "max_tokens": 2048,
                    "input_hard_limit": 129024,
                    "input_safety_margin": 4096,
                },
            )

            self.assertEqual(status, "rewritten")
            self.assertIn(
                "一句话记忆版：固定模型看框架",
                output.read_text(encoding="utf-8"),
            )
            self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_long_complete_card_requires_refinement(self):
        self.assertTrue(card_needs_refinement(LONG_CARD))
        self.assertFalse(card_needs_refinement(REFINED_CARD))

    def test_rewrite_card_accepts_valid_eight_field_result(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _resp_with_content(REFINED_CARD)
        result = rewrite_card(
            client,
            LONG_CARD,
            effective_cfg={
                "card_prompt": "compress",
                "model": "test-model",
                "max_tokens": 2048,
                "input_hard_limit": 129024,
                "input_safety_margin": 4096,
            },
        )

        self.assertIn("笔记标题:分离测量框架贡献", result)
        self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_process_refines_before_injecting_institution_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "2608.00001.md"
            output = root / "out.md"
            source.write_text(LONG_CARD, encoding="utf-8")
            client = MagicMock()
            client.chat.completions.create.return_value = _resp_with_content(
                REFINED_CARD
            )

            _, status = process_one(
                client,
                source,
                output,
                {
                    "2608.00001": {
                        "title": "A Controlled Benchmark",
                        "source": "arXiv,2608.00001",
                        "instution": "MIT",
                    }
                },
                effective_cfg={
                    "card_prompt": "compress",
                    "model": "test-model",
                    "max_tokens": 2048,
                    "input_hard_limit": 129024,
                    "input_safety_margin": 4096,
                },
            )

            result = output.read_text(encoding="utf-8")
            self.assertEqual(status, "rewritten")
            self.assertTrue(result.startswith("MIT:分离测量框架贡献\n"))
            self.assertNotIn("MIT:MIT", result)
            self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_contract_rejects_changed_metadata_and_new_number(self):
        candidate = REFINED_CARD.replace(
            "A Controlled Benchmark", "Changed Title"
        ).replace("框架收益。", "框架收益99%。")

        errors = card_contract_errors(candidate, source_draft=LONG_CARD)

        self.assertIn("original_title_changed", errors)
        self.assertTrue(any(item.startswith("unsupported_numbers=") for item in errors))

    def test_existing_section_customization_disables_default_card_prompt(self):
        user_cfg = {
            "llm_api_key": "dummy-key",
            "llm_base_url": "https://example.com/v1",
            "llm_model": "dummy-model",
            "summary_limit_prompt_intro": "my custom intro compressor",
        }
        with patch(
            "Controller.summary_limit._load_user_config", return_value=user_cfg
        ), patch(
            "Controller.summary_limit._load_explicit_user_config",
            return_value=user_cfg,
        ):
            cfg = build_effective_cfg(user_id=7)

        self.assertEqual(cfg["card_prompt"], "")
        self.assertEqual(
            cfg["section_prompts"]["intro"], "my custom intro compressor"
        )

    def test_equivalent_quote_style_is_not_treated_as_customization(self):
        method_prompt = SECTION_PROMPTS_DEFAULT["method"].replace("“", '"').replace(
            "”", '"'
        )
        merged = {
            "llm_api_key": "dummy-key",
            "llm_base_url": "https://example.com/v1",
            "llm_model": "dummy-model",
            "summary_limit_prompt_method": method_prompt,
        }
        explicit = {"summary_limit_prompt_method": method_prompt}
        with patch(
            "Controller.summary_limit._load_user_config", return_value=merged
        ), patch(
            "Controller.summary_limit._load_explicit_user_config",
            return_value=explicit,
        ):
            cfg = build_effective_cfg(user_id=7)

        self.assertTrue(cfg["card_prompt"])

    def test_explicit_empty_card_prompt_disables_full_card_refinement(self):
        merged = {
            "llm_api_key": "dummy-key",
            "llm_base_url": "https://example.com/v1",
            "llm_model": "dummy-model",
            "summary_limit_prompt_card": "",
        }
        with patch(
            "Controller.summary_limit._load_user_config", return_value=merged
        ), patch(
            "Controller.summary_limit._load_explicit_user_config",
            return_value={"summary_limit_prompt_card": ""},
        ):
            cfg = build_effective_cfg(user_id=7)

        self.assertEqual(cfg["card_prompt"], "")


if __name__ == "__main__":
    unittest.main()
