from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_MODULES = (
    "Sever/routers/preference_router.py",
    "Sever/routers/radar_router.py",
    "Sever/routers/recap_router.py",
    "Sever/routers/task_center_router.py",
    "Sever/scripts/calibrate_user_weights.py",
    "Sever/services/arxiv_rate_limit.py",
    "Sever/services/calibration_service.py",
    "Sever/services/impression_service.py",
    "Sever/services/pdf_cleanup_service.py",
    "Sever/services/preference_service.py",
    "Sever/services/recap_service.py",
    "Sever/services/research_memory_service.py",
    "Sever/services/task_center_service.py",
)
_LITERAL_SECRET_RE = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{8,}|"
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)"
    r"\s*=\s*['\"][^'\"]{4,}['\"])"
)


class RuntimeModuleRecoveryTests(unittest.TestCase):
    def test_deployed_runtime_modules_exist_and_parse_from_repository(self) -> None:
        self.assertEqual(len(_RUNTIME_MODULES), len(set(_RUNTIME_MODULES)))
        for relative in _RUNTIME_MODULES:
            path = _ROOT / relative
            self.assertTrue(path.is_file(), relative)
            ast.parse(path.read_text(encoding="utf-8"), filename=relative)

    def test_runtime_modules_contain_no_obvious_literal_credentials(self) -> None:
        for relative in _RUNTIME_MODULES:
            source = (_ROOT / relative).read_text(encoding="utf-8")
            self.assertIsNone(_LITERAL_SECRET_RE.search(source), relative)

    def test_api_wires_all_runtime_routers(self) -> None:
        source = (_ROOT / "Sever/api.py").read_text(encoding="utf-8")
        for router_name in (
            "preference_router",
            "radar_router",
            "recap_router",
            "task_center_router",
        ):
            self.assertIn(
                f"from routers.{router_name} import router as {router_name}", source
            )
            self.assertIn(f"app.include_router({router_name})", source)

    def test_admin_diagnostics_do_not_return_raw_exceptions(self) -> None:
        preference = (_ROOT / "Sever/services/preference_service.py").read_text(
            encoding="utf-8"
        )
        cleanup = (_ROOT / "Sever/services/pdf_cleanup_service.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('return {"error": str(exc)}', preference)
        self.assertIn("safe_failure_detail", preference)
        self.assertNotIn('errors.append(f"{pdf_path}: {exc}")', cleanup)
        self.assertIn("redact_sensitive_text", cleanup)


if __name__ == "__main__":
    unittest.main()
