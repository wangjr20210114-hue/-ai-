"""Read chat and production UI state from the latest LangGraph checkpoint."""

import json

from ..shared.workspace import active_map_payload, load_user_workspace, public_action


def _value(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return ""


async def handler(ctx):
    conversation_id = ctx.conversation_id
    if not conversation_id:
        return {"error": "makers-conversation-id header is required"}, 400

    config = {"configurable": {"thread_id": conversation_id}}
    checkpoint_tuple = await ctx.store.langgraph_checkpointer.aget_tuple(config)
    workspace = await load_user_workspace(ctx.store.langgraph_store, conversation_id)

    checkpoint = _value(checkpoint_tuple, "checkpoint", {}) or {} if checkpoint_tuple is not None else {}
    channel_values = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
    stored_messages = (
        channel_values.get("messages", []) if isinstance(channel_values, dict) else []
    )

    result = []
    schedules_by_id = {}
    latest_map = []
    latest_map_title = "相关地点"
    pending_actions = []
    pending_search_meta = None
    for index, message in enumerate(stored_messages):
        message_type = str(_value(message, "type", _value(message, "role", "")))
        content = _text(_value(message, "content", ""))
        if message_type == "tool" and content:
            try:
                action = json.loads(content)
            except (TypeError, json.JSONDecodeError):
                action = None
            if isinstance(action, dict) and action.get("ui_action") == "calendar_update":
                for event in action.get("events", []):
                    if isinstance(event, dict) and event.get("id"):
                        schedules_by_id[str(event["id"])] = event
            elif isinstance(action, dict) and action.get("ui_action") == "map_update":
                places = action.get("places", [])
                if isinstance(places, list):
                    latest_map = places
                    latest_map_title = str(action.get("title") or "相关地点")
            elif isinstance(action, dict) and action.get("ui_action") in {
                "map_action", "calendar_action", "side_effect_action",
            }:
                prepared = action.get("action")
                if isinstance(prepared, dict):
                    pending_actions.append(prepared)
            elif isinstance(action, dict) and action.get("ui_action") == "rich_search_results":
                metadata = action.get("search_results")
                if isinstance(metadata, dict):
                    pending_search_meta = metadata
            continue
        role = {
            "human": "user",
            "user": "user",
            "ai": "ai",
            "assistant": "ai",
        }.get(message_type)
        if not role or not content:
            continue
        restored = {
                "id": str(_value(message, "id", "") or f"checkpoint-{index}"),
                "role": role,
                "content": content,
                "ts": index,
            }
        if role == "ai" and pending_actions:
            restored["workspaceActions"] = pending_actions
            pending_actions = []
        if role == "ai" and pending_search_meta:
            restored["searchMeta"] = pending_search_meta
            pending_search_meta = None
        result.append(restored)

    schedules = list(workspace.get("schedules", {}).values())
    active_map = active_map_payload(workspace)
    if not schedules:
        schedules = list(schedules_by_id.values())
    if active_map:
        latest_map = active_map.get("places") or []
        latest_map_title = str(active_map.get("title") or "相关地点")
    return {
        "messages": result,
        "schedules": schedules,
        "map_places": latest_map,
        "map_title": latest_map_title,
        "workspace_revision": int(workspace.get("revision") or 0),
        "workspace_actions": [public_action(item) for item in workspace.get("actions", {}).values()],
    }
