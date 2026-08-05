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
    _choice_text,
    load_pdf_info_map_for_run,
    process_one_with_fallback,
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


class TestChoiceText(unittest.TestCase):
    def test_none_content_returns_empty(self):
        self.assertEqual(_choice_text(_resp_with_content(None)), "")

    def test_strips_whitespace(self):
        self.assertEqual(_choice_text(_resp_with_content("  YES  ")), "YES")

    def test_no_choices_returns_empty(self):
        self.assertEqual(_choice_text(SimpleNamespace(choices=[])), "")


class TestStructureMatchesExample(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
