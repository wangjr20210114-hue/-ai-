"""Scheduled and user-controlled proactive runtime endpoint."""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage

from .._shared.proactive import (
    cancel_workflow,
    collect_workflow_signals,
    load_proactive_state,
    decide_workflow,
    decide_workflow_step,
    mutate_notification,
    public_proactive_state,
    run_proactive_tick,
    save_proactive_state,
    update_preferences,
    propose_workflow,
    process_schedule_signals,
)
from .._shared.intelligence import load_intelligence_state, record_feedback, save_intelligence_state
from .._shared.auth import require_user, scoped_conversation_id
from .._shared.http import error
from ..chat._llm import get_model


def _message_text(value) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        ).strip()
    return ""


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    try:
        return getattr(value, name)
    except (AttributeError, KeyError):
        return default


async def _conversation_has_durable_messages(store, conversation_id: str) -> bool:
    """Recheck an empty conversation after the opening LLM call.

    A user can send their first message while the proactive opening is being
    composed.  In that case the user turn wins: do not append an unsolicited
    assistant message behind it or mark the reminder as delivered.
    """
    if not hasattr(store, "get_messages"):
        return False
    try:
        result = await store.get_messages(
            conversation_id=conversation_id, limit=5, order="desc"
        )
    except Exception:
        return False
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        items = result.get("items") or []
    else:
        items = _field(result, "items", [])
    if not isinstance(items, list):
        return False
    for item in items or []:
        role = str(_field(item, "role", _field(item, "type", ""))).lower()
        content = _field(item, "content", "")
        if role in {"user", "human", "assistant", "ai"} and _message_text(content):
            return True
    return False


async def _compose_opening(env, notifications: list[dict]) -> str:
    facts = "\n".join(
        f"- {item.get('title') or '提醒'}：{item.get('body') or ''}；可建议：{item.get('action_prompt') or ''}"
        for item in notifications[:3]
    )
    fallback = "\n".join(
        f"{item.get('title') or '有一项提醒'}：{item.get('body') or ''}"
        for item in notifications[:2]
    )
    try:
        model = get_model(env)
        response = await model.ainvoke([
            SystemMessage(content=(
                "你是元宝的主动服务。把结构化提醒写成一条自然、克制的中文开场消息。"
                "先说最重要的事实，再给一项具体帮助，并询问用户是否希望调整日程、地点、提醒方式或继续处理。"
                "不要提主动模块、扫描、后台、数据库、策略、通知中心或内部实现；不要编造事实；控制在180字内。"
            )),
            HumanMessage(content=f"待提醒事实：\n{facts}"),
        ])
        text = _message_text(response)
        if text:
            return text[:600]
    except Exception:
        pass
    return f"{fallback}\n\n需要我帮你调整时间、地点或提醒方式吗？"[:600]


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    body = ctx.request.body or {}
    operation = str(body.get("operation") or "get")
    store = ctx.store.langgraph_store
    try:
        intelligence_state = await load_intelligence_state(store, user_id)
        proactive_skill_enabled = bool(
            (intelligence_state.get("skill_preferences") or {}).get("proactive-agent", True)
        )
        if not proactive_skill_enabled and operation in {"refresh", "open_conversation", "tick"}:
            disabled_state = await load_proactive_state(store, user_id)
            if (disabled_state.get("preferences") or {}).get("enabled", True):
                update_preferences(disabled_state, {"enabled": False})
                disabled_state = await save_proactive_state(store, disabled_state, user_id)
            return {
                **public_proactive_state(disabled_state),
                "tick_stats": {"disabled_by_skill": True},
                **({"proactive_message": None} if operation == "open_conversation" else {}),
            }
        if operation in {"refresh", "open_conversation"}:
            state, stats = await run_proactive_tick(store, env=ctx.env, user_id=user_id)
            public = public_proactive_state(state)
            if operation == "refresh":
                return {**public, "tick_stats": stats}

            raw_conversation_id = getattr(ctx, "conversation_id", "")
            if not raw_conversation_id:
                return error("makers-conversation-id header is required")
            conversation_id = scoped_conversation_id(ctx, user_id, raw_conversation_id)
            unread = [
                item for item in public.get("notifications", [])
                if item.get("status") == "unread"
            ]
            delivered = state.setdefault("checkpoints", {}).setdefault("conversation_deliveries", {})
            delivered_ids = set(delivered.get(conversation_id) or [])
            selected = [item for item in unread if item.get("id") not in delivered_ids][:3]
            workflows = [
                item for item in public.get("workflows", [])
                if item.get("status") == "awaiting_confirmation" and item.get("id") not in delivered_ids
            ][:2]
            prompts = [*selected, *[{
                "id": item.get("id"),
                "title": f"持续任务建议：{item.get('title') or '未命名任务'}",
                "body": item.get("reason") or "这项持续任务等待你确认",
                "action_prompt": "询问我是否启用、调整步骤或暂不启用",
            } for item in workflows]]
            if not prompts:
                return {**public, "tick_stats": stats, "proactive_message": None}

            content = await _compose_opening(ctx.env, prompts)
            if await _conversation_has_durable_messages(ctx.store, conversation_id):
                return {
                    **public_proactive_state(state),
                    "tick_stats": stats,
                    "proactive_message": None,
                    "opening_suppressed": "conversation_became_active",
                }
            now = int(time.time())
            message_id = await ctx.store.append_message(
                conversation_id=conversation_id,
                role="assistant",
                content=content,
                user_id=user_id,
                metadata={
                    "source": "yuanbao-proactive",
                    "owner_user_id": user_id,
                    "notification_ids": [str(item.get("id") or "") for item in selected],
                    "workflow_ids": [str(item.get("id") or "") for item in workflows],
                },
            )
            delivered[conversation_id] = [str(item.get("id") or "") for item in prompts]
            for item in selected:
                stored = state.get("notifications", {}).get(str(item.get("id") or ""))
                if isinstance(stored, dict):
                    stored.update({"status": "read", "read_at": now, "updated_at": now})
            state = await save_proactive_state(store, state, user_id)
            return {
                **public_proactive_state(state),
                "tick_stats": stats,
                "proactive_message": {
                    "id": str(message_id or f"proactive-{now}"),
                    "role": "ai",
                    "content": content,
                    "ts": now * 1000,
                    "proactive": True,
                },
            }

        if operation == "tick":
            state, stats = await run_proactive_tick(store, env=ctx.env, user_id=user_id)
            return {**public_proactive_state(state), "tick_stats": stats}

        state = await load_proactive_state(store, user_id)
        if operation == "get":
            return public_proactive_state(state)
        if operation == "update_preferences":
            changes = dict(body.get("preferences") or {})
            if not proactive_skill_enabled:
                if changes.get("enabled") is True:
                    raise ValueError("主动式 Agent Skill 已关闭，请先到 Skills 广场开启")
                changes["enabled"] = False
            preferences = update_preferences(state, changes)
            state.setdefault("checkpoints", {})["preference_change"] = {
                "updated_at": int(time.time()),
                "fields": sorted(str(key) for key in changes if key in preferences),
            }
            await save_proactive_state(store, state, user_id)
            refreshed, stats = await run_proactive_tick(
                store, env=ctx.env, user_id=user_id
            )
            return {
                **public_proactive_state(refreshed),
                "preferences": preferences,
                "tick_stats": stats,
            }
        if operation == "propose_workflow":
            if not proactive_skill_enabled:
                raise ValueError("主动式 Agent Skill 已关闭，请先到 Skills 广场开启")
            workflow = propose_workflow(
                state,
                title=str(body.get("title") or ""),
                steps=body.get("steps") if isinstance(body.get("steps"), list) else [],
                reason=str(body.get("reason") or ""),
                now=int(time.time()),
            )
            saved = await save_proactive_state(store, state, user_id)
            return {**public_proactive_state(saved), "workflow": workflow}
        if operation in {"confirm_workflow", "reject_workflow"}:
            workflow = decide_workflow(
                state,
                str(body.get("workflow_id") or ""),
                int(body.get("version") or 0),
                operation == "confirm_workflow",
                int(time.time()),
            )
            saved = await save_proactive_state(store, state, user_id)
            return {**public_proactive_state(saved), "workflow": workflow}
        if operation == "cancel_workflow":
            workflow = cancel_workflow(
                state,
                str(body.get("workflow_id") or ""),
                int(body.get("version") or 0),
                int(time.time()),
            )
            saved = await save_proactive_state(store, state, user_id)
            return {**public_proactive_state(saved), "workflow": workflow}
        if operation in {
            "complete_workflow_step", "skip_workflow_step", "fail_workflow_step",
            "retry_workflow_step", "compensate_workflow_step",
        }:
            now = int(time.time())
            workflow_id = str(body.get("workflow_id") or "")
            step_id = str(body.get("step_id") or "")
            step_operation = {
                "complete_workflow_step": "complete",
                "skip_workflow_step": "skip",
                "fail_workflow_step": "fail",
                "retry_workflow_step": "retry",
                "compensate_workflow_step": "compensate",
            }[operation]
            workflow = decide_workflow_step(state, workflow_id, step_id, step_operation, now)
            if step_operation == "fail":
                process_schedule_signals(state, collect_workflow_signals(state, now), now)
            for notification in state.get("notifications", {}).values():
                evidence = notification.get("evidence") or {}
                if evidence.get("workflow_id") == workflow_id and evidence.get("step_id") == step_id:
                    notification.update({"status": "read", "read_at": now, "updated_at": now})
            saved = await save_proactive_state(store, state, user_id)
            return {**public_proactive_state(saved), "workflow": workflow}
        if operation in {"mark_read", "dismiss", "snooze"}:
            notification_id = str(body.get("notification_id") or "")
            before = state.get("notifications", {}).get(notification_id) or {}
            notification = mutate_notification(
                state,
                notification_id,
                operation,
                int(time.time()),
                int(body.get("until") or 0),
            )
            saved = await save_proactive_state(store, state, user_id)
            intelligence = await load_intelligence_state(store, user_id)
            record_feedback(
                intelligence,
                target_type="notification",
                target_id=notification_id,
                outcome={"mark_read": "accepted", "dismiss": "dismissed", "snooze": "snoozed"}[operation],
                metadata={"notification_type": before.get("type") or ""},
            )
            await save_intelligence_state(store, intelligence, user_id)
            return {**public_proactive_state(saved), "notification": notification}
        raise ValueError("不支持的主动服务操作")
    except Exception as exc:
        return error(str(exc))
