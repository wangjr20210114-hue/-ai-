"""Owner-only application data reset backed by EdgeOne Makers stores."""

from __future__ import annotations

import hmac
import re

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

    checkpoints_deleted = await _delete_checkpoints(ctx, _conversation_ids(body))
    state_items_deleted = await _delete_application_namespaces(langgraph_store)

    clean_intelligence = empty_intelligence_state()
    clean_intelligence["skill_preferences"] = skills
    await save_intelligence_state(langgraph_store, clean_intelligence, user_id)
    return {
        "ok": True,
        "skills_preserved": skills,
        "checkpoints_deleted": checkpoints_deleted,
        "state_items_deleted": state_items_deleted,
    }
