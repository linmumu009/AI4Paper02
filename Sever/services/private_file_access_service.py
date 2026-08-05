"""Authentication and short-lived signatures for private KB files."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from pathlib import PurePosixPath
from typing import Optional
from urllib.parse import quote, unquote


_SEVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KB_ROOT = os.path.join(_SEVER_ROOT, "data", "kb_files")
_KEY_PATH = os.environ.get(
    "KB_FILE_SIGNING_KEY_PATH",
    os.path.join(_SEVER_ROOT, "database", "kb_file_signing.key"),
)
_STATIC_PREFIX = "/static/kb_files/"
_DEFAULT_TTL_SECONDS = 6 * 60 * 60
_MAX_TTL_SECONDS = 24 * 60 * 60
_key_lock = threading.Lock()


def _load_or_create_signing_key() -> bytes:
    try:
        with open(_KEY_PATH, "rb") as handle:
            key = handle.read()
        if len(key) >= 32:
            return key
    except FileNotFoundError:
        pass

    with _key_lock:
        try:
            with open(_KEY_PATH, "rb") as handle:
                key = handle.read()
            if len(key) >= 32:
                return key
        except FileNotFoundError:
            pass

        os.makedirs(os.path.dirname(os.path.abspath(_KEY_PATH)), exist_ok=True)
        key = secrets.token_bytes(32)
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
            fd = os.open(_KEY_PATH, flags, 0o600)
        except FileExistsError:
            with open(_KEY_PATH, "rb") as handle:
                existing = handle.read()
            if len(existing) < 32:
                raise RuntimeError("KB file signing key is invalid")
            return existing
        try:
            remaining = memoryview(key)
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise OSError("Failed to write KB file signing key")
                remaining = remaining[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.chmod(_KEY_PATH, 0o600)
        except OSError:
            pass
        return key


def _normalize_relative_path(relative_path: str) -> str:
    raw = unquote(str(relative_path or "")).replace("\\", "/").lstrip("/")
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
        or "\x00" in raw
    ):
        raise ValueError("Invalid KB file path")
    return path.as_posix()


def path_belongs_to_user(relative_path: str, user_id: int) -> bool:
    try:
        parts = PurePosixPath(_normalize_relative_path(relative_path)).parts
    except ValueError:
        return False
    expected = str(int(user_id))
    if len(parts) >= 3 and parts[0] == "user_papers":
        return parts[1] == expected
    return len(parts) >= 2 and parts[0] == expected


def _relative_from_absolute(abs_path: str) -> str:
    root = os.path.abspath(_KB_ROOT)
    candidate = os.path.abspath(abs_path)
    if candidate == root or not candidate.startswith(root + os.sep):
        raise ValueError("KB file is outside the private root")
    return _normalize_relative_path(os.path.relpath(candidate, root))


def _signature_payload(user_id: int, expires_at: int, relative_path: str) -> bytes:
    return f"v1\n{int(user_id)}\n{int(expires_at)}\n{relative_path}".encode("utf-8")


def _sign(user_id: int, expires_at: int, relative_path: str) -> str:
    return hmac.new(
        _load_or_create_signing_key(),
        _signature_payload(user_id, expires_at, relative_path),
        hashlib.sha256,
    ).hexdigest()


def build_signed_kb_file_url(
    abs_path: str,
    user_id: int,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> str:
    relative_path = _relative_from_absolute(abs_path)
    if not path_belongs_to_user(relative_path, user_id):
        raise ValueError("KB file does not belong to this user")
    ttl = max(60, min(int(ttl_seconds), _MAX_TTL_SECONDS))
    expires_at = int(time.time()) + ttl
    signature = _sign(user_id, expires_at, relative_path)
    encoded_path = quote(relative_path, safe="/")
    return (
        f"{_STATIC_PREFIX}{encoded_path}?uid={int(user_id)}"
        f"&exp={expires_at}&sig={signature}"
    )


def verify_signed_kb_file_url(
    relative_path: str,
    user_id: int,
    expires_at: int,
    signature: str,
    *,
    now: Optional[int] = None,
) -> bool:
    try:
        normalized = _normalize_relative_path(relative_path)
        uid = int(user_id)
        expiry = int(expires_at)
    except (TypeError, ValueError):
        return False
    current = int(time.time()) if now is None else int(now)
    if expiry < current or expiry > current + _MAX_TTL_SECONDS + 60:
        return False
    if not path_belongs_to_user(normalized, uid):
        return False
    expected = _sign(uid, expiry, normalized)
    return bool(signature) and hmac.compare_digest(expected, str(signature))


def _json_error(status_code: int, detail: str):
    from starlette.responses import JSONResponse

    return JSONResponse({"detail": detail}, status_code=status_code)


def _get_request_user(request):
    from services import auth_service

    return auth_service.get_current_user_optional(request)


class PrivateKbFilesMiddleware:
    """Protect the existing StaticFiles mount without changing its URL shape."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        root_path = str(scope.get("root_path") or "").rstrip("/")
        if root_path and (path == root_path or path.startswith(root_path + "/")):
            path = path[len(root_path):] or "/"
        if not path.startswith(_STATIC_PREFIX):
            await self.app(scope, receive, send)
            return
        if scope.get("method") not in ("GET", "HEAD"):
            await _json_error(405, "Method not allowed")(scope, receive, send)
            return

        from starlette.requests import Request
        request = Request(scope, receive=receive)
        relative_path = path[len(_STATIC_PREFIX):]
        signed_ok = verify_signed_kb_file_url(
            relative_path,
            request.query_params.get("uid", ""),
            request.query_params.get("exp", ""),
            request.query_params.get("sig", ""),
        )

        user = None
        if not signed_ok:
            try:
                user = _get_request_user(request)
            except Exception:
                user = None
        session_ok = bool(user) and path_belongs_to_user(relative_path, user["id"])
        if not signed_ok and not session_ok:
            status = 403 if user else 401
            await _json_error(status, "无权访问该知识库文件")(scope, receive, send)
            return

        async def send_private(message):
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.extend([
                    (b"cache-control", b"private, max-age=300"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-content-type-options", b"nosniff"),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_private)
