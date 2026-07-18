"""Regression tests for public SEO and sitemap endpoints."""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

_SEVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SEVER_DIR not in sys.path:
    sys.path.insert(0, _SEVER_DIR)

from fastapi import HTTPException  # noqa: E402
from routers import seo_router  # noqa: E402


class TestSitemapPaperCollection(unittest.TestCase):
    def tearDown(self):
        seo_router._clear_sitemap_cache()

    @patch("services.data_service.get_papers_by_date")
    @patch("services.data_service.list_dates")
    def test_uses_database_data_and_deduplicates_papers(self, mock_dates, mock_papers):
        mock_dates.return_value = ["2026-07-18", "2026-07-17"]
        mock_papers.side_effect = lambda date_str, user_id=0: {
            "2026-07-18": [
                {"paper_id": "2607.12345"},
                {"paper_id": "2607.54321"},
                {"paper_id": "../invalid"},
            ],
            "2026-07-17": [{"paper_id": "2607.12345"}],
        }[date_str]

        entries = seo_router._collect_sitemap_paper_entries()

        self.assertEqual(
            entries,
            [
                ("2026-07-18", "2607.12345"),
                ("2026-07-18", "2607.54321"),
            ],
        )

    @patch("routers.seo_router._collect_sitemap_paper_entries")
    def test_stats_use_the_same_entries_as_sitemap(self, mock_entries):
        mock_entries.return_value = [
            ("2026-07-18", "2607.1"),
            ("2026-07-17", "2607.2"),
            ("2026-07-18", "2607.3"),
        ]

        total, dates = seo_router._collect_paper_stats()

        self.assertEqual(total, 3)
        self.assertEqual(dates, ["2026-07-18", "2026-07-17"])


class TestSitemapRoutes(unittest.TestCase):
    @patch("routers.seo_router._collect_sitemap_paper_entries")
    def test_single_sitemap_contains_public_guides_and_papers(self, mock_entries):
        mock_entries.return_value = [("2026-07-18", "2607.12345")]

        response = asyncio.run(seo_router.sitemap_xml())
        body = response.body.decode("utf-8")

        self.assertIn("<urlset", body)
        self.assertIn("https://ai4papers.com/guides/", body)
        self.assertIn("https://ai4papers.com/papers/2607.12345", body)
        self.assertNotIn("https://ai4papers.com/workbench", body)
        self.assertNotIn("https://ai4papers.com/community", body)

    @patch("routers.seo_router._SITEMAP_SPLIT_THRESHOLD", 1)
    @patch("routers.seo_router._collect_sitemap_paper_entries")
    def test_large_sitemap_index_points_to_real_child_routes(self, mock_entries):
        mock_entries.return_value = [
            ("2026-06-30", "2606.11111"),
            ("2026-07-18", "2607.22222"),
        ]

        response = asyncio.run(seo_router.sitemap_xml())
        body = response.body.decode("utf-8")

        self.assertIn("<sitemapindex", body)
        self.assertIn("/sitemap-static.xml", body)
        self.assertIn("/sitemap-2026-06.xml", body)
        self.assertIn("/sitemap-2026-07.xml", body)

        month_response = asyncio.run(seo_router.sitemap_month_xml("2026-07"))
        month_body = month_response.body.decode("utf-8")
        self.assertIn("/papers/2607.22222", month_body)
        self.assertNotIn("/papers/2606.11111", month_body)

    def test_month_sitemap_rejects_invalid_month(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(seo_router.sitemap_month_xml("2026-13"))
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
