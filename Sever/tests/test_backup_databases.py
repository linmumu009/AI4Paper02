"""Tests for verified host-local SQLite backups."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

_SEVER = Path(__file__).resolve().parents[1]
if str(_SEVER) not in sys.path:
    sys.path.insert(0, str(_SEVER))

from scripts import backup_databases  # noqa: E402


class TestBackupDatabases(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.db_dir = self.root / "database"
        self.backup_root = self.root / "backups"
        self.db_dir.mkdir()
        for name in ("paper_analysis.db", "user_papers.db"):
            conn = sqlite3.connect(self.db_dir / name)
            conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO sample(value) VALUES ('verified')")
            conn.commit()
            conn.close()
        secret_storage_key = self.db_dir / ".secret_storage_key"
        kb_signing_key = self.db_dir / "kb_file_signing.key"
        secret_storage_key.write_bytes(b"secret-storage-key\n")
        kb_signing_key.write_bytes(b"k" * 32)
        secret_storage_key.chmod(0o600)
        kb_signing_key.chmod(0o600)
        self.sms_env = self.root / "etc" / "ai4papers" / "sms.env"
        self.sms_env.parent.mkdir(parents=True)
        self.sms_env.write_text(
            "ALIBABA_CLOUD_ACCESS_KEY_ID=test-id\n"
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET=test-secret\n",
            encoding="utf-8",
        )
        self.sms_env.chmod(0o600)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_creates_compressed_verified_manifest(self) -> None:
        result = backup_databases.create_backup(
            self.db_dir,
            self.backup_root,
            retention_count=3,
            now=datetime(2026, 8, 5, 7, 0, tzinfo=timezone.utc),
            external_recovery_secrets=(self.sms_env,),
        )

        backup_dir = Path(result["backup_dir"])
        manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["host_only"])
        self.assertEqual(manifest["version"], 3)
        self.assertEqual(result["database_count"], 2)
        self.assertEqual(result["recovery_secret_count"], 3)
        self.assertTrue((backup_dir / "paper_analysis.db.gz").is_file())
        self.assertFalse((backup_dir / "paper_analysis.db").exists())
        self.assertTrue((backup_dir / ".secret_storage_key").is_file())
        self.assertTrue((backup_dir / "kb_file_signing.key").is_file())
        self.assertTrue((backup_dir / "sms.env").is_file())
        sms_entry = next(
            item for item in manifest["recovery_secrets"] if item["name"] == "sms.env"
        )
        self.assertEqual(sms_entry["restore_path"], str(self.sms_env))
        self.assertEqual(list(backup_dir.glob("*-wal")), [])
        self.assertEqual(list(backup_dir.glob("*-shm")), [])
        if os.name != "nt":
            self.assertEqual(backup_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                (backup_dir / "manifest.json").stat().st_mode & 0o777,
                0o600,
            )
            self.assertEqual(
                (backup_dir / ".secret_storage_key").stat().st_mode & 0o777,
                0o600,
            )
            self.assertEqual((backup_dir / "sms.env").stat().st_mode & 0o777, 0o600)

        verification = backup_databases.verify_backup(backup_dir)
        self.assertTrue(verification["ok"])
        self.assertEqual(
            verification["verified"], ["paper_analysis.db", "user_papers.db"]
        )
        self.assertEqual(
            verification["verified_recovery_secrets"],
            [".secret_storage_key", "kb_file_signing.key", "sms.env"],
        )
        self.assertEqual(list(backup_dir.glob("*-wal")), [])
        self.assertEqual(list(backup_dir.glob("*-shm")), [])

    def test_retention_removes_only_completed_old_backups(self) -> None:
        for day in (1, 2, 3):
            backup_databases.create_backup(
                self.db_dir,
                self.backup_root,
                retention_count=2,
                now=datetime(2026, 8, day, 7, 0, tzinfo=timezone.utc),
                external_recovery_secrets=(self.sms_env,),
            )

        completed = backup_databases._completed_backup_dirs(self.backup_root)
        self.assertEqual(
            [path.name for path in completed],
            ["2026-08-03T070000Z", "2026-08-02T070000Z"],
        )

    def test_writes_content_free_atomic_health_status(self) -> None:
        result = backup_databases.create_backup(
            self.db_dir,
            self.backup_root,
            retention_count=3,
            now=datetime(2026, 8, 5, 7, 0, tzinfo=timezone.utc),
            external_recovery_secrets=(self.sms_env,),
        )
        status_path = self.db_dir / "backup_health.json"

        payload = backup_databases.write_backup_health_status(
            status_path,
            result,
            verified_at=datetime(2026, 8, 5, 7, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(payload["backup_created_at"], "2026-08-05T07:00:00+00:00")
        self.assertEqual(payload["database_count"], 2)
        self.assertEqual(payload["recovery_secret_count"], 3)
        stored = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(stored, payload)
        self.assertNotIn("backup_dir", stored)
        self.assertNotIn("verified", stored)
        self.assertEqual(list(self.db_dir.glob(".backup_health.json.tmp-*")), [])
        if os.name != "nt":
            self.assertEqual(status_path.stat().st_mode & 0o777, 0o644)

    def test_rejects_unsafe_or_duplicate_recovery_secret_names(self) -> None:
        staging = self.root / "staging"
        staging.mkdir()
        with self.assertRaisesRegex(RuntimeError, "Unsafe recovery-secret"):
            backup_databases._backup_recovery_secret(
                self.sms_env,
                staging,
                archive_name="../sms.env",
                restore_path=str(self.sms_env),
            )

        duplicate = self.root / "duplicate" / "sms.env"
        duplicate.parent.mkdir()
        duplicate.write_text("second", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Duplicate recovery-secret"):
            backup_databases.create_backup(
                self.db_dir,
                self.backup_root,
                retention_count=3,
                now=datetime(2026, 8, 6, 7, 0, tzinfo=timezone.utc),
                external_recovery_secrets=(self.sms_env, duplicate),
            )

    @unittest.skipIf(os.name == "nt", "POSIX permission check")
    def test_rejects_non_private_recovery_secret_source(self) -> None:
        staging = self.root / "staging"
        staging.mkdir()
        self.sms_env.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "not private"):
            backup_databases._backup_recovery_secret(
                self.sms_env,
                staging,
                archive_name="sms.env",
                restore_path=str(self.sms_env),
            )


if __name__ == "__main__":
    unittest.main()
