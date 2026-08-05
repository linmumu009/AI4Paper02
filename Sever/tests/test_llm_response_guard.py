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
        self.assertIn('operation="paper_chat_stream"', chat)
        self.assertIn('operation="idea_stream_generation"', idea)
        self.assertIn("secondary summary generation incomplete", summary)


if __name__ == "__main__":
    unittest.main()
