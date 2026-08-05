"""Application-level encryption and masking for stored credentials."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Mapping

from cryptography.fernet import Fernet, InvalidToken


_SEVER_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_KEY_PATH = _SEVER_ROOT / "database" / ".secret_storage_key"
_KEY_PATH = Path(os.environ.get("AI4PAPERS_SECRET_KEY_FILE", _DEFAULT_KEY_PATH))
_PREFIX = "enc:v1:"
SECRET_MASK = "••••••••"
_key_lock = threading.Lock()
_fernet: Fernet | None = None


class SecretStorageError(RuntimeError):
    pass


def _load_or_create_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    with _key_lock:
        if _fernet is not None:
            return _fernet
        _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            key = _KEY_PATH.read_bytes().strip()
        except FileNotFoundError:
            key = Fernet.generate_key()
            try:
                descriptor = os.open(
                    _KEY_PATH,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                key = _KEY_PATH.read_bytes().strip()
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(key + b"\n")
        try:
            os.chmod(_KEY_PATH, 0o600)
            _fernet = Fernet(key)
        except (OSError, ValueError) as exc:
            raise SecretStorageError("凭据加密密钥不可用") from exc
        return _fernet


def is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    return (
        normalized == "api_key"
        or normalized == "apikey"
        or normalized.endswith("_api_key")
        or normalized.endswith("_apikey")
        or normalized.endswith("_token")
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
    )


def is_encrypted_secret(value: Any) -> bool:
    return str(value or "").startswith(_PREFIX)


def encrypt_secret(value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    if is_encrypted_secret(raw):
        decrypt_secret(raw)
        return raw
    token = _load_or_create_fernet().encrypt(raw.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_secret(value: Any) -> str:
    raw = str(value or "")
    if not raw or not raw.startswith(_PREFIX):
        return raw
    try:
        return _load_or_create_fernet().decrypt(
            raw[len(_PREFIX):].encode("ascii")
        ).decode("utf-8")
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise SecretStorageError("已保存凭据无法解密") from exc


def protect_secret_mapping(
    values: Mapping[str, Any],
    *,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    protected = dict(values)
    previous = existing or {}
    for key, value in list(protected.items()):
        if not is_sensitive_key(key):
            continue
        if value == SECRET_MASK:
            value = previous.get(key, "")
        protected[key] = encrypt_secret(value)
    return protected


def unprotect_secret_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(values)
    for key, value in list(result.items()):
        if is_sensitive_key(key):
            result[key] = decrypt_secret(value)
    return result


def mask_secret_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(values)
    for key, value in list(result.items()):
        if is_sensitive_key(key):
            result[key] = SECRET_MASK if value else ""
    return result


def reset_key_cache_for_tests() -> None:
    global _fernet
    with _key_lock:
        _fernet = None
