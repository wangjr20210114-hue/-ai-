"""Read-only health view for the Makers proactive runtime."""

from __future__ import annotations

import time
from collections import Counter

from ..shared.intelligence import load_intelligence_state, usage_summary
from ..shared.proactive import load_proactive_state
from ..shared.workspace import load_user_workspace
from ..shared.auth import require_user


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    now = int(time.time())
    proactive = await load_proactive_state(ctx.store.langgraph_store, user_id)
    workspace = await load_user_workspace(ctx.store.langgraph_store, ctx.conversation_id, user_id)
    intelligence = await load_intelligence_state(ctx.store.langgraph_store, user_id)
    runs = list((proactive.get("runs") or {}).values())
    notifications = list((proactive.get("notifications") or {}).values())
    actions = list((workspace.get("actions") or {}).values())
    last_tick = proactive.get("last_tick") or {}
    last_finished = int(last_tick.get("finished_at") or 0)
    tick_age = now - last_finished if last_finished else None
    reconciliation = sum(1 for action in actions if action.get("status") == "reconciliation_required")
    feedback = list(intelligence.get("feedback") or [])
    notification_feedback = [item for item in feedback if item.get("target_type") == "notification"]
    outcomes = Counter(str(item.get("outcome") or "unknown") for item in notification_feedback)
    evaluated = sum(outcomes.values())
    accepted = int(outcomes.get("accepted") or 0)
    dismissed = int(outcomes.get("dismissed") or 0)
    policy_quality = {
        "evaluated_notifications": evaluated,
        "outcomes": dict(outcomes),
        "acceptance_rate": round(accepted / evaluated, 4) if evaluated else None,
        "dismissal_rate": round(dismissed / evaluated, 4) if evaluated else None,
        "pending_rule_proposals": sum(
            1 for item in (intelligence.get("rule_proposals") or {}).values() if item.get("status") == "pending"
        ),
        "note": "业务策略效果；通用日志、Trace、Token 与平台告警由 Makers/CLS 承担",
    }
    if reconciliation:
        status = "degraded"
    elif last_finished and tick_age is not None and tick_age > 2 * 3600:
        status = "degraded"
    elif not last_finished:
        status = "initializing"
    else:
        status = "ok"
    return {
        "status": status,
        "time": now,
        "scheduler": {
            "schedule": "0 * * * *",
            "timezone": "Asia/Shanghai",
            "last_tick": last_tick or None,
            "last_tick_age_seconds": tick_age,
            "lease": proactive.get("tick_lease"),
        },
        "runtime": {
            "revision": int(proactive.get("revision") or 0),
            "run_statuses": dict(Counter(str(item.get("status") or "unknown") for item in runs)),
            "notification_statuses": dict(Counter(str(item.get("status") or "unknown") for item in notifications)),
            "checkpoints": proactive.get("checkpoints") or {},
        },
        "actions": {
            "count": len(actions),
            "statuses": dict(Counter(str(item.get("status") or "unknown") for item in actions)),
            "reconciliation_required": reconciliation,
            "provider_ledger_count": len(workspace.get("provider_calls") or {}),
        },
        "intelligence": {
            "confirmed_memories": len(intelligence.get("memories") or {}),
            "pending_memory_proposals": sum(1 for item in (intelligence.get("memory_proposals") or {}).values() if item.get("status") == "pending"),
            "pending_rule_proposals": sum(1 for item in (intelligence.get("rule_proposals") or {}).values() if item.get("status") == "pending"),
            "feedback_count": len(intelligence.get("feedback") or []),
            "usage": usage_summary(intelligence, now),
        },
        "policy_evaluation": policy_quality,
        "providers": {
            "model": bool(ctx.env.get("AI_GATEWAY_API_KEY") or ctx.env.get("HUNYUAN_API_KEY")),
            "search": bool(ctx.env.get("WSA_API_KEY")),
            "vision": bool(ctx.env.get("HUNYUAN_VISION_API_KEY") or ctx.env.get("HUNYUAN_IMAGE_API_KEY")),
            "map": bool(ctx.env.get("TENCENT_MAP_SERVER_KEY") or ctx.env.get("TENCENT_MAP_KEY")),
            "meeting_bridge": bool(ctx.env.get("MEETING_BRIDGE_URL") and ctx.env.get("MEETING_BRIDGE_TOKEN")),
        },
        "identity": {
            "mode": "multi_user" if str(ctx.env.get("AUTH_MODE") or "single_user") == "multi_user" else "single_user",
            "user_id": user_id,
            "roles": identity.get("roles") or [],
            "multi_user_ready": bool(str(ctx.env.get("AUTH_MODE") or "single_user") == "multi_user"),
        },
    }
