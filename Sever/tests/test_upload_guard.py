from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services.upload_guard import UploadTooLarge, read_upload_with_limit  # noqa: E402


class _FakeUpload:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.requested_size: int | None = None

    async def read(self, size: int = -1) -> bytes:
        self.requested_size = size
        return self.payload[:size]


class UploadGuardTests(unittest.TestCase):
    def test_reads_only_one_byte_beyond_limit(self) -> None:
        upload = _FakeUpload(b"abcdef")
        with self.assertRaises(UploadTooLarge):
            asyncio.run(read_upload_with_limit(upload, 4))
        self.assertEqual(upload.requested_size, 5)

    def test_accepts_payload_at_limit(self) -> None:
        upload = _FakeUpload(b"abcd")
        result = asyncio.run(read_upload_with_limit(upload, 4))
        self.assertEqual(result, b"abcd")
        self.assertEqual(upload.requested_size, 5)


if __name__ == "__main__":
    unittest.main()
