"""Trusted calendar proposal operation backed by Makers user state."""

from __future__ import annotations

import asyncio
import copy
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from ..._application.workspace.service import (
    apply_calendar_changes,
    calendar_change_warnings,
    new_action,
    put_action,
    validate_calendar_change_window,
)
from ..._infrastructure.makers.route_repository import load_route_cache, save_route_cache
from .route_resolution import (
    _clarification_action,
    _normalized_place_name,
    _parse_datetime,
    _place_choice_field,
    _place_option_label,
    _place_resolution_with_provider_review,
)


def build_calendar_operation(
    *,
    _load_state,
    _plan_route_metered,
    _save_state,
    _search_places_metered,
    browser_current_location,
    conversation_id,
    enabled_skills,
    map_search_timeout,
    place_disambiguation_model,
    place_skill_id,
    planned_reuse_latest_route,
    provider_place_review_enabled,
    provider_schedule_limit,
    requested_route_plan_id,
    route_gap_hours,
    runtime_env,
    store,
    travel_buffer_minutes,
    user_id,
):
    async def propose_calendar_changes(
        summary: str,
        changes: list[dict] | None = None,
        source_route_plan_id: str = "",
        route_start_time: str = "",
        route_stop_minutes: int = 90,
    ) -> str:
        """Prepare create/update/delete changes; the calendar is mutated only after UI confirmation."""
        state = await _load_state()
        changes = changes if isinstance(changes, list) else []
        candidates = state.get("place_candidates", {})
        latest_route = state.get("latest_route_plan")
        route_plans = state.get("route_plans", {})
        route_source_id = str(
            requested_route_plan_id or source_route_plan_id or ""
        ).strip()
        if not route_source_id and planned_reuse_latest_route and isinstance(latest_route, dict):
            route_source_id = str(latest_route.get("id") or "").strip()
        if not route_source_id and isinstance(latest_route, dict):
            # Infer the route link before normalizing event durations. This
            # lets the adapter safely represent an instantaneous verified
            # departure/arrival marker even if the model omitted only the
            # redundant source id. Identity still comes exclusively from the
            # recent provider-backed route and submitted place ids.
            route_age = int(time.time()) - int(latest_route.get("created_at") or 0)
            route_place_ids = {
                str(item.get("place_id") or "")
                for item in (latest_route.get("ordered_stops") or [])
                if isinstance(item, dict) and str(item.get("place_id") or "")
            }
            submitted_place_ids = set()
            for raw_change in changes:
                if not isinstance(raw_change, dict):
                    continue
                raw_event = (
                    raw_change.get("event")
                    if isinstance(raw_change.get("event"), dict)
                    else raw_change
                )
                raw_place_id = str(
                    raw_event.get("place_id")
                    or raw_event.get("location_place_id")
                    or ""
                ).strip()
                if raw_place_id:
                    submitted_place_ids.add(raw_place_id)
            if (
                0 <= route_age <= 10_800
                and len(route_place_ids & submitted_place_ids) >= 2
            ):
                route_source_id = str(latest_route.get("id") or "")
        linked_route = (
            route_plans.get(route_source_id)
            if route_source_id and isinstance(route_plans, dict)
            else None
        )
        if (
            not isinstance(linked_route, dict)
            and route_source_id
            and isinstance(latest_route, dict)
            and route_source_id == str(latest_route.get("id") or "")
        ):
            # Workspaces created before route history was introduced still
            # expose one valid route through latest_route_plan.
            linked_route = latest_route
        linked_calendar_stops = [
            stop
            for stop in (
                (linked_route.get("ordered_stops") or [])
                if isinstance(linked_route, dict)
                else []
            )
            if isinstance(stop, dict) and str(stop.get("place_id") or "")
        ]
        if (
            isinstance(linked_route, dict)
            and linked_route.get("implicit_browser_origin")
            and linked_calendar_stops
        ):
            linked_calendar_stops = linked_calendar_stops[1:]
        # The route continuation is a trusted adapter boundary. When the UI
        # carries the route id, do not make the model copy every stop and
        # schedule timestamp back into a fragile tool call. Ask only for the
        # missing user-owned timing choices, then derive the ordered proposal
        # from the provider-verified route below.
        route_continuation = bool(
            isinstance(linked_route, dict)
            and route_source_id
            and (planned_reuse_latest_route or requested_route_plan_id)
        )
        if route_continuation and linked_calendar_stops and route_start_time:
            stop_minutes = max(15, min(720, int(route_stop_minutes or 90)))
            start = _parse_datetime(route_start_time)
            leg_data = linked_route.get("legs") if isinstance(linked_route, dict) else []
            leg_offset = 1 if linked_route.get("implicit_browser_origin") else 0
            generated_changes: list[dict[str, Any]] = []
            current = start
            for index, stop in enumerate(linked_calendar_stops):
                end = current + timedelta(minutes=stop_minutes)
                generated_changes.append({
                    "operation": "create",
                    "event": {
                        "title": f"第{index + 1}站：{str(stop.get('name') or '行程地点')[:100]}",
                        "start_time": current.isoformat(),
                        "end_time": end.isoformat(),
                        "place_id": str(stop.get("place_id") or ""),
                        "location_kind": "physical",
                        "description": "由已核实路线自动排入；确认前仍可编辑",
                    },
                })
                current = end
                leg_index = index + leg_offset
                if isinstance(leg_data, list) and leg_index < len(leg_data):
                    current += timedelta(
                        seconds=max(0, int(float((leg_data[leg_index] or {}).get("duration_seconds") or 0)))
                    )
            changes = generated_changes
        elif route_continuation and linked_calendar_stops and (
            len(changes) != len(linked_calendar_stops)
        ):
            return _clarification_action(
                conversation_id,
                title="把这条路线排进日程",
                prompt="请补充出发日期和时间，以及每个地点预计停留多久；我会按已核实的路线顺序生成可编辑日程。",
                fields=[
                    {
                        "id": "route_calendar_start",
                        "label": "什么时候出发？",
                        "type": "datetime",
                        "required": True,
                        "options": [],
                        "placeholder": "例如：2026-08-04 08:00",
                    },
                    {
                        "id": "route_calendar_stop_minutes",
                        "label": "每个地点停留多久？",
                        "type": "single",
                        "required": True,
                        "options": ["60 分钟", "90 分钟", "120 分钟"],
                        "option_values": {"60 分钟": "60", "90 分钟": "90", "120 分钟": "120"},
                    },
                ],
            )
        if not 1 <= len(changes) <= 24:
            raise ValueError("日程变更数量必须在 1 到 24 项之间")
        if isinstance(linked_route, dict):
            for stop in linked_route.get("ordered_stops") or []:
                if not isinstance(stop, dict) or stop.get("ephemeral"):
                    continue
                stop_id = str(stop.get("place_id") or "").strip()
                if stop_id:
                    candidates.setdefault(stop_id, copy.deepcopy(stop))
        implicit_route_origin = (
            (linked_route.get("ordered_stops") or [None])[0]
            if (
                isinstance(linked_route, dict)
                and linked_route.get("implicit_browser_origin")
                and (linked_route.get("ordered_stops") or [])
            )
            else None
        )
        ephemeral_place_ids = {
            str(place.get("place_id") or "")
            for place in (browser_current_location, implicit_route_origin)
            if isinstance(place, dict) and str(place.get("place_id") or "")
        }
        linked_route_place_ids = {
            str(place.get("place_id") or "")
            for place in (
                (linked_route.get("ordered_stops") or [])
                if isinstance(linked_route, dict)
                else []
            )
            if isinstance(place, dict) and str(place.get("place_id") or "")
        }
        submitted_create_count = sum(
            1
            for raw_change in changes
            if isinstance(raw_change, dict)
            and str(raw_change.get("operation") or "create") == "create"
        )
        can_bind_route_order = bool(
            route_source_id
            and linked_calendar_stops
            and submitted_create_count == len(linked_calendar_stops)
        )
        linked_create_index = 0
        normalization_warnings: list[str] = []
        skipped_changes: list[dict[str, str]] = []
        normalized = []
        for change_index, raw in enumerate(changes, 1):
            if not isinstance(raw, dict):
                raise ValueError("日程变更格式无效")
            operation = str(raw.get("operation") or "create")
            if operation not in {"create", "update", "delete"}:
                raise ValueError("日程操作只能是 create、update 或 delete")
            change: dict[str, Any] = {"operation": operation}
            previous_event: dict[str, Any] = {}
            if operation in {"update", "delete"}:
                schedule_id = str(raw.get("schedule_id") or "")
                if schedule_id not in state.get("schedules", {}):
                    event = raw.get("event") if isinstance(raw.get("event"), dict) else {}
                    label = str(
                        event.get("title")
                        or raw.get("title")
                        or schedule_id
                        or f"第 {change_index} 项"
                    ).strip()[:120]
                    skipped_changes.append({
                        "operation": operation,
                        "target": label,
                        "reason": "当前日程表中不存在，已跳过",
                    })
                    continue
                change["schedule_id"] = schedule_id
                previous_event = state.get("schedules", {}).get(schedule_id) or {}
            if operation != "delete":
                nested_event = raw.get("event")
                # Some tool-calling models flatten list-item fields. Accept
                # both wire shapes, then normalize into the canonical contract.
                event = nested_event if isinstance(nested_event, dict) else raw
                title = str(event.get("title") or event.get("name") or "").strip()[:120]
                start_value = str(event.get("start_time") or event.get("start") or "").strip()
                if operation == "create" and (not title or not start_value):
                    raise ValueError("新增日程必须包含标题和开始时间")
                event_place_id = str(
                    event.get("place_id") or event.get("location_place_id") or ""
                ).strip()
                if operation == "create" and can_bind_route_order:
                    expected_stop = linked_calendar_stops[linked_create_index]
                    linked_create_index += 1
                    expected_place_id = str(expected_stop.get("place_id") or "")
                    if event_place_id != expected_place_id:
                        # The route id and complete event count freeze the
                        # provider-backed station sequence. Repairing transport
                        # omissions here avoids a second model round without
                        # inferring anything from titles or place-language rules.
                        event_place_id = expected_place_id
                        warning = "路线日程地点已按最近核实的站点顺序补齐，可在确认前编辑"
                        if warning not in normalization_warnings:
                            normalization_warnings.append(warning)
                normalized_event: dict[str, Any] = {}
                if title:
                    normalized_event["title"] = title
                end_value = str(event.get("end_time") or event.get("end") or "").strip()
                if start_value:
                    start = _parse_datetime(start_value)
                    normalized_event["start_time"] = int(start.timestamp())
                    if end_value:
                        end = _parse_datetime(end_value)
                    elif operation == "update":
                        end = start + timedelta(
                            minutes=max(1, int(previous_event.get("duration_minutes") or 60))
                        )
                    else:
                        end = start + timedelta(hours=1)
                    if (
                        end == start
                        and operation == "create"
                        and event_place_id in linked_route_place_ids
                    ):
                        # Calendar storage requires a positive interval, while
                        # route-derived departure/arrival markers are naturally
                        # instantaneous. Preserve the selected timestamp and
                        # verified stop at the minimum calendar granularity.
                        # The proposal remains editable and still needs consent.
                        end = start + timedelta(minutes=1)
                        normalization_warnings.append(
                            "路线中的瞬时出发或抵达提醒已按日历最小粒度记为 1 分钟，可在确认前编辑"
                        )
                    if end <= start:
                        raise ValueError(f"日程结束时间必须晚于开始时间：{title}")
                    normalized_event["duration_minutes"] = max(1, int((end - start).total_seconds() // 60))
                elif end_value and operation == "update":
                    start = datetime.fromtimestamp(int(previous_event.get("start_time") or 0), timezone.utc)
                    end = _parse_datetime(end_value)
                    if end <= start:
                        raise ValueError(f"日程结束时间必须晚于开始时间：{title or previous_event.get('title') or '该日程'}")
                    normalized_event["duration_minutes"] = max(1, int((end - start).total_seconds() // 60))
                elif "duration_minutes" in event:
                    normalized_event["duration_minutes"] = max(1, min(10_080, int(event.get("duration_minutes") or 60)))
                for key in ("category", "description", "done"):
                    if key in event:
                        normalized_event[key] = event[key]
                place_id = event_place_id
                location_text = str(event.get("location") or "").strip()
                if place_id and place_id in ephemeral_place_ids:
                    # Browser coordinates are request-scoped routing input.
                    # Keep a useful departure reminder, but never persist its
                    # transient place object or readable address in a calendar.
                    place_id = ""
                    location_text = ""
                    normalized_event["location"] = ""
                clear_location = bool(event.get("clear_location", False))
                location_kind = str(event.get("location_kind") or "").strip().lower()
                if location_kind not in {"", "physical", "online"}:
                    raise ValueError("location_kind 只能是 physical 或 online")
                online_location = bool(location_text and location_kind == "online")
                if clear_location:
                    place_id = ""
                    location_text = ""
                    normalized_event["place"] = None
                    normalized_event["location"] = ""
                elif online_location:
                    normalized_event["location"] = location_text
                    normalized_event["location_kind"] = "online"
                if location_text and not place_id:
                    if online_location:
                        change["event"] = normalized_event
                        normalized.append(change)
                        continue
                    # A route or place tool in an earlier turn has already
                    # persisted verified candidates.  Reuse an unambiguous
                    # match instead of making the model transport a fragile
                    # provider id across turns.  This remains provider-backed:
                    # free-form locations that were never verified are refused.
                    normalized_location = _normalized_place_name(location_text)
                    matched = [
                        (candidate_id, candidate)
                        for candidate_id, candidate in candidates.items()
                        if isinstance(candidate, dict)
                        and normalized_location
                        and _normalized_place_name(candidate.get("name"))
                        and (
                            normalized_location == _normalized_place_name(candidate.get("name"))
                            or normalized_location == _normalized_place_name(candidate.get("address"))
                            or normalized_location == _normalized_place_name(
                                _place_option_label(candidate)
                            )
                        )
                    ]
                    if len(matched) == 1:
                        place_id = str(matched[0][0])
                    elif len(matched) > 1:
                        raise ValueError(f"“{location_text}”对应多个已核实地点，请先选择具体地点")
                    else:
                        # A semantic planner normally schedules search_places
                        # before this tool. Keep the Action reliable when that
                        # optional hint omits needs_places: the calendar tool
                        # safely reuses the same Tencent/OSM adapter once,
                        # rather than failing and leaving a phantom card.
                        maps_enabled = (
                            enabled_skills is None
                            or place_skill_id in enabled_skills
                        )
                        if not maps_enabled:
                            raise ValueError(
                                f"“{location_text}”需要地图 Skill 核实，请先到 Skills 广场开启地图"
                            )
                        verified = await _search_places_metered(
                            str(
                                runtime_env.get("TENCENT_MAP_SERVER_KEY")
                                or runtime_env.get("TENCENT_MAP_KEY")
                                or runtime_env.get("VITE_TENCENT_MAP_KEY")
                                or ""
                            ),
                            location_text,
                            city="全国",
                            limit=6,
                        )
                        if not verified:
                            raise ValueError(f"没有核实到地点“{location_text}”")
                        for candidate in verified:
                            candidate_id = str(candidate.get("place_id") or "").strip()
                            if candidate_id:
                                candidates[candidate_id] = candidate
                        if len(verified) > 1:
                            decision, selected, _reason = await _place_resolution_with_provider_review(
                                place_disambiguation_model,
                                location_text,
                                verified,
                                context="calendar event location",
                                enabled=provider_place_review_enabled,
                                timeout_seconds=min(8.0, map_search_timeout),
                            )
                            if decision == "auto_use" and isinstance(selected, dict):
                                place_id = str(selected.get("place_id") or "")
                            else:
                                return _clarification_action(
                                    conversation_id,
                                    title="请选择日程地点",
                                    prompt="地点服务返回了多个候选。请选择后我会继续生成日程提案。",
                                    fields=[_place_choice_field(
                                        "calendar_place",
                                        location_text,
                                        verified,
                                    )],
                                )
                        if not place_id:
                            place_id = str(verified[0].get("place_id") or "")
                if place_id:
                    place = candidates.get(place_id)
                    if not isinstance(place, dict) and location_text:
                        # Tool-calling models occasionally copy a display id
                        # incorrectly. Resolve the explicit user-visible
                        # location instead of accepting or persisting that id.
                        maps_enabled = (
                            enabled_skills is None
                            or place_skill_id in enabled_skills
                        )
                        if maps_enabled:
                            verified = await _search_places_metered(
                                str(
                                    runtime_env.get("TENCENT_MAP_SERVER_KEY")
                                    or runtime_env.get("TENCENT_MAP_KEY")
                                    or runtime_env.get("VITE_TENCENT_MAP_KEY")
                                    or ""
                                ),
                                location_text,
                                city="全国",
                                limit=6,
                            )
                            for candidate in verified:
                                candidate_id = str(candidate.get("place_id") or "").strip()
                                if candidate_id:
                                    candidates[candidate_id] = candidate
                            if len(verified) > 1:
                                decision, selected, _reason = await _place_resolution_with_provider_review(
                                    place_disambiguation_model,
                                    location_text,
                                    verified,
                                    context="calendar event location",
                                    enabled=provider_place_review_enabled,
                                    timeout_seconds=min(8.0, map_search_timeout),
                                )
                                if decision == "choose":
                                    return _clarification_action(
                                        conversation_id,
                                        title="请选择日程地点",
                                        prompt="地点服务返回了多个候选。请选择后我会继续生成日程提案。",
                                        fields=[_place_choice_field(
                                            "calendar_place",
                                            location_text,
                                            verified,
                                        )],
                                    )
                                if isinstance(selected, dict):
                                    place_id = str(selected.get("place_id") or "")
                                    place = selected
                            if verified and not place_id:
                                place_id = str(verified[0].get("place_id") or "")
                                place = candidates.get(place_id)
                    if not isinstance(place, dict):
                        raise ValueError(f"地点 ID 未通过本轮地点搜索验证：{place_id}")
                    normalized_event["place"] = place
                    normalized_event["location"] = place.get("address") or place.get("name")
                change["event"] = normalized_event
            normalized.append(change)
        if not normalized:
            return json.dumps({
                "ui_action": "calendar_change_report",
                "applied_count": 0,
                "proposed_count": 0,
                "skipped_changes": skipped_changes,
                "calendar_snapshot": {
                    "revision": int(state.get("revision") or 0),
                    "schedule_count": len(state.get("schedules") or {}),
                },
                "response_constraint": (
                    "本轮已读取当前日程表，但没有可执行的差量变更；"
                    "请逐项说明未找到的更新或删除目标，不得改为新增日程。"
                ),
            }, ensure_ascii=False)
        if not route_source_id and isinstance(latest_route, dict):
            # If a proposal contains at least two places from a very recent
            # verified route, it is semantically a route-derived calendar
            # proposal even when the model omitted the explicit source id.
            # Enforce completeness instead of silently accepting a compressed
            # two-event version of a four-stop itinerary.
            route_age = int(time.time()) - int(latest_route.get("created_at") or 0)
            route_place_ids = {
                str(item.get("place_id") or "")
                for item in (latest_route.get("ordered_stops") or [])
                if isinstance(item, dict) and str(item.get("place_id") or "")
            }
            proposed_place_ids = {
                str(((change.get("event") or {}).get("place") or {}).get("place_id") or "")
                for change in normalized
                if change.get("operation") == "create"
            }
            if 0 <= route_age <= 10_800 and len(route_place_ids & proposed_place_ids) >= 2:
                route_source_id = str(latest_route.get("id") or "")
                linked_route = latest_route

        if route_source_id:
            if not isinstance(linked_route, dict):
                raise ValueError("引用的路线规划已经变化，请根据最近一次已核实路线重新生成日程提案")
            route_stops = [
                item for item in (linked_route.get("ordered_stops") or [])
                if isinstance(item, dict) and str(item.get("place_id") or "")
            ]
            required_stops = (
                route_stops[1:]
                if linked_route.get("implicit_browser_origin") and route_stops
                else route_stops
            )
            required_ids = [str(item.get("place_id") or "") for item in required_stops]
            created = [
                change for change in normalized if change.get("operation") == "create"
            ]
            created.sort(key=lambda change: int(
                ((change.get("event") or {}).get("start_time") or 0)
            ))
            proposed_ids = [
                str(((change.get("event") or {}).get("place") or {}).get("place_id") or "")
                for change in created
            ]
            missing_names = [
                str(stop.get("name") or "未命名地点")
                for stop, place_id in zip(required_stops, required_ids)
                if place_id not in proposed_ids
            ]
            proposed_route_order = [
                place_id for place_id in proposed_ids if place_id in set(required_ids)
            ]
            if len(created) < len(required_ids) or missing_names:
                raise ValueError(
                    f"完整路线包含 {len(required_ids)} 个站点，日程提案必须至少创建 "
                    f"{len(required_ids)} 个按站点拆分的事件；尚未覆盖："
                    f"{'、'.join(missing_names) or '部分站点'}"
                )
            if proposed_route_order[:len(required_ids)] != required_ids:
                raise ValueError("日程事件顺序必须与已核实路线的站点顺序完全一致，不能合并或重排")

        validate_calendar_change_window(state, normalized)
        warnings = calendar_change_warnings(state, normalized)
        warnings.extend(normalization_warnings)
        warnings.extend(
            f"{item['operation']}“{item['target']}”：{item['reason']}"
            for item in skipped_changes
        )
        warnings = list(dict.fromkeys(warnings))[:8]

        # Preview route feasibility before confirmation. The mutation remains
        # independent: route failure never writes or cancels the calendar
        # proposal, but users see whether travel time was verified.
        preview = copy.deepcopy(state)
        preview_changed = apply_calendar_changes(preview, normalized)
        changed_ids = {
            str(item.get("id") or "")
            for item in preview_changed
            if not item.get("deleted")
        }
        preview_schedules = sorted(
            (
                item for item in (preview.get("schedules") or {}).values()
                if (
                    isinstance(item, dict)
                    and not item.get("done")
                    and int(item.get("start_time") or 0) >= int(time.time()) - 24 * 60 * 60
                )
            ),
            key=lambda item: int(item.get("start_time") or 0),
        )[:provider_schedule_limit]
        route_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for previous, current in zip(preview_schedules, preview_schedules[1:]):
            if (
                str(previous.get("id") or "") not in changed_ids
                and str(current.get("id") or "") not in changed_ids
            ):
                continue
            available = (
                int(current.get("start_time") or 0)
                - int(previous.get("start_time") or 0)
                - max(1, int(previous.get("duration_minutes") or 60)) * 60
            )
            if not 0 < available <= route_gap_hours * 3600:
                continue
            previous_place = (
                (previous.get("extra") or {}).get("place")
                if isinstance(previous.get("extra"), dict) else None
            )
            current_place = (
                (current.get("extra") or {}).get("place")
                if isinstance(current.get("extra"), dict) else None
            )
            if isinstance(previous_place, dict) and isinstance(current_place, dict):
                route_pairs.append((previous, current))
            if len(route_pairs) >= 3:
                break

        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )

        async def preview_route_pair(
            previous: dict[str, Any], current: dict[str, Any],
        ) -> str:
            previous_place = (previous.get("extra") or {}).get("place")
            current_place = (current.get("extra") or {}).get("place")
            available = (
                int(current.get("start_time") or 0)
                - int(previous.get("start_time") or 0)
                - max(1, int(previous.get("duration_minutes") or 60)) * 60
            )
            try:
                route = await load_route_cache(
                    store, user_id, [previous_place, current_place], False,
                )
                if route is None:
                    route = await _plan_route_metered(
                        map_key, [previous_place, current_place], optimize=False,
                    )
                    await save_route_cache(
                        store, user_id, [previous_place, current_place], False, route,
                    )
                route_minutes = max(1, round(float(route.get("duration_seconds") or 0) / 60))
                required_minutes = route_minutes + travel_buffer_minutes
                available_minutes = max(0, available // 60)
                if required_minutes > available_minutes:
                    return (
                        f"“{previous.get('title') or '前一项日程'}”到"
                        f"“{current.get('title') or '后一项日程'}”道路路线约 {route_minutes} 分钟，"
                        f"加 {travel_buffer_minutes} 分钟缓冲共需 {required_minutes} 分钟，"
                        f"当前只有 {available_minutes} 分钟"
                    )
            except Exception:
                return (
                    f"暂未核验“{previous.get('title') or '前一项日程'}”到"
                    f"“{current.get('title') or '后一项日程'}”的道路通勤时间"
                )
            return ""

        if route_pairs:
            route_warning_results = await asyncio.gather(*(
                preview_route_pair(previous, current)
                for previous, current in route_pairs
            ))
            warnings.extend(value for value in route_warning_results if value)
            warnings = list(dict.fromkeys(warnings))[:8]
        action = new_action(
            "calendar_changes",
            {
                "summary": str(summary or "日程变更")[:300],
                "changes": normalized,
                "warnings": warnings,
                "skipped_changes": skipped_changes,
                "calendar_snapshot": {
                    "revision": int(state.get("revision") or 0),
                    "schedule_count": len(state.get("schedules") or {}),
                },
                **({"source_route_plan_id": route_source_id} if route_source_id else {}),
            },
            requires_confirmation=True,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({"ui_action": "calendar_action", "action": action}, ensure_ascii=False)

    return propose_calendar_changes
