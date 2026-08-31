from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from Controller.llm_select_theme import parse_score, score_one  # noqa: E402
from Controller.paper_assets import (  # noqa: E402
    build_summary_fallback_blocks,
    extract_blocks_with_llm,
    parse_json_from_text,
    process_one,
)
from Controller.pdf_info import parse_json_or_fallback  # noqa: E402
from services.idea_pipeline_service import _call_llm_json  # noqa: E402
from services.llm_response_guard import (  # noqa: E402
    EmptyLlmResponseError,
    InvalidLlmResponseError,
    has_meaningful_text,
    require_meaningful_structure,
)


class _FakeCompletions:
    def __init__(self, content):
        self.content = content

    def create(self, **_kwargs):
        choices = [] if self.content is ... else [
            SimpleNamespace(message=SimpleNamespace(content=self.content))
        ]
        return SimpleNamespace(choices=choices)


def _client(content):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions(content))
    )


class _SequenceCompletions:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        content = self.contents[min(self.calls, len(self.contents) - 1)]
        self.calls += 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason="stop",
                )
            ]
        )


class StructuredLlmResponseContractTests(unittest.TestCase):
    def test_nested_payload_requires_visible_text(self) -> None:
        self.assertTrue(has_meaningful_text({"items": [{"title": " result "}]}))
        for value in ({}, {"items": []}, {"score": 1}, [None, 0, False]):
            with self.subTest(value=value):
                with self.assertRaises(InvalidLlmResponseError):
                    require_meaningful_structure(value, operation="test")

    def test_theme_score_rejects_empty_or_unparseable_success(self) -> None:
        self.assertEqual(parse_score("0.83"), 0.83)
        self.assertEqual(parse_score("相关性：1.0"), 1.0)
        for value, error_type in (
            (None, EmptyLlmResponseError),
            ("", EmptyLlmResponseError),
            ("无法判断", InvalidLlmResponseError),
            ("1.2", InvalidLlmResponseError),
        ):
            with self.subTest(value=value):
                with self.assertRaises(error_type):
                    parse_score(value)

    def test_theme_call_does_not_turn_empty_response_into_zero(self) -> None:
        record = SimpleNamespace(title="paper", abstract="abstract")
        with self.assertRaises(EmptyLlmResponseError):
            score_one(
                _client(None),
                record,
                {"model": "test", "system_prompt": "score"},
            )

    def test_paper_assets_reject_empty_and_empty_json(self) -> None:
        cfg = {"model": "test", "system_prompt": "analyze"}
        for content, error_type in (
            (None, EmptyLlmResponseError),
            ("{}", InvalidLlmResponseError),
            ('{"blocks": {"summary": {}}}', InvalidLlmResponseError),
        ):
            with self.subTest(content=content):
                with self.assertRaises(error_type):
                    extract_blocks_with_llm(
                        _client(content),
                        "paper text",
                        cfg,
                        max_attempts=1,
                    )

        blocks = extract_blocks_with_llm(
            _client(
                '{"blocks":{"summary":{"one_sentence_summary":"finding"}}}'
            ),
            "paper text",
            cfg,
        )
        self.assertEqual(blocks["summary"]["one_sentence_summary"], "finding")

    def test_paper_assets_retries_invalid_json_before_failing_the_paper(self) -> None:
        completions = _SequenceCompletions(
            [
                "not json",
                '{"blocks":{"summary":{"one_sentence_summary":"finding"}}}',
            ]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )

        blocks = extract_blocks_with_llm(
            client,
            "paper text",
            {"model": "test", "system_prompt": "analyze"},
            sleep=lambda _delay: None,
        )

        self.assertEqual(completions.calls, 2)
        self.assertEqual(blocks["summary"]["one_sentence_summary"], "finding")

    def test_paper_assets_recovers_json_surrounded_by_brace_noise(self) -> None:
        parsed = parse_json_from_text(
            '说明：{"blocks":{"summary":{"one_sentence_summary":"finding"}}}'
            ' 后记中的坏括号 {not-json}'
        )

        self.assertEqual(
            parsed["blocks"]["summary"]["one_sentence_summary"],
            "finding",
        )

    def test_paper_assets_preserves_compact_block_shorthand(self) -> None:
        blocks = extract_blocks_with_llm(
            _client(
                '{"blocks":{"objective":["question"],"summary":"finding"}}'
            ),
            "paper text",
            {"model": "test", "system_prompt": "analyze"},
        )

        self.assertEqual(blocks["objective"]["bullets"], ["question"])
        self.assertEqual(blocks["summary"]["text"], "finding")

    def test_paper_assets_uses_deepseek_json_mode_and_low_temperature(self) -> None:
        completions = _SequenceCompletions(
            [
                "not json",
                '{"blocks":{"summary":{"one_sentence_summary":"finding"}}}',
            ]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )

        blocks = extract_blocks_with_llm(
            client,
            "paper text",
            {
                "model": "deepseek-v4-flash",
                "llm_base_url": "https://api.deepseek.com",
                "system_prompt": "analyze as JSON",
                "temperature": 1.0,
            },
            sleep=lambda _delay: None,
        )

        self.assertEqual(blocks["summary"]["one_sentence_summary"], "finding")
        self.assertEqual(
            completions.requests[0]["response_format"],
            {"type": "json_object"},
        )
        self.assertEqual(completions.requests[0]["temperature"], 0.2)
        self.assertEqual(completions.requests[1]["temperature"], 0.2)
        self.assertIn(
            "结构化输出重试约束",
            completions.requests[1]["messages"][0]["content"],
        )

    def test_paper_assets_final_attempt_uses_compact_recovery_prompt(self) -> None:
        completions = _SequenceCompletions(
            [
                "not json",
                "still not json",
                "also not json",
                '{"blocks":{"summary":{"one_sentence_summary":"recovered"}}}',
            ]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )

        blocks = extract_blocks_with_llm(
            client,
            "paper text",
            {
                "model": "test",
                "system_prompt": "analyze as JSON",
                "temperature": 1.0,
            },
            sleep=lambda _delay: None,
        )

        self.assertEqual(blocks["summary"]["one_sentence_summary"], "recovered")
        self.assertEqual(completions.calls, 4)
        self.assertEqual(completions.requests[-1]["temperature"], 0.0)
        self.assertIn(
            "结构化分析恢复器",
            completions.requests[-1]["messages"][0]["content"],
        )

    def test_paper_assets_summary_fallback_preserves_grounded_card_fields(self) -> None:
        blocks = build_summary_fallback_blocks(
            """笔记标题：可靠回退
📖标题：A Reliable Fallback
推荐理由：该论文给出了可复现的验证路径。

🛎️文章简介
🔸研究问题：如何避免单篇异常阻塞整批任务？
🔸主要贡献：提出逐篇恢复并保留完整性校验。

📝重点思路
🔸先严格解析结构化输出
🔸失败后降低温度重试

🔎分析总结
🔸大多数论文可直接生成
🔸异常论文可由已有摘要保底

💡个人观点
这种降级方式比发布空数据更可靠。

一句话记忆版：单篇异常不应拖垮整日推荐。
"""
        )

        self.assertEqual(
            blocks["objective"]["research_questions"],
            ["如何避免单篇异常阻塞整批任务？"],
        )
        self.assertEqual(
            blocks["method"]["key_mechanisms"],
            ["先严格解析结构化输出", "失败后降低温度重试"],
        )
        self.assertEqual(
            blocks["results"]["main_findings"],
            ["大多数论文可直接生成", "异常论文可由已有摘要保底"],
        )
        self.assertEqual(
            blocks["summary"]["one_sentence_summary"],
            "单篇异常不应拖垮整日推荐。",
        )

    def test_paper_assets_process_one_uses_summary_fallback_after_invalid_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "2608.28062.md"
            md_path.write_text(
                "🔸主要贡献：保留已有摘要作为结构化分析保底。\n"
                "一句话记忆版：单篇异常不阻塞整批发布。\n",
                encoding="utf-8",
            )
            with patch(
                "Controller.paper_assets.extract_blocks_with_llm",
                side_effect=InvalidLlmResponseError("invalid structured output"),
            ):
                result = process_one(_client(None), md_path, {})

        self.assertEqual(result["paper_id"], "2608.28062")
        self.assertEqual(
            result["blocks"]["summary"]["one_sentence_summary"],
            "单篇异常不阻塞整批发布。",
        )

    def test_idea_json_call_rejects_empty_malformed_and_empty_payload(self) -> None:
        cfg = {"llm_model": "test"}
        for content, error_type in (
            (None, EmptyLlmResponseError),
            ("not json", InvalidLlmResponseError),
            ('{"items": []}', InvalidLlmResponseError),
        ):
            with self.subTest(content=content):
                with self.assertRaises(error_type):
                    _call_llm_json(_client(content), cfg, "system", "input")

        result = _call_llm_json(
            _client('{"items":[{"title":"idea"}]}'),
            cfg,
            "system",
            "input",
        )
        self.assertEqual(result["items"][0]["title"], "idea")

    def test_pdf_info_parser_rejects_empty_or_unstructured_success(self) -> None:
        for content, error_type in (
            (None, EmptyLlmResponseError),
            ("", EmptyLlmResponseError),
            ("not json", InvalidLlmResponseError),
            ("{}", InvalidLlmResponseError),
        ):
            with self.subTest(content=content):
                with self.assertRaises(error_type):
                    parse_json_or_fallback(content)

        result = parse_json_or_fallback(
            '{"institution":"Unknown","is_large":false,"institution_tier":4}'
        )
        self.assertEqual(result["instution"], "Unknown")
        self.assertFalse(result["is_large"])
        fenced = parse_json_or_fallback(
            '```json\n{"instution":"","is_large":"false","institution_tier":4}\n```'
        )
        self.assertFalse(fenced["is_large"])
        with self.assertRaises(InvalidLlmResponseError):
            parse_json_or_fallback('{"instution":"Unknown","is_large":"maybe"}')


if __name__ == "__main__":
    unittest.main()
