from __future__ import annotations

import ast
import threading
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch


_ROUTER_PATH = Path(__file__).resolve().parents[1] / "routers" / "pipeline_router.py"


def _load_rollback_function(namespace: dict):
    source = _ROUTER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_rollback_rerun_launch"
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(_ROUTER_PATH), "exec"), namespace)
    return namespace["_rollback_rerun_launch"]


class PipelineRerunLaunchRecoveryTests(unittest.TestCase):
    def test_launch_failure_contract_rolls_back_all_registered_state(self) -> None:
        source = _ROUTER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rerun = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "api_pipeline_rerun"
        )
        rerun_source = ast.get_source_segment(source, rerun) or ""

        self.assertIn("runtime_registered = True", rerun_source)
        self.assertGreaterEqual(rerun_source.count("_rollback_rerun_launch("), 2)
        self.assertIn("_release_execution_lease(lease_token)", rerun_source)
        self.assertIn("_pdb.update_run_status(new_run_id, \"failed\"", rerun_source)
        self.assertNotIn("detail=str(exc)", source)

    def test_rollback_marks_database_memory_and_disk_failed(self) -> None:
        state = {
            "running": True,
            "process": object(),
            "current_step": "starting",
            "run_id": "rerun_91",
        }
        saved_states = []
        db_service = types.ModuleType("services.pipeline_db_service")
        db_service.update_run_status = Mock()
        services = types.ModuleType("services")
        services.pipeline_db_service = db_service
        logger = Mock()
        namespace = {
            "BaseException": BaseException,
            "datetime": datetime,
            "timezone": timezone,
            "_pipeline_lock": threading.Lock(),
            "_pipeline_state": state,
            "_save_runtime_state": saved_states.append,
            "logger": logger,
            "redact_sensitive_text": lambda value: "redacted",
        }
        rollback = _load_rollback_function(namespace)

        with patch.dict(
            "sys.modules",
            {
                "services": services,
                "services.pipeline_db_service": db_service,
            },
        ):
            rollback(
                91,
                "2026-08-06T01:02:03+00:00",
                {"rerun_of": 90},
                "/tmp/rerun.log",
                "启动失败（错误编号：123456789abc）",
            )

        db_service.update_run_status.assert_called_once_with(
            91,
            "failed",
            error="启动失败（错误编号：123456789abc）",
        )
        self.assertFalse(state["running"])
        self.assertIsNone(state["process"])
        self.assertEqual(state["current_step"], "重跑启动失败")
        self.assertEqual(state["exit_code"], -1)
        self.assertEqual(len(saved_states), 1)
        self.assertFalse(saved_states[0]["running"])
        self.assertEqual(saved_states[0]["exit_code"], -1)
        self.assertEqual(saved_states[0]["error"], "启动失败（错误编号：123456789abc）")


if __name__ == "__main__":
    unittest.main()
