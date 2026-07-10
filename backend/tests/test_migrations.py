from __future__ import annotations

import unittest

import aiosqlite

from database.migrations import Migration, apply_migrations
from database.init_db import SCHEMA


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_migration_is_idempotent(self) -> None:
        db = await aiosqlite.connect(":memory:")
        try:
            migration = Migration(1, "create_example", "CREATE TABLE IF NOT EXISTS example(id TEXT PRIMARY KEY);")
            self.assertEqual(await apply_migrations(db, [migration]), [1])
            self.assertEqual(await apply_migrations(db, [migration]), [])

            cursor = await db.execute("SELECT version, name FROM schema_migrations")
            self.assertEqual(await cursor.fetchall(), [(1, "create_example")])
        finally:
            await db.close()

    async def test_initial_schema_can_be_adopted_by_an_existing_database(self) -> None:
        db = await aiosqlite.connect(":memory:")
        try:
            await db.executescript(SCHEMA)

            applied = await apply_migrations(db, [Migration(1, "initial_schema", SCHEMA)])
            self.assertEqual(applied, [1])

            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('travel_plans', 'schedules', 'papers')"
            )
            self.assertEqual({row[0] for row in await cursor.fetchall()}, {"travel_plans", "schedules", "papers"})
        finally:
            await db.close()
