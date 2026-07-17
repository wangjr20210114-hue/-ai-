"""Scheduled and user-controlled proactive runtime endpoint."""

from __future__ import annotations

import time

from .._shared.proactive import (
    cancel_workflow,
    collect_workflow_signals,
    load_proactive_state,
    decide_workflow,
    decide_workflow_step,
    ingest_external_signal,
    mutate_notification,
    public_proactive_state,
    run_proactive_tick,
    save_proactive_state,
    update_preferences,
    propose_workflow,
    process_schedule_signals,
)
from .._shared.intelligence import load_intelligence_state, record_feedback, save_intelligence_state
from .._shared.auth import require_user


async def handler(ctx):
    identity = require_user(ctx, allow_system=True)
    user_id = str(identity["user_id"])
    body = ctx.request.body or {}
    operation = str(body.get("operation") or "get")
    store = ctx.store.langgraph_store
    try:
        if operation == "tick":
            state, stats = await run_proactive_tick(store, env=ctx.env, user_id=user_id)
            return {**public_proactive_state(state), "tick_stats": stats}

        state = await load_proactive_state(store, user_id)
        if operation == "get":
            return public_proactive_state(state)
        if operation == "update_preferences":
            preferences = update_preferences(state, body.get("preferences") or {})
            saved = await save_proactive_state(store, state, user_id)
            return {**public_proactive_state(saved), "preferences": preferences}
        if operation == "ingest_signal":
            signal_type = str(body.get("signal_type") or "")
            if signal_type == "external_webhook" and not identity.get("system"):
                raise ValueError("外部信号只接受已验证的系统连接器")
            event, created = ingest_external_signal(
                state,
                signal_type=signal_type,
                dedup_key=str(body.get("dedup_key") or ""),
                payload=body.get("payload") if isinstance(body.get("payload"), dict) else {},
                now=int(time.time()),
            )
            saved = await save_proactive_state(store, state, user_id)
            return {**public_proactive_state(saved), "event": event, "created": created}
        if operation == "propose_workflow":
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
        return {"error": str(exc)}, 400
