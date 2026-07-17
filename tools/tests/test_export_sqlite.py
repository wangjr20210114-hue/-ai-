from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools.export_sqlite import build_bundle


class ExportSqliteTests(unittest.TestCase):
    def test_export_is_read_only_normalized_and_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "yuanbao.db"
            attachment = root / "paper.pdf"
            attachment.write_bytes(b"%PDF-1.4\nlegacy")
            connection = sqlite3.connect(database)
            connection.executescript("""
                CREATE TABLE users(id TEXT PRIMARY KEY, display_name TEXT, timezone TEXT);
                CREATE TABLE conversations(id TEXT PRIMARY KEY, user_id TEXT, title TEXT, summary TEXT, created_at REAL, updated_at REAL);
                CREATE TABLE messages(id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, metadata TEXT, created_at REAL);
                CREATE TABLE schedules(id TEXT PRIMARY KEY, session_id TEXT, title TEXT, extra TEXT, created_at REAL, updated_at REAL);
                CREATE TABLE scheduled_jobs(id TEXT PRIMARY KEY, user_id TEXT, status TEXT, payload TEXT);
                CREATE TABLE files(id TEXT PRIMARY KEY, owner_id TEXT, storage_path TEXT, original_name TEXT, sha256 TEXT, metadata TEXT);
            """)
            connection.execute("INSERT INTO users VALUES('local-user','我','Asia/Shanghai')")
            connection.execute("INSERT INTO conversations VALUES('c1','local-user','历史','',1,2)")
            connection.execute("INSERT INTO messages VALUES('m1','c1','ai','你好','{}',3)")
            connection.execute("INSERT INTO schedules VALUES('s1','local-user','提醒','{}',1,2)")
            connection.execute("INSERT INTO scheduled_jobs VALUES('j1','local-user','enabled','{}')")
            connection.execute("INSERT INTO files VALUES('f1','local-user',?,'paper.pdf','old','{}')", (str(attachment),))
            connection.commit()
            connection.close()

            before = database.read_bytes()
            manifest = build_bundle(database, root / "bundle", include_files=True)
            self.assertEqual(before, database.read_bytes())
            self.assertEqual(manifest["counts"]["messages"], 1)
            self.assertFalse(manifest["safety"]["legacy_jobs_activated"])
            message = json.loads((root / "bundle/messages.ndjson").read_text().strip())
            self.assertEqual(message["role"], "assistant")
            state = json.loads((root / "bundle/states.ndjson").read_text().strip())
            self.assertIn("s1", state["workspace"]["schedules"])
            self.assertEqual(state["proactive"]["legacy_jobs"]["j1"]["status"], "migration_review_required")
            file_item = json.loads((root / "bundle/files.ndjson").read_text().strip())
            self.assertTrue(file_item["source_exists"])
            self.assertTrue((root / "bundle" / file_item["exported_path"]).is_file())

    def test_non_empty_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "empty.db"
            sqlite3.connect(database).close()
            output = root / "bundle"
            output.mkdir()
            (output / "keep.txt").write_text("keep")
            with self.assertRaises(FileExistsError):
                build_bundle(database, output)


if __name__ == "__main__":
    unittest.main()
