from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import fitz

from api import paper_routes, routes
from config import settings
from database import connection
from database.init_db import (
    M1_SCHEMA,
    SCHEMA,
    import_legacy_messages,
    prepare_legacy_message_table,
)
from database.migrations import Migration, apply_migrations
from database.repositories import conversation_repo, file_repo, plan_repo, schedule_repo
from models.schemas import SavePlanRequest, SaveScheduleRequest
from services.file_service import store_pdf


class M1PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA foreign_keys=ON")
        await apply_migrations(
            self.db,
            [
                Migration(1, "initial_schema", SCHEMA),
                Migration(2, "persistent_identity_conversations_files", M1_SCHEMA),
            ],
        )
        self.conversation_db = patch.object(conversation_repo, "get_db", return_value=self.db)
        self.file_db = patch.object(file_repo, "get_db", return_value=self.db)
        self.plan_db = patch.object(plan_repo, "get_db", return_value=self.db)
        self.schedule_db = patch.object(schedule_repo, "get_db", return_value=self.db)
        self.connection_db = patch.object(connection, "get_db", return_value=self.db)
        self.conversation_db.start()
        self.file_db.start()
        self.plan_db.start()
        self.schedule_db.start()
        self.connection_db.start()
        paper_routes._paper_cache.clear()

    async def asyncTearDown(self) -> None:
        self.connection_db.stop()
        self.schedule_db.stop()
        self.plan_db.stop()
        self.conversation_db.stop()
        self.file_db.stop()
        await self.db.close()

    async def test_local_identity_and_messages_survive_repository_reload(self) -> None:
        await conversation_repo.ensure_local_identity()
        await conversation_repo.save_message(
            conversation_repo.DEFAULT_CONVERSATION_ID,
            "message-1",
            "user",
            "persistent hello",
            {"followUps": ["next"]},
            123.0,
        )

        restored = await conversation_repo.list_messages(conversation_repo.DEFAULT_CONVERSATION_ID)
        self.assertEqual(restored[0]["content"], "persistent hello")
        self.assertEqual(restored[0]["metadata"]["followUps"], ["next"])

    async def test_legacy_session_data_is_adopted_by_local_user(self) -> None:
        await self.db.execute(
            "INSERT INTO schedules(id, session_id, created_at, updated_at) VALUES('old', 'sess-random', 1, 1)"
        )
        await self.db.execute("DELETE FROM schema_migrations WHERE version=2")
        await self.db.commit()
        await apply_migrations(self.db, [Migration(2, "persistent_identity_conversations_files", M1_SCHEMA)])
        cursor = await self.db.execute("SELECT session_id FROM schedules WHERE id='old'")
        self.assertEqual((await cursor.fetchone())[0], "local-user")

    async def test_legacy_message_table_is_upgraded_without_data_loss(self) -> None:
        await self.db.execute("DROP TABLE messages")
        await self.db.execute(
            "CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
            "scenario TEXT, content TEXT, created_at REAL)"
        )
        await self.db.execute(
            "INSERT INTO messages VALUES(1, 'old-session', 'user', 'search', 'legacy hello', 456)"
        )
        await self.db.execute("DELETE FROM schema_migrations WHERE version=2")
        await self.db.commit()

        moved = await prepare_legacy_message_table(self.db)
        await apply_migrations(
            self.db,
            [Migration(2, "persistent_identity_conversations_files", M1_SCHEMA)],
        )
        imported = await import_legacy_messages(self.db)
        imported_again = await import_legacy_messages(self.db)
        cursor = await self.db.execute(
            "SELECT conversation_id, role, content, metadata FROM messages WHERE id='legacy-message-1'"
        )
        row = await cursor.fetchone()

        self.assertTrue(moved)
        self.assertEqual(imported, 1)
        self.assertEqual(imported_again, 0)
        self.assertEqual(row["conversation_id"], conversation_repo.DEFAULT_CONVERSATION_ID)
        self.assertEqual(row["role"], "user")
        self.assertEqual(row["content"], "legacy hello")
        self.assertEqual(json.loads(row["metadata"])["legacy_scenario"], "search")

    async def test_pdf_is_hashed_safely_and_restored_from_database(self) -> None:
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Persistent PDF content")
        content = document.tobytes()
        document.close()

        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "file_storage_dir", directory):
            first = await store_pdf(content, "../../unsafe.pdf", conversation_repo.DEFAULT_CONVERSATION_ID)
            second = await store_pdf(content, "duplicate.pdf", conversation_repo.DEFAULT_CONVERSATION_ID)
            restored = await file_repo.get_file(first["id"])

            self.assertEqual(first["id"], second["id"])
            self.assertEqual(first["original_name"], "unsafe.pdf")
            self.assertTrue(Path(first["storage_path"]).is_relative_to(Path(directory)))
            self.assertIn("Persistent PDF content", restored["extracted_text"])

            Path(first["storage_path"]).unlink()
            recovered = await store_pdf(content, "recover.pdf", conversation_repo.DEFAULT_CONVERSATION_ID)
            cursor = await self.db.execute("SELECT COUNT(*) FROM files WHERE sha256=?", (first["sha256"],))

            self.assertEqual(recovered["id"], first["id"])
            self.assertTrue(Path(recovered["storage_path"]).is_file())
            self.assertEqual((await cursor.fetchone())[0], 1)

    async def test_legacy_resource_routes_always_use_local_user(self) -> None:
        schedule_response = await routes.create_schedule(
            SaveScheduleRequest(
                session_id="random-session",
                schedule={"id": "schedule-1", "title": "固定归属日程"},
            )
        )
        plan_response = await routes.create_plan(
            SavePlanRequest(
                session_id="random-session",
                plan={"id": "plan-1", "session_id": "random-session", "title": "固定归属计划"},
            )
        )

        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Local user paper")
        content = document.tobytes()
        document.close()
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "file_storage_dir", directory):
            stored = await store_pdf(content, "paper.pdf", conversation_repo.DEFAULT_CONVERSATION_ID)
            paper_response = await paper_routes.save_paper(
                stored["id"], "固定归属论文", "", "random-session"
            )

        schedules = await routes.list_user_schedules("random-session")
        plans = await routes.list_user_plans("random-session")
        papers = await paper_routes.list_saved_papers("random-session")
        cursor = await self.db.execute(
            "SELECT session_id FROM schedules UNION SELECT session_id FROM travel_plans "
            "UNION SELECT session_id FROM papers"
        )

        self.assertTrue(schedule_response["ok"])
        self.assertTrue(plan_response["ok"])
        self.assertTrue(paper_response["ok"])
        self.assertEqual([row[0] for row in await cursor.fetchall()], [conversation_repo.LOCAL_USER_ID])
        self.assertEqual(schedules["schedules"][0]["session_id"], conversation_repo.LOCAL_USER_ID)
        self.assertEqual(plans["plans"][0]["session_id"], conversation_repo.LOCAL_USER_ID)
        self.assertEqual(len(papers["papers"]), 1)
