from __future__ import annotations

import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]


class NginxSecurityTests(unittest.TestCase):
    def test_api_has_per_ip_rate_and_connection_limits(self) -> None:
        config = (_ROOT / "nginx" / "arxivpaper4.conf").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "limit_req_zone $binary_remote_addr "
            "zone=ai4papers_api_per_ip:10m rate=20r/s;",
            config,
        )
        self.assertIn(
            "limit_conn_zone $binary_remote_addr "
            "zone=ai4papers_connections_per_ip:10m;",
            config,
        )
        self.assertEqual(
            config.count(
                "limit_req zone=ai4papers_api_per_ip burst=40 nodelay;"
            ),
            2,
        )
        self.assertEqual(
            config.count("limit_conn ai4papers_connections_per_ip 30;"),
            2,
        )
        self.assertIn("limit_req_status 429;", config)
        self.assertIn("limit_conn_status 429;", config)

    def test_nginx_version_is_not_exposed(self) -> None:
        config = (_ROOT / "nginx" / "arxivpaper4.conf").read_text(
            encoding="utf-8"
        )
        self.assertIn("server_tokens off;", config)


if __name__ == "__main__":
    unittest.main()
