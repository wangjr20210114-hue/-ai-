"""建表脚本：启动时自动初始化。"""
from __future__ import annotations

from database.connection import get_db

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


async def init_db() -> None:
    db = await get_db()
    await db.executescript(SCHEMA)
    await db.commit()
    # 写入 POI 种子数据
    from services.poi_data import seed_pois
    await seed_pois(db)
