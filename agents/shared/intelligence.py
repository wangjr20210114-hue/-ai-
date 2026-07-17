"""User-controlled long-term memory, feedback, rules, and usage state."""

from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .workspace import USER_WORKSPACE_ID


SCHEMA_VERSION = 1
STATE_KEY = "state"
BEIJING = timezone(timedelta(hours=8))


def empty_intelligence_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "memory_proposals": {},
        "memories": {},
        "feedback": [],
        "rule_proposals": {},
        "usage": [],
        "usage_preferences": {
            "daily_token_limit": 250_000,
            "monthly_token_limit": 3_000_000,
            "enforcement": "soft",
        },
    }


def _value(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


def intelligence_namespace(user_id: str = USER_WORKSPACE_ID) -> tuple[str, str]:
    return ("yuanbao_intelligence_v1", str(user_id or USER_WORKSPACE_ID))


async def load_intelligence_state(store: Any, user_id: str = USER_WORKSPACE_ID) -> dict[str, Any]:
    state = empty_intelligence_state()
    if store is None:
        return state
    stored = _value(await store.aget(intelligence_namespace(user_id), STATE_KEY))
    if not stored:
        return state
    state.update(copy.deepcopy(stored))
    for key in ("memory_proposals", "memories", "rule_proposals"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    for key in ("feedback", "usage"):
        if not isinstance(state.get(key), list):
            state[key] = []
    return state


async def save_intelligence_state(
    store: Any, state: dict[str, Any], user_id: str = USER_WORKSPACE_ID,
) -> dict[str, Any]:
    saved = copy.deepcopy(state)
    saved["schema_version"] = SCHEMA_VERSION
    saved["revision"] = int(saved.get("revision") or 0) + 1
    saved["feedback"] = list(saved.get("feedback") or [])[-500:]
    saved["usage"] = list(saved.get("usage") or [])[-2000:]
    if len(saved.get("memory_proposals", {})) > 300:
        ordered = sorted(saved["memory_proposals"].values(), key=lambda item: int(item.get("updated_at") or 0), reverse=True)[:300]
        saved["memory_proposals"] = {item["id"]: item for item in ordered}
    if store is not None:
        await store.aput(intelligence_namespace(user_id), STATE_KEY, saved)
    return saved


def propose_memory(
    state: dict[str, Any], key: str, value: Any, reason: str, *, sensitivity: str = "normal", source_message_id: str = "",
) -> dict[str, Any]:
    memory_key = str(key or "").strip()[:120]
    if not memory_key:
        raise ValueError("记忆键不能为空")
    sensitivity = sensitivity if sensitivity in {"normal", "sensitive"} else "normal"
    encoded = json.dumps({"key": memory_key, "value": value}, ensure_ascii=False, sort_keys=True, default=str)
    proposal_id = f"memprop_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]}"
    existing = state.setdefault("memory_proposals", {}).get(proposal_id)
    if isinstance(existing, dict) and existing.get("status") == "pending":
        return copy.deepcopy(existing)
    current = next((item for item in state.get("memories", {}).values() if item.get("memory_key") == memory_key), None)
    now = int(time.time())
    proposal = {
        "id": proposal_id,
        "memory_key": memory_key,
        "value": copy.deepcopy(value),
        "reason": str(reason or "用户希望长期保留此信息")[:500],
        "sensitivity": sensitivity,
        "source_message_id": str(source_message_id or ""),
        "expected_memory_version": int(current.get("version") or 0) if isinstance(current, dict) else 0,
        "status": "pending",
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    state["memory_proposals"][proposal_id] = proposal
    return copy.deepcopy(proposal)


def confirm_memory(state: dict[str, Any], proposal_id: str, version: int) -> tuple[dict[str, Any], dict[str, Any]]:
    proposal = state.get("memory_proposals", {}).get(proposal_id)
    if not isinstance(proposal, dict) or proposal.get("status") != "pending":
        raise ValueError("记忆提案不存在或已处理")
    if int(proposal.get("version") or 0) != int(version):
        raise ValueError("记忆提案版本已变化")
    memory_key = str(proposal["memory_key"])
    current = next((item for item in state.get("memories", {}).values() if item.get("memory_key") == memory_key), None)
    actual_version = int(current.get("version") or 0) if isinstance(current, dict) else 0
    if actual_version != int(proposal.get("expected_memory_version") or 0):
        raise ValueError("记忆内容已变化，请重新确认")
    now = int(time.time())
    memory_id = str(current.get("id")) if isinstance(current, dict) else f"memory_{uuid.uuid4().hex}"
    history = copy.deepcopy(current.get("history") or []) if isinstance(current, dict) else []
    if isinstance(current, dict):
        history.append({
            "version": actual_version,
            "value": copy.deepcopy(current.get("value")),
            "sensitivity": current.get("sensitivity") or "normal",
            "source_message_id": current.get("source_message_id") or "",
            "updated_at": int(current.get("updated_at") or now),
        })
    memory = {
        "id": memory_id,
        "memory_key": memory_key,
        "value": copy.deepcopy(proposal.get("value")),
        "confidence": 1.0,
        "sensitivity": proposal.get("sensitivity") or "normal",
        "source_message_id": proposal.get("source_message_id") or "",
        "version": actual_version + 1,
        "history": history[-20:],
        "created_at": int(current.get("created_at") or now) if isinstance(current, dict) else now,
        "updated_at": now,
    }
    state.setdefault("memories", {})[memory_id] = memory
    proposal.update({"status": "confirmed", "version": int(proposal["version"]) + 1, "updated_at": now})
    return copy.deepcopy(proposal), copy.deepcopy(memory)


def reject_memory(state: dict[str, Any], proposal_id: str, version: int) -> dict[str, Any]:
    proposal = state.get("memory_proposals", {}).get(proposal_id)
    if not isinstance(proposal, dict) or proposal.get("status") != "pending":
        raise ValueError("记忆提案不存在或已处理")
    if int(proposal.get("version") or 0) != int(version):
        raise ValueError("记忆提案版本已变化")
    proposal.update({"status": "rejected", "version": int(proposal["version"]) + 1, "updated_at": int(time.time())})
    return copy.deepcopy(proposal)


def delete_memory(state: dict[str, Any], memory_id: str) -> None:
    if state.get("memories", {}).pop(memory_id, None) is None:
        raise ValueError("记忆不存在")


def rollback_memory(state: dict[str, Any], memory_id: str, target_version: int) -> dict[str, Any]:
    memory = state.get("memories", {}).get(memory_id)
    if not isinstance(memory, dict):
        raise ValueError("记忆不存在")
    history = list(memory.get("history") or [])
    target = next((item for item in history if int(item.get("version") or 0) == int(target_version)), None)
    if not isinstance(target, dict):
        raise ValueError("找不到目标记忆版本")
    now = int(time.time())
    history.append({
        "version": int(memory.get("version") or 0),
        "value": copy.deepcopy(memory.get("value")),
        "sensitivity": memory.get("sensitivity") or "normal",
        "source_message_id": memory.get("source_message_id") or "",
        "updated_at": int(memory.get("updated_at") or now),
    })
    memory.update({
        "value": copy.deepcopy(target.get("value")),
        "sensitivity": target.get("sensitivity") or "normal",
        "source_message_id": target.get("source_message_id") or "",
        "version": int(memory.get("version") or 0) + 1,
        "updated_at": now,
        "history": history[-20:],
    })
    return copy.deepcopy(memory)


def record_feedback(
    state: dict[str, Any], *, target_type: str, target_id: str, outcome: str, metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = int(time.time())
    item = {
        "id": f"feedback_{uuid.uuid4().hex}",
        "target_type": str(target_type),
        "target_id": str(target_id),
        "outcome": str(outcome),
        "metadata": copy.deepcopy(metadata or {}),
        "created_at": now,
    }
    state.setdefault("feedback", []).append(item)
    notification_type = str((metadata or {}).get("notification_type") or "")
    if target_type == "notification" and outcome == "dismissed" and notification_type:
        similar = [
            entry for entry in state["feedback"]
            if entry.get("target_type") == "notification"
            and entry.get("outcome") == "dismissed"
            and str((entry.get("metadata") or {}).get("notification_type") or "") == notification_type
        ]
        if len(similar) >= 3:
            rule_id = f"rule_{hashlib.sha256(f'disable:{notification_type}'.encode()).hexdigest()[:24]}"
            if rule_id not in state.setdefault("rule_proposals", {}):
                state["rule_proposals"][rule_id] = {
                    "id": rule_id,
                    "kind": "disable_notification_type",
                    "target": notification_type,
                    "reason": f"你已连续忽略 {len(similar)} 条同类提醒",
                    "status": "pending",
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                }
    return copy.deepcopy(item)


def decide_rule(state: dict[str, Any], rule_id: str, version: int, accept: bool) -> dict[str, Any]:
    rule = state.get("rule_proposals", {}).get(rule_id)
    if not isinstance(rule, dict) or rule.get("status") != "pending":
        raise ValueError("规则提案不存在或已处理")
    if int(rule.get("version") or 0) != int(version):
        raise ValueError("规则提案版本已变化")
    rule.update({"status": "confirmed" if accept else "rejected", "version": int(rule["version"]) + 1, "updated_at": int(time.time())})
    return copy.deepcopy(rule)


def record_usage(state: dict[str, Any], input_tokens: int, output_tokens: int, total_tokens: int, source: str) -> None:
    if max(input_tokens, output_tokens, total_tokens) <= 0:
        return
    state.setdefault("usage", []).append({
        "id": f"usage_{uuid.uuid4().hex}",
        "source": str(source),
        "input_tokens": max(0, int(input_tokens)),
        "output_tokens": max(0, int(output_tokens)),
        "total_tokens": max(0, int(total_tokens or input_tokens + output_tokens)),
        "created_at": int(time.time()),
    })


def usage_summary(state: dict[str, Any], now: int | None = None) -> dict[str, Any]:
    timestamp = int(now or time.time())
    local = datetime.fromtimestamp(timestamp, BEIJING)
    today = local.date()
    month = (local.year, local.month)
    daily = monthly = 0
    for item in state.get("usage", []):
        created = datetime.fromtimestamp(int(item.get("created_at") or 0), BEIJING)
        tokens = int(item.get("total_tokens") or 0)
        if created.date() == today:
            daily += tokens
        if (created.year, created.month) == month:
            monthly += tokens
    preferences = state.get("usage_preferences") or {}
    daily_limit = int(preferences.get("daily_token_limit") or 0)
    monthly_limit = int(preferences.get("monthly_token_limit") or 0)
    return {
        "daily_tokens": daily,
        "monthly_tokens": monthly,
        "preferences": copy.deepcopy(preferences),
        "alerts": {
            "daily": daily_limit > 0 and daily >= daily_limit,
            "monthly": monthly_limit > 0 and monthly >= monthly_limit,
        },
    }


def confirmed_memory_context(state: dict[str, Any], limit: int = 20) -> str:
    memories = [
        item for item in sorted(
            state.get("memories", {}).values(), key=lambda item: int(item.get("updated_at") or 0), reverse=True,
        )
        if item.get("sensitivity") != "sensitive"
    ][:limit]
    if not memories:
        return ""
    return "\n".join(
        f"- {item.get('memory_key')}: {json.dumps(item.get('value'), ensure_ascii=False, default=str)}"
        for item in memories
    )


def public_intelligence_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": int(state.get("revision") or 0),
        "memory_proposals": sorted(state.get("memory_proposals", {}).values(), key=lambda item: int(item.get("updated_at") or 0), reverse=True),
        "memories": sorted(state.get("memories", {}).values(), key=lambda item: int(item.get("updated_at") or 0), reverse=True),
        "rule_proposals": sorted(state.get("rule_proposals", {}).values(), key=lambda item: int(item.get("updated_at") or 0), reverse=True),
        "feedback_count": len(state.get("feedback") or []),
        "usage": usage_summary(state),
    }
