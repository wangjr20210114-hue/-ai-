"""建表脚本：启动时自动初始化。"""
from __future__ import annotations

import json

from database.connection import get_db
from database.migrations import Migration, apply_migrations

LEGACY_MESSAGES_TABLE = "messages_legacy_m0"

SCHEMA = """
CREATE TABLE IF NOT EXISTS travel_plans (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    title TEXT DEFAULT '',
    departure TEXT DEFAULT '',
    destination TEXT DEFAULT '',
    days INTEGER DEFAULT 3,
    travel_style TEXT DEFAULT '',
    scenery_preference TEXT DEFAULT '',
    budget TEXT DEFAULT '',
    extra_notes TEXT DEFAULT '',
    markdown_content TEXT DEFAULT '',
    baike_info TEXT DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    title TEXT DEFAULT '',
    category TEXT DEFAULT 'other',
    start_time REAL DEFAULT 0,
    duration_minutes INTEGER DEFAULT 0,
    duration_days INTEGER DEFAULT 0,
    location TEXT DEFAULT '',
    description TEXT DEFAULT '',
    markdown_content TEXT DEFAULT '',
    extra TEXT DEFAULT '{}',
    done INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pois (
    id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    name TEXT NOT NULL,
    address TEXT DEFAULT '',
    category TEXT DEFAULT 'other',
    ticket INTEGER DEFAULT 0,
    stay_time INTEGER DEFAULT 60,
    cost_estimate INTEGER DEFAULT 0,
    place_type TEXT DEFAULT 'other',
    lat REAL DEFAULT 0,
    lng REAL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pois_city ON pois(city);
CREATE INDEX IF NOT EXISTS idx_pois_name ON pois(name);

CREATE TABLE IF NOT EXISTS geo_cache (
    address TEXT PRIMARY KEY,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    adcode TEXT DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_cache (
    city TEXT PRIMARY KEY,
    weather_json TEXT NOT NULL,
    adcode TEXT DEFAULT '',
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    title TEXT DEFAULT '',
    arxiv_id TEXT DEFAULT '',
    filename TEXT DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_papers_session ON papers(session_id);
"""

M1_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '我',
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '默认会话',
    summary TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'ai', 'system')),
    content TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at ASC);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    sha256 TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    page_count INTEGER NOT NULL DEFAULT 0,
    extracted_text TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    UNIQUE(owner_id, sha256)
);
CREATE INDEX IF NOT EXISTS idx_files_owner ON files(owner_id, created_at DESC);

INSERT OR IGNORE INTO users(id, display_name, timezone, created_at, updated_at)
VALUES('local-user', '我', 'Asia/Shanghai', CAST(strftime('%s','now') AS REAL), CAST(strftime('%s','now') AS REAL));
INSERT OR IGNORE INTO conversations(id, user_id, title, summary, created_at, updated_at)
VALUES('default-conversation', 'local-user', '默认会话', '', CAST(strftime('%s','now') AS REAL), CAST(strftime('%s','now') AS REAL));

UPDATE travel_plans SET session_id='local-user' WHERE session_id<>'local-user';
UPDATE schedules SET session_id='local-user' WHERE session_id<>'local-user';
UPDATE papers SET session_id='local-user' WHERE session_id<>'local-user';
"""

M2_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_events (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id TEXT,
    payload TEXT NOT NULL DEFAULT '{}',
    dedup_key TEXT NOT NULL UNIQUE,
    occurred_at REAL NOT NULL,
    received_at REAL NOT NULL,
    processed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_agent_events_pending ON agent_events(processed_at, received_at);

CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    event_id TEXT REFERENCES agent_events(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('created','classified','planned','policy_checked','waiting_confirmation','queued','executing','succeeded','failed','cancelled','skipped')),
    intent TEXT NOT NULL DEFAULT '',
    plan_json TEXT NOT NULL DEFAULT '{}',
    plan_hash TEXT NOT NULL DEFAULT '',
    lease_until REAL,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status, updated_at);

CREATE TABLE IF NOT EXISTS agent_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    step TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_observations_run ON agent_observations(run_id, id);

CREATE TABLE IF NOT EXISTS pending_actions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_name TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('draft','awaiting_confirmation','confirmed','executing','succeeded','failed','cancelled','expired')),
    expires_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    executed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_pending_actions_status ON pending_actions(status, updated_at);
"""


async def _table_columns(db, table_name: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    return {str(row[1]) for row in await cursor.fetchall()}


async def prepare_legacy_message_table(db) -> bool:
    """Move the pre-M1 messages table aside so migration 2 can create the new schema."""
    columns = await _table_columns(db, "messages")
    if not columns or "conversation_id" in columns:
        return False
    if await _table_columns(db, LEGACY_MESSAGES_TABLE):
        raise RuntimeError("旧消息表与备份表同时存在，拒绝自动覆盖")
    await db.execute(f"ALTER TABLE messages RENAME TO {LEGACY_MESSAGES_TABLE}")
    await db.commit()
    return True


async def import_legacy_messages(db) -> int:
    """Idempotently adopt pre-M1 messages into the default persistent conversation."""
    if not await _table_columns(db, LEGACY_MESSAGES_TABLE):
        return 0
    cursor = await db.execute(
        f"SELECT id, session_id, role, scenario, content, created_at FROM {LEGACY_MESSAGES_TABLE} ORDER BY id"
    )
    rows = await cursor.fetchall()
    imported = 0
    latest = 0.0
    for row in rows:
        role = row[2] if row[2] in {"user", "ai", "system"} else "system"
        metadata = json.dumps(
            {
                "migrated_from": LEGACY_MESSAGES_TABLE,
                "legacy_session_id": row[1],
                "legacy_scenario": row[3],
            },
            ensure_ascii=False,
        )
        result = await db.execute(
            "INSERT OR IGNORE INTO messages(id, conversation_id, role, content, metadata, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (f"legacy-message-{row[0]}", "default-conversation", role, row[4] or "", metadata, row[5]),
        )
        imported += max(result.rowcount, 0)
        latest = max(latest, float(row[5] or 0))
    if latest:
        await db.execute(
            "UPDATE conversations SET updated_at=MAX(updated_at, ?) WHERE id='default-conversation'",
            (latest,),
        )
    await db.commit()
    return imported


async def init_db() -> None:
    db = await get_db()
    await prepare_legacy_message_table(db)
    await apply_migrations(
        db,
        [
            Migration(1, "initial_schema", SCHEMA),
            Migration(2, "persistent_identity_conversations_files", M1_SCHEMA),
            Migration(3, "persistent_agent_runtime", M2_SCHEMA),
        ],
    )
    await import_legacy_messages(db)
    # 写入 POI 种子数据
    from services.poi_data import seed_pois
    await seed_pois(db)
    from services.file_service import import_legacy_paper_files
    await import_legacy_paper_files()
