from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import config_mapper, config_service, llm_config_service  # noqa: E402
from services import secret_storage_service as secrets  # noqa: E402


class LlmConfigBindingSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.db_path = root / "paper_analysis.db"
        self.config_path = root / "config.json"
        self.key_path = root / "credential.key"
        self.module_snapshot = config_service._get_all_config_items()
        self.patches = [
            patch.object(llm_config_service, "_DB_PATH", str(self.db_path)),
            patch.object(config_service, "_CONFIG_JSON_PATH", str(self.config_path)),
            patch.object(secrets, "_KEY_PATH", self.key_path),
        ]
        for item in self.patches:
            item.start()
        secrets.reset_key_cache_for_tests()
        llm_config_service.init_db()

    def tearDown(self) -> None:
        for key, value in self.module_snapshot.items():
            setattr(config_service.config_module, key, value)
        secrets.reset_key_cache_for_tests()
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def _create_config(self, *, name: str = "DeepSeek", key: str = "sk-old") -> dict:
        return llm_config_service.create_config(
            {
                "name": name,
                "base_url": "https://api.deepseek.com",
                "api_key": key,
                "model": "deepseek-v4-flash",
                "max_tokens": 8192,
                "temperature": 0.3,
            }
        )

    def _update_data(self, *, key: str) -> dict:
        return {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com",
            "api_key": key,
            "model": "deepseek-v4-flash",
            "max_tokens": 8192,
            "temperature": 0.3,
        }

    def test_apply_persists_binding_and_public_status(self) -> None:
        config = self._create_config()

        config_mapper.apply_llm_config(config["id"], "summary")

        self.assertEqual(
            llm_config_service.get_binding_map(),
            {"summary": config["id"]},
        )
        public = llm_config_service.to_public_llm_config(config)
        self.assertEqual(public["bound_prefixes"], ["summary"])
        self.assertEqual(
            config_service._load_config_json()["qwen_api_key"],
            "sk-old",
        )

    def test_editing_bound_config_automatically_updates_active_key(self) -> None:
        config = self._create_config()
        for prefix in ("theme_select", "org", "summary", "summary_limit"):
            config_mapper.apply_llm_config(config["id"], prefix)

        response = config_mapper.update_and_reapply_llm_config(
            config["id"],
            self._update_data(key="sk-new"),
        )

        self.assertEqual(
            response["applied_prefixes"],
            ["org", "summary", "summary_limit", "theme_select"],
        )
        self.assertEqual(
            config_service._load_config_json()["qwen_api_key"],
            "sk-new",
        )
        self.assertEqual(
            llm_config_service.to_public_llm_config(response["config"])["bound_prefixes"],
            response["applied_prefixes"],
        )

    def test_masked_key_round_trip_keeps_real_active_key(self) -> None:
        config = self._create_config()
        config_mapper.apply_llm_config(config["id"], "summary_batch")

        response = config_mapper.update_and_reapply_llm_config(
            config["id"],
            {
                **self._update_data(key=secrets.SECRET_MASK),
                "temperature": 0.2,
            },
        )

        self.assertEqual(response["config"]["api_key"], "sk-old")
        self.assertEqual(
            config_service._load_config_json()["summary_batch_api_key"],
            "sk-old",
        )
        self.assertNotEqual(
            config_service._load_config_json()["summary_batch_api_key"],
            secrets.SECRET_MASK,
        )

    def test_first_edit_migrates_exact_legacy_copy(self) -> None:
        config = self._create_config()
        config_service.update_config(
            {
                "theme_select_base_url": config["base_url"],
                "theme_select_model": config["model"],
                "theme_select_use_openrouter_free_pool": False,
                "qwen_api_key": config["api_key"],
            }
        )
        self.assertEqual(llm_config_service.get_binding_map(), {})

        response = config_mapper.update_and_reapply_llm_config(
            config["id"],
            self._update_data(key="sk-new"),
        )

        self.assertIn("theme_select", response["applied_prefixes"])
        self.assertEqual(
            llm_config_service.get_binding_map()["theme_select"],
            config["id"],
        )
        self.assertEqual(
            config_service._load_config_json()["qwen_api_key"],
            "sk-new",
        )

    def test_rebinding_moves_status_and_protects_active_config_from_delete(self) -> None:
        first = self._create_config(name="first", key="sk-first")
        second = self._create_config(name="second", key="sk-second")
        config_mapper.batch_apply(
            [{"config_id": first["id"], "prefix": "summary_batch"}],
            [],
        )
        config_mapper.batch_apply(
            [{"config_id": second["id"], "prefix": "summary_batch"}],
            [],
        )

        self.assertEqual(llm_config_service.get_bound_prefixes(first["id"]), [])
        self.assertEqual(
            llm_config_service.get_bound_prefixes(second["id"]),
            ["summary_batch"],
        )
        self.assertTrue(llm_config_service.delete_config(first["id"]))
        with self.assertRaisesRegex(ValueError, "仍应用于"):
            llm_config_service.delete_config(second["id"])

    def test_invalid_prefix_is_rejected_without_binding(self) -> None:
        config = self._create_config()
        with self.assertRaisesRegex(ValueError, "不支持"):
            config_mapper.apply_llm_config(config["id"], "unknown")
        self.assertEqual(llm_config_service.get_binding_map(), {})


if __name__ == "__main__":
    unittest.main()
