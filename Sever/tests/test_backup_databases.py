"""Tests for verified host-local SQLite backups."""

from __future__ import annotations

import json
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

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_creates_compressed_verified_manifest(self) -> None:
        result = backup_databases.create_backup(
            self.db_dir,
            self.backup_root,
            retention_count=3,
            now=datetime(2026, 8, 5, 7, 0, tzinfo=timezone.utc),
        )

        backup_dir = Path(result["backup_dir"])
        manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["host_only"])
        self.assertEqual(result["database_count"], 2)
        self.assertTrue((backup_dir / "paper_analysis.db.gz").is_file())
        self.assertFalse((backup_dir / "paper_analysis.db").exists())

        verification = backup_databases.verify_backup(backup_dir)
        self.assertTrue(verification["ok"])
        self.assertEqual(
            verification["verified"], ["paper_analysis.db", "user_papers.db"]
        )

    def test_retention_removes_only_completed_old_backups(self) -> None:
        for day in (1, 2, 3):
            backup_databases.create_backup(
                self.db_dir,
                self.backup_root,
                retention_count=2,
                now=datetime(2026, 8, day, 7, 0, tzinfo=timezone.utc),
            )

        completed = backup_databases._completed_backup_dirs(self.backup_root)
        self.assertEqual(
            [path.name for path in completed],
            ["2026-08-03T070000Z", "2026-08-02T070000Z"],
        )


if __name__ == "__main__":
    unittest.main()
