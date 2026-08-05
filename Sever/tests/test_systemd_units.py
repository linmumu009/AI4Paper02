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

    def test_healthcheck_timer_is_periodic_and_installed(self) -> None:
        timer = (
            _ROOT / "deploy" / "systemd" / "ai4papers-healthcheck.timer"
        ).read_text(encoding="utf-8")
        service = (
            _ROOT / "deploy" / "systemd" / "ai4papers-healthcheck.service"
        ).read_text(encoding="utf-8")
        script = (_ROOT / "deploy_server.sh").read_text(encoding="utf-8")
        self.assertIn("OnCalendar=*-*-* *:00/10:00", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("check_system_health.py --no-alert", service)
        self.assertNotIn("EnvironmentFile", service)
        self.assertIn("systemctl enable --now ai4papers-healthcheck.timer", script)


if __name__ == "__main__":
    unittest.main()
