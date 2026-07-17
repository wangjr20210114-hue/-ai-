"""Validated local backup and restart-safe restore for Agent state.

Backups contain the SQLite database plus managed uploaded files. Secrets such as
.env values and the local access token are never included. Restore is staged
while the application is running and applied atomically before database startup.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from config import settings

BACKUP_SCHEMA_VERSION = 1
MAX_BACKUP_BYTES = 1024 * 1024 * 1024
MAX_BACKUP_ENTRIES = 20_000
MAX_MANAGED_FILE_BYTES = 100 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_RETAINED_BACKUPS = 10


class BackupValidationError(ValueError):
    """The archive is malformed, unsafe, or does not match its manifest."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise BackupValidationError(f"unsafe archive path: {name}")
    if any(part in {"", "."} for part in path.parts):
        raise BackupValidationError(f"invalid archive path: {name}")
    return path


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF)


class BackupService:
    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        file_storage_dir: str | Path | None = None,
        state_dir: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path or settings.db_path).resolve()
        self.file_storage_dir = Path(file_storage_dir or settings.file_storage_dir).resolve()
        self.state_dir = Path(state_dir or settings.agent_state_dir).resolve()
        self.backup_dir = self.state_dir / "backups"
        self.pending_restore_path = self.state_dir / "pending-restore.zip"
        self.restore_safety_dir = self.state_dir / "restore-safety"

    def create_backup(self) -> Path:
        if not self.db_path.is_file():
            raise FileNotFoundError(f"database not found: {self.db_path}")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        destination = self.backup_dir / f"yuanbao-agent-backup-{timestamp}.zip"
        counter = 1
        while destination.exists():
            destination = self.backup_dir / f"yuanbao-agent-backup-{timestamp}-{counter}.zip"
            counter += 1

        with tempfile.TemporaryDirectory(dir=self.state_dir) as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            snapshot = temp_dir / "database.sqlite3"
            self._sqlite_snapshot(snapshot)
            files: list[dict[str, Any]] = []
            total_bytes = snapshot.stat().st_size
            if self.file_storage_dir.exists():
                for source in sorted(self.file_storage_dir.rglob("*")):
                    if not source.is_file() or source.is_symlink():
                        continue
                    relative = source.relative_to(self.file_storage_dir).as_posix()
                    size = source.stat().st_size
                    if size > MAX_MANAGED_FILE_BYTES:
                        raise BackupValidationError(f"managed file is too large: {relative}")
                    total_bytes += size
                    if total_bytes > MAX_BACKUP_BYTES:
                        raise BackupValidationError("backup exceeds size limit")
                    files.append(
                        {
                            "path": relative,
                            "size_bytes": size,
                            "sha256": _sha256_file(source),
                        }
                    )

            manifest = {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "created_at": time.time(),
                "database": {
                    "path": "database.sqlite3",
                    "size_bytes": snapshot.stat().st_size,
                    "sha256": _sha256_file(snapshot),
                },
                "files": files,
                "excluded": [".env", "API keys", "local access token"],
            }
            temp_archive = destination.with_suffix(".tmp")
            try:
                with zipfile.ZipFile(temp_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr(
                        "manifest.json",
                        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                    )
                    archive.write(snapshot, "database.sqlite3")
                    for item in files:
                        archive.write(
                            self.file_storage_dir / item["path"],
                            f"files/{item['path']}",
                        )
                os.replace(temp_archive, destination)
                self._prune_old_backups(keep=MAX_RETAINED_BACKUPS)
            finally:
                temp_archive.unlink(missing_ok=True)
        return destination

    def stage_restore(self, archive_bytes: bytes) -> dict[str, Any]:
        return self.stage_restore_file(io.BytesIO(archive_bytes))

    def stage_restore_file(self, source: Any) -> dict[str, Any]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_dir / f"pending-restore-{os.getpid()}.tmp"
        size = 0
        try:
            with temporary.open("wb") as destination:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BACKUP_BYTES:
                        raise BackupValidationError("backup exceeds size limit")
                    destination.write(chunk)
            if size == 0:
                raise BackupValidationError("backup is empty")
            manifest = self.validate_backup(temporary)
            os.replace(temporary, self.pending_restore_path)
            return {
                "staged": True,
                "restart_required": True,
                "created_at": manifest["created_at"],
                "file_count": len(manifest["files"]),
                "database_size_bytes": manifest["database"]["size_bytes"],
            }
        finally:
            temporary.unlink(missing_ok=True)

    def validate_backup(self, archive_path: str | Path) -> dict[str, Any]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = Path(archive_path)
        if not path.is_file() or path.stat().st_size > MAX_BACKUP_BYTES:
            raise BackupValidationError("backup file is missing or too large")
        try:
            archive = zipfile.ZipFile(path, "r")
        except zipfile.BadZipFile as error:
            raise BackupValidationError("invalid ZIP backup") from error
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_BACKUP_ENTRIES:
                raise BackupValidationError("backup contains too many entries")
            if sum(info.file_size for info in infos) > MAX_BACKUP_BYTES:
                raise BackupValidationError("backup expands beyond size limit")
            seen: set[str] = set()
            for info in infos:
                normalized = str(_safe_member(info.filename))
                if normalized in seen:
                    raise BackupValidationError(f"duplicate archive path: {normalized}")
                seen.add(normalized)
                if _is_symlink(info):
                    raise BackupValidationError("symbolic links are not allowed")
                if info.file_size > MAX_BACKUP_BYTES:
                    raise BackupValidationError(f"archive entry is too large: {normalized}")
            required = {"manifest.json", "database.sqlite3"}
            if not required.issubset(seen):
                raise BackupValidationError("backup is missing manifest or database")
            if archive.getinfo("manifest.json").file_size > MAX_MANIFEST_BYTES:
                raise BackupValidationError("backup manifest is too large")
            try:
                manifest = json.loads(archive.read("manifest.json"))
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as error:
                raise BackupValidationError("backup manifest is invalid") from error
            self._validate_manifest_shape(manifest)
            expected_paths = {"manifest.json", "database.sqlite3"} | {
                f"files/{item['path']}" for item in manifest["files"]
            }
            if seen != expected_paths:
                raise BackupValidationError("archive entries do not match manifest")
            self._verify_zip_entry(
                archive,
                "database.sqlite3",
                manifest["database"]["sha256"],
                int(manifest["database"]["size_bytes"]),
            )
            for item in manifest["files"]:
                self._verify_zip_entry(
                    archive,
                    f"files/{item['path']}",
                    item["sha256"],
                    int(item["size_bytes"]),
                )
            with tempfile.TemporaryDirectory(dir=self.state_dir) as temp_dir_name:
                db_snapshot = Path(temp_dir_name) / "database.sqlite3"
                db_snapshot.write_bytes(archive.read("database.sqlite3"))
                self._verify_sqlite(db_snapshot)
            return manifest

    def apply_pending_restore(self) -> dict[str, Any] | None:
        """Apply a staged restore before the application opens its database."""
        if not self.pending_restore_path.is_file():
            return None
        manifest = self.validate_backup(self.pending_restore_path)
        self.restore_safety_dir.mkdir(parents=True, exist_ok=True)
        safety = self.restore_safety_dir / time.strftime("%Y%m%d-%H%M%S", time.localtime())
        safety.mkdir(parents=True, exist_ok=False)

        with tempfile.TemporaryDirectory(dir=self.state_dir) as temp_dir_name:
            extracted = Path(temp_dir_name)
            with zipfile.ZipFile(self.pending_restore_path, "r") as archive:
                archive.extract("database.sqlite3", extracted)
                for item in manifest["files"]:
                    archive.extract(f"files/{item['path']}", extracted)
            restored_db = extracted / "database.sqlite3"
            restored_files = extracted / "files"
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_storage_dir.parent.mkdir(parents=True, exist_ok=True)

            old_db = safety / "database.sqlite3"
            old_files = safety / "files"
            had_db = self.db_path.exists()
            had_files = self.file_storage_dir.exists()
            try:
                if had_db:
                    shutil.copy2(self.db_path, old_db)
                if had_files:
                    shutil.move(str(self.file_storage_dir), str(old_files))
                os.replace(restored_db, self.db_path)
                self.db_path.with_suffix(self.db_path.suffix + "-wal").unlink(missing_ok=True)
                self.db_path.with_suffix(self.db_path.suffix + "-shm").unlink(missing_ok=True)
                if restored_files.exists():
                    shutil.move(str(restored_files), str(self.file_storage_dir))
                else:
                    self.file_storage_dir.mkdir(parents=True, exist_ok=True)
                self.pending_restore_path.unlink()
            except Exception:
                self.db_path.unlink(missing_ok=True)
                if had_db and old_db.exists():
                    shutil.copy2(old_db, self.db_path)
                if self.file_storage_dir.exists():
                    shutil.rmtree(self.file_storage_dir)
                if had_files and old_files.exists():
                    shutil.move(str(old_files), str(self.file_storage_dir))
                raise
        return {
            "applied": True,
            "created_at": manifest["created_at"],
            "file_count": len(manifest["files"]),
            "safety_copy": str(safety),
        }

    def pending_restore(self) -> bool:
        return self.pending_restore_path.is_file()

    def _sqlite_snapshot(self, destination: Path) -> None:
        source = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
            target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            result = target.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise BackupValidationError("database snapshot failed integrity check")
        finally:
            target.close()
            source.close()

    @staticmethod
    def _verify_sqlite(path: Path) -> None:
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                result = connection.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise BackupValidationError("backup database failed integrity check")
            finally:
                connection.close()
        except sqlite3.DatabaseError as error:
            raise BackupValidationError("backup database is invalid") from error

    @staticmethod
    def _verify_zip_entry(
        archive: zipfile.ZipFile,
        name: str,
        expected_hash: str,
        expected_size: int,
    ) -> None:
        digest = hashlib.sha256()
        size = 0
        with archive.open(name) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                size += len(chunk)
                if size > MAX_BACKUP_BYTES:
                    raise BackupValidationError(f"entry exceeds size limit: {name}")
                digest.update(chunk)
        if size != expected_size or digest.hexdigest() != expected_hash:
            raise BackupValidationError(f"hash or size mismatch: {name}")

    @staticmethod
    def _validate_manifest_shape(manifest: Any) -> None:
        if not isinstance(manifest, dict) or manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
            raise BackupValidationError("unsupported backup schema")
        if not isinstance(manifest.get("created_at"), (int, float)):
            raise BackupValidationError("backup creation time is invalid")
        database = manifest.get("database")
        files = manifest.get("files")
        if not isinstance(database, dict) or not isinstance(files, list):
            raise BackupValidationError("backup manifest fields are invalid")
        if database.get("path") != "database.sqlite3":
            raise BackupValidationError("database path is invalid")
        if not isinstance(database.get("sha256"), str) or len(database["sha256"]) != 64:
            raise BackupValidationError("database hash is invalid")
        if not isinstance(database.get("size_bytes"), int) or database["size_bytes"] < 0:
            raise BackupValidationError("database size is invalid")
        paths: set[str] = set()
        for item in files:
            if not isinstance(item, dict):
                raise BackupValidationError("file manifest entry is invalid")
            relative = str(_safe_member(str(item.get("path") or "")))
            if relative.startswith("files/"):
                raise BackupValidationError("file path must be relative to managed storage")
            if relative in paths:
                raise BackupValidationError("duplicate file path in manifest")
            paths.add(relative)
            if not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64:
                raise BackupValidationError("file hash is invalid")
            if not isinstance(item.get("size_bytes"), int) or item["size_bytes"] < 0:
                raise BackupValidationError("file size is invalid")

    def _prune_old_backups(self, *, keep: int) -> None:
        backups = sorted(
            self.backup_dir.glob("yuanbao-agent-backup-*.zip"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in backups[max(1, keep):]:
            path.unlink(missing_ok=True)
