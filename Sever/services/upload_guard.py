"""Bounded reads for user-controlled uploads."""

from __future__ import annotations

from typing import Protocol


class AsyncUpload(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class UploadTooLarge(ValueError):
    pass


async def read_upload_with_limit(file: AsyncUpload, max_bytes: int) -> bytes:
    """Read at most ``max_bytes + 1`` bytes and reject oversized uploads."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    payload = await file.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise UploadTooLarge(f"upload exceeds {max_bytes} bytes")
    return payload
