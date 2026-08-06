from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import (  # noqa: E402
    auto_classify_service,
    entitlement_service,
    kb_pipeline_service,
    translate_service,
    user_paper_pipeline_service,
)


class BackgroundTaskLaunchFailureTests(unittest.TestCase):
    def tearDown(self) -> None:
        auto_classify_service._running_jobs.clear()
        kb_pipeline_service._running_jobs.clear()
        user_paper_pipeline_service._running_jobs.clear()
        translate_service._translate_jobs.clear()
        translate_service._cancel_requests.clear()

    @staticmethod
    def _make_thread_start_fail(thread_cls) -> None:
        thread_cls.return_value.start.side_effect = RuntimeError("private launch detail")

    def test_auto_classify_launch_failure_releases_claim_and_marks_failed(self) -> None:
        with (
            patch("services.kb_service.set_classify_status") as set_status,
            patch.object(auto_classify_service.threading, "Thread") as thread_cls,
        ):
            self._make_thread_start_fail(thread_cls)

            started = auto_classify_service.enqueue_classify(7, "paper-auto", "kb")

        self.assertFalse(started)
        self.assertFalse(auto_classify_service.is_classifying(7, "paper-auto", "kb"))
        self.assertEqual(set_status.call_args_list[0].kwargs["status"], "pending")
        failure = set_status.call_args_list[-1].kwargs
        self.assertEqual(failure["status"], "failed")
        self.assertIn("自动分类任务启动失败", failure["error"])
        self.assertNotIn("private launch detail", failure["error"])

    def test_kb_pipeline_launch_failure_releases_claim_and_marks_failed(self) -> None:
        with (
            patch("services.kb_service.get_kb_paper", return_value={"paper_id": "paper-kb"}),
            patch("services.kb_service.set_kb_paper_process_status") as set_status,
            patch.object(kb_pipeline_service.threading, "Thread") as thread_cls,
        ):
            self._make_thread_start_fail(thread_cls)

            started, message = kb_pipeline_service.start_kb_paper_process(
                7, "paper-kb", "kb"
            )

        self.assertFalse(started)
        self.assertFalse(kb_pipeline_service.is_processing("paper-kb"))
        self.assertIn("知识库论文处理任务启动失败", message)
        self.assertNotIn("private launch detail", message)
        self.assertEqual(set_status.call_args_list[0].kwargs["status"], "pending")
        self.assertEqual(set_status.call_args_list[-1].kwargs["status"], "failed")

    def test_user_pipeline_launch_failure_releases_claim_and_marks_failed(self) -> None:
        with (
            patch("services.user_paper_service.set_process_status") as set_status,
            patch.object(user_paper_pipeline_service.threading, "Thread") as thread_cls,
        ):
            self._make_thread_start_fail(thread_cls)

            started, message = user_paper_pipeline_service.start_processing(
                7, "paper-user"
            )

        self.assertFalse(started)
        self.assertIn("论文处理任务启动失败", message)
        self.assertNotIn("private launch detail", message)
        self.assertFalse(user_paper_pipeline_service.is_processing("paper-user"))
        self.assertEqual(set_status.call_args_list[0].kwargs["status"], "pending")
        failure = set_status.call_args_list[-1].kwargs
        self.assertEqual(failure["status"], "failed")
        self.assertTrue(failure["finished"])
        self.assertNotIn("private launch detail", failure["error"])

    def test_user_translation_launch_failure_releases_claim_and_marks_failed(self) -> None:
        with (
            patch("services.user_paper_service.get_paper", return_value={"paper_id": "paper-tr"}),
            patch("services.user_paper_service.set_translate_status") as set_status,
            patch.object(translate_service.threading, "Thread") as thread_cls,
        ):
            self._make_thread_start_fail(thread_cls)

            started, message = translate_service.start_translation(7, "paper-tr")

        self.assertFalse(started)
        self.assertFalse(translate_service.is_translating("paper-tr"))
        self.assertIn("翻译任务启动失败", message)
        self.assertNotIn("private launch detail", message)
        self.assertEqual(set_status.call_args_list[0].kwargs["status"], "processing")
        failure = set_status.call_args_list[-1].kwargs
        self.assertEqual(failure["status"], "failed")
        self.assertTrue(failure["finished"])

    def test_kb_translation_launch_failure_releases_claim_and_marks_failed(self) -> None:
        with (
            patch("services.kb_service.get_kb_paper", return_value={"paper_id": "paper-kb-tr"}),
            patch("services.kb_service.set_kb_paper_translate_status") as set_status,
            patch.object(translate_service.threading, "Thread") as thread_cls,
        ):
            self._make_thread_start_fail(thread_cls)

            started, message = translate_service.start_kb_translation(
                7, "paper-kb-tr", "kb"
            )

        self.assertFalse(started)
        self.assertFalse(translate_service.is_translating("paper-kb-tr"))
        self.assertIn("翻译任务启动失败", message)
        self.assertNotIn("private launch detail", message)
        self.assertEqual(set_status.call_args_list[0].kwargs["status"], "processing")
        self.assertEqual(set_status.call_args_list[-1].kwargs["status"], "failed")

    def test_translation_launch_failure_refunds_reserved_quota(self) -> None:
        with (
            patch("services.user_paper_service.get_paper", return_value={"paper_id": "paper-bill"}),
            patch("services.user_paper_service.set_translate_status"),
            patch.object(translate_service.threading, "Thread") as thread_cls,
            patch.object(
                entitlement_service,
                "reserve_quota",
                return_value={"reservation_id": "reservation-1"},
            ) as reserve,
            patch.object(entitlement_service, "commit_quota_reservation") as commit,
            patch.object(entitlement_service, "release_quota_reservation") as release,
        ):
            self._make_thread_start_fail(thread_cls)

            started, _message = translate_service.start_translation(
                7,
                "paper-bill",
                charge_quota=True,
            )

        self.assertFalse(started)
        reserve.assert_called_once_with(7, "translate")
        commit.assert_not_called()
        release.assert_called_once_with("reservation-1")

    def test_duplicate_translation_does_not_reserve_quota(self) -> None:
        job_key = translate_service._translation_job_key(
            7,
            "paper-duplicate",
            source="user",
        )
        self.assertTrue(translate_service._claim(job_key))
        with (
            patch("services.user_paper_service.get_paper", return_value={"paper_id": "paper-duplicate"}),
            patch.object(entitlement_service, "reserve_quota") as reserve,
        ):
            started, message = translate_service.start_translation(
                7,
                "paper-duplicate",
                charge_quota=True,
            )

        self.assertFalse(started)
        self.assertIn("进行中", message)
        reserve.assert_not_called()

    def test_translation_claims_are_isolated_by_user_and_source(self) -> None:
        user_7 = translate_service._translation_job_key(7, "same-paper", source="user")
        user_8 = translate_service._translation_job_key(8, "same-paper", source="user")
        kb_7 = translate_service._translation_job_key(
            7,
            "same-paper",
            source="kb",
            scope="kb",
        )

        self.assertTrue(translate_service._claim(user_7))
        self.assertTrue(translate_service._claim(user_8))
        self.assertTrue(translate_service._claim(kb_7))
        self.assertTrue(
            translate_service.is_translating(
                "same-paper",
                8,
                source="user",
            )
        )

    def test_cancel_keeps_claim_until_worker_exits(self) -> None:
        job_key = translate_service._translation_job_key(
            7,
            "paper-cancel",
            source="user",
        )
        self.assertTrue(translate_service._claim(job_key))
        with (
            patch(
                "services.user_paper_service.get_paper",
                return_value={"paper_id": "paper-cancel", "translate_status": "processing"},
            ),
            patch("services.user_paper_service.set_translate_status"),
        ):
            ok, _message = translate_service.cancel_translation(7, "paper-cancel")

        self.assertTrue(ok)
        self.assertTrue(
            translate_service.is_translating(
                "paper-cancel",
                7,
                source="user",
            )
        )


if __name__ == "__main__":
    unittest.main()
