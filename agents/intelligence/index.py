"""User-controlled memory, feedback, rule, and budget endpoint."""

from __future__ import annotations

from .._shared.intelligence import (
    DEFAULT_MAP_PREFERENCES,
    DEFAULT_SKILL_PREFERENCES,
    confirm_memory,
    decide_rule,
    delete_memory,
    load_intelligence_state,
    public_intelligence_state,
    reject_memory,
    rollback_memory,
    save_intelligence_state,
    normalize_map_preferences,
    configure_skill_connection,
    disconnect_skill_connection,
    public_skill_connections,
    skill_runtime_env,
)
from .._shared.proactive import load_proactive_state, save_proactive_state, update_preferences
from .._shared.auth import require_user
from .._shared.http import error
from .._shared.skill_registry import (
    public_skill_catalog,
    run_preference_hooks,
    skill_manifest,
)


def _public_state(state, env):
    public = public_intelligence_state(state)
    catalog = public_skill_catalog(skill_runtime_env(env, state))
    public["skill_catalog"] = catalog
    public["skill_connections"] = public_skill_connections(state)
    public["providers"] = {
        item["id"]: bool(item["configured"])
        for item in catalog
        if item.get("external")
    }
    return public


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    body = ctx.request.body or {}
    operation = str(body.get("operation") or "get")
    store = ctx.store.langgraph_store
    try:
        state = await load_intelligence_state(store, user_id)
        if operation == "get" or operation == "export":
            return _public_state(state, getattr(ctx, "env", {}) or {})
        if operation == "confirm_memory":
            confirm_memory(state, str(body.get("proposal_id") or ""), int(body.get("version") or 0))
        elif operation == "reject_memory":
            reject_memory(state, str(body.get("proposal_id") or ""), int(body.get("version") or 0))
        elif operation == "delete_memory":
            delete_memory(state, str(body.get("memory_id") or ""))
        elif operation == "rollback_memory":
            rollback_memory(state, str(body.get("memory_id") or ""), int(body.get("target_version") or 0))
        elif operation in {"confirm_rule", "reject_rule"}:
            rule = decide_rule(
                state, str(body.get("rule_id") or ""), int(body.get("version") or 0), operation == "confirm_rule",
            )
            if operation == "confirm_rule" and rule.get("kind") == "disable_notification_type":
                proactive = await load_proactive_state(store, user_id)
                preferences = proactive.get("preferences") or {}
                types = dict(preferences.get("types") or {})
                types[str(rule.get("target") or "")] = False
                update_preferences(proactive, {"types": types})
                await save_proactive_state(store, proactive, user_id)
        elif operation == "update_usage_preferences":
            changes = body.get("preferences") or {}
            current = dict(state.get("usage_preferences") or {})
            if "daily_token_limit" in changes:
                current["daily_token_limit"] = max(0, int(changes["daily_token_limit"]))
            if "monthly_token_limit" in changes:
                current["monthly_token_limit"] = max(0, int(changes["monthly_token_limit"]))
            if changes.get("enforcement") in {"off", "soft", "hard"}:
                current["enforcement"] = changes["enforcement"]
            state["usage_preferences"] = current
        elif operation == "update_memory_preferences":
            state["memory_preferences"] = {
                "enabled": bool((body.get("preferences") or {}).get("enabled", True)),
            }
        elif operation == "update_search_preferences":
            changes = body.get("preferences") or {}
            current = dict(state.get("search_preferences") or {})
            if "result_limit" in changes:
                current["result_limit"] = max(4, min(18, int(changes["result_limit"])))
            if "image_limit" in changes:
                current["image_limit"] = max(0, min(8, int(changes["image_limit"])))
            if "parallel_image_search" in changes:
                current["parallel_image_search"] = bool(changes["parallel_image_search"])
            state["search_preferences"] = current
        elif operation == "update_map_preferences":
            changes = body.get("preferences") or {}
            if not isinstance(changes, dict):
                raise ValueError("地图设置格式无效")
            current = dict(state.get("map_preferences") or DEFAULT_MAP_PREFERENCES)
            current.update(changes)
            state["map_preferences"] = normalize_map_preferences(current)
        elif operation == "update_skill_preferences":
            requested = body.get("preferences") or {}
            if not isinstance(requested, dict):
                raise ValueError("Skills 设置格式无效")
            previous = dict(
                state.get("skill_preferences") or DEFAULT_SKILL_PREFERENCES
            )
            current = dict(previous)
            for skill_id in DEFAULT_SKILL_PREFERENCES:
                manifest = skill_manifest(skill_id)
                if manifest and manifest.locked:
                    current[skill_id] = True
                elif skill_id in requested:
                    current[skill_id] = bool(requested[skill_id])
            # Enabling a Skill is atomic with all hard dependencies declared by
            # its manifest. Disabling a dependency does not destroy a user's
            # preference for dependants; runtime resolution simply withholds
            # those tools until the requirement is enabled again.
            pending = [
                skill_id
                for skill_id, enabled in requested.items()
                if bool(enabled)
            ]
            while pending:
                skill_id = pending.pop()
                manifest = skill_manifest(skill_id)
                if manifest is None:
                    continue
                for dependency in manifest.requires:
                    if not current.get(dependency, False):
                        current[dependency] = True
                        pending.append(dependency)
            state["skill_preferences"] = current
            await run_preference_hooks(
                {
                    "state_store": store,
                    "user_id": user_id,
                    "env": getattr(ctx, "env", {}) or {},
                },
                previous,
                current,
            )
        elif operation == "configure_skill_connection":
            configure_skill_connection(
                state,
                str(body.get("skill_id") or ""),
                str(body.get("token") or ""),
            )
        elif operation == "disconnect_skill_connection":
            disconnect_skill_connection(
                state,
                str(body.get("skill_id") or ""),
            )
        elif operation == "clear_memories":
            state["memories"] = {}
            state["memory_proposals"] = {}
        else:
            raise ValueError("不支持的记忆与反馈操作")
        saved = await save_intelligence_state(store, state, user_id)
        return _public_state(saved, getattr(ctx, "env", {}) or {})
    except Exception as exc:
        return error(str(exc))
