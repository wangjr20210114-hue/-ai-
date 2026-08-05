"""Application service for user-controlled intelligence state."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ..._infrastructure.makers.data_version import namespace
from ..._infrastructure.makers.identity import required_user_id
from ..i18n import text as copy_text
from ..skills.registry import default_skill_preferences, locked_skill_ids


SCHEMA_VERSION = 2
STATE_KEY = "state"
BEIJING = timezone(timedelta(hours=8))

DEFAULT_SKILL_PREFERENCES = default_skill_preferences()
LOCKED_SKILL_IDS = locked_skill_ids()

MAX_USER_SKILL_INSTRUCTIONS = 12_000
USER_SKILL_SOURCE_TYPES = frozenset({
    "file",
    "folder",
    "package",
    "paste",
    "url",
})

DEFAULT_MAP_PREFERENCES = {
    # Fast/balanced/complete control the provider concurrency and total search
    # budget. Concrete limits remain explicit so users can tune the main
    # latency drivers without exposing provider implementation details.
    "service_mode": "balanced",
    "place_result_limit": 6,
    "route_stop_limit": 8,
    "search_timeout_seconds": 30,
    "preferred_route_mode": "driving",
    "route_strategy": "time_then_cost",
    "near_time_tolerance_minutes": 10,
    "learn_route_preferences": True,
}


def normalize_map_preferences(value: Any) -> dict[str, Any]:
    preferences = value if isinstance(value, dict) else {}
    mode = str(preferences.get("service_mode") or "balanced")
    if mode not in {"fast", "balanced", "complete"}:
        mode = "balanced"
    mode_defaults = {
        "fast": {"place_result_limit": 4, "route_stop_limit": 4, "search_timeout_seconds": 20},
        "balanced": {"place_result_limit": 6, "route_stop_limit": 8, "search_timeout_seconds": 30},
        "complete": {"place_result_limit": 10, "route_stop_limit": 12, "search_timeout_seconds": 55},
    }[mode]

    def bounded_int(key: str, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(maximum, int(preferences.get(key, mode_defaults[key]))))
        except (TypeError, ValueError):
            return int(mode_defaults[key])

    try:
        near_time_tolerance = max(
            0,
            min(
                30,
                int(preferences.get("near_time_tolerance_minutes", 10) or 0),
            ),
        )
    except (TypeError, ValueError):
        near_time_tolerance = 10
    return {
        "service_mode": mode,
        "place_result_limit": bounded_int("place_result_limit", 3, 12),
        "route_stop_limit": bounded_int("route_stop_limit", 2, 12),
        # Keep enough room for the Tencent direction call while guaranteeing
        # the complete map operation remains below the product's 60s ceiling.
        "search_timeout_seconds": bounded_int("search_timeout_seconds", 10, 55),
        "preferred_route_mode": (
            str(preferences.get("preferred_route_mode") or "driving")
            if str(preferences.get("preferred_route_mode") or "driving")
            in {"driving", "transit", "walking", "bicycling"}
            else "driving"
        ),
        "route_strategy": (
            str(preferences.get("route_strategy") or "time_then_cost")
            if str(preferences.get("route_strategy") or "time_then_cost")
            in {"time_then_cost", "least_time", "least_cost"}
            else "time_then_cost"
        ),
        "near_time_tolerance_minutes": near_time_tolerance,
        "learn_route_preferences": bool(
            preferences.get("learn_route_preferences", True)
        ),
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
            "image_limit": 8,
            "parallel_image_search": True,
        },
        "map_preferences": copy.deepcopy(DEFAULT_MAP_PREFERENCES),
        "skill_preferences": copy.deepcopy(DEFAULT_SKILL_PREFERENCES),
        "skill_connections": {},
        "user_skills": {},
    }


def _user_skill_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:36]
    digest = hashlib.sha256(name.casefold().encode("utf-8")).hexdigest()[:10]
    return f"user-{slug or 'skill'}-{digest}"


def _normalize_user_skill_record(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    name = str(value.get("name") or "").strip()[:80]
    instructions = str(value.get("instructions") or "").strip()
    if not name or not instructions:
        return None
    source_type = str(value.get("source_type") or "paste").strip()
    if source_type not in USER_SKILL_SOURCE_TYPES:
        source_type = "paste"
    installed_at = max(0, int(value.get("installed_at") or 0))
    updated_at = max(installed_at, int(value.get("updated_at") or installed_at))
    return {
        "id": _user_skill_id(name),
        "name": name,
        "description": str(value.get("description") or "").strip()[:280],
        "instructions": instructions[:MAX_USER_SKILL_INSTRUCTIONS],
        "source_type": source_type,
        "source_url": str(value.get("source_url") or "").strip()[:1000],
        "enabled": bool(value.get("enabled", True)),
        "installed_at": installed_at,
        "updated_at": updated_at,
        "review_status": "not_submitted",
    }


def normalize_user_skills(value: Any) -> dict[str, dict[str, Any]]:
    source = value if isinstance(value, dict) else {}
    normalized: dict[str, dict[str, Any]] = {}
    for candidate in list(source.values())[:100]:
        record = _normalize_user_skill_record(candidate)
        if record is not None:
            normalized[record["id"]] = record
    return normalized


def install_user_skill(
    state: dict[str, Any],
    payload: Any,
    *,
    limit: int,
    now_ms: int | None = None,
    response_language: object = "zh-CN",
) -> dict[str, Any]:
    """Install a model-only user Skill without accepting executable adapters."""
    if not isinstance(payload, dict):
        raise ValueError(copy_text("user_skill.payload_invalid", response_language))
    timestamp = int(now_ms if now_ms is not None else time.time() * 1000)
    record = _normalize_user_skill_record({
        **payload,
        "installed_at": payload.get("installed_at") or timestamp,
        "updated_at": timestamp,
        "enabled": True,
    })
    if record is None:
        raise ValueError(copy_text("user_skill.content_required", response_language))
    skills = normalize_user_skills(state.get("user_skills"))
    if record["id"] not in skills and len(skills) >= max(0, int(limit)):
        raise ValueError(copy_text("user_skill.limit_reached", response_language))
    previous = skills.get(record["id"])
    if previous:
        record["installed_at"] = int(previous.get("installed_at") or timestamp)
    skills[record["id"]] = record
    state["user_skills"] = skills
    return copy.deepcopy(record)


def set_user_skill_enabled(
    state: dict[str, Any],
    skill_id: str,
    enabled: bool,
    *, response_language: object = "zh-CN",
) -> dict[str, Any]:
    skills = normalize_user_skills(state.get("user_skills"))
    clean_id = str(skill_id or "").strip()
    if clean_id not in skills:
        raise ValueError(copy_text("user_skill.missing", response_language))
    skills[clean_id]["enabled"] = bool(enabled)
    skills[clean_id]["updated_at"] = int(time.time() * 1000)
    state["user_skills"] = skills
    return copy.deepcopy(skills[clean_id])


def remove_user_skill(
    state: dict[str, Any], skill_id: str, *,
    response_language: object = "zh-CN",
) -> None:
    skills = normalize_user_skills(state.get("user_skills"))
    clean_id = str(skill_id or "").strip()
    if clean_id not in skills:
        raise ValueError(copy_text("user_skill.missing", response_language))
    del skills[clean_id]
    state["user_skills"] = skills


def user_skill_prompt_context(state: dict[str, Any]) -> str:
    """Render bounded, lower-trust model-only preferences for answer synthesis."""
    enabled = [
        item
        for item in normalize_user_skills(state.get("user_skills")).values()
        if item.get("enabled")
    ][:20]
    if not enabled:
        return ""
    chunks = []
    remaining = 18_000
    for item in enabled:
        text = str(item.get("instructions") or "").strip()
        chunk = f"[{item['name']}]\n{text}"[:remaining]
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
        if remaining <= 0:
            break
    return "\n\n".join(chunks)


def _value(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


def intelligence_namespace(user_id: str) -> tuple[str, str]:
    return namespace("intelligence", required_user_id(user_id))


async def load_intelligence_state(store: Any, user_id: str = "") -> dict[str, Any]:
    user_id = required_user_id(user_id)
    state = empty_intelligence_state()
    if store is None:
        return state
    stored = _value(await store.aget(intelligence_namespace(user_id), STATE_KEY))
    if not stored:
        return state
    stored_schema_version = int(stored.get("schema_version") or 0)
    state.update(copy.deepcopy(stored))
    state["schema_version"] = SCHEMA_VERSION
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
    image_limit = (
        preferences.get("image_limit")
        if preferences.get("image_limit") is not None
        else 8
    )
    # Version 1 shipped with two images as the implicit default. Migrate only
    # that legacy value once; an explicit choice of two made after this schema
    # upgrade remains untouched.
    if stored_schema_version < 2 and image_limit == 2:
        image_limit = 8
    state["search_preferences"] = {
        "result_limit": max(4, min(18, int(preferences.get("result_limit") or 8))),
        "image_limit": max(0, min(8, int(image_limit))),
        "parallel_image_search": bool(preferences.get("parallel_image_search", True)),
    }
    state["map_preferences"] = normalize_map_preferences(state.get("map_preferences"))
    skill_preferences = state.get("skill_preferences")
    if not isinstance(skill_preferences, dict):
        skill_preferences = {}
    state["skill_preferences"] = {
        skill_id: True if skill_id in LOCKED_SKILL_IDS else bool(
            skill_preferences.get(skill_id, enabled)
        )
        for skill_id, enabled in DEFAULT_SKILL_PREFERENCES.items()
    }
    state["user_skills"] = normalize_user_skills(state.get("user_skills"))
    connections = state.get("skill_connections")
    if not isinstance(connections, dict):
        connections = {}
    now = int(time.time())
    state["skill_connections"] = {
        str(skill_id): {
            "token": str(connection.get("token") or "")[:4096],
            "connected_at": int(connection.get("connected_at") or 0),
            "expires_at": int(connection.get("expires_at") or 0),
        }
        for skill_id, connection in connections.items()
        if (
            isinstance(connection, dict)
            and str(connection.get("token") or "").strip()
            and int(connection.get("expires_at") or 0) > now
        )
    }
    prune_automatic_memories(state)
    return state


def configure_skill_connection(
    state: dict[str, Any],
    skill_id: str,
    token: str,
    *,
    now: int | None = None,
    response_language: object = "zh-CN",
) -> dict[str, int]:
    """Store one manifest-declared personal token without exposing it publicly."""
    from ..skills.registry import skill_manifest

    manifest = skill_manifest(str(skill_id or "").strip())
    credential = dict(manifest.credential) if manifest else {}
    if credential.get("kind") != "token":
        raise ValueError(copy_text("intelligence.skill_connection.unsupported", response_language))
    clean_token = str(token or "").strip()
    if not 16 <= len(clean_token) <= 4096:
        raise ValueError(copy_text("intelligence.skill_connection.invalid_token", response_language))
    timestamp = int(time.time() if now is None else now)
    ttl = int(credential.get("ttl_seconds") or 0)
    connection = {
        "token": clean_token,
        "connected_at": timestamp,
        "expires_at": timestamp + ttl,
    }
    state.setdefault("skill_connections", {})[manifest.id] = connection
    return {
        "connected_at": connection["connected_at"],
        "expires_at": connection["expires_at"],
    }


def disconnect_skill_connection(state: dict[str, Any], skill_id: str) -> None:
    connections = state.setdefault("skill_connections", {})
    if isinstance(connections, dict):
        connections.pop(str(skill_id or "").strip(), None)


def skill_runtime_env(
    env: dict[str, Any] | None,
    state: dict[str, Any],
    *,
    now: int | None = None,
) -> dict[str, Any]:
    """Overlay unexpired user credentials onto one request-local env copy."""
    from ..skills.registry import skill_manifest

    runtime = dict(env or {})
    timestamp = int(time.time() if now is None else now)
    connections = state.get("skill_connections")
    if not isinstance(connections, dict):
        return runtime
    for skill_id, connection in connections.items():
        manifest = skill_manifest(str(skill_id or ""))
        credential = dict(manifest.credential) if manifest else {}
        if (
            credential.get("kind") != "token"
            or not isinstance(connection, dict)
            or int(connection.get("expires_at") or 0) <= timestamp
        ):
            continue
        token = str(connection.get("token") or "").strip()
        env_key = str(credential.get("env_key") or "").strip()
        if token and env_key:
            runtime[env_key] = token
    return runtime


def public_skill_connections(
    state: dict[str, Any],
    *,
    now: int | None = None,
) -> dict[str, dict[str, int | bool]]:
    timestamp = int(time.time() if now is None else now)
    connections = state.get("skill_connections")
    if not isinstance(connections, dict):
        return {}
    return {
        str(skill_id): {
            "configured": bool(
                str(connection.get("token") or "").strip()
                and int(connection.get("expires_at") or 0) > timestamp
            ),
            "connected_at": int(connection.get("connected_at") or 0),
            "expires_at": int(connection.get("expires_at") or 0),
        }
        for skill_id, connection in connections.items()
        if isinstance(connection, dict)
    }


async def save_intelligence_state(
    store: Any, state: dict[str, Any], user_id: str = "",
) -> dict[str, Any]:
    user_id = required_user_id(user_id)
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
    state: dict[str, Any], key: str, value: Any, reason: str, *, sensitivity: str = "normal", source_message_id: str = "", response_language: object = "zh-CN",
) -> dict[str, Any]:
    memory_key = str(key or "").strip()[:120]
    if not memory_key:
        raise ValueError(copy_text("intelligence.memory.key_required", response_language))
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
        "reason": str(reason or copy_text("intelligence.memory.default_reason", response_language))[:500],
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


def confirm_memory(state: dict[str, Any], proposal_id: str, version: int, *, response_language: object = "zh-CN") -> tuple[dict[str, Any], dict[str, Any]]:
    proposal = state.get("memory_proposals", {}).get(proposal_id)
    if not isinstance(proposal, dict) or proposal.get("status") != "pending":
        raise ValueError(copy_text("intelligence.memory.proposal_missing", response_language))
    if int(proposal.get("version") or 0) != int(version):
        raise ValueError(copy_text("intelligence.memory.proposal_version_changed", response_language))
    memory_key = str(proposal["memory_key"])
    current = next((item for item in state.get("memories", {}).values() if item.get("memory_key") == memory_key), None)
    actual_version = int(current.get("version") or 0) if isinstance(current, dict) else 0
    if actual_version != int(proposal.get("expected_memory_version") or 0):
        raise ValueError(copy_text("intelligence.memory.content_changed", response_language))
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


def reject_memory(state: dict[str, Any], proposal_id: str, version: int, *, response_language: object = "zh-CN") -> dict[str, Any]:
    proposal = state.get("memory_proposals", {}).get(proposal_id)
    if not isinstance(proposal, dict) or proposal.get("status") != "pending":
        raise ValueError(copy_text("intelligence.memory.proposal_missing", response_language))
    if int(proposal.get("version") or 0) != int(version):
        raise ValueError(copy_text("intelligence.memory.proposal_version_changed", response_language))
    proposal.update({"status": "rejected", "version": int(proposal["version"]) + 1, "updated_at": int(time.time())})
    return copy.deepcopy(proposal)


def delete_memory(state: dict[str, Any], memory_id: str, *, response_language: object = "zh-CN") -> None:
    if state.get("memories", {}).pop(memory_id, None) is None:
        raise ValueError(copy_text("intelligence.memory.missing", response_language))


def rollback_memory(state: dict[str, Any], memory_id: str, target_version: int, *, response_language: object = "zh-CN") -> dict[str, Any]:
    memory = state.get("memories", {}).get(memory_id)
    if not isinstance(memory, dict):
        raise ValueError(copy_text("intelligence.memory.missing", response_language))
    history = list(memory.get("history") or [])
    target = next((item for item in history if int(item.get("version") or 0) == int(target_version)), None)
    if not isinstance(target, dict):
        raise ValueError(copy_text("intelligence.memory.version_missing", response_language))
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
    state: dict[str, Any], *, target_type: str, target_id: str, outcome: str, metadata: dict[str, Any] | None = None, response_language: object = "zh-CN",
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
                    "reason": copy_text("intelligence.rule.ignored_reason", response_language, count=len(similar)),
                    "status": "pending",
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                }
    return copy.deepcopy(item)


def decide_rule(state: dict[str, Any], rule_id: str, version: int, accept: bool, *, response_language: object = "zh-CN") -> dict[str, Any]:
    rule = state.get("rule_proposals", {}).get(rule_id)
    if not isinstance(rule, dict) or rule.get("status") != "pending":
        raise ValueError(copy_text("intelligence.rule.proposal_missing", response_language))
    if int(rule.get("version") or 0) != int(version):
        raise ValueError(copy_text("intelligence.rule.version_changed", response_language))
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
            source_changed = bool(
                source_message_id
                and str(current.get("source_message_id") or "")
                != str(source_message_id)
            )
            if encoded_new != encoded_old or source_changed:
                history.append({
                    "version": int(current.get("version") or 1),
                    "value": copy.deepcopy(current.get("value")),
                    "sensitivity": "normal",
                    "source": current.get("source") or "automatic",
                    "source_message_id": current.get("source_message_id") or "",
                    "updated_at": int(current.get("updated_at") or timestamp),
                    "confidence": float(current.get("confidence") or 0),
                    "use_count": int(current.get("use_count") or 0),
                    "last_used_at": int(current.get("last_used_at") or 0),
                    "expires_at": int(current.get("expires_at") or 0),
                })
            if encoded_new != encoded_old:
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


def discard_turn_intelligence(
    state: dict[str, Any], source_message_id: str,
) -> int:
    """Rollback automatic memory written by an explicitly stopped turn.

    Stop can race terminal optional work.  Every automatic upsert therefore
    retains the previous snapshot, allowing the stop endpoint and finalizer to
    converge on the same clean state without deleting an older user memory.
    """
    source_id = str(source_message_id or "").strip()
    if not source_id:
        return 0
    changed = 0
    proposals = state.setdefault("memory_proposals", {})
    for proposal_id, proposal in list(proposals.items()):
        if (
            isinstance(proposal, dict)
            and str(proposal.get("source_message_id") or "") == source_id
        ):
            proposals.pop(proposal_id, None)
            changed += 1
    memories = state.setdefault("memories", {})
    for memory_id, memory in list(memories.items()):
        if not isinstance(memory, dict):
            continue
        history = [
            copy.deepcopy(item)
            for item in (memory.get("history") or [])
            if isinstance(item, dict)
        ]
        if str(memory.get("source_message_id") or "") == source_id:
            previous = next((
                item for item in reversed(history)
                if str(item.get("source_message_id") or "") != source_id
            ), None)
            if previous is None:
                memories.pop(memory_id, None)
            else:
                memory.update({
                    "value": copy.deepcopy(previous.get("value")),
                    "sensitivity": previous.get("sensitivity") or "normal",
                    "source": previous.get("source") or "automatic",
                    "source_message_id": str(
                        previous.get("source_message_id") or ""
                    ),
                    "version": int(previous.get("version") or 1),
                    "confidence": float(previous.get("confidence") or 0),
                    "use_count": int(previous.get("use_count") or 0),
                    "last_used_at": int(previous.get("last_used_at") or 0),
                    "expires_at": int(previous.get("expires_at") or 0),
                    "updated_at": int(previous.get("updated_at") or 0),
                    "history": [
                        item for item in history
                        if item is not previous
                        and str(item.get("source_message_id") or "") != source_id
                    ][-20:],
                })
            changed += 1
            continue
        filtered_history = [
            item for item in history
            if str(item.get("source_message_id") or "") != source_id
        ]
        if len(filtered_history) != len(history):
            memory["history"] = filtered_history[-20:]
            changed += 1
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


async def extract_automatic_memory_candidates(model: Any, user_message: str, *, response_language: object = "zh-CN") -> list[dict[str, Any]]:
    """Use semantic extraction; deterministic filters remain the final privacy boundary."""
    prompt = copy_text("model.memory.extract", response_language)
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
            "result_limit": 8, "image_limit": 8, "parallel_image_search": True,
        }),
        "map_preferences": normalize_map_preferences(state.get("map_preferences")),
        "skill_preferences": copy.deepcopy(state.get("skill_preferences") or DEFAULT_SKILL_PREFERENCES),
        "user_skills": sorted(
            normalize_user_skills(state.get("user_skills")).values(),
            key=lambda item: int(item.get("updated_at") or 0),
            reverse=True,
        ),
        "rule_proposals": sorted(state.get("rule_proposals", {}).values(), key=lambda item: int(item.get("updated_at") or 0), reverse=True),
        "feedback_count": len(state.get("feedback") or []),
        "usage": usage_summary(state),
    }
