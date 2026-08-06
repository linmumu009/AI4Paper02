from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
import sys
import tempfile
import unittest
import urllib.error
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
        self.assertLess(helper.index("create_paper"), helper.index("commit=created"))
        self.assertIn("commit=False", helper)
        self.assertIn('paper.pop("_created", True)', helper)

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

    def test_arxiv_duplicate_short_circuits_before_network_and_quota(self) -> None:
        route = _function_source(_ROUTER, "api_user_paper_import_arxiv")

        self.assertLess(route.index("normalize_arxiv_id"), route.index("get_paper_by_source"))
        self.assertLess(route.index("get_paper_by_source"), route.index("fetch_arxiv_metadata"))
        self.assertLess(route.index("if existing is not None"), route.index("fetch_arxiv_metadata"))
        self.assertLess(route.index("fetch_arxiv_metadata"), route.index("_create_paper_with_quota"))
        self.assertIn("deduplicate_source=True", route)

    def test_manual_and_pdf_duplicates_short_circuit_before_quota(self) -> None:
        manual = _function_source(_ROUTER, "api_user_paper_import_manual")
        pdf = _function_source(_ROUTER, "api_user_paper_import_pdf")

        self.assertLess(manual.index("build_manual_source_ref"), manual.index("get_paper_by_source"))
        self.assertLess(manual.index("get_paper_by_source"), manual.index("_create_paper_with_quota"))
        self.assertIn("deduplicate_source=True", manual)

        self.assertLess(pdf.index("read_upload_with_limit"), pdf.index("build_pdf_source_ref"))
        self.assertLess(pdf.index("build_pdf_source_ref"), pdf.index("get_paper_by_source"))
        self.assertLess(pdf.index("get_paper_by_source"), pdf.index("_create_paper_with_quota"))
        self.assertIn("deduplicate_source=True", pdf)

    def test_manual_fingerprint_uses_complete_normalized_metadata(self) -> None:
        first = user_paper_service.build_manual_source_ref(
            title="  A   Paper ",
            authors=["Alice", "BOB"],
            abstract="An abstract",
            institution="PKU",
            year=2026,
            external_url="HTTPS://EXAMPLE.COM/PAPER",
        )
        equivalent = user_paper_service.build_manual_source_ref(
            title="a paper",
            authors=["alice", "bob"],
            abstract="an   abstract",
            institution="pku",
            year=2026,
            external_url="https://example.com/paper",
        )
        different = user_paper_service.build_manual_source_ref(
            title="a paper",
            authors=["alice", "bob"],
            abstract="a different abstract",
            institution="pku",
            year=2026,
            external_url="https://example.com/paper",
        )

        self.assertEqual(first, equivalent)
        self.assertNotEqual(first, different)
        self.assertTrue(first.startswith("manual-sha256:"))

    def test_pdf_fingerprint_depends_only_on_exact_content(self) -> None:
        first = user_paper_service.build_pdf_source_ref(b"%PDF-same")
        second = user_paper_service.build_pdf_source_ref(b"%PDF-same")
        different = user_paper_service.build_pdf_source_ref(b"%PDF-different")

        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertTrue(first.startswith("pdf-sha256:"))

    def test_arxiv_id_normalization_is_strict_and_canonical(self) -> None:
        self.assertEqual(
            user_paper_service.normalize_arxiv_id(
                "https://arxiv.org/pdf/2501.00001V2.pdf?download=1"
            ),
            "2501.00001v2",
        )
        self.assertEqual(
            user_paper_service.normalize_arxiv_id("arXiv:hep-th/9901001v3"),
            "hep-th/9901001v3",
        )
        for invalid in ("", "../../etc/passwd", "https://example.com/2501.00001"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(user_paper_service.ArxivMetadataError):
                    user_paper_service.normalize_arxiv_id(invalid)

    def test_arxiv_http_reason_is_not_exposed(self) -> None:
        upstream = urllib.error.HTTPError(
            "https://export.arxiv.org/api/query",
            500,
            "private upstream token sk-secret-value",
            hdrs=None,
            fp=None,
        )
        with (
            patch("services.arxiv_rate_limit.wait_before_request"),
            patch("urllib.request.urlopen", side_effect=upstream),
        ):
            with self.assertRaises(user_paper_service.ArxivMetadataError) as raised:
                user_paper_service.fetch_arxiv_metadata("2501.00001")

        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn("private", str(raised.exception))
        self.assertNotIn("sk-secret", str(raised.exception))

    def test_concurrent_arxiv_create_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(user_paper_service, "_DB_PATH", str(root / "papers.db")),
                patch.object(user_paper_service, "_KB_DB_PATH", str(root / "analysis.db")),
                patch.object(user_paper_service, "_USER_PAPERS_DIR", str(root / "files")),
            ):
                user_paper_service.init_db()

                def create_once(_: int) -> dict:
                    return user_paper_service.create_paper(
                        7,
                        source_type="arxiv",
                        source_ref="2501.00001",
                        title="paper",
                        deduplicate_source=True,
                    )

                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(create_once, range(2)))

                self.assertEqual({item["paper_id"] for item in results}, {results[0]["paper_id"]})
                self.assertEqual(sorted(item["_created"] for item in results), [False, True])
                self.assertEqual(len(user_paper_service.list_papers(7)), 1)

    def test_concurrent_pdf_create_writes_only_one_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_bytes = b"%PDF-identical"
            source_ref = user_paper_service.build_pdf_source_ref(pdf_bytes)
            with (
                patch.object(user_paper_service, "_DB_PATH", str(root / "papers.db")),
                patch.object(user_paper_service, "_KB_DB_PATH", str(root / "analysis.db")),
                patch.object(user_paper_service, "_USER_PAPERS_DIR", str(root / "files")),
            ):
                user_paper_service.init_db()

                def create_once(_: int) -> dict:
                    return user_paper_service.create_paper(
                        7,
                        source_type="pdf",
                        source_ref=source_ref,
                        title="paper",
                        pdf_bytes=pdf_bytes,
                        deduplicate_source=True,
                    )

                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(create_once, range(2)))

                self.assertEqual({item["paper_id"] for item in results}, {results[0]["paper_id"]})
                self.assertEqual(sorted(item["_created"] for item in results), [False, True])
                self.assertEqual(len(user_paper_service.list_papers(7)), 1)
                self.assertEqual(len(list((root / "files").rglob("*.pdf"))), 1)

    def test_duplicate_response_sanitizes_stored_task_errors(self) -> None:
        router_source = _ROUTER.read_text(encoding="utf-8")
        enrich = _function_source(_ROUTER, "_enrich_user_paper")

        self.assertIn("safe_stored_error", router_source)
        self.assertIn('p.get("process_error")', enrich)
        self.assertIn('p.get("translate_error")', enrich)

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
