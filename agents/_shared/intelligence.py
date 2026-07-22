"""User-controlled memory, feedback, rules, and usage state; not a route."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .data_version import namespace
from .workspace import USER_WORKSPACE_ID


SCHEMA_VERSION = 1
STATE_KEY = "state"
BEIJING = timezone(timedelta(hours=8))

DEFAULT_SKILL_PREFERENCES = {
    "core": True,
    "web-search": True,
    "vision": True,
    "image-studio": True,
    "maps": True,
    "calendar": True,
    "proactive-agent": True,
    "paper-reading": True,
    "tencent-meeting": True,
}


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
        "memory_preferences": {"enabled": True},
        "search_preferences": {
            "result_limit": 8,
            "image_limit": 2,
            "parallel_image_search": True,
        },
        "skill_preferences": copy.deepcopy(DEFAULT_SKILL_PREFERENCES),
    }


def _value(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


def intelligence_namespace(user_id: str = USER_WORKSPACE_ID) -> tuple[str, str]:
    return namespace("intelligence", str(user_id or USER_WORKSPACE_ID))


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
    if not isinstance(state.get("memory_preferences"), dict):
        state["memory_preferences"] = {"enabled": True}
    else:
        state["memory_preferences"]["enabled"] = bool(state["memory_preferences"].get("enabled", True))
    preferences = state.get("search_preferences")
    if not isinstance(preferences, dict):
        preferences = {}
    state["search_preferences"] = {
        "result_limit": max(4, min(18, int(preferences.get("result_limit") or 8))),
        "image_limit": max(0, min(4, int(preferences.get("image_limit") if preferences.get("image_limit") is not None else 2))),
        "parallel_image_search": bool(preferences.get("parallel_image_search", True)),
    }
    skill_preferences = state.get("skill_preferences")
    if not isinstance(skill_preferences, dict):
        skill_preferences = {}
    state["skill_preferences"] = {
        skill_id: True if skill_id == "core" else bool(skill_preferences.get(skill_id, enabled))
        for skill_id, enabled in DEFAULT_SKILL_PREFERENCES.items()
    }
    prune_automatic_memories(state)
    return state


async def save_intelligence_state(
    store: Any, state: dict[str, Any], user_id: str = USER_WORKSPACE_ID,
) -> dict[str, Any]:
    saved = copy.deepcopy(state)
    saved["schema_version"] = SCHEMA_VERSION
    saved["revision"] = int(saved.get("revision") or 0) + 1
    saved["feedback"] = list(saved.get("feedback") or [])[-500:]
    saved["usage"] = list(saved.get("usage") or [])[-2000:]
    prune_automatic_memories(saved)
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
    now = int(time.time())
    memories = [
        item for item in sorted(
            state.get("memories", {}).values(), key=lambda item: int(item.get("updated_at") or 0), reverse=True,
        )
        if item.get("sensitivity") != "sensitive"
        and (not int(item.get("expires_at") or 0) or int(item.get("expires_at") or 0) > now)
        and _safe_memory(str(item.get("memory_key") or ""), item.get("value"))
    ][:limit]
    if not memories:
        return ""
    return "\n".join(
        f"- {item.get('memory_key')}: {json.dumps(item.get('value'), ensure_ascii=False, default=str)}"
        for item in memories
    )


SENSITIVE_KEY_RE = re.compile(
    r"password|passwd|secret|token|api.?key|credential|身份证|证件|护照|银行卡|信用卡|"
    r"手机号|电话|邮箱|住址|详细地址|病历|疾病|诊断|药物|过敏|财务|收入|账户",
    re.I,
)
SENSITIVE_VALUE_RES = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{15}(?:\d{2}[0-9Xx])?(?!\d)"),
    re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?:password|passwd|secret|token|api.?key|密码|口令|密钥)\s*[:：=]", re.I),
)


def _safe_memory(key: str, value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, default=str)[:4000]
    if not key.strip() or not text.strip() or SENSITIVE_KEY_RE.search(key) or SENSITIVE_KEY_RE.search(text):
        return False
    return not any(pattern.search(text) for pattern in SENSITIVE_VALUE_RES)


def safe_non_sensitive_text(value: Any, *, max_chars: int = 4000) -> bool:
    """Conservative reusable guard for automatically surfaced text."""
    text = str(value or "")[:max(1, min(20_000, int(max_chars)))]
    return bool(text.strip()) and _safe_memory("content", text)


def prune_automatic_memories(state: dict[str, Any], now: int | None = None) -> int:
    """Remove expired, sensitive, low-confidence, and stale low-value memories."""
    timestamp = int(now or time.time())
    removed = 0
    for memory_id, item in list(state.setdefault("memories", {}).items()):
        confidence = float(item.get("confidence") or 0)
        expires_at = int(item.get("expires_at") or 0)
        updated_at = int(item.get("updated_at") or item.get("created_at") or 0)
        low_value_stale = confidence < 0.65 and int(item.get("use_count") or 0) <= 1 and timestamp - updated_at > 90 * 86_400
        if (
            item.get("sensitivity") == "sensitive"
            or not _safe_memory(str(item.get("memory_key") or ""), item.get("value"))
            or (expires_at and expires_at <= timestamp)
            or low_value_stale
        ):
            state["memories"].pop(memory_id, None)
            removed += 1
    return removed


def apply_automatic_memory_candidates(
    state: dict[str, Any], candidates: list[dict[str, Any]], source_message_id: str = "", now: int | None = None,
) -> int:
    """Upsert model-extracted non-sensitive stable memories without a confirmation UI."""
    if not bool((state.get("memory_preferences") or {}).get("enabled", True)):
        return 0
    timestamp = int(now or time.time())
    changed = 0
    for candidate in candidates[:3]:
        if not isinstance(candidate, dict):
            continue
        key = str(candidate.get("key") or candidate.get("memory_key") or "").strip()[:120]
        value = candidate.get("value")
        try:
            confidence = max(0.0, min(1.0, float(candidate.get("confidence") or 0)))
            ttl_days = max(30, min(365, int(candidate.get("ttl_days") or 180)))
        except (TypeError, ValueError):
            continue
        if confidence < 0.7 or not _safe_memory(key, value):
            continue
        current = next((item for item in state.get("memories", {}).values() if item.get("memory_key") == key), None)
        encoded_new = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        encoded_old = json.dumps((current or {}).get("value"), ensure_ascii=False, sort_keys=True, default=str)
        if isinstance(current, dict):
            history = list(current.get("history") or [])
            if encoded_new != encoded_old:
                history.append({
                    "version": int(current.get("version") or 1),
                    "value": copy.deepcopy(current.get("value")),
                    "sensitivity": "normal",
                    "source_message_id": current.get("source_message_id") or "",
                    "updated_at": int(current.get("updated_at") or timestamp),
                })
                current["value"] = copy.deepcopy(value)
                current["version"] = int(current.get("version") or 1) + 1
            current.update({
                "confidence": max(float(current.get("confidence") or 0), confidence),
                "sensitivity": "normal",
                "source": "automatic",
                "source_message_id": str(source_message_id or ""),
                "history": history[-20:],
                "use_count": int(current.get("use_count") or 0) + 1,
                "last_used_at": timestamp,
                "expires_at": timestamp + ttl_days * 86_400,
                "updated_at": timestamp,
            })
        else:
            memory_id = f"memory_{uuid.uuid4().hex}"
            state.setdefault("memories", {})[memory_id] = {
                "id": memory_id,
                "memory_key": key,
                "value": copy.deepcopy(value),
                "confidence": confidence,
                "sensitivity": "normal",
                "source": "automatic",
                "source_message_id": str(source_message_id or ""),
                "version": 1,
                "history": [],
                "use_count": 1,
                "last_used_at": timestamp,
                "expires_at": timestamp + ttl_days * 86_400,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        changed += 1
    prune_automatic_memories(state, timestamp)
    return changed


def _memory_candidates(content: Any) -> list[dict[str, Any]]:
    text = content if isinstance(content, str) else str(content or "")
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return []
    values = payload.get("memories") if isinstance(payload, dict) else []
    return values if isinstance(values, list) else []


async def extract_automatic_memory_candidates(model: Any, user_message: str) -> list[dict[str, Any]]:
    """Use semantic extraction; deterministic filters remain the final privacy boundary."""
    prompt = """你是后台记忆筛选器，只从用户自己的话提取值得跨会话保留的非敏感稳定信息，不回答用户。
可保留：长期偏好、长期目标、反复习惯、稳定项目背景、用户明确陈述且非敏感的事实。
必须丢弃：一次性任务参数、临时时间地点、寒暄、普通问题、搜索词、模型推断、第三方信息，以及密码/令牌/密钥/账号/联系方式/证件/精确地址/财务/健康医疗等敏感信息。
如果没有合格内容返回 {"memories":[]}。否则最多 3 项，每项为 {"key":"稳定的语义键","value":"简洁事实","confidence":0到1,"ttl_days":30到365}。只有置信度至少 0.7 的内容才输出。只输出 JSON。"""
    try:
        response = await model.ainvoke([
            {"role": "system", "content": prompt},
            {"role": "user", "content": str(user_message or "")[:4000]},
        ])
    except Exception:
        return []
    return _memory_candidates(getattr(response, "content", ""))


def public_intelligence_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": int(state.get("revision") or 0),
        # Memory content is intentionally private implementation state. The UI
        # only receives a count and controls, never the stored values.
        "memory_proposals": [],
        "memories": [],
        "memory_count": len(state.get("memories", {})),
        "memory_preferences": copy.deepcopy(state.get("memory_preferences") or {"enabled": True}),
        "search_preferences": copy.deepcopy(state.get("search_preferences") or {
            "result_limit": 8, "image_limit": 2, "parallel_image_search": True,
        }),
        "skill_preferences": copy.deepcopy(state.get("skill_preferences") or DEFAULT_SKILL_PREFERENCES),
        "rule_proposals": sorted(state.get("rule_proposals", {}).values(), key=lambda item: int(item.get("updated_at") or 0), reverse=True),
        "feedback_count": len(state.get("feedback") or []),
        "usage": usage_summary(state),
    }
