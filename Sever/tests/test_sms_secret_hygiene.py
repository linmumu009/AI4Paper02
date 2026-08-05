from __future__ import annotations

import ast
import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]


class SmsSecretHygieneTests(unittest.TestCase):
    def test_sms_service_does_not_import_legacy_secret_config(self) -> None:
        path = _ROOT / "Sever/services/sms_service.py"
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        self.assertNotIn("sms_config1", source)
        self.assertIn("ALIBABA_CLOUD_ACCESS_KEY_ID", source)
        self.assertIn("ALIBABA_CLOUD_ACCESS_KEY_SECRET", source)
        self.assertIn("AI4PAPERS_SMS_TEMPLATE_CODE", source)

    def test_sms_errors_are_not_returned_or_printed_raw(self) -> None:
        source = (_ROOT / "Sever/services/sms_service.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('f"发送失败：{exc}"', source)
        self.assertNotIn("check_verify_code error: {exc_str}", source)
        self.assertGreaterEqual(source.count("safe_failure_detail("), 2)

    def test_service_unit_uses_root_managed_environment_file(self) -> None:
        unit = (_ROOT / "deploy/systemd/arxiv-api.service").read_text(
            encoding="utf-8"
        )
        deploy = (_ROOT / "deploy_server.sh").read_text(encoding="utf-8")
        self.assertIn("EnvironmentFile=-/etc/ai4papers/sms.env", unit)
        self.assertIn("install -d -o root -g root -m 0700 /etc/ai4papers", deploy)


if __name__ == "__main__":
    unittest.main()
