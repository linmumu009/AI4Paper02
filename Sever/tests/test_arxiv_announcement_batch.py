from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from Controller import arxiv_search04  # noqa: E402
from services import data_service, pipeline_db_service  # noqa: E402


def _rss(batch_date: str, items: str):
    payload = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"
         xmlns:arxiv="http://arxiv.org/schemas/atom"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
      <channel>
        <title>arXiv test feed</title>
        <pubDate>{batch_date}</pubDate>
        {items}
      </channel>
    </rss>
    """
    return arxiv_search04.feedparser.parse(payload)


def _item(
    paper_id: str,
    title: str,
    announce_type: str,
    categories: tuple[str, ...],
) -> str:
    category_xml = "".join(f"<category>{cat}</category>" for cat in categories)
    return f"""
      <item>
        <title>{title}</title>
        <link>https://arxiv.org/abs/{paper_id}</link>
        <description>arXiv:{paper_id} Announce Type: {announce_type}
        Abstract: Abstract for {title}.</description>
        <dc:creator>Alice Example, Bob Example</dc:creator>
        <arxiv:announce_type>{announce_type}</arxiv:announce_type>
        {category_xml}
        <pubDate>Tue, 18 Aug 2026 00:00:00 -0400</pubDate>
      </item>
    """


def _listing(
    batch_label: str,
    new_ids: tuple[str, ...],
    cross_ids: tuple[str, ...] = (),
    replacement_ids: tuple[str, ...] = (),
) -> str:
    def section(label: str, ids: tuple[str, ...]) -> str:
        links = "".join(
            f'<dt><a href ="/abs/{paper_id}" title="Abstract">arXiv:{paper_id}</a></dt>'
            for paper_id in ids
        )
        return f"<h3>{label} (showing {len(ids)} of {len(ids)} entries)</h3>{links}"

    return (
        f"<h3>Showing new listings for {batch_label}</h3>"
        + section("New submissions", new_ids)
        + section("Cross submissions", cross_ids)
        + section("Replacement submissions", replacement_ids)
    )


def _pastweek(days: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    sections = []
    for label, ids in days:
        links = "".join(
            f'<dt><a href="/abs/{paper_id}" title="Abstract">arXiv:{paper_id}</a></dt>'
            for paper_id in ids
        )
        sections.append(
            f"<h3>{label} (showing {len(ids)} of {len(ids)} entries )</h3>{links}"
        )
    return '<div class="morefewer">Showing up to 2000 entries per page:</div>' + "".join(sections)


def _oai_record(
    paper_id: str,
    title: str,
    abstract: str,
    categories: str = "cs.AI",
) -> str:
    return f"""
      <record>
        <header>
          <identifier>oai:arXiv.org:{paper_id}</identifier>
          <datestamp>2026-08-28</datestamp>
          <setSpec>cs:cs:AI</setSpec>
        </header>
        <metadata>
          <arXiv xmlns="http://arxiv.org/OAI/arXiv/">
            <id>{paper_id}</id>
            <created>2026-08-27</created>
            <authors>
              <author><keyname>Example</keyname><forenames>Alice</forenames><affiliation>Example University</affiliation></author>
              <author><keyname>Researcher</keyname><forenames>Bob</forenames></author>
            </authors>
            <title>{title}</title>
            <categories>{categories}</categories>
            <abstract>{abstract}</abstract>
          </arXiv>
        </metadata>
      </record>
    """


def _oai(records: str, token: str = "") -> bytes:
    token_xml = f"<resumptionToken>{token}</resumptionToken>" if token else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
      <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
        <responseDate>2026-08-28T00:00:00Z</responseDate>
        <ListRecords>{records}{token_xml}</ListRecords>
      </OAI-PMH>
    """.encode("utf-8")


class OfficialAnnouncementBatchTests(unittest.TestCase):
    def test_new_listing_parser_keeps_new_and_cross_but_not_replacements(self) -> None:
        batch_date, ids = arxiv_search04.parse_new_listing_page(
            _listing(
                "Tuesday, 18 August 2026",
                ("2608.10001", "2608.10002"),
                ("2608.10003",),
                ("2608.00001v2",),
            )
        )
        self.assertEqual(batch_date, date(2026, 8, 18))
        self.assertEqual(ids, ["2608.10001", "2608.10002", "2608.10003"])

    def test_pastweek_parser_selects_one_exact_day(self) -> None:
        page = _pastweek(
            (
                ("Fri, 28 Aug 2026", ("2608.20001",)),
                ("Thu, 27 Aug 2026", ("2608.10001", "2506.09557")),
            )
        )
        ids = arxiv_search04.parse_pastweek_listing_page(
            page,
            date(2026, 8, 27),
            "cs.AI",
        )
        self.assertEqual(ids, ["2608.10001", "2506.09557"])

    def test_pastweek_missing_day_is_retryable_not_an_empty_batch(self) -> None:
        page = _pastweek((("Fri, 28 Aug 2026", ("2608.20001",)),))
        with self.assertRaises(arxiv_search04.AnnouncementBatchNotReady):
            arxiv_search04.parse_pastweek_listing_page(
                page,
                date(2026, 8, 27),
                "cs.AI",
            )

    def test_oai_category_mapping_matches_official_hierarchy(self) -> None:
        self.assertEqual(
            arxiv_search04.oai_set_spec_for_category("cs.AI"),
            "cs:cs:AI",
        )
        self.assertEqual(
            arxiv_search04.oai_set_spec_for_category("stat.ML"),
            "stat:stat:ML",
        )

    def test_oai_record_preserves_full_metadata(self) -> None:
        payload = _oai(
            _oai_record(
                "2608.12345",
                "Graph agents for science",
                "A complete abstract with equations and evidence.",
                "cs.AI cs.LG",
            )
        )
        papers, token = arxiv_search04.parse_oai_records(
            payload,
            date(2026, 8, 28),
        )
        self.assertEqual(token, "")
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].arxiv_id, "2608.12345")
        self.assertEqual(papers[0].authors, ["Alice Example", "Bob Researcher"])
        self.assertEqual(papers[0].paper_categories, ["cs.AI", "cs.LG"])
        self.assertEqual(papers[0].affiliations, ["Example University"])
        self.assertEqual(
            papers[0].summary,
            "A complete abstract with equations and evidence.",
        )

    def test_local_query_supports_phrases_fields_parentheses_and_wildcards(self) -> None:
        paper = arxiv_search04.Paper(
            title="Graph neural agents for scientific discovery",
            published_utc=datetime(2026, 8, 28, tzinfo=timezone.utc),
            arxiv_id="2608.12345",
            link="https://arxiv.org/abs/2608.12345",
            authors=["Alice Example"],
            summary="We evaluate language reasoning without a vision benchmark.",
            paper_categories=["cs.AI", "cs.LG"],
        )
        matching_queries = (
            '"graph neural" discovery',
            'ti:graph AND (abs:language OR au:missing)',
            'cat:cs.LG AND ti:agen*',
        )
        for query in matching_queries:
            with self.subTest(query=query):
                self.assertEqual(
                    arxiv_search04.filter_papers_by_local_arxiv_query([paper], query),
                    [paper],
                )
        self.assertEqual(
            arxiv_search04.filter_papers_by_local_arxiv_query(
                [paper],
                "ti:graph ANDNOT abs:vision",
            ),
            [],
        )

    def test_local_query_rejects_fields_missing_from_oai_instead_of_misfiltering(self) -> None:
        paper = arxiv_search04.Paper(
            title="Paper",
            published_utc=datetime(2026, 8, 28, tzinfo=timezone.utc),
            arxiv_id="2608.12345",
            link="https://arxiv.org/abs/2608.12345",
            authors=[],
            summary="Abstract",
            paper_categories=["cs.AI"],
        )
        with self.assertRaisesRegex(ValueError, "cannot be evaluated"):
            arxiv_search04.filter_papers_by_local_arxiv_query(
                [paper],
                "submittedDate:202608280000",
            )

    def test_oai_daily_batch_fills_small_cross_list_gap_with_get_record(self) -> None:
        daily_payload = _oai(
            _oai_record(
                "2608.10001",
                "Graph transformers",
                "Vision benchmark.",
            )
        )
        gap_payload = _oai(
            _oai_record(
                "2506.09557",
                "Graph agents",
                "Language reasoning benchmark.",
            )
        )

        def payload_for(_session, params, _logger, **_kwargs):
            return daily_payload if params["verb"] == "ListRecords" else gap_payload

        with patch.object(
            arxiv_search04,
            "fetch_oai_xml_with_retry",
            side_effect=payload_for,
        ) as fetch:
            papers = arxiv_search04.fetch_metadata_for_announcement_ids(
                object(),
                ["2608.10001", "2506.09557"],
                ["cs.AI"],
                date(2026, 8, 28),
                "ti:graph ANDNOT abs:vision",
                logging.getLogger("test"),
                retries=1,
                sleep_seconds=0,
                base_429_wait=1,
                max_429_wait=1,
            )

        self.assertEqual([paper.arxiv_id for paper in papers], ["2506.09557"])
        self.assertEqual(fetch.call_count, 2)

    def test_large_oai_gap_waits_for_batch_instead_of_hammering_get_record(self) -> None:
        paper_ids = [f"2608.{index:05d}" for index in range(20)]
        with (
            patch.object(
                arxiv_search04,
                "fetch_oai_category_records",
                return_value=[],
            ),
            patch.object(arxiv_search04, "fetch_oai_record") as get_record,
        ):
            with self.assertRaises(arxiv_search04.AnnouncementMetadataIncomplete):
                arxiv_search04.fetch_metadata_for_announcement_ids(
                    object(),
                    paper_ids,
                    ["cs.AI"],
                    date(2026, 8, 28),
                    "",
                    logging.getLogger("test"),
                    retries=1,
                    sleep_seconds=0,
                    base_429_wait=1,
                    max_429_wait=1,
                )
        get_record.assert_not_called()

    def test_recent_historical_batch_uses_pastweek_then_oai(self) -> None:
        current = _listing("Friday, 28 August 2026", ("2608.20001",))
        pastweek = _pastweek(
            (("Thu, 27 Aug 2026", ("2608.10001", "2506.09557")),)
        )
        metadata = [
            arxiv_search04.Paper(
                title=f"Paper {paper_id}",
                published_utc=datetime(2026, 8, 27, tzinfo=timezone.utc),
                arxiv_id=paper_id,
                link=f"https://arxiv.org/abs/{paper_id}",
                authors=["Alice"],
                summary="Abstract",
                paper_categories=["cs.AI"],
            )
            for paper_id in ("2608.10001", "2506.09557")
        ]
        with (
            patch.object(
                arxiv_search04,
                "fetch_new_listing_with_retry",
                return_value=current,
            ) as fetch_new,
            patch.object(
                arxiv_search04,
                "fetch_pastweek_listing_with_retry",
                return_value=pastweek,
            ) as fetch_pastweek,
            patch.object(
                arxiv_search04,
                "fetch_metadata_for_announcement_ids",
                return_value=metadata,
            ) as hydrate,
            patch.object(arxiv_search04.time, "sleep"),
        ):
            papers, candidates, listing_dates = (
                arxiv_search04.fetch_official_new_listing_batch(
                    object(),
                    ["cs.AI", "cs.LG"],
                    date(2026, 8, 27),
                    "",
                    logging.getLogger("test"),
                    max_papers=10,
                    retries=1,
                    sleep_seconds=0,
                    base_429_wait=1,
                    max_429_wait=1,
                )
            )

        self.assertEqual([paper.arxiv_id for paper in papers], ["2608.10001", "2506.09557"])
        self.assertEqual(candidates, 2)
        self.assertEqual(
            listing_dates,
            {"cs.AI": "2026-08-27", "cs.LG": "2026-08-27"},
        )
        self.assertEqual(fetch_new.call_count, 1)
        self.assertEqual(fetch_pastweek.call_count, 2)
        self.assertEqual(hydrate.call_args.args[2], ["cs.AI", "cs.LG"])

    def test_historical_cutoff_window_includes_tuesday_weekend_backlog(self) -> None:
        start, end = arxiv_search04.compute_submission_window_for_announcement_date(
            date(2026, 8, 18)
        )
        self.assertEqual(start, datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 8, 17, 18, 0, tzinfo=timezone.utc))

        monday_start, monday_end = (
            arxiv_search04.compute_submission_window_for_announcement_date(
                date(2026, 8, 17)
            )
        )
        self.assertEqual(
            monday_start,
            datetime(2026, 8, 13, 18, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            monday_end,
            datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc),
        )

    def test_rss_batch_metadata_and_abstract_are_parsed(self) -> None:
        feed = _rss(
            "Tue, 18 Aug 2026 00:00:00 -0400",
            _item("2608.12345v2", "A useful paper", "new", ("cs.CL",)),
        )

        self.assertEqual(arxiv_search04.parse_rss_batch_date(feed), date(2026, 8, 18))
        paper = arxiv_search04.paper_from_rss_entry(feed.entries[0], date(2026, 8, 18))
        self.assertEqual(paper.arxiv_id, "2608.12345")
        self.assertEqual(paper.summary, "Abstract for A useful paper.")
        self.assertEqual(paper.authors, ["Alice Example", "Bob Example"])
        self.assertEqual(paper.paper_categories, ["cs.CL"])

    def test_batch_unions_categories_deduplicates_and_excludes_replacements(self) -> None:
        batch_date = "Tue, 18 Aug 2026 00:00:00 -0400"
        cl_feed = _rss(
            batch_date,
            _item("2608.10001", "Shared paper", "new", ("cs.CL", "cs.AI"))
            + _item("2608.10002", "Replacement", "replace", ("cs.CL",)),
        )
        ai_feed = _rss(
            batch_date,
            _item("2608.10001", "Shared paper", "cross", ("cs.CL", "cs.AI"))
            + _item("2608.10003", "AI paper", "new", ("cs.AI",)),
        )
        feeds = {"cs.CL": cl_feed, "cs.AI": ai_feed}

        with (
            patch.object(
                arxiv_search04,
                "fetch_rss_feed_with_retry",
                side_effect=lambda _session, category, _logger, **_kwargs: feeds[category],
            ),
            patch.object(arxiv_search04.time, "sleep"),
        ):
            papers, candidates, feed_dates = (
                arxiv_search04.fetch_official_announcement_batch(
                    object(),
                    ["cs.CL", "cs.AI"],
                    date(2026, 8, 18),
                    "",
                    logging.getLogger("test"),
                    retries=1,
                    sleep_seconds=0,
                    base_429_wait=1,
                    max_429_wait=1,
                )
            )

        self.assertEqual([paper.arxiv_id for paper in papers], ["2608.10003", "2608.10001"])
        self.assertEqual(candidates, 2)
        self.assertEqual(
            feed_dates,
            {"cs.CL": "2026-08-18", "cs.AI": "2026-08-18"},
        )

    def test_stale_rss_batch_is_retryable_instead_of_becoming_empty_success(self) -> None:
        stale_feed = _rss(
            "Mon, 17 Aug 2026 00:00:00 -0400",
            _item("2608.00001", "Old paper", "new", ("cs.CL",)),
        )
        with patch.object(
            arxiv_search04,
            "fetch_rss_feed_with_retry",
            return_value=stale_feed,
        ):
            with self.assertRaises(arxiv_search04.AnnouncementBatchNotReady):
                arxiv_search04.fetch_official_announcement_batch(
                    object(),
                    ["cs.CL"],
                    date(2026, 8, 18),
                    "",
                    logging.getLogger("test"),
                    retries=1,
                    sleep_seconds=0,
                    base_429_wait=1,
                    max_429_wait=1,
                )


class AnnouncementPersistenceTests(unittest.TestCase):
    @staticmethod
    def _paper(paper_id: str) -> dict:
        return {
            "paper_arxiv_id": paper_id,
            "title": f"Paper {paper_id}",
            "abstract_text": "Abstract",
            "authors": ["Author"],
            "published_utc": "2026-08-18T04:00:00+00:00",
            "link": f"https://arxiv.org/abs/{paper_id}",
            "categories": ["cs.CL"],
            "paper_categories": ["cs.CL"],
        }

    def test_verified_batch_replaces_stale_rows_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "pipeline.db")
            with patch.object(pipeline_db_service, "_DB_PATH", db_path):
                pipeline_db_service.init_db()
                pipeline_db_service.bulk_upsert_arxiv_list(
                    "2026-08-18",
                    [self._paper("old.1"), self._paper("keep.1")],
                )
                pipeline_db_service.bulk_upsert_arxiv_list(
                    "2026-08-18",
                    [self._paper("keep.1"), self._paper("new.1")],
                    replace_existing=True,
                )
                ids = pipeline_db_service.get_arxiv_list_ids("2026-08-18")

        self.assertEqual(ids, ["keep.1", "new.1"])

    def test_weekend_digest_has_an_explanatory_notice_without_a_pipeline_run(self) -> None:
        with (
            patch.object(data_service, "get_papers_by_date", return_value=[]),
            patch.object(pipeline_db_service, "get_date_notice", return_value=None),
        ):
            digest = data_service.get_daily_digest("2026-08-22", user_id=7)

        self.assertEqual(digest["notice"]["type"], "no_papers_weekend")


if __name__ == "__main__":
    unittest.main()
