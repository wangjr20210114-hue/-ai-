"""One-time Makers-managed import helpers; not an Agent route."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from .intelligence import load_intelligence_state, save_intelligence_state
from .proactive import load_proactive_state, save_proactive_state
from .workspace import load_user_workspace, save_user_workspace


BUNDLE_SCHEMA_VERSION = 1


def validate_export_id(value: Any) -> str:
    export_id = str(value or "")
    if not re.fullmatch(r"sqlite_[0-9a-f]{24}", export_id):
        raise ValueError("无效迁移 export_id")
    return export_id


def migration_namespace(user_id: str, export_id: str) -> tuple[str, str, str]:
    return ("yuanbao_migration_v1", str(user_id), validate_export_id(export_id))


def _value(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


def _same(left: Any, right: Any) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True, default=str) == json.dumps(
        right, ensure_ascii=False, sort_keys=True, default=str,
    )


def _merge_mapping(current: dict[str, Any], incoming: Any) -> tuple[int, int, int]:
    imported = skipped = conflicts = 0
    if not isinstance(incoming, dict):
        return imported, skipped, conflicts
    for key, value in incoming.items():
        normalized = str(key)
        if normalized not in current:
            current[normalized] = copy.deepcopy(value)
            imported += 1
        elif _same(current[normalized], value):
            skipped += 1
        else:
            conflicts += 1
    return imported, skipped, conflicts


def _merge_list(current: list[Any], incoming: Any) -> tuple[int, int, int]:
    imported = skipped = conflicts = 0
    if not isinstance(incoming, list):
        return imported, skipped, conflicts
    by_id = {str(item.get("id")): item for item in current if isinstance(item, dict) and item.get("id") is not None}
    fingerprints = {json.dumps(item, ensure_ascii=False, sort_keys=True, default=str) for item in current}
    for value in incoming:
        fingerprint = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        item_id = str(value.get("id")) if isinstance(value, dict) and value.get("id") is not None else ""
        if fingerprint in fingerprints:
            skipped += 1
        elif item_id and item_id in by_id:
            conflicts += 1
        else:
            current.append(copy.deepcopy(value))
            fingerprints.add(fingerprint)
            if item_id:
                by_id[item_id] = value
            imported += 1
    return imported, skipped, conflicts


async def import_state_bundle(store: Any, user_id: str, export_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
    """Non-destructively merge normalized business state into Makers BaseStore."""
    validate_export_id(export_id)
    if not isinstance(bundle, dict) or str(bundle.get("user_id") or user_id) not in {str(user_id), "local-user"}:
        raise ValueError("迁移状态与目标用户不匹配")
    namespace = migration_namespace(user_id, export_id)
    marker = _value(await store.aget(namespace, "state"))
    if marker and marker.get("status") == "done":
        return {"status": "done", "idempotent": True, **copy.deepcopy(marker.get("result") or {})}

    workspace = await load_user_workspace(store, user_id=user_id)
    proactive = await load_proactive_state(store, user_id)
    intelligence = await load_intelligence_state(store, user_id)
    totals = {"imported": 0, "skipped": 0, "conflicts": 0}

    incoming_workspace = bundle.get("workspace") if isinstance(bundle.get("workspace"), dict) else {}
    for key in ("schedules", "travel_plans", "actions", "provider_calls"):
        current = workspace.setdefault(key, {})
        result = _merge_mapping(current, incoming_workspace.get(key))
        for name, value in zip(totals, result):
            totals[name] += value

    incoming_proactive = bundle.get("proactive") if isinstance(bundle.get("proactive"), dict) else {}
    for key in ("events", "runs", "notifications", "workflows", "checkpoints", "legacy_jobs"):
        current = proactive.setdefault(key, {})
        result = _merge_mapping(current, incoming_proactive.get(key))
        for name, value in zip(totals, result):
            totals[name] += value
    result = _merge_list(proactive.setdefault("observations", []), incoming_proactive.get("observations"))
    for name, value in zip(totals, result):
        totals[name] += value
    preferences = incoming_proactive.get("preferences")
    if isinstance(preferences, dict) and int(proactive.get("revision") or 0) == 0:
        proactive["preferences"].update(copy.deepcopy(preferences))

    incoming_intelligence = bundle.get("intelligence") if isinstance(bundle.get("intelligence"), dict) else {}
    for key in ("memory_proposals", "memories", "rule_proposals"):
        current = intelligence.setdefault(key, {})
        result = _merge_mapping(current, incoming_intelligence.get(key))
        for name, value in zip(totals, result):
            totals[name] += value
    for key in ("feedback", "usage"):
        result = _merge_list(intelligence.setdefault(key, []), incoming_intelligence.get(key))
        for name, value in zip(totals, result):
            totals[name] += value
    legacy_preferences = incoming_intelligence.get("legacy_usage_preferences")
    if isinstance(legacy_preferences, dict):
        intelligence["legacy_usage_preferences"] = copy.deepcopy(legacy_preferences)

    if totals["conflicts"]:
        await store.aput(namespace, "state", {"status": "conflict", "result": totals})
        return {"status": "conflict", **totals}

    await save_user_workspace(store, workspace, user_id)
    await save_proactive_state(store, proactive, user_id)
    await save_intelligence_state(store, intelligence, user_id)
    await store.aput(namespace, "state", {"status": "done", "result": totals})
    return {"status": "done", "idempotent": False, **totals}


def message_marker_key(message: dict[str, Any]) -> str:
    legacy_id = str(message.get("id") or (message.get("metadata") or {}).get("legacy_message_id") or "")
    if not legacy_id:
        raise ValueError("迁移消息缺少稳定 ID")
    return f"message_{hashlib.sha256(legacy_id.encode('utf-8')).hexdigest()[:32]}"


async def import_message_batch(
    conversation_store: Any,
    state_store: Any,
    *,
    user_id: str,
    export_id: str,
    conversation_id: str,
    messages: list[dict[str, Any]],
    title: str = "",
) -> dict[str, Any]:
    """Append a bounded message batch using the native Makers Conversation Store."""
    validate_export_id(export_id)
    if not 1 <= len(messages) <= 50:
        raise ValueError("每批迁移消息数量必须在 1 到 50 之间")
    namespace = migration_namespace(user_id, export_id)
    imported = skipped = 0
    unknown: list[str] = []
    for message in messages:
        marker_key = message_marker_key(message)
        marker = _value(await state_store.aget(namespace, marker_key))
        if marker and marker.get("status") == "done":
            skipped += 1
            continue
        if marker and marker.get("status") in {"started", "unknown"}:
            unknown.append(str(message.get("id") or marker_key))
            continue
        role = "assistant" if message.get("role") == "ai" else str(message.get("role") or "")
        content = message.get("content")
        if role not in {"user", "assistant", "system", "tool"} or not isinstance(content, (str, list, dict)):
            raise ValueError("迁移消息格式无效")
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        await state_store.aput(namespace, marker_key, {"status": "started", "legacy_id": str(message.get("id") or "")})
        try:
            message_id = await conversation_store.append_message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                user_id=user_id,
                metadata={**metadata, "migration_export_id": export_id, "legacy_message_id": str(message.get("id") or "")},
            )
        except Exception:
            await state_store.aput(namespace, marker_key, {"status": "unknown", "legacy_id": str(message.get("id") or "")})
            raise
        await state_store.aput(namespace, marker_key, {"status": "done", "message_id": str(message_id)})
        imported += 1
    if title and hasattr(conversation_store, "update_conversation"):
        await conversation_store.update_conversation(
            conversation_id=conversation_id,
            metadata={"title": str(title)[:120], "owner_user_id": user_id, "migration_export_id": export_id},
        )
    return {"status": "reconciliation_required" if unknown else "done", "imported": imported, "skipped": skipped, "unknown": unknown}
