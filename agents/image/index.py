"""POST /image: keep long image edits alive with an SSE heartbeat."""
from __future__ import annotations

import asyncio
import time

from .._shared.side_effects import generate_image, resolve_image_reference
from .._shared.auth import require_user, scoped_conversation_id
from .._shared.http import error
from .._shared.intelligence import load_intelligence_state
from .._shared.workspace import (
    USER_WORKSPACE_ID,
    begin_action_execution,
    finish_provider_call,
    get_action,
    image_versions,
    load_user_workspace,
    new_action,
    public_action,
    put_action,
    save_workspace,
    seal_action_snapshot,
    start_provider_call,
)


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    conversation_id = scoped_conversation_id(ctx, user_id)
    body = ctx.request.body or {}
    prompt = str(body.get("prompt") or "").strip()[:2000]
    parent_id = str(body.get("parent_action_id") or "").strip()
    if not prompt or not parent_id:
        return error("修改提示词和原图版本不能为空")

    store = ctx.store.langgraph_store
    intelligence = await load_intelligence_state(store, user_id)
    if not (intelligence.get("skill_preferences") or {}).get("image-studio", True):
        return error("图片工坊 Skill 已关闭，请先到 Skills 广场开启", 403, code="SKILL_DISABLED")
    state = await load_user_workspace(store, conversation_id, user_id)
    parent = get_action(state, parent_id)
    if parent.get("kind") != "image_generate" or parent.get("status") != "succeeded":
        return error("原图版本不可用于修改")
    parent_payload = parent.get("payload") or {}
    parent_result = parent.get("result") or {}
    reference = await resolve_image_reference(parent_result)
    if not reference.startswith(("https://", "data:image/")):
        return error("无法读取原图，请重新生成后再修改")

    group_id = str(parent_payload.get("group_id") or parent.get("id") or "")
    action = new_action(
        "image_generate",
        {"prompt": prompt, "parent_action_id": parent_id, "group_id": group_id},
        requires_confirmation=False,
    )
    action["payload"]["group_id"] = group_id or action["id"]
    seal_action_snapshot(action)
    now = int(time.time())
    begin_action_execution(action, owner=f"image:{action['id']}", now=now)
    put_action(state, action)
    start_provider_call(state, action, now)
    await save_workspace(store, user_id, state)

    async def gen():
        yield ctx.utils.sse({"type": "image_progress", "stage": "preparing"})
        task = asyncio.create_task(generate_image(ctx.env, prompt, [reference], user_id=user_id))
        while not task.done():
            done, _pending = await asyncio.wait({task}, timeout=5)
            if not done:
                yield ctx.utils.sse({"type": "ping", "ts": int(time.time() * 1000)})
        result = await task
        if not result.get("ok") and parent_result.get("storage_key"):
            blob_reference = await resolve_image_reference(parent_result, prefer_blob=True)
            if blob_reference.startswith("data:image/") and blob_reference != reference:
                yield ctx.utils.sse({"type": "image_progress", "stage": "retrying_blob"})
                retry = asyncio.create_task(generate_image(ctx.env, prompt, [blob_reference], user_id=user_id))
                while not retry.done():
                    done, _pending = await asyncio.wait({retry}, timeout=5)
                    if not done:
                        yield ctx.utils.sse({"type": "ping", "ts": int(time.time() * 1000)})
                result = await retry

        latest = await load_user_workspace(store, conversation_id, user_id)
        current = get_action(latest, action["id"])
        finish_provider_call(latest, current, result, int(time.time()))
        if result.get("ok"):
            current["result"]["versions"] = image_versions(latest, str(current["payload"]["group_id"]))
        await save_workspace(store, user_id, latest)
        yield ctx.utils.sse({"type": "image_action", "action": public_action(current)})
        yield b"data: [DONE]\n\n"

    return ctx.utils.stream_sse(gen())
