from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services.llm_response_guard import (  # noqa: E402
    EmptyLlmResponseError,
    require_nonempty_text,
)
from services.translate_service import (  # noqa: E402
    _translate_blocks_batch,
    _translate_one_chunk,
)
from services.research_service import _call_llm_sync, _stream_llm  # noqa: E402


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


def _stream_client(chunks):
    completions = SimpleNamespace(create=lambda **_kwargs: iter(chunks))
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


class LlmResponseGuardTests(unittest.TestCase):
    def test_requires_visible_text(self) -> None:
        self.assertEqual(require_nonempty_text("  result  ", operation="test"), "result")
        for value in (None, "", " \n\t"):
            with self.subTest(value=value):
                with self.assertRaises(EmptyLlmResponseError):
                    require_nonempty_text(value, operation="test")

    def test_chunk_translation_rejects_empty_success(self) -> None:
        with self.assertLogs("services.translate_service", level="ERROR"):
            with self.assertRaises(EmptyLlmResponseError):
                _translate_one_chunk(
                    2,
                    "source",
                    client=_client(None),
                    model="test",
                    max_tokens=100,
                    temperature=0.1,
                )

    def test_block_translation_rejects_missing_blocks(self) -> None:
        batch = [
            SimpleNamespace(block_id="a", render_md="A"),
            SimpleNamespace(block_id="b", render_md="B"),
        ]
        with self.assertRaisesRegex(RuntimeError, "omitted 1 translated blocks"):
            _translate_blocks_batch(
                0,
                batch,
                client=_client("[BLOCK:a]\n译文"),
                model="test",
                max_tokens=100,
                temperature=0.1,
            )

    def test_user_facing_streams_enforce_nonempty_content(self) -> None:
        chat = (_SEVER / "services/chat_service.py").read_text(encoding="utf-8")
        idea = (_SEVER / "services/idea_pipeline_service.py").read_text(
            encoding="utf-8"
        )
        summary = (_SEVER / "Controller/paper_summary_claude.py").read_text(
            encoding="utf-8"
        )
        compare = (_SEVER / "services/compare_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('operation="paper_chat_stream"', chat)
        self.assertIn('operation="idea_stream_generation"', idea)
        self.assertIn('operation="paper_compare_stream"', compare)
        self.assertIn("secondary summary generation incomplete", summary)

    def test_research_sync_rejects_empty_success(self) -> None:
        with self.assertRaises(EmptyLlmResponseError):
            _call_llm_sync(
                _client(None),
                {"llm_model": "test"},
                [{"role": "user", "content": "question"}],
            )

    def test_research_stream_records_empty_success_as_error(self) -> None:
        errors = []
        with self.assertLogs("services.research_service", level="ERROR"):
            events = list(
                _stream_llm(
                    _stream_client([]),
                    {"llm_model": "test"},
                    [{"role": "user", "content": "question"}],
                    round_num=2,
                    error_state=errors,
                )
            )
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], EmptyLlmResponseError)
        self.assertTrue(any('"type": "error"' in event for event in events))


if __name__ == "__main__":
    unittest.main()
