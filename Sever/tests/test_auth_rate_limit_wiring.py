from __future__ import annotations

import unittest
from pathlib import Path


_SEVER = Path(__file__).resolve().parents[1]


class AuthRateLimitWiringTests(unittest.TestCase):
    def test_login_is_limited_by_ip_and_account(self) -> None:
        source = (_SEVER / "routers" / "auth_router.py").read_text(encoding="utf-8")
        start = source.index("def api_auth_login(")
        end = source.index("\n\n@router.post", start)
        login_source = source[start:end]
        self.assertIn("_login_limiter.check(client_ip)", login_source)
        self.assertIn("_login_account_limiter.check(body.username)", login_source)

    def test_sms_is_limited_by_ip_and_phone(self) -> None:
        source = (_SEVER / "routers" / "auth_router.py").read_text(encoding="utf-8")
        self.assertIn("_sms_send_limiter.check(client_ip)", source)
        self.assertIn("_sms_send_phone_limiter.check(body.phone)", source)
        self.assertIn("_sms_verify_limiter.check(client_ip)", source)
        self.assertIn("_sms_verify_phone_limiter.check(body.phone)", source)


if __name__ == "__main__":
    unittest.main()
