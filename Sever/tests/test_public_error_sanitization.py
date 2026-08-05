from __future__ import annotations

import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]


class PublicErrorSanitizationTests(unittest.TestCase):
    def _source(self, relative: str) -> str:
        return (_SEVER / relative).read_text(encoding="utf-8")

    def test_streaming_services_do_not_emit_raw_exceptions(self) -> None:
        expectations = {
            "services/idea_pipeline_service.py": ("生成失败: {exc}",),
            "services/compare_service.py": ("分析失败: {exc}",),
            "services/chat_service.py": ("问答失败: {exc}",),
            "services/research_service.py": (
                "摘要分析失败: {exc}",
                "全文分析失败: {exc}",
                "研究会话异常: {exc}",
                "续接 Round 3 异常: {exc}",
                "追问会话异常: {exc}",
                "exc.message",
                "return str(exc)",
            ),
        }
        for relative, forbidden in expectations.items():
            source = self._source(relative)
            self.assertIn("safe_failure_detail", source, relative)
            for value in forbidden:
                self.assertNotIn(value, source, f"{relative}: {value}")

    def test_background_task_errors_are_stored_as_public_references(self) -> None:
        for relative in (
            "services/user_paper_pipeline_service.py",
            "services/kb_pipeline_service.py",
            "services/auto_classify_service.py",
            "services/translate_service.py",
        ):
            source = self._source(relative)
            self.assertIn("safe_failure_detail", source, relative)
            self.assertNotIn("error=str(exc)[:500]", source, relative)

    def test_status_endpoints_hide_legacy_raw_database_errors(self) -> None:
        kb_router = self._source("routers/kb_router.py")
        user_router = self._source("routers/user_paper_router.py")
        self.assertGreaterEqual(kb_router.count("safe_stored_error("), 3)
        self.assertGreaterEqual(user_router.count("safe_stored_error("), 2)


if __name__ == "__main__":
    unittest.main()
