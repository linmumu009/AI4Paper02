from __future__ import annotations

import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services.network_target_guard import (  # noqa: E402
    OutboundURLRejected,
    validate_user_llm_base_url,
)


class NetworkTargetGuardTests(unittest.TestCase):
    def test_empty_url_uses_system_default(self) -> None:
        self.assertEqual(validate_user_llm_base_url("  "), "")

    def test_public_https_url_is_normalized(self) -> None:
        resolved = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        with patch("services.network_target_guard.socket.getaddrinfo", return_value=resolved):
            value = validate_user_llm_base_url(" HTTPS://API.Example.COM/v1/ ")
        self.assertEqual(value, "https://api.example.com/v1")

    def test_rejects_insecure_or_credentialed_urls(self) -> None:
        for value in (
            "http://api.example.com/v1",
            "https://user:password@api.example.com/v1",
            "https://api.example.com/v1#fragment",
            "https://api.example.com/v1?token=hidden",
            "https://api.example.com:99999/v1",
        ):
            with self.subTest(value=value), self.assertRaises(OutboundURLRejected):
                validate_user_llm_base_url(value)

    def test_rejects_literal_private_and_metadata_addresses(self) -> None:
        for value in (
            "https://127.0.0.1/v1",
            "https://10.0.0.2/v1",
            "https://169.254.169.254/latest/meta-data",
            "https://[::1]/v1",
        ):
            with self.subTest(value=value), self.assertRaises(OutboundURLRejected):
                validate_user_llm_base_url(value)

    def test_rejects_domains_that_resolve_to_private_addresses(self) -> None:
        resolved = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.20", 443))
        ]
        with (
            patch("services.network_target_guard.socket.getaddrinfo", return_value=resolved),
            self.assertRaises(OutboundURLRejected),
        ):
            validate_user_llm_base_url("https://model.example.com/v1")

    def test_rejects_local_domain_suffixes_before_dns(self) -> None:
        with patch("services.network_target_guard.socket.getaddrinfo") as resolver:
            with self.assertRaises(OutboundURLRejected):
                validate_user_llm_base_url("https://model.internal/v1")
        resolver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
