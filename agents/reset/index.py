"""Owner-only application data reset backed by EdgeOne Makers stores."""

from __future__ import annotations

import hmac

from .._shared.auth import require_user
from .._shared.http import error
from .._shared.intelligence import (
    DEFAULT_SKILL_PREFERENCES,
    empty_intelligence_state,
    load_intelligence_state,
    save_intelligence_state,
)


def _value(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


async def _gather(*operations):
    # Import inside the callable so the Makers route packager keeps the stdlib
    # dependency in the generated route module.
    import asyncio as asyncio_runtime
    return await asyncio_runtime.gather(*operations)


async def _delete_application_namespaces(store) -> int:
    if store is None:
        return 0
    namespaces: list[tuple[str, ...]] = []
    offset = 0
    while True:
        page = await store.alist_namespaces(limit=100, offset=offset)
        if not page:
            break
        namespaces.extend(
            tuple(str(part) for part in namespace)
            for namespace in page
            if namespace and str(namespace[0]).startswith("yuanbao_")
        )
        if len(page) < 100:
            break
        offset += len(page)

    async def delete_namespace(namespace: tuple[str, ...]) -> int:
        deleted = 0
        while True:
            items = await store.asearch(namespace, limit=100)
            if not items:
                break
            await _gather(*(
                store.adelete(tuple(_value(item, "namespace", namespace)), str(_value(item, "key", "")))
                for item in items
                if str(_value(item, "key", ""))
            ))
            deleted += len(items)
        return deleted

    counts = await _gather(*(delete_namespace(namespace) for namespace in namespaces))
    return sum(counts)


async def _delete_conversation(ctx, conversation_id: str) -> None:
    operations = [ctx.store.delete_conversation(conversation_id)]
    if getattr(ctx.store, "langgraph_checkpointer", None) is not None:
        operations.append(ctx.store.langgraph_checkpointer.adelete_thread(conversation_id))
    await _gather(*operations)


async def _delete_conversations(ctx, user_id: str) -> int:
    deleted = 0
    for _ in range(100):
        result = await ctx.store.list_conversations(
            user_id=user_id,
            limit=100,
            order="desc",
        )
        items = list(_value(result, "items", []) or [])
        if not items:
            break
        conversation_ids = [
            str(_value(item, "conversation_id", "") or _value(item, "conversationId", ""))
            for item in items
        ]
        conversation_ids = [conversation_id for conversation_id in conversation_ids if conversation_id]
        for offset in range(0, len(conversation_ids), 8):
            batch = conversation_ids[offset:offset + 8]
            await _gather(*(
                _delete_conversation(ctx, conversation_id)
                for conversation_id in batch
            ))
            deleted += len(batch)
    return deleted


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    body = ctx.request.body or {}
    supplied = str(body.get("password") or "")
    configured = str((getattr(ctx, "env", {}) or {}).get("DATA_CLEAR_PASSWORD") or "")
    if not configured:
        return error("数据清理功能暂不可用", 503, code="RESET_NOT_CONFIGURED")
    if not supplied or not hmac.compare_digest(supplied, configured):
        return error("密码不正确", 403, code="INVALID_PASSWORD")

    langgraph_store = ctx.store.langgraph_store
    current = await load_intelligence_state(langgraph_store, user_id)
    skills = {
        skill_id: True if skill_id == "core" else bool(
            (current.get("skill_preferences") or {}).get(skill_id, enabled)
        )
        for skill_id, enabled in DEFAULT_SKILL_PREFERENCES.items()
    }

    conversations_deleted, state_items_deleted = await _gather(
        _delete_conversations(ctx, user_id),
        _delete_application_namespaces(langgraph_store),
    )

    clean_intelligence = empty_intelligence_state()
    clean_intelligence["skill_preferences"] = skills
    await save_intelligence_state(langgraph_store, clean_intelligence, user_id)
    return {
        "ok": True,
        "skills_preserved": skills,
        "conversations_deleted": conversations_deleted,
        "state_items_deleted": state_items_deleted,
    }
