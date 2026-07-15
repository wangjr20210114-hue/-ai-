"""POST /workspace: activate, confirm and cancel frozen workspace actions."""

from __future__ import annotations

import time

from ..shared.side_effects import create_tencent_meeting, generate_image
from ..shared.workspace import (
    active_map_payload,
    apply_calendar_changes,
    check_action_version,
    get_action,
    load_user_workspace,
    load_workspace,
    public_action,
    save_workspace,
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


async def handler(ctx):
    body = ctx.request.body or {}
    operation = str(body.get("operation") or "get")
    conversation_id = ctx.conversation_id
    if not conversation_id:
        return {"error": "makers-conversation-id header is required"}, 400
    store = ctx.store.langgraph_store
    state = await load_user_workspace(store, conversation_id)
    workspace_id = USER_WORKSPACE_ID
    try:
        if operation == "get":
            return _response(state, actions=[public_action(item) for item in state.get("actions", {}).values()])

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
            return _response(state, changed=changed)

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
        if kind == "calendar_changes":
            changed = apply_calendar_changes(state, payload.get("changes") or [])
            action["status"] = "succeeded"
            action["result"] = {"changed": changed}
            action["version"] = int(action.get("version") or 1) + 1
            action["updated_at"] = int(time.time())
            state["active_map_action_id"] = ""
            state = await save_workspace(store, workspace_id, state)
            return _response(state, action, changed=changed)

        action["status"] = "executing"
        action["updated_at"] = int(time.time())
        state = await save_workspace(store, workspace_id, state)
        if kind == "meeting_create":
            result = await create_tencent_meeting(
                ctx.env,
                str(payload.get("subject") or "腾讯会议"),
                str(payload.get("start_time") or ""),
                str(payload.get("end_time") or ""),
            )
        elif kind == "image_generate":
            result = await generate_image(ctx.env, str(payload.get("prompt") or ""))
        else:
            raise ValueError("该操作没有可执行 Provider")

        latest = await load_workspace(store, workspace_id)
        action = get_action(latest, action["id"])
        action["result"] = result
        action["status"] = "succeeded" if result.get("ok") else "failed"
        action["error"] = "" if result.get("ok") else str(result.get("error") or "执行失败")
        action["version"] = int(action.get("version") or 1) + 1
        action["updated_at"] = int(time.time())
        latest = await save_workspace(store, workspace_id, latest)
        return _response(latest, action)
    except Exception as exc:
        return {"error": str(exc)}, 400
