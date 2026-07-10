from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import aiosqlite

from database.init_db import M1_SCHEMA, M2_SCHEMA, SCHEMA
from database.migrations import Migration, apply_migrations
from database.repositories import runtime_repo


class M2RuntimeRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA foreign_keys=ON")
        await apply_migrations(
            self.db,
            [
                Migration(1, "initial_schema", SCHEMA),
                Migration(2, "persistent_identity_conversations_files", M1_SCHEMA),
                Migration(3, "persistent_agent_runtime", M2_SCHEMA),
            ],
        )
        self.db_patch = patch.object(runtime_repo, "get_db", return_value=self.db)
        self.db_patch.start()

    async def asyncTearDown(self) -> None:
        self.db_patch.stop()
        await self.db.close()

    async def _waiting_run(self, dedup_key: str = "event:1") -> dict:
        event, _ = await runtime_repo.create_event("user.activity", {"text": "hello"}, dedup_key)
        run = await runtime_repo.create_run(event["id"], max_attempts=2)
        for status in ("classified", "planned", "policy_checked", "waiting_confirmation"):
            run = await runtime_repo.transition_run(run["id"], status, step=f"to_{status}")
        return run

    async def test_event_dedup_and_confirmed_snapshot_are_immutable(self) -> None:
        first, created = await runtime_repo.create_event("user.activity", {"text": "hello"}, "same-event")
        second, created_again = await runtime_repo.create_event("user.activity", {"text": "changed"}, "same-event")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["payload"], {"text": "hello"})

        run = await runtime_repo.create_run(first["id"], max_attempts=2)
        for status in ("classified", "planned", "policy_checked", "waiting_confirmation"):
            run = await runtime_repo.transition_run(run["id"], status, step=f"to_{status}")
        snapshot = {"subject": "评审会", "start_time": "2026-07-11T14:00:00+08:00"}
        action = await runtime_repo.create_action(run["id"], "meeting", snapshot, "meeting:1")

        with self.assertRaises(runtime_repo.StateConflict):
            await runtime_repo.confirm_action(action["id"], 2)
        confirmed = await runtime_repo.confirm_action(action["id"], 1)
        restored_run = await runtime_repo.get_run(run["id"])

        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["snapshot"], snapshot)
        self.assertEqual(restored_run["status"], "queued")
        self.assertEqual(restored_run["observations"][-1]["step"], "action_confirmed")
        with self.assertRaises(runtime_repo.StateConflict):
            await runtime_repo.confirm_action(action["id"], 1)

    async def test_expiry_cancel_and_limited_retry(self) -> None:
        expiring_run = await self._waiting_run("event:expiring")
        expiring = await runtime_repo.create_action(
            expiring_run["id"], "meeting", {"subject": "expired"}, "meeting:expired", expires_at=time.time() - 1
        )
        self.assertEqual(await runtime_repo.list_actions(), [])
        self.assertEqual((await runtime_repo.get_action(expiring["id"]))["status"], "expired")
        self.assertEqual((await runtime_repo.get_run(expiring_run["id"]))["status"], "cancelled")
        with self.assertRaises(runtime_repo.StateConflict):
            await runtime_repo.confirm_action(expiring["id"], 1)

        cancellable_run = await self._waiting_run("event:cancellable")
        cancellable = await runtime_repo.create_action(
            cancellable_run["id"], "meeting", {"subject": "cancel"}, "meeting:cancel"
        )
        cancelled = await runtime_repo.cancel_action(cancellable["id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual((await runtime_repo.get_run(cancellable_run["id"]))["status"], "cancelled")

        event, _ = await runtime_repo.create_event("user.activity", {}, "event:retry")
        failed_run = await runtime_repo.create_run(event["id"], max_attempts=2)
        failed_run = await runtime_repo.transition_run(failed_run["id"], "failed", step="failed", error="temporary")
        retried = await runtime_repo.retry_run(failed_run["id"])
        self.assertEqual(retried["status"], "queued")
        self.assertEqual(retried["attempt"], 1)
        with self.assertRaises(runtime_repo.StateConflict):
            await runtime_repo.retry_run(failed_run["id"])
