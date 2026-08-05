"""Controller for user memory, preferences, Skill switches, and connections."""

from __future__ import annotations

from .._application.intelligence.service import (
    DEFAULT_MAP_PREFERENCES,
    DEFAULT_SKILL_PREFERENCES,
    confirm_memory,
    decide_rule,
    delete_memory,
    load_intelligence_state,
    reject_memory,
    rollback_memory,
    save_intelligence_state,
    normalize_map_preferences,
    configure_skill_connection,
    disconnect_skill_connection,
    install_user_skill,
    remove_user_skill,
    set_user_skill_enabled,
)
from .._application.proactive.service import load_proactive_state, save_proactive_state, update_preferences
from .._infrastructure.makers.identity import require_user
from .._domain.entitlements.policy import public_entitlements
from .._infrastructure.http import error
from .._application.skills.runtime import run_preference_hooks
from .._application.intelligence.skill_preferences import apply_skill_preference_batch
from .._views.intelligence import public_intelligence_view
from .._application.i18n import normalize_language, text


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    body = ctx.request.body or {}
    response_language = normalize_language(body.get("response_language"))
    operation = str(body.get("operation") or "get")
    store = ctx.store.langgraph_store
    operation_metadata = {}
    try:
        state = await load_intelligence_state(store, user_id)
        if operation == "get" or operation == "export":
            return public_intelligence_view(
                state,
                getattr(ctx, "env", {}) or {},
                identity,
            )
        if operation == "confirm_memory":
            confirm_memory(state, str(body.get("proposal_id") or ""), int(body.get("version") or 0), response_language=response_language)
        elif operation == "reject_memory":
            reject_memory(state, str(body.get("proposal_id") or ""), int(body.get("version") or 0), response_language=response_language)
        elif operation == "delete_memory":
            delete_memory(state, str(body.get("memory_id") or ""), response_language=response_language)
        elif operation == "rollback_memory":
            rollback_memory(state, str(body.get("memory_id") or ""), int(body.get("target_version") or 0), response_language=response_language)
        elif operation in {"confirm_rule", "reject_rule"}:
            rule = decide_rule(
                state, str(body.get("rule_id") or ""), int(body.get("version") or 0), operation == "confirm_rule", response_language=response_language,
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
                raise ValueError(text("settings.map_invalid", response_language))
            current = dict(state.get("map_preferences") or DEFAULT_MAP_PREFERENCES)
            current.update(changes)
            state["map_preferences"] = normalize_map_preferences(current)
        elif operation == "update_skill_preferences":
            requested = body.get("preferences") or {}
            if not isinstance(requested, dict):
                raise ValueError(text("settings.skills_invalid", response_language))
            previous = dict(
                state.get("skill_preferences") or DEFAULT_SKILL_PREFERENCES
            )
            current, preference_results = apply_skill_preference_batch(
                identity,
                previous,
                DEFAULT_SKILL_PREFERENCES,
                requested,
            )
            operation_metadata["skill_preference_results"] = preference_results
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
            if str(identity.get("auth_type") or "guest") == "guest":
                raise ValueError(text("settings.connection_login", response_language))
            configure_skill_connection(
                state,
                str(body.get("skill_id") or ""),
                str(body.get("token") or ""),
                response_language=response_language,
            )
        elif operation == "disconnect_skill_connection":
            if str(identity.get("auth_type") or "guest") == "guest":
                raise ValueError(text("settings.connection_guest", response_language))
            disconnect_skill_connection(
                state,
                str(body.get("skill_id") or ""),
            )
        elif operation in {
            "install_user_skill",
            "set_user_skill_enabled",
            "remove_user_skill",
        }:
            if str(identity.get("auth_type") or "guest") == "guest":
                raise ValueError(text("settings.private_skill_login", response_language))
            if operation == "install_user_skill":
                limits = public_entitlements(identity).get("limits") or {}
                install_user_skill(
                    state,
                    body.get("skill"),
                    limit=int(
                        limits.get("user_skill_uploads")
                        or limits.get("userSkillUploads")
                        or 0
                    ),
                    response_language=response_language,
                )
            elif operation == "set_user_skill_enabled":
                set_user_skill_enabled(
                    state,
                    str(body.get("skill_id") or ""),
                    bool(body.get("enabled")),
                    response_language=response_language,
                )
            else:
                remove_user_skill(
                    state, str(body.get("skill_id") or ""),
                    response_language=response_language,
                )
        elif operation == "clear_memories":
            state["memories"] = {}
            state["memory_proposals"] = {}
        else:
            raise ValueError(text("settings.operation_unsupported", response_language))
        saved = await save_intelligence_state(store, state, user_id)
        public = public_intelligence_view(
            saved,
            getattr(ctx, "env", {}) or {},
            identity,
        )
        return {**public, **operation_metadata}
    except Exception as exc:
        return error(str(exc))
