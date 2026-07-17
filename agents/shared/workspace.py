"""Versioned workspace state stored in the Makers LangGraph store.

The workspace is deliberately small and deterministic. LLM tools may prepare
actions, but only this module can activate a map selection or mutate schedules.
"""

from __future__ import annotations

import copy
import hashlib
import json
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
        "provider_calls": {},
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
    for key in ("schedules", "actions", "place_candidates", "provider_calls"):
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


async def load_user_workspace(
    store: Any, _legacy_conversation_id: str = "", user_id: str = USER_WORKSPACE_ID,
) -> dict[str, Any]:
    """Load only the explicit user namespace; old conversation state is never inherited."""
    return await load_workspace(store, str(user_id or USER_WORKSPACE_ID))


async def save_user_workspace(
    store: Any, state: dict[str, Any], user_id: str = USER_WORKSPACE_ID,
) -> dict[str, Any]:
    return await save_workspace(store, str(user_id or USER_WORKSPACE_ID), state)


def new_action(kind: str, payload: dict[str, Any], *, requires_confirmation: bool) -> dict[str, Any]:
    now = int(time.time())
    prefix = {
        "map_recommendation": "maprec",
        "calendar_changes": "cal",
        "meeting_create": "meet",
        "image_generate": "img",
    }.get(kind, "act")
    action_id = f"{prefix}_{uuid.uuid4().hex}"
    snapshot_hash = action_snapshot_hash(kind, payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "id": action_id,
        "kind": kind,
        "status": "awaiting_confirmation" if requires_confirmation else "ready",
        "version": 1,
        "payload": copy.deepcopy(payload),
        "snapshot_hash": snapshot_hash,
        "idempotency_key": f"{action_id}:{snapshot_hash[:16]}",
        "attempt": 0,
        "lease_owner": "",
        "lease_until": 0,
        "provider_request_id": "",
        "reconciliation_required": False,
        "result": None,
        "error": "",
        "created_at": now,
        "updated_at": now,
    }


def action_snapshot_hash(kind: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"kind": str(kind), "payload": payload}, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def seal_action_snapshot(action: dict[str, Any]) -> None:
    """Seal a newly constructed action after all payload defaults are filled."""
    digest = action_snapshot_hash(str(action.get("kind") or ""), action.get("payload") or {})
    action["snapshot_hash"] = digest
    action["idempotency_key"] = f"{action.get('id')}:{digest[:16]}"


def verify_action_snapshot(action: dict[str, Any]) -> None:
    expected = str(action.get("snapshot_hash") or "")
    actual = action_snapshot_hash(str(action.get("kind") or ""), action.get("payload") or {})
    if expected and expected != actual:
        raise ValueError("操作参数快照校验失败，已拒绝执行")
    if not expected:
        action["snapshot_hash"] = actual
        action["idempotency_key"] = str(action.get("idempotency_key") or f"{action.get('id')}:{actual[:16]}")


def begin_action_execution(action: dict[str, Any], *, owner: str, now: int, lease_seconds: int = 180) -> None:
    verify_action_snapshot(action)
    if action.get("status") == "succeeded":
        return
    if action.get("status") == "executing":
        if int(action.get("lease_until") or 0) > now:
            raise ValueError("操作正在执行，请勿重复提交")
        action["status"] = "reconciliation_required"
        action["reconciliation_required"] = True
        action["error"] = "执行租约已过期，外部结果未知；为避免重复副作用，已停止自动重试"
        action["version"] = int(action.get("version") or 1) + 1
        action["updated_at"] = now
        raise ValueError(action["error"])
    if action.get("status") not in {"awaiting_confirmation", "ready"}:
        raise ValueError("该操作当前不能执行")
    action["status"] = "executing"
    action["attempt"] = int(action.get("attempt") or 0) + 1
    action["lease_owner"] = str(owner)
    action["lease_until"] = now + max(30, int(lease_seconds))
    action["updated_at"] = now


def start_provider_call(state: dict[str, Any], action: dict[str, Any], now: int) -> dict[str, Any]:
    verify_action_snapshot(action)
    key = str(action.get("idempotency_key") or "")
    calls = state.setdefault("provider_calls", {})
    existing = calls.get(key)
    if isinstance(existing, dict):
        if existing.get("status") == "succeeded":
            return existing
        raise ValueError("同一操作已有未核对的 Provider 调用，已阻止重复执行")
    request_id = f"provider_{uuid.uuid4().hex}"
    call = {
        "id": request_id,
        "action_id": str(action.get("id") or ""),
        "idempotency_key": key,
        "status": "started",
        "result": None,
        "error": "",
        "created_at": now,
        "updated_at": now,
    }
    calls[key] = call
    action["provider_request_id"] = request_id
    return call


def finish_provider_call(state: dict[str, Any], action: dict[str, Any], result: dict[str, Any], now: int) -> None:
    key = str(action.get("idempotency_key") or "")
    call = state.setdefault("provider_calls", {}).get(key)
    if not isinstance(call, dict):
        raise ValueError("Provider 调用账本缺失")
    call.update({
        "status": "succeeded" if result.get("ok") else "failed",
        "result": copy.deepcopy(result),
        "error": "" if result.get("ok") else str(result.get("error") or "执行失败"),
        "updated_at": now,
    })
    action["result"] = copy.deepcopy(result)
    action["status"] = "succeeded" if result.get("ok") else "failed"
    action["error"] = call["error"]
    action["lease_owner"] = ""
    action["lease_until"] = 0
    action["version"] = int(action.get("version") or 1) + 1
    action["updated_at"] = now


def recover_stale_actions(state: dict[str, Any], now: int) -> list[dict[str, Any]]:
    recovered = []
    for action in state.get("actions", {}).values():
        if not isinstance(action, dict) or action.get("status") != "executing":
            continue
        lease_until = int(action.get("lease_until") or action.get("updated_at") or 0)
        if lease_until > now:
            continue
        action["status"] = "reconciliation_required"
        action["reconciliation_required"] = True
        action["error"] = "执行中断且外部结果未知；已阻止自动重试，请人工核对"
        action["lease_owner"] = ""
        action["lease_until"] = 0
        action["version"] = int(action.get("version") or 1) + 1
        action["updated_at"] = now
        recovered.append(public_action(action))
    return recovered


def image_versions(state: dict[str, Any], group_id: str) -> list[dict[str, Any]]:
    versions = []
    for action in state.get("actions", {}).values():
        if not isinstance(action, dict) or action.get("kind") != "image_generate":
            continue
        payload = action.get("payload") or {}
        result = action.get("result") or {}
        if str(payload.get("group_id") or action.get("id")) != group_id or not result.get("ok"):
            continue
        versions.append({
            "id": str(action.get("id") or ""),
            "prompt": str(payload.get("prompt") or ""),
            "image_url": str(result.get("image_url") or ""),
            "storage_key": str(result.get("storage_key") or ""),
            "parent_action_id": str(payload.get("parent_action_id") or ""),
            "created_at": int(action.get("created_at") or 0),
        })
    return sorted(versions, key=lambda item: item["created_at"])


def public_action(action: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(action.get(key))
        for key in (
            "schema_version", "id", "kind", "status", "version", "payload",
            "result", "error", "created_at", "updated_at", "snapshot_hash",
            "idempotency_key", "attempt", "lease_owner", "lease_until",
            "provider_request_id", "reconciliation_required",
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
