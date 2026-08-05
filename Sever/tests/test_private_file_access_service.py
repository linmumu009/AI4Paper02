from __future__ import annotations

import os
import asyncio
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import private_file_access_service as service  # noqa: E402


class PrivateFileAccessServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "kb_files"
        self.key_path = Path(self.temp_dir.name) / "database" / "signing.key"
        self.root.mkdir(parents=True)
        self.patches = [
            patch.object(service, "_KB_ROOT", str(self.root)),
            patch.object(service, "_KEY_PATH", str(self.key_path)),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def _parse(self, url: str) -> tuple[str, dict[str, list[str]]]:
        parsed = urlsplit(url)
        relative = unquote(parsed.path.removeprefix(service._STATIC_PREFIX))
        return relative, parse_qs(parsed.query)

    def _middleware_status(self, path: str, query: str = "") -> int:
        messages: list[dict] = []

        async def downstream(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query.encode("ascii"),
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("test", 443),
        }
        with patch.object(service, "_get_request_user", return_value=None):
            asyncio.run(service.PrivateKbFilesMiddleware(downstream)(scope, receive, send))
        return next(message["status"] for message in messages if message["type"] == "http.response.start")

    def test_signed_url_is_valid_only_for_owner_and_unmodified_path(self) -> None:
        target = self.root / "3" / "2608.00001" / "paper.pdf"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"pdf")

        relative, query = self._parse(
            service.build_signed_kb_file_url(str(target), user_id=3)
        )

        self.assertTrue(service.verify_signed_kb_file_url(
            relative, 3, int(query["exp"][0]), query["sig"][0]
        ))
        self.assertFalse(service.verify_signed_kb_file_url(
            relative, 4, int(query["exp"][0]), query["sig"][0]
        ))
        self.assertFalse(service.verify_signed_kb_file_url(
            relative + ".other", 3, int(query["exp"][0]), query["sig"][0]
        ))

    def test_expired_signature_is_rejected(self) -> None:
        relative = "3/2608.00001/paper.pdf"
        expiry = int(time.time()) - 1
        signature = service._sign(3, expiry, relative)
        self.assertFalse(service.verify_signed_kb_file_url(
            relative, 3, expiry, signature
        ))

    def test_user_paper_and_kb_ownership_patterns(self) -> None:
        self.assertTrue(service.path_belongs_to_user("3/paper/file.pdf", 3))
        self.assertFalse(service.path_belongs_to_user("3/paper/file.pdf", 4))
        self.assertTrue(service.path_belongs_to_user("user_papers/4/paper/file.pdf", 4))
        self.assertFalse(service.path_belongs_to_user("user_papers/4/paper/file.pdf", 3))
        self.assertFalse(service.path_belongs_to_user("paper/file.pdf", 3))
        self.assertFalse(service.path_belongs_to_user("3/../4/file.pdf", 3))

    def test_signing_refuses_files_outside_private_root(self) -> None:
        outside = Path(self.temp_dir.name) / "outside.pdf"
        outside.write_bytes(b"pdf")
        with self.assertRaises(ValueError):
            service.build_signed_kb_file_url(str(outside), user_id=3)

    def test_middleware_denies_anonymous_unsigned_request(self) -> None:
        self.assertEqual(
            self._middleware_status("/static/kb_files/3/paper/file.pdf"),
            401,
        )

    def test_middleware_accepts_valid_signed_request(self) -> None:
        target = self.root / "3" / "2608.00001" / "paper.pdf"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"pdf")
        signed_url = service.build_signed_kb_file_url(str(target), user_id=3)
        parsed = urlsplit(signed_url)

        self.assertEqual(self._middleware_status(parsed.path, parsed.query), 200)


if __name__ == "__main__":
    unittest.main()
