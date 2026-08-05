from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

_fastapi_stub = types.ModuleType("fastapi")


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


_fastapi_stub.HTTPException = _HTTPException
_fastapi_stub.Request = object
_spec = importlib.util.spec_from_file_location(
    "auth_service_session_test",
    _SEVER / "services" / "auth_service.py",
)
assert _spec is not None and _spec.loader is not None
auth_service = importlib.util.module_from_spec(_spec)
with patch.dict(
    sys.modules,
    {"fastapi": _fastapi_stub, "auth_service_session_test": auth_service},
):
    _spec.loader.exec_module(auth_service)


class AuthSessionRevocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "auth.db")
        self.patches = [
            patch.object(auth_service, "_DB_PATH", self.db_path),
            patch.object(auth_service, "PBKDF2_ROUNDS", 1_000),
        ]
        for item in self.patches:
            item.start()
        auth_service.init_auth_db()
        self.user = auth_service.register_user("security-user", "old-password")

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def _two_sessions(self) -> tuple[str, str]:
        first = auth_service.create_session(self.user["id"])["session_id"]
        second = auth_service.create_session(self.user["id"])["session_id"]
        return first, second

    def test_user_password_change_revokes_all_sessions(self) -> None:
        first, second = self._two_sessions()

        auth_service.change_user_password(
            self.user["id"],
            "old-password",
            "new-password",
        )

        self.assertIsNone(auth_service.get_user_by_session(first))
        self.assertIsNone(auth_service.get_user_by_session(second))
        self.assertIsNotNone(
            auth_service.verify_credentials("security-user", "new-password")
        )

    def test_admin_password_reset_revokes_all_sessions(self) -> None:
        first, second = self._two_sessions()

        auth_service.admin_reset_password(self.user["id"], "admin-new-password")

        self.assertIsNone(auth_service.get_user_by_session(first))
        self.assertIsNone(auth_service.get_user_by_session(second))
        self.assertIsNotNone(
            auth_service.verify_credentials("security-user", "admin-new-password")
        )


if __name__ == "__main__":
    unittest.main()
