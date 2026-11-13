from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import auth_service, date_notice_service, pipeline_db_service  # noqa: E402


class DateNoticeAudienceTests(unittest.TestCase):
    def test_notice_audience_includes_registered_and_configured_users(self) -> None:
        with (
            patch.object(auth_service, "list_user_ids", return_value=[3, 28]),
            patch.object(
                date_notice_service,
                "list_users_with_custom_configs",
                return_value=[3, 34],
            ),
        ):
            self.assertEqual(
                date_notice_service.list_notice_user_ids(),
                [0, 3, 28, 34],
            )

    def test_notice_audience_falls_back_when_auth_lookup_fails(self) -> None:
        with (
            patch.object(auth_service, "list_user_ids", side_effect=OSError("db")),
            patch.object(
                date_notice_service,
                "list_users_with_custom_configs",
                return_value=[34],
            ),
        ):
            self.assertEqual(date_notice_service.list_notice_user_ids(), [0, 34])

    def test_notice_is_written_for_every_user(self) -> None:
        with (
            patch.object(
                date_notice_service,
                "list_notice_user_ids",
                return_value=[0, 28, 34],
            ),
            patch.object(pipeline_db_service, "upsert_date_notice") as upsert,
        ):
            recipients = date_notice_service.upsert_notice_for_all_users(
                "2026-11-13",
                "pipeline_processing",
                "正在生成",
            )

        self.assertEqual(recipients, [0, 28, 34])
        self.assertEqual(
            upsert.call_args_list,
            [
                call(0, "2026-11-13", "pipeline_processing", "正在生成"),
                call(28, "2026-11-13", "pipeline_processing", "正在生成"),
                call(34, "2026-11-13", "pipeline_processing", "正在生成"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
