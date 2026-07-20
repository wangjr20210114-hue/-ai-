"""POST /workspace: activate, confirm and cancel frozen workspace actions."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid

from .._shared.side_effects import create_tencent_meeting, generate_image, resolve_image_reference
from .._shared.proactive import (
    collect_provider_signals,
    collect_schedule_signals,
    ingest_workspace_signal,
    load_proactive_state,
    process_schedule_signals,
    reconcile_schedule_notifications,
    save_proactive_state,
)
from .._shared.auth import require_user, scoped_conversation_id
from .._shared.http import error
from .._shared.workspace import (
    active_map_payload,
    apply_calendar_changes,
    begin_action_execution,
    check_action_version,
    finish_provider_call,
    get_action,
    image_versions,
    load_user_workspace,
    load_workspace,
    new_action,
    put_action,
    public_action,
    save_workspace,
    seal_action_snapshot,
    start_provider_call,
    verify_action_snapshot,
    USER_WORKSPACE_ID,
)


def _response(state, action=None, **extra):
    payload = {
        "revision": int(state.get("revision") or 0),
        "schedules": sorted(state.get("schedules", {}).values(), key=lambda item: int(item.get("start_time") or 0)),
        "map": active_map_payload(state),
    }
    if action is not None:
        payload["action"] = public_action(action)
    payload.update(extra)
    return payload


async def _record_calendar_signal(store, changed: list[dict], source: str, user_id: str, env: dict | None = None) -> None:
    if not changed:
        return
    value = "|".join(sorted(f"{item.get('id')}:{item.get('updated_at')}:{bool(item.get('deleted'))}" for item in changed))
    state = await load_proactive_state(store, user_id)
    ingest_workspace_signal(
        state,
        signal_type="calendar_changed",
        dedup_key=hashlib.sha256(f"{source}:{value}".encode("utf-8")).hexdigest(),
        payload={"source": source, "changes": changed},
        now=int(time.time()),
    )
    try:
        workspace = await load_user_workspace(store, user_id=user_id)
        schedules = list((workspace.get("schedules") or {}).values())
        preferences = state.get("preferences") or {}
        lookahead = int(preferences.get("lookahead_hours") or 24)
        now = int(time.time())
        signals = collect_schedule_signals(schedules, now, lookahead)
        provider_signals, provider_diagnostics = await collect_provider_signals(env or {}, schedules, now, lookahead)
        signals.extend(provider_signals)
        affected_ids = {str(item.get("id") or "") for item in changed if str(item.get("id") or "")}
        reconciliation = reconcile_schedule_notifications(state, signals, affected_ids, now)
        stats = process_schedule_signals(state, signals, now)
        state.setdefault("checkpoints", {})["calendar_change"] = {
            "last_scan_at": now,
            "schedule_count": len(schedules),
            "signal_count": len(signals),
            "provider": provider_diagnostics,
            "reconciliation": reconciliation,
            "stats": stats,
        }
    except Exception as exc:
        logging.warning("immediate proactive calendar scan failed: %s", exc)
    await save_proactive_state(store, state, user_id)


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    body = ctx.request.body or {}
    operation = str(body.get("operation") or "get")
    raw_conversation_id = ctx.conversation_id
    if not raw_conversation_id:
        return error("makers-conversation-id header is required")
    conversation_id = scoped_conversation_id(ctx, user_id, raw_conversation_id)
    store = ctx.store.langgraph_store
    state = await load_user_workspace(store, conversation_id, user_id)
    workspace_id = user_id
    try:
        if operation == "get":
            active_statuses = {"awaiting_confirmation", "ready", "active", "executing", "reconciliation_required"}
            active_actions = [
                public_action(item) for item in state.get("actions", {}).values()
                if str(item.get("status") or "") in active_statuses
            ]
            return _response(
                state,
                actions=active_actions[-30:],
                travel_plans=sorted(
                    state.get("travel_plans", {}).values(),
                    key=lambda item: int(item.get("updated_at") or item.get("created_at") or 0),
                    reverse=True,
                ),
            )

        if operation == "save_travel_plan":
            raw = body.get("plan") or {}
            if not isinstance(raw, dict):
                raise ValueError("旅行计划格式无效")
            title = str(raw.get("title") or "").strip()[:160]
            destination = str(raw.get("destination") or "").strip()[:120]
            if not title or not destination:
                raise ValueError("旅行计划必须包含标题和目的地")
            plans = state.setdefault("travel_plans", {})
            plan_id = str(raw.get("id") or f"travel_{uuid.uuid4().hex}")[:120]
            previous = plans.get(plan_id) if isinstance(plans.get(plan_id), dict) else {}
            now = int(time.time())
            plan = {
                "id": plan_id,
                "title": title,
                "departure": str(raw.get("departure") or "").strip()[:120],
                "destination": destination,
                "days": max(1, min(60, int(raw.get("days") or 1))),
                "travel_style": str(raw.get("travel_style") or "").strip()[:120],
                "scenery_preference": str(raw.get("scenery_preference") or "").strip()[:240],
                "budget": str(raw.get("budget") or "").strip()[:120],
                "extra_notes": str(raw.get("extra_notes") or "").strip()[:1000],
                "markdown_content": str(raw.get("markdown_content") or "")[:100_000],
                "baike_info": raw.get("baike_info") if isinstance(raw.get("baike_info"), dict) else {},
                "created_at": int(previous.get("created_at") or now),
                "updated_at": now,
            }
            plans[plan_id] = plan
            state = await save_workspace(store, workspace_id, state)
            return _response(state, travel_plan=plan, travel_plans=list(state["travel_plans"].values()))

        if operation == "delete_travel_plan":
            plan_id = str(body.get("plan_id") or "")
            if state.setdefault("travel_plans", {}).pop(plan_id, None) is None:
                raise ValueError("旅行计划不存在")
            state = await save_workspace(store, workspace_id, state)
            return _response(state, deleted_plan_id=plan_id, travel_plans=list(state["travel_plans"].values()))

        if operation == "activate_map":
            action = get_action(state, str(body.get("action_id") or ""))
            check_action_version(action, int(body.get("version") or 0))
            if action.get("kind") != "map_recommendation" or action.get("status") not in {"ready", "active"}:
                raise ValueError("该操作不是可用的地图推荐")
            action["status"] = "active"
            action["updated_at"] = int(time.time())
            state["active_map_action_id"] = action["id"]
            state = await save_workspace(store, workspace_id, state)
            return _response(state, action)

        if operation == "deactivate_map":
            state["active_map_action_id"] = ""
            state = await save_workspace(store, workspace_id, state)
            return _response(state)

        if operation == "direct_calendar_changes":
            changes = body.get("changes") or []
            if not isinstance(changes, list) or not changes:
                raise ValueError("缺少日程变更")
            changed = apply_calendar_changes(state, changes)
            state["active_map_action_id"] = ""
            state = await save_workspace(store, workspace_id, state)
            await _record_calendar_signal(store, changed, "direct_calendar_changes", user_id, ctx.env)
            return _response(state, changed=changed)

        if operation == "generate_image":
            prompt = str(body.get("prompt") or "").strip()[:2000]
            if not prompt:
                raise ValueError("生图提示词不能为空")
            parent_id = str(body.get("parent_action_id") or "")
            parent = state.get("actions", {}).get(parent_id)
            references = []
            group_id = ""
            if isinstance(parent, dict) and parent.get("kind") == "image_generate":
                parent_payload = parent.get("payload") or {}
                parent_result = parent.get("result") or {}
                source_url = await resolve_image_reference(parent_result)
                if source_url.startswith(("https://", "data:image/")):
                    references.append(source_url)
                group_id = str(parent_payload.get("group_id") or parent.get("id") or "")
            action = new_action(
                "image_generate",
                {"prompt": prompt, "parent_action_id": parent_id, "group_id": group_id},
                requires_confirmation=False,
            )
            action["payload"]["group_id"] = group_id or action["id"]
            seal_action_snapshot(action)
            now = int(time.time())
            begin_action_execution(action, owner=f"workspace:{action['id']}", now=now)
            put_action(state, action)
            start_provider_call(state, action, now)
            state = await save_workspace(store, workspace_id, state)
            result = await generate_image(ctx.env, prompt, references, user_id=user_id)
            latest = await load_workspace(store, workspace_id)
            action = get_action(latest, action["id"])
            finish_provider_call(latest, action, result, int(time.time()))
            if result.get("ok"):
                action["result"]["versions"] = image_versions(latest, str(action["payload"]["group_id"]))
            latest = await save_workspace(store, workspace_id, latest)
            return _response(latest, action)

        if operation == "cancel_action":
            action = get_action(state, str(body.get("action_id") or ""))
            check_action_version(action, int(body.get("version") or 0))
            if action.get("status") in {"succeeded", "failed", "cancelled"}:
                return _response(state, action)
            action["status"] = "cancelled"
            action["version"] = int(action.get("version") or 1) + 1
            action["updated_at"] = int(time.time())
            state = await save_workspace(store, workspace_id, state)
            return _response(state, action)

        if operation != "confirm_action":
            raise ValueError("不支持的工作区操作")

        action = get_action(state, str(body.get("action_id") or ""))
        check_action_version(action, int(body.get("version") or 0))
        if action.get("status") == "succeeded":
            return _response(state, action)
        if action.get("status") != "awaiting_confirmation":
            raise ValueError("该操作当前不能确认")
        kind = str(action.get("kind") or "")
        payload = action.get("payload") or {}
        verify_action_snapshot(action)
        if kind == "calendar_changes":
            changed = apply_calendar_changes(state, payload.get("changes") or [])
            action["status"] = "succeeded"
            action["result"] = {"changed": changed}
            action["version"] = int(action.get("version") or 1) + 1
            action["updated_at"] = int(time.time())
            state["active_map_action_id"] = ""
            state = await save_workspace(store, workspace_id, state)
            await _record_calendar_signal(store, changed, action["id"], user_id, ctx.env)
            return _response(state, action, changed=changed)

        now = int(time.time())
        begin_action_execution(action, owner=f"workspace:{action['id']}", now=now)
        start_provider_call(state, action, now)
        state = await save_workspace(store, workspace_id, state)
        if kind == "meeting_create":
            result = await create_tencent_meeting(
                ctx.env,
                str(payload.get("subject") or "腾讯会议"),
                str(payload.get("start_time") or ""),
                str(payload.get("end_time") or ""),
            )
        elif kind == "image_generate":
            result = await generate_image(ctx.env, str(payload.get("prompt") or ""), user_id=user_id)
        else:
            raise ValueError("该操作没有可执行 Provider")

        latest = await load_workspace(store, workspace_id)
        action = get_action(latest, action["id"])
        finish_provider_call(latest, action, result, int(time.time()))
        if kind == "image_generate" and result.get("ok"):
            action["result"]["versions"] = image_versions(latest, str(action["payload"].get("group_id") or action["id"]))
        latest = await save_workspace(store, workspace_id, latest)
        return _response(latest, action)
    except Exception as exc:
        return error(str(exc))
