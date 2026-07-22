"""Persistent proactive Event/Run/Notification loop; not an Agent route.

The first production collector is deliberately deterministic: it turns the
user-owned schedule workspace into deduplicated facts and notifications. No
browser session or chat request is required for a scheduled tick.
"""

from __future__ import annotations

import copy
import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .data_version import namespace
from .workspace import USER_WORKSPACE_ID, load_user_workspace, recover_stale_actions, save_user_workspace
from .tencent_location import get_current_weather, plan_verified_route


SCHEMA_VERSION = 1
BEIJING = timezone(timedelta(hours=8))
STATE_KEY = "state"
TERMINAL_RUNS = {"succeeded", "skipped", "failed", "cancelled"}


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def default_preferences() -> dict[str, Any]:
    return {
        "enabled": True,
        "autonomy_mode": "propose",
        "timezone": "Asia/Shanghai",
        "quiet_hours": {"enabled": True, "start": "22:00", "end": "08:00"},
        "daily_limit": 5,
        "lookahead_hours": 24,
        "types": {
            "schedule_conflict": True,
            "tight_transfer": True,
            "schedule_upcoming": True,
            "weather_risk": True,
            "route_risk": True,
            "workflow_step_due": True,
        },
    }


def empty_proactive_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "preferences": default_preferences(),
        "events": {},
        "runs": {},
        "observations": [],
        "notifications": {},
        "workflows": {},
        "checkpoints": {},
        "last_tick": None,
        "tick_lease": None,
    }


def _item_value(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
    return value if isinstance(value, dict) else None


def _merge_preferences(value: Any) -> dict[str, Any]:
    base = default_preferences()
    if not isinstance(value, dict):
        return base
    for key in ("enabled", "autonomy_mode", "timezone", "daily_limit", "lookahead_hours"):
        if key in value:
            base[key] = copy.deepcopy(value[key])
    if isinstance(value.get("quiet_hours"), dict):
        base["quiet_hours"].update(copy.deepcopy(value["quiet_hours"]))
    if isinstance(value.get("types"), dict):
        base["types"].update({str(k): bool(v) for k, v in value["types"].items()})
    base["enabled"] = bool(base["enabled"])
    if base["autonomy_mode"] not in {"observe", "remind", "propose", "low_risk_auto"}:
        base["autonomy_mode"] = "propose"
    base["daily_limit"] = max(0, min(50, int(base["daily_limit"] or 0)))
    base["lookahead_hours"] = max(1, min(168, int(base["lookahead_hours"] or 24)))
    return base


def proactive_namespace(user_id: str = USER_WORKSPACE_ID) -> tuple[str, str]:
    return namespace("proactive", str(user_id or USER_WORKSPACE_ID))


async def load_proactive_state(store: Any, user_id: str = USER_WORKSPACE_ID) -> dict[str, Any]:
    state = empty_proactive_state()
    if store is None:
        return state
    value = _item_value(await store.aget(proactive_namespace(user_id), STATE_KEY))
    if not value:
        return state
    state.update(copy.deepcopy(value))
    state["preferences"] = _merge_preferences(state.get("preferences"))
    for key in ("events", "runs", "notifications", "workflows", "checkpoints"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    if not isinstance(state.get("observations"), list):
        state["observations"] = []
    return state


def _prune(state: dict[str, Any]) -> None:
    for key, limit in (("events", 240), ("runs", 240), ("notifications", 240), ("workflows", 100)):
        values = state.get(key) or {}
        if len(values) <= limit:
            continue
        ordered = sorted(
            values.values(), key=lambda item: float(item.get("updated_at") or item.get("created_at") or 0), reverse=True,
        )
        state[key] = {str(item["id"]): item for item in ordered[:limit]}
    state["observations"] = list(state.get("observations") or [])[-600:]


async def save_proactive_state(
    store: Any, state: dict[str, Any], user_id: str = USER_WORKSPACE_ID,
) -> dict[str, Any]:
    saved = copy.deepcopy(state)
    saved["schema_version"] = SCHEMA_VERSION
    saved["revision"] = int(saved.get("revision") or 0) + 1
    _prune(saved)
    if store is not None:
        await store.aput(proactive_namespace(user_id), STATE_KEY, saved)
    return saved


def _observation(state: dict[str, Any], run_id: str, status: str, step: str, now: int, **payload: Any) -> None:
    state.setdefault("observations", []).append({
        "id": f"obs_{uuid.uuid4().hex}",
        "run_id": run_id,
        "status": status,
        "step": step,
        "payload": payload,
        "created_at": now,
    })


def _schedule_end(item: dict[str, Any]) -> int:
    return int(item.get("start_time") or 0) + max(1, int(item.get("duration_minutes") or 60)) * 60


def collect_schedule_signals(schedules: list[dict[str, Any]], now: int, lookahead_hours: int = 24) -> list[dict[str, Any]]:
    horizon = now + max(1, lookahead_hours) * 3600
    future = sorted(
        [item for item in schedules if now <= int(item.get("start_time") or 0) <= horizon and not item.get("done")],
        key=lambda item: int(item.get("start_time") or 0),
    )
    signals: list[dict[str, Any]] = []
    for index, item in enumerate(future):
        schedule_id = str(item.get("id") or "")
        if not schedule_id:
            continue
        start = int(item.get("start_time") or 0)
        signals.append({
            "type": "schedule_upcoming",
            "dedup_key": f"schedule_upcoming:{schedule_id}:{start}",
            "priority": "normal",
            "subject_ids": [schedule_id],
            "title": "即将开始",
            "detail": f"{item.get('title') or '未命名日程'}将在24小时内开始",
            "action": f"请帮我为即将开始的“{item.get('title') or '日程'}”做准备，检查地点、路线、天气和需要携带的东西",
            "evidence": {"schedule": copy.deepcopy(item)},
            "occurred_at": now,
        })
        if index == 0:
            continue
        previous = future[index - 1]
        previous_end = _schedule_end(previous)
        current_start = int(item.get("start_time") or 0)
        pair = f"{previous.get('id')}:{previous.get('start_time')}:{schedule_id}:{start}"
        if current_start < previous_end:
            signals.append({
                "type": "schedule_conflict",
                "dedup_key": f"schedule_conflict:{pair}",
                "priority": "high",
                "subject_ids": [str(previous.get("id") or ""), schedule_id],
                "title": "发现日程冲突",
                "detail": f"“{previous.get('title') or '上一项日程'}”与“{item.get('title') or '下一项日程'}”时间重叠",
                "action": "请检查我最近的日程冲突，并给出最合适的调整方案",
                "evidence": {"previous": copy.deepcopy(previous), "current": copy.deepcopy(item)},
                "occurred_at": now,
            })
        elif (
            previous.get("location") and item.get("location")
            and str(previous.get("location")) != str(item.get("location"))
            and current_start - previous_end < 30 * 60
        ):
            signals.append({
                "type": "tight_transfer",
                "dedup_key": f"tight_transfer:{pair}",
                "priority": "high",
                "subject_ids": [str(previous.get("id") or ""), schedule_id],
                "title": "行程衔接较紧",
                "detail": f"“{previous.get('title') or '上一项日程'}”后不足30分钟就要前往{item.get('location')}",
                "action": "请检查我最近两项日程之间的真实路线和通勤时间，必要时建议调整",
                "evidence": {"previous": copy.deepcopy(previous), "current": copy.deepcopy(item)},
                "occurred_at": now,
            })
    priority = {"high": 0, "normal": 1, "low": 2}
    return sorted(signals, key=lambda item: (priority.get(str(item.get("priority")), 9), str(item["dedup_key"])))


def _verified_place(schedule: dict[str, Any]) -> dict[str, Any] | None:
    extra = schedule.get("extra") or {}
    place = extra.get("place") if isinstance(extra, dict) else None
    if not isinstance(place, dict):
        return None
    if not str(place.get("place_id") or ""):
        return None
    if not isinstance(place.get("latitude"), (int, float)) or not isinstance(place.get("longitude"), (int, float)):
        return None
    return place


async def collect_provider_signals(
    env: dict[str, Any], schedules: list[dict[str, Any]], now: int, lookahead_hours: int = 24,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collect bounded weather/route risks; provider failures stay observations."""
    horizon = now + max(1, lookahead_hours) * 3600
    future = sorted(
        [item for item in schedules if now <= int(item.get("start_time") or 0) <= horizon and not item.get("done")],
        key=lambda item: int(item.get("start_time") or 0),
    )[:4]
    key = str(env.get("TENCENT_MAP_SERVER_KEY") or env.get("TENCENT_MAP_KEY") or env.get("VITE_TENCENT_MAP_KEY") or "")
    signals: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {
        "weather_checked": 0,
        "routes_checked": 0,
        "weather_facts": [],
        "route_facts": [],
        "errors": [],
    }
    weather_keywords = ("雨", "雪", "雷", "暴", "台风", "大风", "沙尘", "雾", "冰雹", "冻")
    for schedule in future[:3]:
        place = _verified_place(schedule)
        if not place:
            continue
        try:
            weather = await get_current_weather(key, place)
            diagnostics["weather_checked"] += 1
            condition = str(weather.get("weather") or "")
            diagnostics["weather_facts"].append({
                "schedule_id": str(schedule.get("id") or ""),
                "schedule_title": str(schedule.get("title") or ""),
                "place_id": str(place.get("place_id") or ""),
                "condition": condition,
                "temperature": weather.get("temperature"),
                "humidity": weather.get("humidity"),
                "observed_at": now,
            })
            if condition and any(keyword in condition for keyword in weather_keywords):
                schedule_id = str(schedule.get("id") or "")
                start = int(schedule.get("start_time") or 0)
                signals.append({
                    "type": "weather_risk",
                    "dedup_key": f"weather_risk:{schedule_id}:{start}:{condition}",
                    "priority": "high",
                    "subject_ids": [schedule_id],
                    "title": "行程天气需要关注",
                    "detail": f"“{schedule.get('title') or '日程'}”所在地当前天气为{condition}",
                    "action": f"请结合“{schedule.get('title') or '日程'}”的时间和地点，检查天气风险并给出准备建议",
                    "evidence": {"schedule": copy.deepcopy(schedule), "weather": weather},
                    "occurred_at": now,
                })
        except Exception as exc:
            diagnostics["errors"].append({"collector": "weather", "schedule_id": schedule.get("id"), "error": str(exc)[:240]})

    for previous, current in zip(future, future[1:]):
        previous_place = _verified_place(previous)
        current_place = _verified_place(current)
        available = int(current.get("start_time") or 0) - _schedule_end(previous)
        if not previous_place or not current_place or available <= 0 or available > 3 * 3600:
            continue
        try:
            route = await plan_verified_route(key, [previous_place, current_place])
            diagnostics["routes_checked"] += 1
            required = int(route.get("duration_seconds") or 0) + 15 * 60
            diagnostics["route_facts"].append({
                "previous_schedule_id": str(previous.get("id") or ""),
                "current_schedule_id": str(current.get("id") or ""),
                "available_seconds": available,
                "route_duration_seconds": int(route.get("duration_seconds") or 0),
                "distance_meters": float(route.get("distance_meters") or 0),
                "provider": str(route.get("provider") or ""),
                "observed_at": now,
            })
            if required > available:
                pair = f"{previous.get('id')}:{previous.get('start_time')}:{current.get('id')}:{current.get('start_time')}"
                signals.append({
                    "type": "route_risk",
                    "dedup_key": f"route_risk:{pair}",
                    "priority": "high",
                    "subject_ids": [str(previous.get("id") or ""), str(current.get("id") or "")],
                    "title": "真实通勤时间可能不足",
                    "detail": f"两项日程之间有{max(0, available // 60)}分钟，当前路线预计需{max(1, int(route.get('duration_seconds') or 0) // 60)}分钟",
                    "action": "请根据真实路线重新检查这两项日程，并给出调整时间或地点的方案",
                    "evidence": {"previous": copy.deepcopy(previous), "current": copy.deepcopy(current), "route": route},
                    "occurred_at": now,
                })
        except Exception as exc:
            diagnostics["errors"].append({"collector": "route", "schedule_ids": [previous.get("id"), current.get("id")], "error": str(exc)[:240]})
    return signals, diagnostics


def propose_workflow(
    state: dict[str, Any], *, title: str, steps: list[dict[str, Any]], reason: str, now: int,
) -> dict[str, Any]:
    """Create a versioned workflow proposal. Activation always needs confirmation."""
    clean_title = str(title or "").strip()[:120]
    if not clean_title:
        raise ValueError("工作流标题不能为空")
    clean_steps: list[dict[str, Any]] = []
    for index, item in enumerate(steps[:20]):
        if not isinstance(item, dict):
            continue
        step_title = str(item.get("title") or "").strip()[:160]
        if not step_title:
            continue
        raw_compensation = item.get("compensation") if isinstance(item.get("compensation"), dict) else {}
        compensation_title = str(raw_compensation.get("title") or "").strip()[:160]
        compensation = None
        if compensation_title:
            compensation = {
                "title": compensation_title,
                "body": str(raw_compensation.get("body") or "")[:1000],
                "action_prompt": str(raw_compensation.get("action_prompt") or "")[:1000],
            }
        clean_steps.append({
            "id": f"step_{index + 1}",
            "offset_minutes": max(0, min(525_600, int(item.get("offset_minutes") or 0))),
            "title": step_title,
            "body": str(item.get("body") or "")[:1000],
            "action_prompt": str(item.get("action_prompt") or "")[:1000],
            "depends_on": [str(value) for value in (item.get("depends_on") or []) if str(value).strip()][:10],
            "_explicit_depends": "depends_on" in item,
            "status": "pending",
            "attempt": 0,
            "last_error": "",
            "compensation": compensation,
            "due_at": None,
            "emitted_at": None,
            "compensation_emitted_at": None,
        })
    if not clean_steps:
        raise ValueError("工作流至少需要一个有效步骤")
    valid_ids = {step["id"] for step in clean_steps}
    for index, step in enumerate(clean_steps):
        normalized: list[str] = []
        for raw in step["depends_on"]:
            dependency = f"step_{int(raw)}" if raw.isdigit() else raw
            if dependency in valid_ids and dependency != step["id"] and dependency not in normalized:
                normalized.append(dependency)
        # Sequential is the safe default unless the model explicitly supplied dependencies.
        if index > 0 and not normalized and not step.pop("_explicit_depends", False):
            normalized = [clean_steps[index - 1]["id"]]
        else:
            step.pop("_explicit_depends", None)
        step["depends_on"] = normalized
    # A repeated model turn can phrase the same requested workflow with slightly
    # different step bodies or reasons.  While a proposal with the same title is
    # still pending or active, return it instead of creating a second card that
    # the user must reconcile manually.  Completed/rejected/cancelled workflows
    # do not block a later run with the same human-facing title.
    title_identity = " ".join(clean_title.casefold().split())
    for pending in state.setdefault("workflows", {}).values():
        if not isinstance(pending, dict) or pending.get("status") not in {"awaiting_confirmation", "active"}:
            continue
        pending_title = " ".join(str(pending.get("title") or "").casefold().split())
        if pending_title == title_identity:
            return copy.deepcopy(pending)
    canonical = repr((clean_title, [
        (step["offset_minutes"], step["title"], step["body"], step["depends_on"], step.get("compensation"))
        for step in clean_steps
    ]))
    workflow_id = _stable_id("workflow", canonical)
    existing = state["workflows"].get(workflow_id)
    if isinstance(existing, dict) and existing.get("status") in {"awaiting_confirmation", "active"}:
        return copy.deepcopy(existing)
    workflow = {
        "id": workflow_id,
        "title": clean_title,
        "reason": str(reason or "用户希望建立持久工作流")[:500],
        "status": "awaiting_confirmation",
        "version": 1,
        "steps": clean_steps,
        "anchor_at": None,
        "created_at": now,
        "updated_at": now,
    }
    state["workflows"][workflow_id] = workflow
    return copy.deepcopy(workflow)


def decide_workflow(state: dict[str, Any], workflow_id: str, version: int, accept: bool, now: int) -> dict[str, Any]:
    workflow = state.get("workflows", {}).get(workflow_id)
    if not isinstance(workflow, dict) or workflow.get("status") != "awaiting_confirmation":
        raise ValueError("工作流提案不存在或已处理")
    if int(workflow.get("version") or 0) != int(version):
        raise ValueError("工作流版本已变化")
    workflow["status"] = "active" if accept else "rejected"
    workflow["version"] = int(workflow["version"]) + 1
    workflow["updated_at"] = now
    if accept:
        workflow["anchor_at"] = now
        for step in workflow.get("steps") or []:
            step["due_at"] = now + int(step.get("offset_minutes") or 0) * 60
    else:
        _retire_workflow_notifications(state, workflow_id, now)
    return copy.deepcopy(workflow)


def _retire_workflow_notifications(
    state: dict[str, Any], workflow_id: str, now: int, step_id: str | None = None,
) -> None:
    """Hide workflow notifications as soon as their workflow/step is resolved."""
    for notification in state.setdefault("notifications", {}).values():
        if not isinstance(notification, dict) or notification.get("dismissed_at"):
            continue
        evidence = notification.get("evidence") if isinstance(notification.get("evidence"), dict) else {}
        if str(evidence.get("workflow_id") or "") != workflow_id:
            continue
        if step_id is not None and str(evidence.get("step_id") or "") != step_id:
            continue
        notification.update({
            "status": "dismissed",
            "dismissed_at": now,
            "updated_at": now,
            "version": int(notification.get("version") or 1) + 1,
        })


def collect_workflow_signals(state: dict[str, Any], now: int) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for workflow in state.get("workflows", {}).values():
        if workflow.get("status") != "active":
            continue
        step_status = {str(item.get("id")): str(item.get("status")) for item in workflow.get("steps") or []}
        for step in workflow.get("steps") or []:
            if step.get("status") == "failed" and not step.get("compensation_emitted_at"):
                compensation = step.get("compensation") if isinstance(step.get("compensation"), dict) else None
                signals.append({
                    "type": "workflow_compensation_due" if compensation else "workflow_step_failed",
                    "source": "workflow_scheduler",
                    "dedup_key": f"workflow_compensation:{workflow.get('id')}:{step.get('id')}:{step.get('attempt', 0)}",
                    "priority": "high",
                    "subject_ids": [str(workflow.get("id") or ""), str(step.get("id") or "")],
                    "title": str((compensation or {}).get("title") or f"步骤失败：{step.get('title') or workflow.get('title') or '工作流'}"),
                    "detail": str((compensation or {}).get("body") or step.get("last_error") or "需要人工决定重试或终止"),
                    "action": str((compensation or {}).get("action_prompt") or "请帮我核对失败原因并决定下一步"),
                    "evidence": {
                        "workflow_id": workflow.get("id"), "step_id": step.get("id"),
                        "workflow_phase": "compensation" if compensation else "failure",
                    },
                    "occurred_at": now,
                })
                step["status"] = "compensating" if compensation else "attention_required"
                step["compensation_emitted_at"] = now
                continue
            if step.get("status") != "pending" or int(step.get("due_at") or 0) > now:
                continue
            if any(step_status.get(str(dependency)) not in {"completed", "skipped", "compensated"} for dependency in step.get("depends_on") or []):
                continue
            signals.append({
                "type": "workflow_step_due",
                "source": "workflow_scheduler",
                "dedup_key": (
                    f"workflow_step_due:{workflow.get('id')}:{step.get('id')}:"
                    f"{int(step.get('attempt') or 0)}:{step.get('due_at')}"
                ),
                "priority": "normal",
                "subject_ids": [str(workflow.get("id") or ""), str(step.get("id") or "")],
                "title": str(step.get("title") or workflow.get("title") or "工作流提醒"),
                "detail": str(step.get("body") or workflow.get("reason") or "工作流步骤已到期"),
                "action": str(step.get("action_prompt") or "请帮我继续处理这个工作流步骤"),
                "evidence": {"workflow_id": workflow.get("id"), "step_id": step.get("id")},
                "occurred_at": now,
            })
            step["status"] = "notified"
            step["emitted_at"] = now
        if workflow.get("steps") and all(step.get("status") in {"completed", "skipped", "compensated"} for step in workflow["steps"]):
            workflow["status"] = "completed"
            workflow["updated_at"] = now
            _retire_workflow_notifications(state, str(workflow.get("id") or ""), now)
    return signals


def decide_workflow_step(
    state: dict[str, Any], workflow_id: str, step_id: str, operation: str, now: int,
) -> dict[str, Any]:
    workflow = state.get("workflows", {}).get(workflow_id)
    if not isinstance(workflow, dict) or workflow.get("status") != "active":
        raise ValueError("工作流不存在或当前未运行")
    step = next((item for item in workflow.get("steps") or [] if item.get("id") == step_id), None)
    if not isinstance(step, dict):
        raise ValueError("工作流步骤不存在或已处理")
    status = str(step.get("status") or "")
    if operation not in {"complete", "skip", "fail", "retry", "compensate"}:
        raise ValueError("不支持的工作流步骤操作")
    if operation in {"complete", "skip", "fail"} and status not in {"pending", "notified"}:
        raise ValueError("工作流步骤当前不能处理")
    if operation == "retry" and status not in {"failed", "compensating", "attention_required"}:
        raise ValueError("只有失败步骤可以重试")
    if operation == "compensate" and status not in {"failed", "compensating", "attention_required"}:
        raise ValueError("当前步骤不需要补偿")
    if operation == "complete":
        step["status"] = "completed"
        step["resolved_at"] = now
    elif operation == "skip":
        step["status"] = "skipped"
        step["resolved_at"] = now
    elif operation == "fail":
        step["status"] = "failed"
        step["last_error"] = "用户标记步骤失败"
        step["resolved_at"] = now
    elif operation == "retry":
        step.update({
            "status": "pending", "due_at": now, "emitted_at": None, "resolved_at": None,
            "compensation_emitted_at": None, "last_error": "", "attempt": int(step.get("attempt") or 0) + 1,
        })
    else:
        step["status"] = "compensated"
        step["resolved_at"] = now
    _retire_workflow_notifications(state, workflow_id, now, step_id)
    workflow["version"] = int(workflow.get("version") or 1) + 1
    workflow["updated_at"] = now
    if all(item.get("status") in {"completed", "skipped", "compensated"} for item in workflow.get("steps") or []):
        workflow["status"] = "completed"
        _retire_workflow_notifications(state, workflow_id, now)
    return copy.deepcopy(workflow)


def cancel_workflow(state: dict[str, Any], workflow_id: str, version: int, now: int) -> dict[str, Any]:
    workflow = state.get("workflows", {}).get(workflow_id)
    if not isinstance(workflow, dict) or workflow.get("status") not in {"awaiting_confirmation", "active"}:
        raise ValueError("工作流不存在或已结束")
    if int(workflow.get("version") or 0) != int(version):
        raise ValueError("工作流版本已变化")
    workflow.update({"status": "cancelled", "version": int(workflow["version"]) + 1, "updated_at": now})
    _retire_workflow_notifications(state, workflow_id, now)
    return copy.deepcopy(workflow)


def _parse_clock(value: Any, default: tuple[int, int]) -> tuple[int, int]:
    try:
        hour, minute = str(value).split(":", 1)
        parsed = int(hour), int(minute)
        if 0 <= parsed[0] <= 23 and 0 <= parsed[1] <= 59:
            return parsed
    except (TypeError, ValueError):
        pass
    return default


def _quiet_until(preferences: dict[str, Any], now: int) -> int:
    quiet = preferences.get("quiet_hours") or {}
    if not quiet.get("enabled"):
        return 0
    local_now = datetime.fromtimestamp(now, BEIJING)
    start_hour, start_minute = _parse_clock(quiet.get("start"), (22, 0))
    end_hour, end_minute = _parse_clock(quiet.get("end"), (8, 0))
    current = local_now.hour * 60 + local_now.minute
    start = start_hour * 60 + start_minute
    end = end_hour * 60 + end_minute
    in_quiet = start <= current < end if start < end else current >= start or current < end
    if not in_quiet:
        return 0
    end_date = local_now.date()
    if start >= end and current >= start:
        end_date += timedelta(days=1)
    target = datetime.combine(end_date, datetime.min.time(), BEIJING).replace(hour=end_hour, minute=end_minute)
    return int(target.timestamp())


def _created_today(notification: dict[str, Any], now: int) -> bool:
    if notification.get("dismissed_at"):
        return False
    created = int(notification.get("created_at") or 0)
    return datetime.fromtimestamp(created, BEIJING).date() == datetime.fromtimestamp(now, BEIJING).date()


def reconcile_schedule_notifications(
    state: dict[str, Any], signals: list[dict[str, Any]], affected_schedule_ids: set[str], now: int,
) -> dict[str, int]:
    """Refresh or retire notifications whose source schedule was edited/deleted."""
    valid = {str(signal.get("dedup_key") or ""): signal for signal in signals}
    refreshed = superseded = 0
    notifications = state.setdefault("notifications", {})
    for event in state.setdefault("events", {}).values():
        subjects = {str(value) for value in (event.get("subject_ids") or [])}
        if not subjects.intersection(affected_schedule_ids):
            continue
        dedup_key = str(event.get("dedup_key") or "")
        signal = valid.get(dedup_key)
        related = [item for item in notifications.values() if item.get("event_id") == event.get("id")]
        if signal is not None:
            event["payload"] = copy.deepcopy(signal)
            event["updated_at"] = now
            for notification in related:
                if notification.get("dismissed_at"):
                    continue
                notification.update({
                    "title": str(signal.get("title") or "主动提醒"),
                    "body": str(signal.get("detail") or ""),
                    "reason": str(signal.get("detail") or ""),
                    "action_prompt": str(signal.get("action") or ""),
                    "priority": str(signal.get("priority") or "normal"),
                    "evidence": copy.deepcopy(signal.get("evidence") or {}),
                    "updated_at": now,
                    "version": int(notification.get("version") or 1) + 1,
                })
                refreshed += 1
            continue
        for notification in related:
            if notification.get("dismissed_at"):
                continue
            notification.update({
                "status": "superseded",
                "dismissed_at": now,
                "updated_at": now,
                "version": int(notification.get("version") or 1) + 1,
            })
            superseded += 1
    return {"refreshed": refreshed, "superseded": superseded}


def process_schedule_signals(state: dict[str, Any], signals: list[dict[str, Any]], now: int) -> dict[str, int]:
    preferences = _merge_preferences(state.get("preferences"))
    state["preferences"] = preferences
    stats = {"signals": len(signals), "events_created": 0, "runs_created": 0, "notifications_created": 0, "skipped": 0}
    daily_count = sum(1 for item in state.get("notifications", {}).values() if _created_today(item, now))
    for signal in signals:
        dedup_key = str(signal["dedup_key"])
        event_id = _stable_id("evt", dedup_key)
        if event_id in state.setdefault("events", {}):
            stats["skipped"] += 1
            continue
        event = {
            "id": event_id,
            "type": signal["type"],
            "source": str(signal.get("source") or "schedule_collector"),
            "dedup_key": dedup_key,
            "subject_ids": signal.get("subject_ids") or [],
            "payload": copy.deepcopy(signal),
            "occurred_at": int(signal.get("occurred_at") or now),
            "created_at": now,
            "updated_at": now,
        }
        state["events"][event_id] = event
        stats["events_created"] += 1
        run_id = _stable_id("run", event_id)
        run = {
            "id": run_id,
            "event_id": event_id,
            "status": "created",
            "intent": str(signal["type"]),
            "trigger_origin": str(signal.get("source") or "scheduled_collector"),
            "reason": "",
            "created_at": now,
            "updated_at": now,
        }
        state.setdefault("runs", {})[run_id] = run
        stats["runs_created"] += 1
        _observation(state, run_id, "created", "event_ingested", now, event_id=event_id, dedup_key=dedup_key)

        allowed_type = bool((preferences.get("types") or {}).get(str(signal["type"]), True))
        allowed = bool(preferences.get("enabled")) and allowed_type and preferences.get("autonomy_mode") != "observe"
        reason = ""
        if not preferences.get("enabled"):
            reason = "proactive_disabled"
        elif preferences.get("autonomy_mode") == "observe":
            reason = "observe_only"
        elif not allowed_type:
            reason = "notification_type_disabled"
        elif daily_count >= int(preferences.get("daily_limit") or 0):
            allowed = False
            reason = "daily_limit_reached"
        _observation(state, run_id, "policy_checked", "notification_policy", now, allowed=allowed, reason=reason)
        if not allowed:
            run.update({"status": "skipped", "reason": reason, "updated_at": now})
            stats["skipped"] += 1
            continue

        notification_id = _stable_id("ntf", dedup_key)
        snoozed_until = _quiet_until(preferences, now)
        notification = {
            "id": notification_id,
            "event_id": event_id,
            "run_id": run_id,
            "type": str(signal["type"]),
            "title": str(signal.get("title") or "主动提醒"),
            "body": str(signal.get("detail") or ""),
            "reason": str(signal.get("detail") or ""),
            "action_prompt": str(signal.get("action") or ""),
            "priority": str(signal.get("priority") or "normal"),
            "evidence": copy.deepcopy(signal.get("evidence") or {}),
            "status": "snoozed" if snoozed_until else "unread",
            "version": 1,
            "snoozed_until": snoozed_until or None,
            "read_at": None,
            "dismissed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        state.setdefault("notifications", {})[notification_id] = notification
        daily_count += 1
        stats["notifications_created"] += 1
        run.update({"status": "succeeded", "reason": "notification_created", "updated_at": now})
        _observation(state, run_id, "succeeded", "notification_created", now, notification_id=notification_id)
    return stats


def ingest_workspace_signal(
    state: dict[str, Any], *, signal_type: str, dedup_key: str, payload: dict[str, Any], now: int,
) -> tuple[dict[str, Any], bool]:
    allowed = {"file_uploaded", "calendar_changed", "route_changed", "preference_changed"}
    normalized_type = str(signal_type or "")
    if normalized_type not in allowed:
        raise ValueError("不支持的工作区信号类型")
    normalized_key = str(dedup_key or "").strip()
    if not normalized_key:
        raise ValueError("工作区信号缺少去重键")
    event_id = _stable_id("evt", f"{normalized_type}:{normalized_key}")
    existing = state.setdefault("events", {}).get(event_id)
    if isinstance(existing, dict):
        return copy.deepcopy(existing), False
    event = {
        "id": event_id,
        "type": normalized_type,
        "source": "workspace",
        "dedup_key": normalized_key,
        "subject_ids": [],
        "payload": copy.deepcopy(payload),
        "occurred_at": now,
        "created_at": now,
        "updated_at": now,
    }
    state["events"][event_id] = event
    run_id = _stable_id("run", event_id)
    state.setdefault("runs", {})[run_id] = {
        "id": run_id,
        "event_id": event_id,
        "status": "succeeded",
        "intent": normalized_type,
        "trigger_origin": "workspace_change",
        "reason": "signal_persisted",
        "created_at": now,
        "updated_at": now,
    }
    _observation(state, run_id, "succeeded", "workspace_signal_persisted", now, event_id=event_id)
    return copy.deepcopy(event), True


async def run_proactive_tick(
    store: Any, now: int | None = None, env: dict[str, Any] | None = None, user_id: str = USER_WORKSPACE_ID,
) -> tuple[dict[str, Any], dict[str, int]]:
    timestamp = int(now or time.time())
    state = await load_proactive_state(store, user_id)
    last_tick = state.get("last_tick") or {}
    if timestamp - int(last_tick.get("started_at") or 0) < 60:
        return state, {"throttled": 1, "signals": 0, "events_created": 0, "runs_created": 0, "notifications_created": 0, "skipped": 0}
    lease = state.get("tick_lease") or {}
    if int(lease.get("until") or 0) > timestamp:
        return state, {"locked": 1, "signals": 0, "events_created": 0, "runs_created": 0, "notifications_created": 0, "skipped": 0}
    lease_owner = f"tick_{uuid.uuid4().hex}"
    state["tick_lease"] = {"owner": lease_owner, "until": timestamp + 120, "acquired_at": timestamp}
    state = await save_proactive_state(store, state, user_id)
    workspace = await load_user_workspace(store, user_id=user_id)
    recovered_actions = recover_stale_actions(workspace, timestamp)
    if recovered_actions:
        await save_user_workspace(store, workspace, user_id)
    preferences = _merge_preferences(state.get("preferences"))
    schedules = list((workspace.get("schedules") or {}).values())
    signals = collect_schedule_signals(schedules, timestamp, int(preferences["lookahead_hours"]))
    signals.extend(collect_workflow_signals(state, timestamp))
    provider_signals, provider_diagnostics = await collect_provider_signals(
        env or {}, schedules, timestamp, int(preferences["lookahead_hours"]),
    )
    signals.extend(provider_signals)
    stats = process_schedule_signals(state, signals, timestamp)
    for fact in provider_diagnostics.get("weather_facts", []):
        _observation(
            state,
            _stable_id("run", f"weather:{fact.get('schedule_id')}:{timestamp}"),
            "observed",
            "weather_checked",
            timestamp,
            **copy.deepcopy(fact),
        )
    for fact in provider_diagnostics.get("route_facts", []):
        _observation(
            state,
            _stable_id(
                "run",
                f"route:{fact.get('previous_schedule_id')}:{fact.get('current_schedule_id')}:{timestamp}",
            ),
            "observed",
            "route_checked",
            timestamp,
            **copy.deepcopy(fact),
        )
    stats["actions_reconciliation_required"] = len(recovered_actions)
    state["checkpoints"]["schedule_collector"] = {
        "last_scan_at": timestamp,
        "schedule_count": len(schedules),
        "signal_count": len(signals),
        "provider": provider_diagnostics,
    }
    state["last_tick"] = {"started_at": timestamp, "finished_at": int(time.time()), "stats": stats}
    state["tick_lease"] = None
    saved = await save_proactive_state(store, state, user_id)
    return saved, stats


def public_proactive_state(state: dict[str, Any], now: int | None = None) -> dict[str, Any]:
    timestamp = int(now or time.time())
    notifications = sorted(
        [copy.deepcopy(item) for item in state.get("notifications", {}).values() if not item.get("dismissed_at")],
        key=lambda item: (0 if item.get("priority") == "high" else 1, -int(item.get("created_at") or 0)),
    )
    for item in notifications:
        snoozed_until = int(item.get("snoozed_until") or 0)
        if item.get("status") == "snoozed" and snoozed_until <= timestamp:
            item["status"] = "unread"
            item["snoozed_until"] = None
    runs = sorted(state.get("runs", {}).values(), key=lambda item: int(item.get("updated_at") or 0), reverse=True)[:50]
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": int(state.get("revision") or 0),
        "preferences": copy.deepcopy(state.get("preferences") or default_preferences()),
        "notifications": notifications[:100],
        "workflows": copy.deepcopy(sorted(
            state.get("workflows", {}).values(),
            key=lambda item: int(item.get("updated_at") or 0),
            reverse=True,
        )[:100]),
        "runs": copy.deepcopy(runs),
        "checkpoints": copy.deepcopy(state.get("checkpoints") or {}),
        "last_tick": copy.deepcopy(state.get("last_tick")),
    }


def update_preferences(state: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        key: changes[key]
        for key in ("enabled", "autonomy_mode", "timezone", "daily_limit", "lookahead_hours", "quiet_hours", "types")
        if key in changes
    }
    merged = copy.deepcopy(state.get("preferences") or {})
    merged.update(allowed)
    state["preferences"] = _merge_preferences(merged)
    return state["preferences"]


def mutate_notification(state: dict[str, Any], notification_id: str, operation: str, now: int, until: int = 0) -> dict[str, Any]:
    notification = state.get("notifications", {}).get(notification_id)
    if not isinstance(notification, dict):
        raise ValueError("提醒不存在")
    if operation == "mark_read":
        notification["status"] = "read"
        notification["read_at"] = notification.get("read_at") or now
    elif operation == "dismiss":
        notification["status"] = "dismissed"
        notification["dismissed_at"] = now
    elif operation == "snooze":
        target = int(until or now + 3600)
        if target <= now:
            raise ValueError("稍后提醒时间必须晚于当前时间")
        notification["status"] = "snoozed"
        notification["snoozed_until"] = target
    else:
        raise ValueError("不支持的提醒操作")
    notification["version"] = int(notification.get("version") or 1) + 1
    notification["updated_at"] = now
    return copy.deepcopy(notification)
