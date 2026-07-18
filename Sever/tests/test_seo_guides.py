"""Validate the static, crawlable SEO/GEO guide pages."""

import json
import os
import unittest
from html.parser import HTMLParser

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_GUIDES_ROOT = os.path.join(_PROJECT_ROOT, "View", "public", "guides")


class _GuideParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1_count = 0
        self.canonical = ""
        self.json_ld_blocks: list[str] = []
        self._in_json_ld = False
        self._json_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "h1":
            self.h1_count += 1
        if tag == "link" and attributes.get("rel") == "canonical":
            self.canonical = attributes.get("href", "")
        if tag == "script" and attributes.get("type") == "application/ld+json":
            self._in_json_ld = True
            self._json_parts = []

    def handle_data(self, data):
        if self._in_json_ld:
            self._json_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_json_ld:
            self.json_ld_blocks.append("".join(self._json_parts).strip())
            self._in_json_ld = False


class TestSeoGuides(unittest.TestCase):
    GUIDE_PAGES = {
        "index.html": "https://ai4papers.com/guides/",
        os.path.join("ai-paper-recommendation", "index.html"): "https://ai4papers.com/guides/ai-paper-recommendation/",
        os.path.join("arxiv-chinese-summary", "index.html"): "https://ai4papers.com/guides/arxiv-chinese-summary/",
        os.path.join("research-paper-workflow", "index.html"): "https://ai4papers.com/guides/research-paper-workflow/",
    }

    def test_pages_have_one_h1_canonical_and_valid_json_ld(self):
        for relative_path, expected_canonical in self.GUIDE_PAGES.items():
            with self.subTest(page=relative_path):
                full_path = os.path.join(_GUIDES_ROOT, relative_path)
                with open(full_path, "r", encoding="utf-8") as handle:
                    content = handle.read()

                parser = _GuideParser()
                parser.feed(content)

                self.assertEqual(parser.h1_count, 1)
                self.assertEqual(parser.canonical, expected_canonical)
                self.assertTrue(parser.json_ld_blocks)
                for block in parser.json_ld_blocks:
                    parsed = json.loads(block)
                    self.assertEqual(parsed.get("@context"), "https://schema.org")

    def test_machine_readable_index_links_every_article(self):
        llms_path = os.path.join(_GUIDES_ROOT, "llms.txt")
        with open(llms_path, "r", encoding="utf-8") as handle:
            content = handle.read()

        for canonical in list(self.GUIDE_PAGES.values())[1:]:
            self.assertIn(canonical, content)
        self.assertIn("AI summaries may be incomplete or wrong", content)


if __name__ == "__main__":
    unittest.main()
