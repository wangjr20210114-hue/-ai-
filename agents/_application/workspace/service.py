"""Workspace application service over Makers LangGraph state.

The workspace is deliberately small and deterministic. LLM tools may prepare
actions, but only this module can activate a map selection or mutate schedules.
"""

from __future__ import annotations

import asyncio
import copy
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ..._domain.workspace.models import WorkspaceConflictError, WorkspaceSnapshotError
from ..._domain.workspace.policy import (
    action_snapshot_hash,
    seal_action_snapshot,
    verify_action_snapshot as verify_action_snapshot_integrity,
)
from ..._infrastructure.makers.data_version import namespace
from ..._infrastructure.makers.identity import required_user_id
from ..i18n import text


SCHEMA_VERSION = 1
_workspace_write_locks: dict[str, asyncio.Lock] = {}


def _copy(key: str, **params: object) -> str:
    """Resolve persistent workspace copy through the shared product catalog."""
    return text(key, "zh-CN", **params)


def verify_action_snapshot(
    action: dict[str, Any], *, response_language: object = "zh-CN",
) -> None:
    """Translate the pure domain integrity error at the application boundary."""
    try:
        verify_action_snapshot_integrity(action)
    except WorkspaceSnapshotError as exc:
        raise ValueError(
            text("workspace.action.snapshot_invalid", response_language)
        ) from exc


def _workspace_write_lock(conversation_id: str) -> asyncio.Lock:
    key = required_user_id(conversation_id)
    lock = _workspace_write_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _workspace_write_locks[key] = lock
    return lock


def empty_workspace() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "schedules": {},
        "travel_plans": {},
        "actions": {},
        "place_candidates": {},
        "provider_calls": {},
        "active_map_action_id": "",
        "latest_route_plan": {},
        "route_plans": {},
    }


def _namespace(conversation_id: str) -> tuple[str, str]:
    return namespace("workspace", conversation_id)


def _item_value(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


async def load_workspace(store: Any, conversation_id: str) -> dict[str, Any]:
    conversation_id = required_user_id(conversation_id)
    if store is None:
        return empty_workspace()
    item = await store.aget(_namespace(conversation_id), "state")
    value = _item_value(item)
    if not value:
        return empty_workspace()
    state = empty_workspace()
    state.update(copy.deepcopy(value))
    for key in (
        "schedules",
        "travel_plans",
        "actions",
        "place_candidates",
        "provider_calls",
        "route_plans",
    ):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    if not isinstance(state.get("latest_route_plan"), dict):
        state["latest_route_plan"] = {}
    return state


async def save_workspace(store: Any, conversation_id: str, state: dict[str, Any]) -> dict[str, Any]:
    conversation_id = required_user_id(conversation_id)
    expected_revision = int(state.get("revision") or 0)
    async with _workspace_write_lock(conversation_id):
        if store is not None:
            current = _item_value(await store.aget(_namespace(conversation_id), "state"))
            current_revision = int((current or {}).get("revision") or 0)
            if current_revision != expected_revision:
                raise WorkspaceConflictError(
                    _copy("workspace.conflict")
                )
        saved = copy.deepcopy(state)
        saved["schema_version"] = SCHEMA_VERSION
        saved["revision"] = expected_revision + 1
        if store is not None:
            await store.aput(_namespace(conversation_id), "state", saved)
        # Keep callers that perform a second step on the same object aligned
        # with the stored revision while preserving the returned copy contract.
        state["revision"] = saved["revision"]
        return saved


async def load_user_workspace(
    store: Any, *, user_id: str,
) -> dict[str, Any]:
    """Load only the explicit user namespace; old conversation state is never inherited."""
    return await load_workspace(store, required_user_id(user_id))


async def save_user_workspace(
    store: Any, state: dict[str, Any], *, user_id: str,
) -> dict[str, Any]:
    return await save_workspace(store, required_user_id(user_id), state)


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


def begin_action_execution(action: dict[str, Any], *, owner: str, now: int, lease_seconds: int = 180) -> None:
    verify_action_snapshot(action)
    if action.get("status") == "succeeded":
        return
    if action.get("status") == "executing":
        if int(action.get("lease_until") or 0) > now:
            raise ValueError(_copy("workspace.action.executing"))
        action["status"] = "reconciliation_required"
        action["reconciliation_required"] = True
        action["error"] = _copy("workspace.action.lease_expired")
        action["version"] = int(action.get("version") or 1) + 1
        action["updated_at"] = now
        raise ValueError(action["error"])
    if action.get("status") not in {"awaiting_confirmation", "ready"}:
        raise ValueError(_copy("workspace.action.unavailable"))
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
        raise ValueError(_copy("workspace.action.provider_pending"))
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
        raise ValueError(_copy("workspace.action.provider_ledger_missing"))
    unknown = bool(result.get("reconciliation_required"))
    call.update({
        "status": "succeeded" if result.get("ok") else "unknown" if unknown else "failed",
        "result": copy.deepcopy(result),
        "error": "" if result.get("ok") else str(result.get("error") or _copy("workspace.action.failed")),
        "updated_at": now,
    })
    action["result"] = copy.deepcopy(result)
    action["status"] = "succeeded" if result.get("ok") else "reconciliation_required" if unknown else "failed"
    action["reconciliation_required"] = unknown
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
        action["error"] = _copy("workspace.action.interrupted")
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
        raise ValueError(_copy("workspace.action.missing"))
    return action


def check_action_version(action: dict[str, Any], version: int) -> None:
    if int(action.get("version") or 0) != int(version):
        raise ValueError(_copy("workspace.action.version_changed"))


def normalize_schedule(event: dict[str, Any], *, existing_id: str = "") -> dict[str, Any]:
    now = int(time.time())
    title = str(event.get("title") or "").strip()[:120]
    start_time = int(event.get("start_time") or 0)
    duration = max(1, int(event.get("duration_minutes") or 60))
    if not title or start_time <= 0:
        raise ValueError(_copy("workspace.schedule.invalid"))
    place = event.get("place")
    if place is not None and not (
        isinstance(place, dict)
        and str(place.get("place_id") or "").strip()
        and isinstance(place.get("latitude"), (int, float))
        and isinstance(place.get("longitude"), (int, float))
    ):
        raise ValueError(_copy("workspace.schedule.unverified_place"))
    category = str(event.get("category") or "travel")
    if category not in {"travel", "meeting", "dining", "remind", "task", "other"}:
        category = "other"
    location = str(event.get("location") or (place or {}).get("address") or "").strip()[:240]
    extra = copy.deepcopy(event.get("extra")) if isinstance(event.get("extra"), dict) else {}
    extra["source"] = str(extra.get("source") or "makers-workspace")
    if place:
        extra["place"] = copy.deepcopy(place)
    elif "place" in event:
        extra.pop("place", None)
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
        "extra": extra,
        "done": bool(event.get("done", False)),
        "created_at": int(event.get("created_at") or now),
        "updated_at": now,
    }


def beijing_day_start(now: int | None = None) -> int:
    """Return the start of today in the product's fixed Asia/Shanghai timezone."""
    tz = timezone(timedelta(hours=8))
    current = datetime.fromtimestamp(int(now if now is not None else time.time()), tz)
    return int(current.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def validate_calendar_change_window(
    state: dict[str, Any], changes: list[dict[str, Any]], *, now: int | None = None,
) -> None:
    """Reject every mutation whose existing or resulting schedule is before today."""
    floor = beijing_day_start(now)
    schedules = state.get("schedules") or {}
    for change in changes:
        operation = str(change.get("operation") or "create")
        previous = schedules.get(str(change.get("schedule_id") or ""))
        if operation in {"update", "delete"} and isinstance(previous, dict):
            if int(previous.get("start_time") or 0) < floor:
                raise ValueError(_copy("workspace.schedule.past_read_only"))
        if operation != "delete":
            event = change.get("event") if isinstance(change.get("event"), dict) else {}
            start = int(event.get("start_time") or (previous or {}).get("start_time") or 0)
            if start and start < floor:
                raise ValueError(_copy("workspace.schedule.past_create"))


def calendar_change_warnings(state: dict[str, Any], changes: list[dict[str, Any]]) -> list[str]:
    """Preview deterministic overlap warnings without mutating the live workspace."""
    preview = copy.deepcopy(state)
    changed = apply_calendar_changes(preview, changes)
    changed_ids = {str(item.get("id") or "") for item in changed if not item.get("deleted")}
    schedules = sorted(
        (item for item in (preview.get("schedules") or {}).values() if isinstance(item, dict)),
        key=lambda item: int(item.get("start_time") or 0),
    )
    warnings: list[str] = []
    for index, left in enumerate(schedules):
        left_start = int(left.get("start_time") or 0)
        left_end = left_start + max(1, int(left.get("duration_minutes") or 60)) * 60
        for right in schedules[index + 1:]:
            right_start = int(right.get("start_time") or 0)
            if right_start >= left_end:
                break
            if str(left.get("id") or "") not in changed_ids and str(right.get("id") or "") not in changed_ids:
                continue
            warnings.append(_copy(
                "workspace.schedule.overlap",
                left=left.get("title") or _copy("workspace.schedule.default_title"),
                right=right.get("title") or _copy("workspace.schedule.default_title"),
            ))
    return list(dict.fromkeys(warnings))[:6]


def meeting_action_payload(
    state: dict[str, Any],
    subject: Any,
    start_time: Any,
    end_time: Any,
) -> dict[str, Any]:
    """Build an editable meeting proposal without inventing missing details."""
    clean_subject = str(subject or "").strip()[:120] or _copy("workspace.meeting.default_title")
    raw_start = str(start_time or "").strip()
    raw_end = str(end_time or "").strip()
    missing_fields: list[str] = []
    validation_errors: list[str] = []

    def parse(value: str, field: str) -> datetime | None:
        if not value:
            missing_fields.append(field)
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            validation_errors.append(_copy(
                "workspace.meeting.start_invalid" if field == "start_time" else "workspace.meeting.end_invalid"
            ))
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
        return parsed

    start = parse(raw_start, "start_time")
    end = parse(raw_end, "end_time")
    warnings: list[str] = []
    if start is not None and end is not None:
        if end <= start:
            validation_errors.append(_copy("workspace.meeting.end_before_start"))
        else:
            meeting_change = [{"operation": "create", "event": {
                "title": clean_subject,
                "start_time": int(start.timestamp()),
                "duration_minutes": max(1, int((end - start).total_seconds() // 60)),
                "category": "meeting",
            }}]
            try:
                validate_calendar_change_window(state, meeting_change)
            except ValueError as exc:
                validation_errors.append(str(exc))
            warnings = calendar_change_warnings(state, meeting_change)

    return {
        "subject": clean_subject,
        "start_time": start.isoformat() if start is not None else raw_start,
        "end_time": end.isoformat() if end is not None else raw_end,
        "missing_fields": missing_fields,
        "validation_errors": list(dict.fromkeys(validation_errors)),
        "warnings": warnings,
    }


def apply_calendar_changes(state: dict[str, Any], changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schedules = state.setdefault("schedules", {})
    changed: list[dict[str, Any]] = []

    def identity(event: dict[str, Any]) -> tuple:
        place = (event.get("extra") or {}).get("place") if isinstance(event.get("extra"), dict) else {}
        return (
            str(event.get("title") or "").strip().casefold(),
            int(event.get("start_time") or 0),
            int(event.get("duration_minutes") or 0),
            str(event.get("location") or "").strip().casefold(),
            str((place or {}).get("place_id") or ""),
        )

    for change in changes:
        operation = str(change.get("operation") or "create")
        if operation == "create":
            event = normalize_schedule(change.get("event") or {})
            # LLM deletion/edit proposals occasionally echoed untouched
            # schedules as creates. Idempotently ignore an exact existing event
            # instead of assigning a fresh id and multiplying it in the UI.
            if any(identity(existing) == identity(event) for existing in schedules.values() if isinstance(existing, dict)):
                continue
            schedules[event["id"]] = event
            changed.append(event)
        elif operation == "update":
            target_id = str(change.get("schedule_id") or "")
            previous = schedules.get(target_id)
            if not isinstance(previous, dict):
                raise ValueError(_copy("workspace.schedule.update_missing", target_id=target_id))
            merged = copy.deepcopy(previous)
            merged.update(change.get("event") or {})
            event = normalize_schedule(merged, existing_id=target_id)
            schedules[target_id] = event
            changed.append(event)
        elif operation == "delete":
            target_id = str(change.get("schedule_id") or "")
            if target_id not in schedules:
                raise ValueError(_copy("workspace.schedule.delete_missing", target_id=target_id))
            removed = schedules.pop(target_id)
            changed.append({**removed, "deleted": True})
        else:
            raise ValueError(_copy("workspace.schedule.operation_unsupported", operation=operation))
    # Repair exact legacy duplicates on the next confirmed mutation. Keep the
    # oldest stable id so references and proactive reminders remain valid.
    seen: set[tuple] = set()
    for schedule_id, event in sorted(
        list(schedules.items()),
        key=lambda item: (int((item[1] or {}).get("created_at") or 0), str(item[0])),
    ):
        if not isinstance(event, dict):
            continue
        key = identity(event)
        if key in seen:
            schedules.pop(schedule_id, None)
            continue
        seen.add(key)
    return changed


def apply_calendar_changes_best_effort(
    state: dict[str, Any],
    changes: list[dict[str, Any]],
    *,
    now: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Apply independent confirmed changes while reporting stale targets.

    Chat proposals are based on a JSON snapshot. Another tab may change that
    snapshot before the user confirms, so one vanished update/delete target
    must not erase other still-valid changes. Direct calendar-editor writes
    continue to use the atomic ``apply_calendar_changes`` path.
    """
    changed: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for index, change in enumerate(changes or [], 1):
        if not isinstance(change, dict):
            skipped.append({
                "operation": "unknown",
                "target": _copy("workspace.change.item", index=index),
                "reason": _copy("workspace.change.invalid"),
            })
            continue
        operation = str(change.get("operation") or "create")
        event = change.get("event") if isinstance(change.get("event"), dict) else {}
        target = str(
            event.get("title")
            or change.get("schedule_id")
            or _copy("workspace.change.item", index=index)
        ).strip()[:120]
        try:
            validate_calendar_change_window(state, [change], now=now)
            applied = apply_calendar_changes(state, [change])
            changed.extend(applied)
            if not applied and operation == "create":
                skipped.append({
                    "operation": operation,
                    "target": target,
                    "reason": _copy("workspace.change.duplicate"),
                })
        except ValueError as exc:
            skipped.append({
                "operation": operation,
                "target": target,
                "reason": str(exc)[:240] or _copy("workspace.change.not_applied"),
            })
    return changed, skipped


def active_map_payload(state: dict[str, Any]) -> dict[str, Any] | None:
    action_id = str(state.get("active_map_action_id") or "")
    action = state.get("actions", {}).get(action_id)
    if not isinstance(action, dict) or action.get("kind") != "map_recommendation":
        return None
    payload = action.get("payload") or {}
    return {
        "action_id": action_id,
        "title": str(payload.get("title") or _copy("workspace.map.default_title")),
        "places": copy.deepcopy(payload.get("places") or []),
        "route_mode": str(payload.get("route_mode") or ""),
        "route_strategy": str(payload.get("route_strategy") or ""),
        "route": copy.deepcopy(payload.get("route") or {}),
        "show_route": bool(payload.get("show_route")),
    }
