from __future__ import annotations

import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]


class SystemdUnitTests(unittest.TestCase):
    def test_api_uses_one_worker_while_in_process_schedulers_exist(self) -> None:
        unit = (_ROOT / "deploy" / "systemd" / "arxiv-api.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("--workers 1", unit)
        self.assertNotIn("--workers 2", unit)
        self.assertIn("KillMode=mixed", unit)
        self.assertIn("UMask=0077", unit)

    def test_deploy_installs_api_unit_before_restart(self) -> None:
        script = (_ROOT / "deploy_server.sh").read_text(encoding="utf-8")
        install_at = script.index("install -m 0644 \"$API_SERVICE_SOURCE\"")
        restart_at = script.index("systemctl restart arxiv-api")
        self.assertLess(install_at, restart_at)


if __name__ == "__main__":
    unittest.main()
