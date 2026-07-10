"""Small, transactional SQLite migration runner for the single-user app."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import aiosqlite


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str


async def apply_migrations(
    db: aiosqlite.Connection,
    migrations: Iterable[Migration],
) -> list[int]:
    """Apply pending migrations once and return versions applied this run."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.commit()

    cursor = await db.execute("SELECT version FROM schema_migrations")
    applied = {int(row[0]) for row in await cursor.fetchall()}
    newly_applied: list[int] = []

    for migration in sorted(migrations, key=lambda item: item.version):
        if migration.version in applied:
            continue
        statements = [statement.strip() for statement in migration.sql.split(";") if statement.strip()]
        await db.execute("BEGIN IMMEDIATE")
        try:
            for statement in statements:
                await db.execute(statement)
            await db.execute(
                "INSERT INTO schema_migrations(version, name) VALUES(?, ?)",
                (migration.version, migration.name),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        newly_applied.append(migration.version)

    return newly_applied
