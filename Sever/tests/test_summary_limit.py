"""Unit tests for summary_limit helpers (no network)."""

from __future__ import annotations

import sys
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
    structure_matches_example,
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
    def test_none_content_treated_as_no(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _resp_with_content(None)
        result = structure_matches_example(
            client, "笔记标题：测试\n🛎️文章简介", paper_id="2605.20022"
        )
        self.assertFalse(result)

    def test_yes_reply(self):
        client = MagicMock()
        client.chat.completions.create.return_value = _resp_with_content("yes")
        result = structure_matches_example(client, "some text", paper_id="x")
        self.assertTrue(result)


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
