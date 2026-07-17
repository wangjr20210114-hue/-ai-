#!/usr/bin/env python3
"""Export the retired SQLite database into a deterministic Makers import bundle.

This utility is deliberately offline and read-only. It does not import FastAPI,
aiosqlite, repositories, or any production runtime module.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Iterable


BUNDLE_SCHEMA_VERSION = 1
JSON_COLUMNS = {
    "metadata", "extra", "payload", "plan_json", "checkpoint", "snapshot",
    "result_json", "candidate_json", "value_json", "response_json", "baike_info",
}


def _json_value(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _normalized(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for key in JSON_COLUMNS.intersection(item):
        fallback = [] if key == "plan_json" else {}
        item[key] = _json_value(item[key], fallback)
    for key, value in list(item.items()):
        if isinstance(value, bytes):
            item[key] = value.hex()
    return item


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def _rows(connection: sqlite3.Connection, table: str, existing: set[str]) -> list[dict[str, Any]]:
    if table not in existing:
        return []
    return [_normalized(row) for row in connection.execute(f'SELECT * FROM "{table}"').fetchall()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_ndjson(path: Path, values: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as output:
        for value in values:
            output.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def _user_for(row: dict[str, Any], known_users: set[str]) -> str:
    for key in ("user_id", "owner_id", "session_id"):
        candidate = str(row.get(key) or "")
        if candidate in known_users:
            return candidate
    return "local-user"


def _safe_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "-" for char in value).strip(".-")
    return (cleaned or "file")[:120]


def build_bundle(database: Path, output: Path, *, include_files: bool = False) -> dict[str, Any]:
    database = database.expanduser().resolve(strict=True)
    if not database.is_file():
        raise ValueError("SQLite source must be a file")
    output = output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)

    source_sha = _sha256(database)
    export_id = f"sqlite_{source_sha[:24]}"
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        existing = _tables(connection)
        users = _rows(connection, "users", existing)
        if not users:
            users = [{"id": "local-user", "display_name": "我", "timezone": "Asia/Shanghai"}]
        known_users = {str(item.get("id") or "local-user") for item in users} | {"local-user"}

        conversations = _rows(connection, "conversations", existing)
        if not conversations:
            conversations = [{
                "id": "default-conversation", "user_id": "local-user", "title": "默认会话",
                "summary": "", "created_at": 0, "updated_at": 0,
            }]
        conversation_users = {str(item.get("id")): _user_for(item, known_users) for item in conversations}

        messages = _rows(connection, "messages", existing)
        legacy_messages = _rows(connection, "messages_legacy_m0", existing)
        for item in legacy_messages:
            messages.append({
                "id": f"legacy-message-{item.get('id')}",
                "conversation_id": "default-conversation",
                "role": item.get("role") or "system",
                "content": item.get("content") or "",
                "metadata": {
                    "migrated_from": "messages_legacy_m0",
                    "legacy_session_id": item.get("session_id"),
                    "legacy_scenario": item.get("scenario"),
                },
                "created_at": item.get("created_at") or 0,
            })
        messages.sort(key=lambda item: (str(item.get("conversation_id") or ""), float(item.get("created_at") or 0), str(item.get("id") or "")))
        for item in messages:
            item["role"] = "assistant" if item.get("role") == "ai" else item.get("role")
            item["user_id"] = conversation_users.get(str(item.get("conversation_id") or ""), "local-user")
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            item["metadata"] = {**metadata, "migration_export_id": export_id, "legacy_message_id": str(item.get("id") or "")}

        states: dict[str, dict[str, Any]] = {}
        for user_id in known_users:
            states[user_id] = {
                "user_id": user_id,
                "workspace": {
                    "schema_version": 1, "revision": 0, "schedules": {}, "travel_plans": {},
                    "actions": {}, "place_candidates": {}, "provider_calls": {}, "active_map_action_id": "",
                },
                "proactive": {
                    "schema_version": 1, "revision": 0, "preferences": {}, "events": {}, "runs": {},
                    "observations": [], "notifications": {}, "workflows": {}, "checkpoints": {},
                    "legacy_jobs": {}, "last_tick": None, "tick_lease": None,
                },
                "intelligence": {
                    "schema_version": 1, "revision": 0, "memory_proposals": {}, "memories": {},
                    "feedback": [], "rule_proposals": {}, "usage": [], "usage_preferences": {},
                },
            }

        for item in _rows(connection, "schedules", existing):
            user_id = _user_for(item, known_users)
            schedule_id = str(item.get("id") or "")
            if schedule_id:
                states[user_id]["workspace"]["schedules"][schedule_id] = item
        for item in _rows(connection, "travel_plans", existing):
            user_id = _user_for(item, known_users)
            item_id = str(item.get("id") or "")
            if item_id:
                states[user_id]["workspace"]["travel_plans"][item_id] = item

        for table, target in (("agent_events", "events"), ("agent_runs", "runs"), ("notifications", "notifications")):
            for item in _rows(connection, table, existing):
                user_id = _user_for(item, known_users)
                item_id = str(item.get("id") or "")
                if item_id:
                    states[user_id]["proactive"][target][item_id] = item
        for item in _rows(connection, "agent_observations", existing):
            run_id = str(item.get("run_id") or "")
            owner = next((uid for uid, state in states.items() if run_id in state["proactive"]["runs"]), "local-user")
            states[owner]["proactive"]["observations"].append(item)
        for item in _rows(connection, "scheduled_jobs", existing):
            user_id = _user_for(item, known_users)
            item_id = str(item.get("id") or "")
            if item_id:
                # Legacy jobs are preserved for inspection but never activated automatically.
                states[user_id]["proactive"]["legacy_jobs"][item_id] = {**item, "status": "migration_review_required"}
        for item in _rows(connection, "collector_checkpoints", existing):
            states["local-user"]["proactive"]["checkpoints"][str(item.get("collector_name") or "unknown")] = item.get("checkpoint") or {}
        for item in _rows(connection, "notification_preferences", existing):
            states[_user_for(item, known_users)]["proactive"]["preferences"] = {
                "enabled": bool(item.get("enabled", 1)),
                "daily_limit": int(item.get("daily_limit") or 5),
                "quiet_hours": {
                    "enabled": True,
                    "start": str(item.get("quiet_hours_start") or "22:00"),
                    "end": str(item.get("quiet_hours_end") or "08:00"),
                },
                "legacy_cooldown_seconds": int(item.get("cooldown_seconds") or 0),
            }

        for table, target in (("memory_proposals", "memory_proposals"), ("memories", "memories")):
            for item in _rows(connection, table, existing):
                user_id = _user_for(item, known_users)
                item_id = str(item.get("id") or "")
                if item_id:
                    states[user_id]["intelligence"][target][item_id] = item
        for item in _rows(connection, "feedback_records", existing):
            states[_user_for(item, known_users)]["intelligence"]["feedback"].append(item)
        for item in _rows(connection, "usage_records", existing):
            states[_user_for(item, known_users)]["intelligence"]["usage"].append(item)
        for item in _rows(connection, "usage_preferences", existing):
            states[_user_for(item, known_users)]["intelligence"]["legacy_usage_preferences"] = item

        file_rows = _rows(connection, "files", existing)
        exported_files = []
        files_dir = output / "files"
        if include_files:
            files_dir.mkdir(exist_ok=True)
        for item in file_rows:
            source_text = str(item.get("storage_path") or "")
            source = Path(source_text).expanduser()
            if not source.is_absolute():
                source = (database.parent / source).resolve()
            exists = source.is_file()
            actual_sha = _sha256(source) if exists else ""
            exported_path = ""
            if include_files and exists:
                name = f"{actual_sha[:16]}-{_safe_filename(str(item.get('original_name') or source.name))}"
                destination = files_dir / name
                if not destination.exists():
                    shutil.copy2(source, destination)
                exported_path = destination.relative_to(output).as_posix()
            exported_files.append({
                **item, "user_id": _user_for(item, known_users), "source_exists": exists,
                "actual_sha256": actual_sha, "exported_path": exported_path,
            })

        counts = {
            "users": _write_ndjson(output / "users.ndjson", users),
            "conversations": _write_ndjson(output / "conversations.ndjson", conversations),
            "messages": _write_ndjson(output / "messages.ndjson", messages),
            "states": _write_ndjson(output / "states.ndjson", [states[key] for key in sorted(states)]),
            "files": _write_ndjson(output / "files.ndjson", exported_files),
        }
        manifest = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "export_id": export_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": {"filename": database.name, "sha256": source_sha},
            "counts": counts,
            "tables_present": sorted(existing),
            "include_files": include_files,
            "missing_file_count": sum(1 for item in exported_files if not item["source_exists"]),
            "safety": {
                "sqlite_open_mode": "read_only",
                "legacy_jobs_activated": False,
                "pending_side_effects_imported": False,
            },
        }
        _write_json(output / "manifest.json", manifest)
        return manifest
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export retired SQLite data for EdgeOne Makers import")
    parser.add_argument("database", type=Path, help="Path to yuanbao.db or a verified backup snapshot")
    parser.add_argument("output", type=Path, help="New or empty output directory")
    parser.add_argument("--include-files", action="store_true", help="Copy referenced file bytes into the bundle")
    args = parser.parse_args()
    manifest = build_bundle(args.database, args.output, include_files=args.include_files)
    print(json.dumps({"ok": True, "export_id": manifest["export_id"], "counts": manifest["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
