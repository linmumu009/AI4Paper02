from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Sever.services import secret_storage_service as service


class SecretStorageServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.key_path = Path(self.temp_dir.name) / "secret.key"
        self.path_patch = patch.object(service, "_KEY_PATH", self.key_path)
        self.path_patch.start()
        service.reset_key_cache_for_tests()

    def tearDown(self) -> None:
        service.reset_key_cache_for_tests()
        self.path_patch.stop()
        self.temp_dir.cleanup()

    def test_encrypts_and_decrypts_without_exposing_plaintext(self) -> None:
        encrypted = service.encrypt_secret("sk-private-value")
        self.assertTrue(encrypted.startswith("enc:v1:"))
        self.assertNotIn("sk-private-value", encrypted)
        self.assertEqual(service.decrypt_secret(encrypted), "sk-private-value")
        self.assertTrue(self.key_path.is_file())

    def test_mapping_masks_and_preserves_existing_secret(self) -> None:
        protected = service.protect_secret_mapping(
            {"llm_api_key": service.SECRET_MASK, "llm_model": "model"},
            existing={"llm_api_key": "existing-key"},
        )
        plain = service.unprotect_secret_mapping(protected)
        public = service.mask_secret_mapping(plain)
        self.assertEqual(plain["llm_api_key"], "existing-key")
        self.assertEqual(public["llm_api_key"], service.SECRET_MASK)
        self.assertEqual(public["llm_model"], "model")

    def test_empty_secret_remains_empty(self) -> None:
        protected = service.protect_secret_mapping({"mineru_token": ""})
        self.assertEqual(protected["mineru_token"], "")


if __name__ == "__main__":
    unittest.main()
