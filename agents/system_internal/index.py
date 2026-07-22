"""Detailed health state backed by the native Makers LangGraph Store."""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from .._shared.auth import require_user
from .._shared.intelligence import load_intelligence_state, usage_summary
from .._shared.proactive import load_proactive_state
from .._shared.workspace import load_user_workspace


BEIJING = timezone(timedelta(hours=8))


def _expected_tick_after(now: int) -> int:
    current = datetime.fromtimestamp(now, BEIJING)
    today_tick = current.replace(hour=8, minute=0, second=0, microsecond=0)
    expected = today_tick if current >= today_tick + timedelta(hours=2) else today_tick - timedelta(days=1)
    return int(expected.timestamp())


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    now = int(time.time())
    store = ctx.store.langgraph_store
    proactive = await load_proactive_state(store, user_id)
    workspace = await load_user_workspace(store, ctx.conversation_id, user_id)
    intelligence = await load_intelligence_state(store, user_id)
    runs = list((proactive.get("runs") or {}).values())
    notifications = list((proactive.get("notifications") or {}).values())
    actions = list((workspace.get("actions") or {}).values())
    last_tick = proactive.get("last_tick") or {}
    last_finished = int(last_tick.get("finished_at") or 0)
    expected_tick_after = _expected_tick_after(now)
    scheduled_tick_stale = not last_finished or last_finished < expected_tick_after
    reconciliation = sum(1 for action in actions if action.get("status") == "reconciliation_required")
    feedback = list(intelligence.get("feedback") or [])
    notification_feedback = [item for item in feedback if item.get("target_type") == "notification"]
    outcomes = Counter(str(item.get("outcome") or "unknown") for item in notification_feedback)
    evaluated = sum(outcomes.values())
    accepted = int(outcomes.get("accepted") or 0)
    dismissed = int(outcomes.get("dismissed") or 0)
    pending_rules = sum(
        1 for item in (intelligence.get("rule_proposals") or {}).values()
        if item.get("status") == "pending"
    )
    return {
        "status": "degraded" if reconciliation or scheduled_tick_stale else ("ok" if last_finished else "initializing"),
        "time": now,
        "scheduler": {
            "schedule": "0 8 * * *",
            "timezone": "Asia/Shanghai",
            "last_tick": last_tick or None,
            "last_tick_age_seconds": now - last_finished if last_finished else None,
            "expected_tick_after": expected_tick_after,
            "scheduled_tick_stale": scheduled_tick_stale,
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
            "pending_memory_proposals": sum(
                1 for item in (intelligence.get("memory_proposals") or {}).values()
                if item.get("status") == "pending"
            ),
            "pending_rule_proposals": pending_rules,
            "feedback_count": len(feedback),
            "usage": usage_summary(intelligence, now),
        },
        "policy_evaluation": {
            "evaluated_notifications": evaluated,
            "outcomes": dict(outcomes),
            "acceptance_rate": round(accepted / evaluated, 4) if evaluated else None,
            "dismissal_rate": round(dismissed / evaluated, 4) if evaluated else None,
            "pending_rule_proposals": pending_rules,
            "note": "业务策略效果；通用日志、Trace、Token 与平台告警由 Makers/CLS 承担",
        },
        "providers": {
            "model": all(bool(ctx.env.get(key)) for key in ("AI_GATEWAY_API_KEY", "AI_GATEWAY_BASE_URL")),
            "model_fallback": bool(ctx.env.get("DEEPSEEK_API_KEY")),
            "search": bool(ctx.env.get("WSA_API_KEY")),
            "vision": bool(
                ctx.env.get("HUNYUAN_VISION_API_KEY") or ctx.env.get("HUNYUAN_IMAGE_API_KEY")
                or (ctx.env.get("CLOUDFLARE_ACCOUNT_ID") and (
                    ctx.env.get("CLOUDFLARE_WORKERS_AI_TOKEN") or ctx.env.get("CLOUDFLARE_API_TOKEN")
                ))
            ),
            "map": bool(ctx.env.get("TENCENT_MAP_SERVER_KEY") or ctx.env.get("TENCENT_MAP_KEY")),
            "meeting": bool(ctx.env.get("TENCENT_MEETING_TOKEN")),
        },
        "identity": {
            "mode": "single_user",
            "user_id": user_id,
            "roles": identity.get("roles") or [],
        },
    }
