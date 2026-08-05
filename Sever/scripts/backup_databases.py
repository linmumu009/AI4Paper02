"""Create verified, compressed SQLite backups on the server.

The script uses SQLite's online backup API, verifies every copy before
compression, writes an integrity manifest, and retains only a bounded number
of completed backup directories.  It never transfers data off the host.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SEVER_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _SEVER_ROOT.parent
_DEFAULT_DB_DIR = _SEVER_ROOT / "database"
_DEFAULT_BACKUP_ROOT = _PROJECT_ROOT / "backups"
_MIN_HEADROOM_BYTES = 128 * 1024 * 1024
_RECOVERY_SECRET_NAMES = (".secret_storage_key", "kb_file_signing.key")
_DEFAULT_EXTERNAL_RECOVERY_SECRETS = (Path("/etc/ai4papers/sms.env"),)


def _chmod_private(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError as exc:
        raise RuntimeError(f"Unable to secure backup path: {path}") from exc


def _quick_check(db_path: Path) -> str:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
        result = str(row[0]) if row else "missing_result"
    finally:
        conn.close()
    if result.lower() != "ok":
        raise RuntimeError(f"SQLite quick_check failed for {db_path}: {result}")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_sqlite_sidecars(db_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)


def _backup_one(source: Path, staging_dir: Path) -> dict[str, Any]:
    plain_path = staging_dir / source.name
    compressed_path = staging_dir / f"{source.name}.gz"

    source_uri = f"file:{source.as_posix()}?mode=ro"
    source_conn = sqlite3.connect(source_uri, uri=True, timeout=30)
    destination_conn = sqlite3.connect(plain_path)
    try:
        source_conn.backup(destination_conn, pages=2048, sleep=0.05)
    finally:
        destination_conn.close()
        source_conn.close()

    _quick_check(plain_path)
    _remove_sqlite_sidecars(plain_path)
    with plain_path.open("rb") as source_handle, gzip.open(
        compressed_path, "wb", compresslevel=6
    ) as compressed_handle:
        shutil.copyfileobj(source_handle, compressed_handle, length=1024 * 1024)
    _chmod_private(compressed_path, 0o600)
    plain_path.unlink()

    # Reading the whole gzip stream verifies its CRC and confirms it is not
    # merely a valid header around truncated data.
    uncompressed_bytes = 0
    with gzip.open(compressed_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            uncompressed_bytes += len(chunk)

    return {
        "name": source.name,
        "source_bytes": source.stat().st_size,
        "backup_uncompressed_bytes": uncompressed_bytes,
        "compressed_bytes": compressed_path.stat().st_size,
        "compressed_sha256": _sha256(compressed_path),
        "quick_check": "ok",
    }


def _backup_recovery_secret(
    source: Path,
    staging_dir: Path,
    *,
    archive_name: str,
    restore_path: str,
) -> dict[str, Any]:
    if not archive_name or Path(archive_name).name != archive_name:
        raise RuntimeError(f"Unsafe recovery-secret archive name: {archive_name!r}")
    if source.is_symlink() or not source.is_file():
        raise RuntimeError(f"Unsafe recovery-secret source: {source}")
    if os.name != "nt" and source.stat().st_mode & 0o077:
        raise RuntimeError(f"Recovery-secret source is not private: {source}")
    destination = staging_dir / archive_name
    shutil.copyfile(source, destination)
    _chmod_private(destination, 0o600)
    return {
        "name": archive_name,
        "restore_path": restore_path,
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def _completed_backup_dirs(backup_root: Path) -> list[Path]:
    if not backup_root.is_dir():
        return []
    return sorted(
        (
            path
            for path in backup_root.iterdir()
            if path.is_dir()
            and not path.name.startswith(".incomplete-")
            and (path / "manifest.json").is_file()
        ),
        key=lambda path: path.name,
        reverse=True,
    )


def _prune_old_backups(backup_root: Path, retention_count: int) -> list[str]:
    removed: list[str] = []
    for path in _completed_backup_dirs(backup_root)[max(1, retention_count):]:
        shutil.rmtree(path)
        removed.append(path.name)
    return removed


def create_backup(
    db_dir: Path,
    backup_root: Path,
    *,
    retention_count: int = 3,
    now: datetime | None = None,
    external_recovery_secrets: tuple[Path, ...] | None = None,
) -> dict[str, Any]:
    db_dir = db_dir.resolve()
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup_root = backup_root.resolve()
    _chmod_private(backup_root, 0o700)

    sources = sorted(path for path in db_dir.glob("*.db") if path.is_file())
    if not sources:
        raise RuntimeError(f"No SQLite databases found in {db_dir}")

    largest_db = max(path.stat().st_size for path in sources)
    required_free = largest_db * 2 + _MIN_HEADROOM_BYTES
    free_bytes = shutil.disk_usage(backup_root).free
    if free_bytes < required_free:
        raise RuntimeError(
            f"Insufficient free space for safe backup: free={free_bytes} "
            f"required={required_free}"
        )

    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H%M%SZ")
    final_dir = backup_root / timestamp
    if final_dir.exists():
        raise RuntimeError(f"Backup destination already exists: {final_dir}")
    staging_dir = backup_root / f".incomplete-{timestamp}-{uuid.uuid4().hex[:8]}"
    staging_dir.mkdir(parents=False, mode=0o700)
    _chmod_private(staging_dir, 0o700)

    try:
        recovery_sources = [
            (db_dir / name, name, str(db_dir / name))
            for name in _RECOVERY_SECRET_NAMES
            if (db_dir / name).is_file()
        ]
        external_sources = (
            _DEFAULT_EXTERNAL_RECOVERY_SECRETS
            if external_recovery_secrets is None
            else external_recovery_secrets
        )
        recovery_sources.extend(
            (source, source.name, str(source))
            for source in external_sources
            if source.is_file()
        )
        archive_names = [archive_name for _, archive_name, _ in recovery_sources]
        if len(archive_names) != len(set(archive_names)):
            raise RuntimeError("Duplicate recovery-secret archive name")
        database_results = [_backup_one(source, staging_dir) for source in sources]
        recovery_secret_results = [
            _backup_recovery_secret(
                source,
                staging_dir,
                archive_name=archive_name,
                restore_path=restore_path,
            )
            for source, archive_name, restore_path in recovery_sources
        ]
        manifest = {
            "version": 3,
            "created_at": (now or datetime.now(timezone.utc)).isoformat(),
            "db_dir": str(db_dir),
            "host_only": True,
            "databases": database_results,
            "recovery_secrets": recovery_secret_results,
        }
        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _chmod_private(manifest_path, 0o600)
        staging_dir.rename(final_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    removed = _prune_old_backups(backup_root, retention_count)
    return {
        "ok": True,
        "backup_dir": str(final_dir),
        "database_count": len(database_results),
        "recovery_secret_count": len(recovery_secret_results),
        "compressed_bytes": sum(item["compressed_bytes"] for item in database_results),
        "removed_backups": removed,
    }


def verify_backup(backup_dir: Path) -> dict[str, Any]:
    backup_dir = backup_dir.resolve()
    manifest_path = backup_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verified: list[str] = []

    for item in manifest.get("databases") or []:
        name = str(item["name"])
        compressed_path = backup_dir / f"{name}.gz"
        if _sha256(compressed_path) != item.get("compressed_sha256"):
            raise RuntimeError(f"Checksum mismatch: {compressed_path}")
        temp_handle = tempfile.NamedTemporaryFile(
            prefix=f"verify-{name}-", suffix=".db", dir=backup_dir, delete=False
        )
        temp_path = Path(temp_handle.name)
        try:
            with temp_handle, gzip.open(compressed_path, "rb") as source:
                shutil.copyfileobj(source, temp_handle, length=1024 * 1024)
            _quick_check(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
            _remove_sqlite_sidecars(temp_path)
        verified.append(name)

    verified_recovery_secrets: list[str] = []
    for item in manifest.get("recovery_secrets") or []:
        name = str(item["name"])
        if not name or Path(name).name != name:
            raise RuntimeError(f"Unsafe recovery-secret archive name: {name!r}")
        secret_path = backup_dir / name
        if _sha256(secret_path) != item.get("sha256"):
            raise RuntimeError(f"Checksum mismatch: {secret_path}")
        if secret_path.stat().st_size != int(item.get("bytes", -1)):
            raise RuntimeError(f"Size mismatch: {secret_path}")
        verified_recovery_secrets.append(name)

    return {
        "ok": True,
        "backup_dir": str(backup_dir),
        "verified": verified,
        "verified_recovery_secrets": verified_recovery_secrets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verified host-local SQLite backup")
    parser.add_argument("--db-dir", type=Path, default=_DEFAULT_DB_DIR)
    parser.add_argument("--backup-root", type=Path, default=_DEFAULT_BACKUP_ROOT)
    parser.add_argument("--retention-count", type=int, default=3)
    parser.add_argument("--verify", type=Path, default=None, help="Verify one backup directory")
    parser.add_argument("--verify-latest", action="store_true")
    args = parser.parse_args()

    if args.verify is not None:
        result = verify_backup(args.verify)
    elif args.verify_latest:
        completed = _completed_backup_dirs(args.backup_root.resolve())
        if not completed:
            raise SystemExit("No completed backup found")
        result = verify_backup(completed[0])
    else:
        result = create_backup(
            args.db_dir,
            args.backup_root,
            retention_count=max(1, args.retention_count),
        )
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
