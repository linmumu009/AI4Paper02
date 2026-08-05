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
        self.assertIn("User=ai4papers", unit)
        self.assertIn("Group=ai4papers", unit)
        self.assertIn("Environment=COOKIE_SECURE=true", unit)
        self.assertIn("Environment=COOKIE_SAMESITE=lax", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("PrivateTmp=true", unit)
        self.assertIn("PrivateDevices=true", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ProtectHome=true", unit)
        self.assertIn("ProtectKernelTunables=true", unit)
        self.assertIn("ProtectKernelModules=true", unit)
        self.assertIn("ProtectControlGroups=true", unit)
        self.assertIn("RestrictSUIDSGID=true", unit)
        self.assertIn("LockPersonality=true", unit)
        self.assertIn("RestrictNamespaces=true", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", unit)
        self.assertIn("CapabilityBoundingSet=", unit)
        self.assertIn("AmbientCapabilities=", unit)
        self.assertIn(
            "ReadWritePaths=/projects/ArxivPaper4/Sever/data", unit
        )
        self.assertIn(
            "ReadWritePaths=/projects/ArxivPaper4/Sever/database", unit
        )
        self.assertIn(
            "ReadWritePaths=/projects/ArxivPaper4/Sever/logs", unit
        )
        self.assertIn(
            "ReadWritePaths=/projects/ArxivPaper4/Sever/config/paperList.json",
            unit,
        )

    def test_deploy_installs_api_unit_before_restart(self) -> None:
        script = (_ROOT / "deploy_server.sh").read_text(encoding="utf-8")
        prepare_at = script.index("prepare_api_runtime_permissions")
        install_at = script.index("install -m 0644 \"$API_SERVICE_SOURCE\"")
        restart_at = script.index("systemctl restart arxiv-api")
        self.assertLess(prepare_at, restart_at)
        self.assertLess(install_at, restart_at)

    def test_deploy_prepares_dedicated_account_and_runtime_paths(self) -> None:
        script = (_ROOT / "deploy_server.sh").read_text(encoding="utf-8")
        self.assertIn('SERVICE_USER="ai4papers"', script)
        self.assertIn("useradd --system --user-group", script)
        self.assertIn('"${server_root}/data"', script)
        self.assertIn('"${server_root}/database"', script)
        self.assertIn('"${server_root}/logs"', script)
        self.assertIn('paper_list="${server_root}/config/paperList.json"', script)
        self.assertIn('setfacl -R -m "u:${SERVICE_USER}:rwX"', script)
        self.assertIn('setfacl -m "d:u:${SERVICE_USER}:rwx"', script)
        self.assertIn('setfacl -m "u:${SERVICE_USER}:rw" "$paper_list"', script)
        self.assertNotIn('chown -R "$SERVICE_USER:$SERVICE_GROUP"', script)
        self.assertIn('"${server_root}/database/.secret_storage_key"', script)
        self.assertIn('"${server_root}/database/kb_file_signing.key"', script)
        self.assertIn('chown "$SERVICE_USER:$SERVICE_GROUP" "$key_file"', script)
        self.assertIn('chmod 0600 "$key_file"', script)

    def test_deploy_rolls_back_api_unit_when_restart_fails(self) -> None:
        script = (_ROOT / "deploy_server.sh").read_text(encoding="utf-8")
        self.assertIn(
            "if ! systemctl restart arxiv-api || ! api_is_ready; then",
            script,
        )
        self.assertIn("http://127.0.0.1:8000/api/papers?date=", script)
        self.assertIn("API restart failed; restoring the previous service unit.", script)
        self.assertIn('mv -f "$API_SERVICE_BACKUP" "$API_SERVICE_TARGET"', script)

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
        self.assertIn("User=ai4papers", service)
        self.assertIn("Group=ai4papers", service)
        self.assertNotIn("EnvironmentFile", service)
        self.assertIn("systemctl enable --now ai4papers-healthcheck.timer", script)


if __name__ == "__main__":
    unittest.main()
