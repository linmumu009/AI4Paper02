from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import user_paper_service  # noqa: E402


_ROUTER = _SEVER / "routers" / "user_paper_router.py"


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )
    return ast.get_source_segment(source, function) or ""


class UserPaperImportQuotaContractTests(unittest.TestCase):
    def test_all_import_routes_finalize_quota_after_create(self) -> None:
        source = _ROUTER.read_text(encoding="utf-8")
        helper = _function_source(_ROUTER, "_create_paper_with_quota")

        self.assertNotIn('consume_quota(_user["id"], "upload")', source)
        self.assertIn('reserve_quota(user_id, "upload")', helper)
        self.assertLess(helper.index("create_paper"), helper.index("commit=True"))
        self.assertIn("commit=False", helper)

        for route_name in (
            "api_user_paper_import_manual",
            "api_user_paper_import_arxiv",
            "api_user_paper_import_pdf",
        ):
            route = _function_source(_ROUTER, route_name)
            self.assertIn("_create_paper_with_quota", route)

    def test_arxiv_transport_error_is_not_exposed(self) -> None:
        route = _function_source(_ROUTER, "api_user_paper_import_arxiv")

        self.assertIn("safe_failure_detail", route)
        self.assertIn("user_paper_arxiv_metadata_fetch", route)
        self.assertNotIn('f"arXiv 请求失败: {exc}"', route)

    def test_failed_database_connection_removes_written_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paper_root = Path(temp_dir) / "user_papers"
            with (
                patch.object(user_paper_service, "_USER_PAPERS_DIR", str(paper_root)),
                patch.object(user_paper_service, "_new_paper_id", return_value="paper-test"),
                patch.object(
                    user_paper_service,
                    "_connect",
                    side_effect=RuntimeError("database unavailable"),
                ),
            ):
                with self.assertRaises(RuntimeError):
                    user_paper_service.create_paper(
                        7,
                        source_type="pdf",
                        title="paper",
                        pdf_bytes=b"%PDF-test",
                        pdf_filename="paper.pdf",
                    )

            self.assertFalse((paper_root / "7" / "paper-test").exists())
            self.assertEqual(list(paper_root.rglob("*.pdf")), [])

    def test_failed_insert_rolls_back_and_removes_written_pdf(self) -> None:
        connection = Mock()
        connection.execute.side_effect = RuntimeError("insert failed")
        with tempfile.TemporaryDirectory() as temp_dir:
            paper_root = Path(temp_dir) / "user_papers"
            with (
                patch.object(user_paper_service, "_USER_PAPERS_DIR", str(paper_root)),
                patch.object(user_paper_service, "_new_paper_id", return_value="paper-test"),
                patch.object(user_paper_service, "_connect", return_value=connection),
            ):
                with self.assertRaises(RuntimeError):
                    user_paper_service.create_paper(
                        7,
                        source_type="pdf",
                        title="paper",
                        pdf_bytes=b"%PDF-test",
                    )

            connection.rollback.assert_called_once_with()
            connection.close.assert_called_once_with()
            self.assertEqual(list(paper_root.rglob("*.pdf")), [])

    def test_reload_failure_happens_before_commit_and_removes_pdf(self) -> None:
        connection = Mock()
        connection.execute.side_effect = (None, RuntimeError("reload failed"))
        with tempfile.TemporaryDirectory() as temp_dir:
            paper_root = Path(temp_dir) / "user_papers"
            with (
                patch.object(user_paper_service, "_USER_PAPERS_DIR", str(paper_root)),
                patch.object(user_paper_service, "_new_paper_id", return_value="paper-test"),
                patch.object(user_paper_service, "_connect", return_value=connection),
            ):
                with self.assertRaises(RuntimeError):
                    user_paper_service.create_paper(
                        7,
                        source_type="pdf",
                        title="paper",
                        pdf_bytes=b"%PDF-test",
                    )

            connection.commit.assert_not_called()
            connection.rollback.assert_called_once_with()
            connection.close.assert_called_once_with()
            self.assertEqual(list(paper_root.rglob("*.pdf")), [])


if __name__ == "__main__":
    unittest.main()
