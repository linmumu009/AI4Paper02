"""Bounded reads for user-controlled uploads."""

from __future__ import annotations

from typing import Protocol


class AsyncUpload(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class UploadTooLarge(ValueError):
    pass


class PdfValidationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


async def read_upload_with_limit(file: AsyncUpload, max_bytes: int) -> bytes:
    """Read at most ``max_bytes + 1`` bytes and reject oversized uploads."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    payload = await file.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise UploadTooLarge(f"upload exceeds {max_bytes} bytes")
    return payload


def validate_pdf_upload(payload: bytes, *, max_pages: int = 2000) -> dict[str, int]:
    """Fail closed unless an upload is a readable, unencrypted PDF."""
    if not payload:
        raise PdfValidationError("PDF 文件为空")
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    if b"%PDF-" not in payload[:1024]:
        raise PdfValidationError("文件内容不是有效的 PDF")
    if b"%%EOF" not in payload[-2048:]:
        raise PdfValidationError("PDF 文件不完整或已损坏")

    try:
        import fitz
    except ImportError as exc:
        raise PdfValidationError(
            "PDF 校验服务暂时不可用，请稍后重试",
            status_code=503,
        ) from exc

    document = None
    try:
        document = fitz.open(stream=payload, filetype="pdf")
        if document.needs_pass:
            raise PdfValidationError("暂不支持加密或需要密码的 PDF")
        page_count = int(document.page_count)
        if page_count < 1:
            raise PdfValidationError("PDF 中没有可读取的页面")
        if page_count > max_pages:
            raise PdfValidationError(f"PDF 页数超过限制（最多 {max_pages} 页）")
        document.load_page(0)
        if page_count > 1:
            document.load_page(page_count - 1)
        return {"page_count": page_count, "size_bytes": len(payload)}
    except PdfValidationError:
        raise
    except Exception as exc:
        raise PdfValidationError("PDF 文件无法解析或已损坏") from exc
    finally:
        if document is not None:
            document.close()
