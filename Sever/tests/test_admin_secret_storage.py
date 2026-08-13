from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from services import config_service, llm_config_service  # noqa: E402
from services import openrouter_key_pool_service as key_pool  # noqa: E402
from services import secret_storage_service as secrets  # noqa: E402
from scripts.migrate_user_secrets import migrate_database  # noqa: E402


class AdminSecretStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.db_path = root / "paper_analysis.db"
        self.config_path = root / "config.json"
        self.key_path = root / "credential.key"
        self.patches = [
            patch.object(llm_config_service, "_DB_PATH", str(self.db_path)),
            patch.object(key_pool, "_DB_PATH", str(self.db_path)),
            patch.object(key_pool, "_DB_DIR", str(root)),
            patch.object(key_pool, "_COOLDOWN_PATH", str(root / "cooldown.json")),
            patch.object(key_pool, "_POOL_LOCK_PATH", str(root / "pool.lock")),
            patch.object(config_service, "_CONFIG_JSON_PATH", str(self.config_path)),
            patch.object(secrets, "_KEY_PATH", self.key_path),
        ]
        for item in self.patches:
            item.start()
        secrets.reset_key_cache_for_tests()
        llm_config_service.init_db()
        key_pool.init_db()

    def tearDown(self) -> None:
        secrets.reset_key_cache_for_tests()
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_admin_llm_key_is_encrypted_masked_and_preserved(self) -> None:
        config = llm_config_service.create_config(
            {
                "name": "admin",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-admin-secret",
                "model": "model",
            }
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            stored = connection.execute(
                "SELECT api_key FROM llm_config WHERE id = ?", (config["id"],)
            ).fetchone()[0]
        self.assertTrue(secrets.is_encrypted_secret(stored))
        self.assertEqual(config["api_key"], "sk-admin-secret")
        public = llm_config_service.to_public_llm_config(config)
        self.assertEqual(public["api_key"], secrets.SECRET_MASK)

        updated = llm_config_service.update_config(
            config["id"], {"name": "renamed", "api_key": secrets.SECRET_MASK}
        )
        self.assertEqual(updated["api_key"], "sk-admin-secret")

    def test_openrouter_pool_encrypts_at_rest_and_decrypts_at_selection(self) -> None:
        key_pool.save_pool("sk-or-first\nsk-or-second", 50)
        with closing(sqlite3.connect(self.db_path)) as connection:
            stored = [
                row[0]
                for row in connection.execute(
                    "SELECT api_key FROM openrouter_key_pool ORDER BY sort_order"
                )
            ]
        self.assertTrue(all(secrets.is_encrypted_secret(value) for value in stored))
        status = key_pool.get_pool_status()
        self.assertEqual(status["total_keys"], 2)
        self.assertTrue(all(not item["masked_key"].startswith("enc:v1:") for item in status["keys"]))
        selected = key_pool.select_available_key()
        self.assertIn(selected["api_key"], {"sk-or-first", "sk-or-second"})

    def test_system_config_json_encrypts_and_masks_secret_values(self) -> None:
        config_service._save_config_json(
            {"qwen_api_key": "sk-system-secret", "MAX_PAPERS_DEFAULT": 10}
        )
        stored = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertTrue(secrets.is_encrypted_secret(stored["qwen_api_key"]))
        loaded = config_service._load_config_json()
        self.assertEqual(loaded["qwen_api_key"], "sk-system-secret")

        original = getattr(config_service.config_module, "qwen_api_key", "")
        try:
            config_service.config_module.qwen_api_key = "sk-default-secret"
            groups = config_service.get_config_with_groups()
        finally:
            config_service.config_module.qwen_api_key = original
        qwen_items = [
            item
            for group in groups["groups"]
            for item in group["items"]
            if item["key"] == "qwen_api_key"
        ]
        self.assertEqual(qwen_items[0]["value"], secrets.SECRET_MASK)
        self.assertEqual(groups["defaults"]["qwen_api_key"], secrets.SECRET_MASK)

    def test_config_module_auto_load_decrypts_secret_for_pipeline_processes(self) -> None:
        config_service._save_config_json(
            {
                "qwen_api_key": "sk-pipeline-secret",
                "theme_select_model": "deepseek-v4-flash",
            }
        )
        stored = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertTrue(secrets.is_encrypted_secret(stored["qwen_api_key"]))

        config_module = config_service.config_module
        original_key = config_module.qwen_api_key
        original_model = config_module.theme_select_model
        try:
            config_module.qwen_api_key = ""
            config_module.theme_select_model = "fallback-model"
            config_module._auto_load_from_json(str(self.config_path))

            self.assertEqual(config_module.qwen_api_key, "sk-pipeline-secret")
            self.assertFalse(
                secrets.is_encrypted_secret(config_module.qwen_api_key)
            )
            self.assertEqual(
                config_module.theme_select_model,
                "deepseek-v4-flash",
            )
        finally:
            config_module.qwen_api_key = original_key
            config_module.theme_select_model = original_model

    def test_card_refinement_prompt_is_exposed_in_admin_prompt_group(self) -> None:
        groups = config_service.get_config_with_groups()["groups"]
        prompt_group = next(group for group in groups if group["name"] == "提示词配置")
        card_items = [
            item
            for item in prompt_group["items"]
            if item["key"] == "summary_limit_prompt_card"
        ]
        self.assertEqual(len(card_items), 1)
        self.assertEqual(
            card_items[0]["description"],
            "推荐卡片八字段整卡终稿精简提示词",
        )

    def test_migration_covers_admin_config_pool_and_config_json(self) -> None:
        now = "2026-08-05T00:00:00+00:00"
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """INSERT INTO llm_config
                   (name, base_url, api_key, model, created_at, updated_at)
                   VALUES ('legacy', 'https://api.example.com/v1',
                           'sk-admin-legacy', 'model', ?, ?)""",
                (now, now),
            )
            connection.execute(
                """INSERT INTO openrouter_key_pool
                   (api_key, enabled, sort_order, created_at, updated_at)
                   VALUES ('sk-pool-legacy', 1, 0, ?, ?)""",
                (now, now),
            )
            connection.commit()
        self.config_path.write_text(
            json.dumps({"qwen_api_key": "sk-config-legacy"}),
            encoding="utf-8",
        )

        result = migrate_database(
            self.db_path,
            config_json_path=self.config_path,
        )
        self.assertEqual(result["admin_llm_changed"], 1)
        self.assertEqual(result["pool_changed"], 1)
        self.assertEqual(result["config_changed"], 1)
        self.assertEqual(result["remaining_plaintext"], 0)


if __name__ == "__main__":
    unittest.main()
