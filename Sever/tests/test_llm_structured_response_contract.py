from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from Controller.llm_select_theme import parse_score, score_one  # noqa: E402
from Controller.paper_assets import extract_blocks_with_llm  # noqa: E402
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
                    extract_blocks_with_llm(_client(content), "paper text", cfg)

        blocks = extract_blocks_with_llm(
            _client(
                '{"blocks":{"summary":{"one_sentence_summary":"finding"}}}'
            ),
            "paper text",
            cfg,
        )
        self.assertEqual(blocks["summary"]["one_sentence_summary"], "finding")

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
