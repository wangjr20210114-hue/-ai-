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
    ingest_workspace_signal,
)
from .._shared.opportunities import (
    detect_generated_image_opportunity,
    file_opportunity_signal,
    opportunity_signal,
)
from .._shared.intelligence import (
    confirmed_memory_context,
    load_intelligence_state,
    record_feedback,
    save_intelligence_state,
)
from .._shared.proactive_memory import infer_memory_reminder
from .._shared.auth import require_user, scoped_conversation_id
from .._shared.http import error
from .._shared.tencent_location import get_current_weather
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


async def _run_tick_with_memory(
    ctx,
    store,
    user_id: str,
    intelligence_state: dict,
    *,
    memory_only: bool = False,
):
    """Use Makers state as the source of truth for the 10-minute memory scan."""
    now = int(time.time())
    current = await load_proactive_state(store, user_id)
    checkpoint = (current.get("checkpoints") or {}).get("memory_window_scan") or {}
    memory_due = now - int(checkpoint.get("checked_at") or 0) >= 10 * 60
    memory_signals: list[dict] = []
    if memory_due and confirmed_memory_context(intelligence_state, limit=1):
        location = (current.get("checkpoints") or {}).get("location_context") or {}
        if int(location.get("expires_at") or 0) <= now:
            location = {}
        public = public_proactive_state(current, now)
        existing = [
            f"{item.get('title') or ''}：{item.get('body') or ''}"
            for item in public.get("notifications", [])
        ]
        candidate = await infer_memory_reminder(
            get_model(ctx.env),
            intelligence_state,
            location_context=location,
            existing_reminders=existing,
            now=now,
            timeout_seconds=float(ctx.env.get("PROACTIVE_MEMORY_TIMEOUT_SECONDS") or 6),
        )
        if candidate:
            memory_signals.append(candidate)
    return await run_proactive_tick(
        store,
        env=ctx.env,
        user_id=user_id,
        memory_signals=memory_signals,
        memory_checked=memory_due,
        collect_scheduled=not memory_only,
    )


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
        if not proactive_skill_enabled and operation in {"refresh", "memory_refresh", "open_conversation", "tick"}:
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
            state, stats = await _run_tick_with_memory(
                ctx, store, user_id, intelligence_state,
            )
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
            state, stats = await _run_tick_with_memory(
                ctx, store, user_id, intelligence_state,
            )
            return {**public_proactive_state(state), "tick_stats": stats}
        if operation == "memory_refresh":
            state, stats = await _run_tick_with_memory(
                ctx, store, user_id, intelligence_state, memory_only=True,
            )
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
            refreshed, stats = await _run_tick_with_memory(
                ctx, store, user_id, intelligence_state,
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
        if operation == "ingest_signal":
            if not proactive_skill_enabled:
                raise ValueError("主动式 Agent Skill 已关闭，请先到 Skills 广场开启")
            signal_type = str(body.get("signal_type") or "")
            dedup_key = str(body.get("dedup_key") or "").strip()
            payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
            now = int(time.time())
            persisted_payload = payload
            if signal_type == "image_generated":
                # The prompt is needed only for this semantic judgment. Keep
                # URLs, Blob keys and the full prompt out of durable proactive
                # events; the original user request already belongs to the
                # Makers conversation history.
                persisted_payload = {
                    "action_id": str(payload.get("action_id") or "")[:120],
                    "has_reference_image": bool(payload.get("has_reference_image")),
                    "has_previous_version": bool(payload.get("has_previous_version")),
                }
            elif signal_type == "browser_location_weather":
                # The browser calls this only after the user has granted
                # geolocation permission. Coordinates are used transiently to
                # resolve city-level weather and are never stored in the event.
                persisted_payload = {
                    "source": "browser_permission",
                    "precision": "city",
                }
            _event, created = ingest_workspace_signal(
                state,
                signal_type=signal_type,
                dedup_key=dedup_key,
                payload=persisted_payload,
                now=now,
            )
            stats = {"signals": 0, "events_created": 0, "runs_created": 0, "notifications_created": 0, "skipped": 0}
            if created and signal_type == "file_uploaded":
                stats = process_schedule_signals(
                    state,
                    [file_opportunity_signal(payload, dedup_key=dedup_key, now=now)],
                    now,
                )
            elif created and signal_type == "image_generated":
                try:
                    opportunity = await detect_generated_image_opportunity(
                        get_model(ctx.env),
                        payload,
                        timeout_seconds=float(ctx.env.get("OPPORTUNITY_PLAN_TIMEOUT_SECONDS") or 6),
                    )
                except Exception:
                    opportunity = None
                if opportunity:
                    stats = process_schedule_signals(
                        state,
                        [opportunity_signal(
                            opportunity,
                            source_id=str(payload.get("action_id") or dedup_key),
                            now=now,
                        )],
                        now,
                    )
            elif signal_type == "browser_location_weather":
                try:
                    latitude = float(payload.get("latitude"))
                    longitude = float(payload.get("longitude"))
                    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                        raise ValueError("定位坐标超出有效范围")
                    key = str(
                        ctx.env.get("TENCENT_MAP_SERVER_KEY")
                        or ctx.env.get("TENCENT_MAP_KEY")
                        or ctx.env.get("VITE_TENCENT_MAP_KEY")
                        or ""
                    )
                    weather = await get_current_weather(
                        key,
                        {"latitude": latitude, "longitude": longitude},
                    )
                    state.setdefault("checkpoints", {})["location_context"] = {
                        key: weather.get(key)
                        for key in (
                            "city", "district", "weather", "temperature",
                            "wind_direction", "wind_power", "humidity",
                            "precipitation", "observed_at",
                        )
                        if weather.get(key) not in (None, "")
                    }
                    state["checkpoints"]["location_context"].update({
                        "precision": "city",
                        "observed_at": now,
                        "expires_at": now + 6 * 3600,
                    })
                    condition = str(weather.get("weather") or "")
                    weather_keywords = ("雨", "雪", "雷", "暴", "台风", "大风", "沙尘", "雾", "冰雹", "冻")
                    if condition and any(keyword in condition for keyword in weather_keywords):
                        place_name = "".join(
                            part for part in (
                                str(weather.get("city") or ""),
                                str(weather.get("district") or ""),
                            ) if part
                        ) or "当前位置"
                        signal = {
                            "type": "weather_risk",
                            "dedup_key": f"browser_weather_risk:{weather.get('adcode')}:{dedup_key}:{condition}",
                            "priority": "normal",
                            "subject_ids": [],
                            "title": "当前位置天气需要关注",
                            "detail": f"{place_name}当前天气为{condition}，出门前可以提前准备",
                            "action": "请结合当前位置天气和我今天的日程，给出简洁的出行准备建议",
                            "evidence": {
                                "weather": {
                                    key: weather.get(key)
                                    for key in (
                                        "provider", "adcode", "city", "district", "weather",
                                        "temperature", "wind_direction", "wind_power", "humidity",
                                        "precipitation", "observed_at",
                                    )
                                },
                                "location_precision": "city",
                            },
                            "occurred_at": now,
                            "expires_at": now + 12 * 3600,
                        }
                        stats = process_schedule_signals(state, [signal], now)
                except Exception:
                    # A location/weather provider failure must not interrupt
                    # map rendering or the normal proactive refresh path.
                    pass
            saved = await save_proactive_state(store, state, user_id)
            return {**public_proactive_state(saved), "signal_created": created, "tick_stats": stats}
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
