"""Encrypt legacy user credentials in-place without exporting database data."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


_SEVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SEVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SEVER_ROOT))

from services.secret_storage_service import (  # noqa: E402
    encrypt_secret,
    is_encrypted_secret,
    is_sensitive_key,
    protect_secret_mapping,
)


_DEFAULT_DB = _SEVER_ROOT / "database" / "paper_analysis.db"


def migrate_database(db_path: Path, *, dry_run: bool = False) -> dict[str, int | bool]:
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    preset_scanned = 0
    preset_changed = 0
    settings_scanned = 0
    settings_changed = 0
    remaining_plaintext = 0
    try:
        connection.execute("BEGIN IMMEDIATE")
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        if "user_llm_presets" in tables:
            rows = connection.execute(
                "SELECT id, api_key FROM user_llm_presets"
            ).fetchall()
            for row in rows:
                value = str(row["api_key"] or "")
                if not value:
                    continue
                preset_scanned += 1
                if not is_encrypted_secret(value):
                    preset_changed += 1
                    if not dry_run:
                        connection.execute(
                            "UPDATE user_llm_presets SET api_key = ? WHERE id = ?",
                            (encrypt_secret(value), row["id"]),
                        )

        if "user_settings" in tables:
            rows = connection.execute(
                "SELECT user_id, feature, settings_json FROM user_settings"
            ).fetchall()
            for row in rows:
                try:
                    settings = json.loads(row["settings_json"] or "{}")
                except (TypeError, ValueError):
                    continue
                if not isinstance(settings, dict):
                    continue
                sensitive = {
                    key: value
                    for key, value in settings.items()
                    if is_sensitive_key(key) and str(value or "")
                }
                if not sensitive:
                    continue
                settings_scanned += 1
                if any(not is_encrypted_secret(value) for value in sensitive.values()):
                    settings_changed += 1
                    if not dry_run:
                        protected = protect_secret_mapping(settings, existing=settings)
                        connection.execute(
                            """UPDATE user_settings SET settings_json = ?
                               WHERE user_id = ? AND feature = ?""",
                            (
                                json.dumps(protected, ensure_ascii=False),
                                row["user_id"],
                                row["feature"],
                            ),
                        )

        if dry_run:
            connection.rollback()
        else:
            connection.commit()

        if not dry_run:
            for (value,) in connection.execute(
                "SELECT api_key FROM user_llm_presets WHERE trim(api_key) <> ''"
            ):
                if not is_encrypted_secret(value):
                    remaining_plaintext += 1
            for (payload,) in connection.execute("SELECT settings_json FROM user_settings"):
                try:
                    settings = json.loads(payload or "{}")
                except (TypeError, ValueError):
                    continue
                if not isinstance(settings, dict):
                    continue
                remaining_plaintext += sum(
                    1
                    for key, value in settings.items()
                    if is_sensitive_key(key)
                    and str(value or "")
                    and not is_encrypted_secret(value)
                )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return {
        "ok": remaining_plaintext == 0,
        "dry_run": dry_run,
        "preset_scanned": preset_scanned,
        "preset_changed": preset_changed,
        "settings_scanned": settings_scanned,
        "settings_changed": settings_changed,
        "remaining_plaintext": remaining_plaintext,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypt legacy user credentials")
    parser.add_argument("--db", type=Path, default=_DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = migrate_database(args.db, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
