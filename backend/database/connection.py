"""SQLite 异步连接管理。"""
from __future__ import annotations

import aiosqlite

from config import settings

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(settings.db_path)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA foreign_keys=ON;")
        await _db.execute("PRAGMA journal_mode=WAL;")
        await _db.execute("PRAGMA busy_timeout=5000;")
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
