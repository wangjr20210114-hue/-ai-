"""Versioned workspace state stored in the Makers LangGraph store.

The workspace is deliberately small and deterministic. LLM tools may prepare
actions, but only this module can activate a map selection or mutate schedules.
"""

from __future__ import annotations

import copy
import time
import uuid
from typing import Any


SCHEMA_VERSION = 1
USER_WORKSPACE_ID = "local-user"


def empty_workspace() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "schedules": {},
        "actions": {},
        "place_candidates": {},
        "active_map_action_id": "",
    }


def _namespace(conversation_id: str) -> tuple[str, str]:
    return ("yuanbao_workspace_v1", conversation_id)


def _item_value(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


async def load_workspace(store: Any, conversation_id: str) -> dict[str, Any]:
    if store is None:
        return empty_workspace()
    item = await store.aget(_namespace(conversation_id), "state")
    value = _item_value(item)
    if not value:
        return empty_workspace()
    state = empty_workspace()
    state.update(copy.deepcopy(value))
    for key in ("schedules", "actions", "place_candidates"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    return state


async def save_workspace(store: Any, conversation_id: str, state: dict[str, Any]) -> dict[str, Any]:
    state = copy.deepcopy(state)
    state["schema_version"] = SCHEMA_VERSION
    state["revision"] = int(state.get("revision") or 0) + 1
    if store is not None:
        await store.aput(_namespace(conversation_id), "state", state)
    return state


async def load_user_workspace(store: Any, legacy_conversation_id: str = "") -> dict[str, Any]:
    """Load user assets and migrate the active legacy conversation once."""
    state = await load_workspace(store, USER_WORKSPACE_ID)
    if int(state.get("revision") or 0) > 0 or legacy_conversation_id == USER_WORKSPACE_ID:
        return state
    if legacy_conversation_id:
        legacy = await load_workspace(store, legacy_conversation_id)
        if int(legacy.get("revision") or 0) > 0:
            return await save_workspace(store, USER_WORKSPACE_ID, legacy)
    return state


async def save_user_workspace(store: Any, state: dict[str, Any]) -> dict[str, Any]:
    return await save_workspace(store, USER_WORKSPACE_ID, state)


def new_action(kind: str, payload: dict[str, Any], *, requires_confirmation: bool) -> dict[str, Any]:
    now = int(time.time())
    prefix = {
        "map_recommendation": "maprec",
        "calendar_changes": "cal",
        "meeting_create": "meet",
        "image_generate": "img",
    }.get(kind, "act")
    return {
        "schema_version": SCHEMA_VERSION,
        "id": f"{prefix}_{uuid.uuid4().hex}",
        "kind": kind,
        "status": "awaiting_confirmation" if requires_confirmation else "ready",
        "version": 1,
        "payload": copy.deepcopy(payload),
        "result": None,
        "error": "",
        "created_at": now,
        "updated_at": now,
    }


def public_action(action: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(action.get(key))
        for key in (
            "schema_version", "id", "kind", "status", "version", "payload",
            "result", "error", "created_at", "updated_at",
        )
    }


def put_action(state: dict[str, Any], action: dict[str, Any]) -> None:
    state.setdefault("actions", {})[str(action["id"])] = copy.deepcopy(action)


def get_action(state: dict[str, Any], action_id: str) -> dict[str, Any]:
    action = state.get("actions", {}).get(action_id)
    if not isinstance(action, dict):
        raise ValueError("操作不存在或已经过期")
    return action


def check_action_version(action: dict[str, Any], version: int) -> None:
    if int(action.get("version") or 0) != int(version):
        raise ValueError("操作版本已变化，请刷新后重试")


def normalize_schedule(event: dict[str, Any], *, existing_id: str = "") -> dict[str, Any]:
    now = int(time.time())
    title = str(event.get("title") or "").strip()[:120]
    start_time = int(event.get("start_time") or 0)
    duration = max(1, int(event.get("duration_minutes") or 60))
    if not title or start_time <= 0:
        raise ValueError("日程必须包含标题和有效开始时间")
    place = event.get("place")
    if place is not None and not (
        isinstance(place, dict)
        and str(place.get("place_id") or "").strip()
        and isinstance(place.get("latitude"), (int, float))
        and isinstance(place.get("longitude"), (int, float))
    ):
        raise ValueError("日程地点必须来自地点搜索候选")
    category = str(event.get("category") or "travel")
    if category not in {"travel", "meeting", "dining", "remind", "task", "other"}:
        category = "other"
    location = str(event.get("location") or (place or {}).get("address") or "").strip()[:240]
    return {
        "id": existing_id or f"makers-{uuid.uuid4().hex}",
        "session_id": "makers",
        "title": title,
        "category": category,
        "start_time": start_time,
        "duration_minutes": duration,
        "duration_days": 0,
        "location": location,
        "description": str(event.get("description") or "").strip()[:1000],
        "markdown_content": "",
        "extra": {"source": "makers-workspace", "place": copy.deepcopy(place)} if place else {"source": "makers-workspace"},
        "done": bool(event.get("done", False)),
        "created_at": int(event.get("created_at") or now),
        "updated_at": now,
    }


def apply_calendar_changes(state: dict[str, Any], changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schedules = state.setdefault("schedules", {})
    changed: list[dict[str, Any]] = []
    for change in changes:
        operation = str(change.get("operation") or "create")
        if operation == "create":
            event = normalize_schedule(change.get("event") or {})
            schedules[event["id"]] = event
            changed.append(event)
        elif operation == "update":
            target_id = str(change.get("schedule_id") or "")
            previous = schedules.get(target_id)
            if not isinstance(previous, dict):
                raise ValueError(f"找不到要更新的日程：{target_id}")
            merged = copy.deepcopy(previous)
            merged.update(change.get("event") or {})
            event = normalize_schedule(merged, existing_id=target_id)
            schedules[target_id] = event
            changed.append(event)
        elif operation == "delete":
            target_id = str(change.get("schedule_id") or "")
            if target_id not in schedules:
                raise ValueError(f"找不到要删除的日程：{target_id}")
            removed = schedules.pop(target_id)
            changed.append({**removed, "deleted": True})
        else:
            raise ValueError(f"不支持的日程操作：{operation}")
    return changed


def active_map_payload(state: dict[str, Any]) -> dict[str, Any] | None:
    action_id = str(state.get("active_map_action_id") or "")
    action = state.get("actions", {}).get(action_id)
    if not isinstance(action, dict) or action.get("kind") != "map_recommendation":
        return None
    payload = action.get("payload") or {}
    return {
        "action_id": action_id,
        "title": str(payload.get("title") or "相关地点"),
        "places": copy.deepcopy(payload.get("places") or []),
    }
