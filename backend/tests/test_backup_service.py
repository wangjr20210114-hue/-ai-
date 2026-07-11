from __future__ import annotations

import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from services.backup_service import BackupService, BackupValidationError


class BackupServiceTests(unittest.TestCase):
    def _create_database(self, path: Path, value: str) -> None:
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE sample(value TEXT NOT NULL)")
            connection.execute("INSERT INTO sample(value) VALUES(?)", (value,))
            connection.commit()
        finally:
            connection.close()

    def _read_value(self, path: Path) -> str:
        connection = sqlite3.connect(path)
        try:
            return str(connection.execute("SELECT value FROM sample").fetchone()[0])
        finally:
            connection.close()

    def test_backup_and_restart_restore_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "yuanbao.db"
            files = root / "uploads" / "files"
            state = root / ".agent"
            files.mkdir(parents=True)
            self._create_database(db_path, "before")
            (files / "file-1.pdf").write_bytes(b"%PDF-test-content")
            (root / ".env").write_text("SECRET=must-not-be-backed-up")
            (state / "access-token").parent.mkdir(parents=True)
            (state / "access-token").write_text("local-secret")

            service = BackupService(
                db_path=db_path,
                file_storage_dir=files,
                state_dir=state,
            )
            archive = service.create_backup()
            manifest = service.validate_backup(archive)
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(len(manifest["files"]), 1)
            with zipfile.ZipFile(archive) as package:
                names = set(package.namelist())
                self.assertNotIn(".env", names)
                self.assertNotIn("access-token", names)

            db_path.unlink()
            self._create_database(db_path, "after")
            (files / "file-1.pdf").write_bytes(b"changed")
            (files / "extra.pdf").write_bytes(b"extra")

            staged = service.stage_restore(archive.read_bytes())
            self.assertTrue(staged["restart_required"])
            applied = service.apply_pending_restore()
            self.assertTrue(applied["applied"])
            self.assertEqual(self._read_value(db_path), "before")
            self.assertEqual((files / "file-1.pdf").read_bytes(), b"%PDF-test-content")
            self.assertFalse((files / "extra.pdf").exists())
            self.assertFalse(service.pending_restore())
            self.assertTrue(Path(applied["safety_copy"]).exists())

    def test_rejects_zip_traversal_before_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = BackupService(
                db_path=root / "missing.db",
                file_storage_dir=root / "files",
                state_dir=root / ".agent",
            )
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w") as archive:
                archive.writestr("../escape.txt", "bad")
                archive.writestr("manifest.json", "{}")
                archive.writestr("database.sqlite3", "bad")
            path = root / "malicious.zip"
            path.write_bytes(payload.getvalue())
            with self.assertRaisesRegex(BackupValidationError, "unsafe archive path"):
                service.validate_backup(path)


if __name__ == "__main__":
    unittest.main()
