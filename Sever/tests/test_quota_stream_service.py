from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import entitlement_service, quota_stream_service  # noqa: E402


class QuotaStreamServiceTests(unittest.TestCase):
    def test_validation_error_stream_releases_uncommitted_quota(self) -> None:
        stream = iter(("data: validation failed\n\n", "data: [DONE]\n\n"))
        with (
            patch.object(entitlement_service, "commit_quota_reservation") as commit,
            patch.object(entitlement_service, "release_quota_reservation") as release,
        ):
            output = list(
                quota_stream_service.guard_quota_stream(
                    stream,
                    "reservation-error",
                )
            )

        self.assertEqual(output, ["data: validation failed\n\n", "data: [DONE]\n\n"])
        commit.assert_not_called()
        release.assert_called_once_with("reservation-error")

    def test_commit_signal_is_filtered_and_finalizes_quota_once(self) -> None:
        on_commit = Mock()
        stream = iter((
            quota_stream_service.STREAM_QUOTA_COMMIT,
            quota_stream_service.STREAM_QUOTA_COMMIT,
            "data: answer\n\n",
        ))
        with (
            patch.object(entitlement_service, "commit_quota_reservation") as commit,
            patch.object(entitlement_service, "release_quota_reservation") as release,
        ):
            output = list(
                quota_stream_service.guard_quota_stream(
                    stream,
                    "reservation-ok",
                    on_commit=on_commit,
                )
            )

        self.assertEqual(output, ["data: answer\n\n"])
        commit.assert_called_once_with("reservation-ok")
        release.assert_not_called()
        on_commit.assert_called_once_with()

    def test_exception_before_signal_refunds_quota(self) -> None:
        def _broken_stream():
            raise RuntimeError("validation crash")
            yield  # pragma: no cover

        with patch.object(entitlement_service, "release_quota_reservation") as release:
            with self.assertRaises(RuntimeError):
                list(
                    quota_stream_service.guard_quota_stream(
                        _broken_stream(),
                        "reservation-crash",
                    )
                )

        release.assert_called_once_with("reservation-crash")


if __name__ == "__main__":
    unittest.main()
