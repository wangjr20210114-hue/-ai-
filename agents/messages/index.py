"""Read chat and production UI state from the latest LangGraph checkpoint."""

import json
import logging

from .._shared.workspace import active_map_payload, image_versions, load_user_workspace, public_action
from .._shared.auth import require_user, scoped_conversation_id
from .._shared.data_version import namespace as data_namespace
from .._shared.http import error
from .._shared.makers_conversation import public_chat_run, read_chat_run
from ..chat._protocol import action_fallback_content, public_content


def _value(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    try:
        return getattr(item, key, default)
    except (AttributeError, KeyError, TypeError):
        # Makers checkpoint message proxies may expose fields through
        # ``__getattr__`` and raise KeyError for an absent optional field.
        # Treat that exactly like a normal missing attribute.
        return default


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


def _action_ids(message: dict) -> set[str]:
    return {
        str(action.get("id") or "")
        for action in (message.get("workspaceActions") or [])
        if isinstance(action, dict) and str(action.get("id") or "")
    }


def _coalesce_action_messages(messages: list[dict]) -> list[dict]:
    """Keep one user-visible row for one durable Workspace Action.

    Makers checkpoints can contain both the provider's final prose and a safe
    action-only fallback when their writes race.  They describe the same
    operation when they carry the same Action ID and must render as one row.
    """
    output: list[dict] = []
    owner_by_action: dict[str, int] = {}
    for message in messages:
        action_ids = _action_ids(message)
        owner = next((owner_by_action[action_id] for action_id in action_ids if action_id in owner_by_action), None)
        if owner is None:
            output.append(message)
            index = len(output) - 1
            for action_id in action_ids:
                owner_by_action[action_id] = index
            continue
        existing = output[owner]
        existing_actions = existing.get("workspaceActions") or []
        incoming_actions = message.get("workspaceActions") or []
        actions = []
        seen = set()
        for action in [*existing_actions, *incoming_actions]:
            action_id = str(action.get("id") or "") if isinstance(action, dict) else ""
            if not action_id or action_id in seen:
                continue
            seen.add(action_id)
            actions.append(action)
            owner_by_action[action_id] = owner
        existing_fallback = str(existing.get("content") or "").strip() == action_fallback_content(existing_actions).strip()
        incoming_fallback = str(message.get("content") or "").strip() == action_fallback_content(incoming_actions).strip()
        if existing_fallback != incoming_fallback:
            richer = message if existing_fallback else existing
        else:
            richer = message if len(str(message.get("content") or "").strip()) > len(str(existing.get("content") or "").strip()) else existing
        merged = {**existing, **richer, "id": existing.get("id"), "ts": existing.get("ts"), "workspaceActions": actions}
        for key in ("searchResults", "papers", "followUps"):
            merged[key] = richer.get(key) or existing.get(key) or message.get(key)
            if not merged[key]:
                merged.pop(key, None)
        output[owner] = merged
    return output


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    raw_conversation_id = ctx.conversation_id
    if not raw_conversation_id:
        return error("makers-conversation-id header is required")
    conversation_id = scoped_conversation_id(ctx, user_id, raw_conversation_id)

    config = {"configurable": {"thread_id": conversation_id}}
    checkpoint_tuple = await ctx.store.langgraph_checkpointer.aget_tuple(config)
    workspace = await load_user_workspace(ctx.store.langgraph_store, conversation_id, user_id)
    run = await read_chat_run(ctx.store, conversation_id)
    latest_extras = None
    if ctx.store.langgraph_store is not None:
        item = await ctx.store.langgraph_store.aget(
            data_namespace("message_meta", conversation_id), "latest_extras"
        )
        latest_extras = _value(item, "value", None)

    checkpoint = _value(checkpoint_tuple, "checkpoint", {}) or {} if checkpoint_tuple is not None else {}
    channel_values = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
    stored_messages = (
        channel_values.get("messages", []) if isinstance(channel_values, dict) else []
    )
    if not stored_messages and hasattr(ctx.store, "get_messages"):
        # A legacy import is written through the native Conversation Store.
        # Until the next chat turn seeds a LangGraph checkpoint, render that
        # platform-owned history directly instead of creating a second store.
        try:
            imported = await ctx.store.get_messages(
                conversation_id=conversation_id, limit=100, order="asc"
            )
            stored_messages = imported if isinstance(imported, list) else _value(imported, "items", [])
        except KeyError as exc:
            # Ignore the known incompatible Node generic-store envelope. The
            # next successful turn creates a proper LangGraph checkpoint.
            logging.warning(
                "ignored incompatible conversation message conversation=%s field=%s",
                conversation_id,
                exc,
            )
            stored_messages = []

    result = []
    schedules_by_id = {}
    latest_map = []
    latest_map_title = "相关地点"
    pending_actions = []
    pending_search_meta = None
    pending_papers = None
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
                    # The checkpoint stores the action snapshot produced during
                    # the chat turn. Image edits happen later through Workspace,
                    # so that snapshot can say 1/1 forever even though the
                    # persisted group has more versions. Rehydrate from the
                    # current Makers Store while preserving the checkpoint as a
                    # fallback for legacy or already-cleaned actions.
                    action_id = str(prepared.get("id") or "")
                    current = (workspace.get("actions") or {}).get(action_id)
                    hydrated = public_action(current) if isinstance(current, dict) else prepared
                    if hydrated.get("kind") == "image_generate":
                        payload = hydrated.get("payload") or {}
                        group_id = str(payload.get("group_id") or hydrated.get("id") or "")
                        versions = image_versions(workspace, group_id)
                        if versions:
                            hydrated = {
                                **hydrated,
                                "result": {**(hydrated.get("result") or {}), "versions": versions},
                            }
                    pending_actions.append(hydrated)
            elif isinstance(action, dict) and action.get("ui_action") == "rich_search_results":
                metadata = action.get("search_results")
                if isinstance(metadata, dict):
                    pending_search_meta = metadata
                papers = action.get("papers")
                if isinstance(papers, list) and papers:
                    pending_papers = papers
            elif isinstance(action, dict) and action.get("ui_action") == "paper_results":
                papers = action.get("papers")
                if isinstance(papers, list):
                    pending_papers = papers
            continue
        role = {
            "human": "user",
            "user": "user",
            "ai": "ai",
            "assistant": "ai",
        }.get(message_type)
        if role == "ai":
            # AI nodes carrying tool_calls are internal planning/transport
            # messages. Their optional prose is never a user-visible answer.
            if _value(message, "tool_calls", None):
                continue
            content = public_content(content)
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
            restored["searchResults"] = pending_search_meta
            pending_search_meta = None
        if role == "ai" and pending_papers:
            restored["papers"] = pending_papers
            pending_papers = None
        result.append(restored)

    if pending_actions:
        result.append({
            "id": f"checkpoint-action-{len(result)}",
            "role": "ai",
            "content": action_fallback_content(pending_actions),
            "ts": len(result),
            "workspaceActions": pending_actions,
        })

    # Older builds persisted the user prompt before the Agent call, so several
    # failed attempts could appear as consecutive user-only rows after a later
    # recovery succeeded. Keep the final prompt in each unanswered run without
    # deleting the underlying Makers checkpoint.
    compacted = []
    for restored in result:
        if restored.get("role") == "user" and compacted and compacted[-1].get("role") == "user":
            compacted[-1] = restored
        else:
            compacted.append(restored)
    result = _coalesce_action_messages(compacted)

    if result and isinstance(latest_extras, dict):
        for restored in reversed(result):
            if restored.get("role") != "ai":
                continue
            if restored.get("content", "").strip() == str(latest_extras.get("original_content") or "").strip():
                enriched_content = str(latest_extras.get("content") or "").strip()
                if enriched_content:
                    restored["content"] = enriched_content
                follow_ups = latest_extras.get("follow_ups")
                if isinstance(follow_ups, list) and follow_ups:
                    restored["followUps"] = [str(item) for item in follow_ups[:3]]
                search_results = latest_extras.get("search_results")
                if isinstance(search_results, dict):
                    restored["searchResults"] = search_results
            break

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
        "run": public_chat_run(run),
    }
