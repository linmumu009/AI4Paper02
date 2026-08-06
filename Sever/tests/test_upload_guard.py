from __future__ import annotations

import asyncio
import io
import sys
import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services.upload_guard import (  # noqa: E402
    PdfValidationError,
    UploadTooLarge,
    read_upload_with_limit,
    validate_pdf_upload,
)


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

    @staticmethod
    def _pdf_bytes(page_count: int = 1, *, encrypted: bool = False) -> bytes:
        import fitz

        document = fitz.open()
        for _ in range(page_count):
            document.new_page()
        output = io.BytesIO()
        save_kwargs = {}
        if encrypted:
            save_kwargs = {
                "encryption": fitz.PDF_ENCRYPT_AES_256,
                "owner_pw": "owner-secret",
                "user_pw": "user-secret",
            }
        document.save(output, **save_kwargs)
        document.close()
        return output.getvalue()

    def test_accepts_readable_pdf_and_reports_bounds(self) -> None:
        payload = self._pdf_bytes(page_count=2)
        result = validate_pdf_upload(payload)

        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["size_bytes"], len(payload))

    def test_rejects_empty_disguised_truncated_and_encrypted_pdf(self) -> None:
        valid = self._pdf_bytes()
        cases = (
            (b"", "为空"),
            (b"not a pdf", "不是有效"),
            (valid.replace(b"%%EOF", b"BROKEN", 1), "不完整"),
            (self._pdf_bytes(encrypted=True), "加密"),
        )
        for payload, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(PdfValidationError) as raised:
                    validate_pdf_upload(payload)
                self.assertIn(expected, str(raised.exception))

    def test_rejects_excessive_page_count(self) -> None:
        with self.assertRaises(PdfValidationError) as raised:
            validate_pdf_upload(self._pdf_bytes(page_count=3), max_pages=2)
        self.assertIn("页数超过限制", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
