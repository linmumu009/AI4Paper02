from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from Controller import instutions_filter  # noqa: E402
from services import pipeline_db_service  # noqa: E402


class InstitutionsFilterEmptyNoticeTests(unittest.TestCase):
    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(output_mode="db", user_id=34)

    def test_zero_intersection_writes_explicit_empty_result_notice(self) -> None:
        paper_info = [
            {"paper_arxiv_id": "paper-a", "title": "A", "is_large": 0, "abstract": "A"},
            {"paper_arxiv_id": "paper-b", "title": "B", "is_large": 1, "abstract": "B"},
        ]
        selected = [
            {"paper_arxiv_id": "paper-a", "passed_theme_filter": 1},
            {"paper_arxiv_id": "paper-b", "passed_theme_filter": 0},
        ]
        with (
            patch.dict(os.environ, {"RUN_DATE": "2026-08-05"}),
            patch.object(pipeline_db_service, "get_paper_info", return_value=paper_info),
            patch.object(
                pipeline_db_service,
                "get_selected_papers",
                return_value=selected,
            ),
            patch.object(
                pipeline_db_service,
                "bulk_upsert_selected_papers",
            ) as bulk_upsert,
            patch.object(pipeline_db_service, "upsert_date_notice") as upsert_notice,
        ):
            instutions_filter.run(self._args())

        upsert_notice.assert_called_once_with(
            34,
            "2026-08-05",
            "no_matching_papers",
            "今天没有同时满足相关性与机构筛选条件的论文。",
        )
        updated_rows = bulk_upsert.call_args.args[2]
        self.assertEqual([row["paper_arxiv_id"] for row in updated_rows], ["paper-a"])

    def test_nonempty_intersection_does_not_write_empty_notice(self) -> None:
        paper_info = [
            {"paper_arxiv_id": "paper-a", "title": "A", "is_large": 1, "abstract": "A"}
        ]
        selected = [{"paper_arxiv_id": "paper-a", "passed_theme_filter": 1}]
        with (
            patch.dict(os.environ, {"RUN_DATE": "2026-08-05"}),
            patch.object(pipeline_db_service, "get_paper_info", return_value=paper_info),
            patch.object(
                pipeline_db_service,
                "get_selected_papers",
                return_value=selected,
            ),
            patch.object(pipeline_db_service, "bulk_upsert_selected_papers"),
            patch.object(pipeline_db_service, "upsert_date_notice") as upsert_notice,
        ):
            instutions_filter.run(self._args())

        upsert_notice.assert_not_called()

    def test_missing_valid_paper_info_fails_instead_of_marking_success(self) -> None:
        selected = [{"paper_arxiv_id": "paper-a", "passed_theme_filter": 1}]
        with (
            patch.dict(os.environ, {"RUN_DATE": "2026-08-05"}),
            patch.object(
                pipeline_db_service,
                "get_paper_info",
                return_value=[{"paper_arxiv_id": "paper-a", "title": "A", "abstract": ""}],
            ),
            patch.object(
                pipeline_db_service,
                "get_selected_papers",
                return_value=selected,
            ),
            patch.object(pipeline_db_service, "bulk_upsert_selected_papers") as bulk_upsert,
        ):
            with self.assertRaises(SystemExit):
                instutions_filter.run(self._args())

        bulk_upsert.assert_not_called()


if __name__ == "__main__":
    unittest.main()
