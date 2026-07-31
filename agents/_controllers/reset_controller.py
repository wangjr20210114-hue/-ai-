"""Controller for authenticated tenant-scoped self-service reset."""

from __future__ import annotations

import re

from .._infrastructure.makers.identity import require_user
from .._infrastructure.http import error
from .._application.intelligence.service import (
    DEFAULT_SKILL_PREFERENCES,
    LOCKED_SKILL_IDS,
    empty_intelligence_state,
    load_intelligence_state,
    save_intelligence_state,
)


def _value(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _restore_makers_store_asyncio(store) -> None:
    """Work around the current Makers adapter omitting asyncio in abatch globals."""
    import asyncio

    abatch = getattr(store, "abatch", None)
    function = getattr(abatch, "__func__", abatch)
    globals_map = getattr(function, "__globals__", None)
    if isinstance(globals_map, dict):
        globals_map.setdefault("asyncio", asyncio)


async def _delete_application_namespaces(
    store,
    user_id: str,
    conversation_ids: list[str],
) -> int:
    if store is None:
        return 0
    _restore_makers_store_asyncio(store)
    namespaces: list[tuple[str, ...]] = []
    offset = 0
    while True:
        page = await store.alist_namespaces(limit=100, offset=offset)
        if not page:
            break
        for namespace in page:
            candidate = tuple(str(part) for part in namespace)
            if (
                len(candidate) >= 2
                and candidate[0].startswith("yuanbao_")
                and candidate[1] in {user_id, *conversation_ids}
            ):
                namespaces.append(candidate)
        if len(page) < 100:
            break
        offset += len(page)

    deleted = 0
    for namespace in namespaces:
        while True:
            items = await store.asearch(namespace, limit=100)
            if not items:
                break
            for item in items:
                key = str(_value(item, "key", ""))
                if key:
                    await store.adelete(tuple(_value(item, "namespace", namespace)), key)
            deleted += len(items)
    return deleted


def _conversation_ids(body) -> list[str]:
    values = body.get("conversation_ids") or []
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for value in values[:1000]:
        conversation_id = str(value or "").strip()
        if (
            6 <= len(conversation_id) <= 36
            and re.fullmatch(r"[0-9A-Za-z._-]+", conversation_id)
            and conversation_id not in output
        ):
            output.append(conversation_id)
    return output


async def _delete_checkpoints(ctx, conversation_ids: list[str]) -> int:
    checkpointer = getattr(ctx.store, "langgraph_checkpointer", None)
    if checkpointer is None:
        return 0
    deleted = 0
    for conversation_id in conversation_ids:
        await checkpointer.adelete_thread(conversation_id)
        deleted += 1
    return deleted


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    body = ctx.request.body or {}
    if str(body.get("confirmation") or "") != "DELETE":
        return error("请输入 DELETE 确认删除自己的数据", 403, code="INVALID_CONFIRMATION")

    langgraph_store = ctx.store.langgraph_store
    current = await load_intelligence_state(langgraph_store, user_id)
    skills = {
        skill_id: True if skill_id in LOCKED_SKILL_IDS else bool(
            (current.get("skill_preferences") or {}).get(skill_id, enabled)
        )
        for skill_id, enabled in DEFAULT_SKILL_PREFERENCES.items()
    }

    conversation_ids = _conversation_ids(body)
    checkpoints_deleted = await _delete_checkpoints(ctx, conversation_ids)
    state_items_deleted = await _delete_application_namespaces(
        langgraph_store,
        user_id,
        conversation_ids,
    )

    clean_intelligence = empty_intelligence_state()
    clean_intelligence["skill_preferences"] = skills
    await save_intelligence_state(langgraph_store, clean_intelligence, user_id)
    return {
        "ok": True,
        "skills_preserved": skills,
        "checkpoints_deleted": checkpoints_deleted,
        "state_items_deleted": state_items_deleted,
    }
