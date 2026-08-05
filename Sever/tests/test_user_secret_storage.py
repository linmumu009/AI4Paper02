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

from services import secret_storage_service as secrets  # noqa: E402
from services import user_presets_service, user_settings_service  # noqa: E402
from scripts.migrate_user_secrets import migrate_database  # noqa: E402


class UserSecretStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.db_path = root / "paper_analysis.db"
        self.key_path = root / "credential.key"
        self.patches = [
            patch.object(user_presets_service, "_DB_PATH", str(self.db_path)),
            patch.object(user_settings_service, "_DB_PATH", str(self.db_path)),
            patch.object(secrets, "_KEY_PATH", self.key_path),
        ]
        for item in self.patches:
            item.start()
        secrets.reset_key_cache_for_tests()
        user_presets_service.init_db()
        user_settings_service.init_db()

    def tearDown(self) -> None:
        secrets.reset_key_cache_for_tests()
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_preset_is_encrypted_at_rest_and_masked_for_api(self) -> None:
        preset = user_presets_service.create_llm_preset(
            7,
            {
                "name": "test",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-user-secret",
                "model": "model",
            },
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            stored = connection.execute(
                "SELECT api_key FROM user_llm_presets WHERE id = ?", (preset["id"],)
            ).fetchone()[0]
        self.assertTrue(secrets.is_encrypted_secret(stored))
        self.assertNotIn("sk-user-secret", stored)
        self.assertEqual(preset["api_key"], "sk-user-secret")

        public = user_presets_service.to_public_llm_preset(preset)
        self.assertEqual(public["api_key"], secrets.SECRET_MASK)
        self.assertTrue(public["has_api_key"])

        updated = user_presets_service.update_llm_preset(
            7,
            preset["id"],
            {"name": "renamed", "api_key": secrets.SECRET_MASK},
        )
        self.assertEqual(updated["api_key"], "sk-user-secret")

    def test_feature_secret_is_encrypted_and_mask_roundtrip_preserves_it(self) -> None:
        saved = user_settings_service.save_settings(
            7,
            "paper_chat",
            {"llm_api_key": "sk-feature-secret", "llm_model": "model"},
        )
        self.assertEqual(saved["llm_api_key"], "sk-feature-secret")
        with closing(sqlite3.connect(self.db_path)) as connection:
            payload = connection.execute(
                "SELECT settings_json FROM user_settings WHERE user_id = 7"
            ).fetchone()[0]
        stored = json.loads(payload)
        self.assertTrue(secrets.is_encrypted_secret(stored["llm_api_key"]))
        self.assertNotIn("sk-feature-secret", payload)

        user_settings_service.save_settings(
            7,
            "paper_chat",
            {"llm_api_key": secrets.SECRET_MASK, "llm_model": "new-model"},
        )
        current = user_settings_service.get_settings(7, "paper_chat")
        self.assertEqual(current["llm_api_key"], "sk-feature-secret")
        self.assertEqual(current["llm_model"], "new-model")

    def test_migration_encrypts_legacy_rows_and_is_idempotent(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            now = "2026-08-05T00:00:00+00:00"
            connection.execute(
                """INSERT INTO user_llm_presets
                   (user_id, name, base_url, api_key, model, created_at, updated_at)
                   VALUES (7, 'legacy', 'https://api.example.com/v1',
                           'sk-legacy-preset', 'model', ?, ?)""",
                (now, now),
            )
            connection.execute(
                """INSERT INTO user_settings
                   (user_id, feature, settings_json, updated_at)
                   VALUES (7, 'paper_chat', ?, ?)""",
                (
                    json.dumps(
                        {"llm_api_key": "sk-legacy-setting", "llm_model": "model"}
                    ),
                    now,
                ),
            )
            connection.commit()

        first = migrate_database(self.db_path)
        second = migrate_database(self.db_path)
        self.assertEqual(first["preset_changed"], 1)
        self.assertEqual(first["settings_changed"], 1)
        self.assertEqual(first["remaining_plaintext"], 0)
        self.assertEqual(second["preset_changed"], 0)
        self.assertEqual(second["settings_changed"], 0)


if __name__ == "__main__":
    unittest.main()
