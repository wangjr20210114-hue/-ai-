"""Trusted route planning operation backed by Makers state and provider adapters."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import time
from typing import Any

from pydantic import BaseModel

from ..._application.workspace.service import new_action, put_action
from ..._infrastructure.makers.route_repository import load_route_cache, save_route_cache
from .route_resolution import (
    _clarification_action,
    _learned_route_preference,
    _merge_clarification_actions,
    _normalized_place_name,
    _place_choice_field,
    _place_resolution_with_provider_review,
    _prioritize_clarification_options_for_city,
    _prioritize_provider_candidates_for_city,
    _provider_city_consensus,
    _rank_verified_workspace_matches,
    _route_plan_leg_summary,
    _selected_place_candidate,
    preserve_planned_route_stops,
)


def build_route_operation(
    *,
    _load_state,
    _plan_route_metered,
    _save_state,
    _search_places_metered,
    _search_places_nearby_metered,
    browser_current_location,
    calendar_skill_id,
    conversation_id,
    enabled_skills,
    map_learn_route_preferences,
    map_near_time_tolerance,
    map_parallelism,
    map_preferred_route_mode,
    map_route_stop_limit,
    map_route_strategy,
    map_search_timeout,
    place_disambiguation_model,
    planned_route_calendar_hint,
    planned_route_city,
    planned_route_mode,
    planned_route_stops,
    planned_route_strategy,
    planned_route_uses_current_location,
    provider_place_review_enabled,
    route_user_message,
    runtime_env,
    store,
    user_id,
):
    async def plan_route_between_places(
        origin_query: str = "",
        destination_query: str = "",
        city: str = "全国",
        origin_near_query: str = "",
        destination_near_query: str = "",
        nearby_radius_meters: int = 5_000,
        route_mode: str = "default",
        route_strategy: str = "default",
        use_current_location_as_origin: bool = False,
        ordered_stops: list[dict[str, str]] | None = None,
    ) -> str:
        """Resolve an ordered itinerary and calculate one verified Tencent route.

        For a two-place request, pass origin_query and destination_query. For a
        multi-stop trip, pass ordered_stops in the user's exact order; every
        item contains query and may contain near_query. Never optimize or
        reorder user-provided stops. When a place is described relative to
        another place, keep them separate, for example
        {"query":"锦江之星","near_query":"北京301医院"}.
        """
        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )
        requested_route_mode = str(route_mode or "default").strip().lower()
        planner_route_mode = str(planned_route_mode or "default").strip().lower()
        if requested_route_mode not in {"default", "driving", "transit", "walking", "bicycling"}:
            requested_route_mode = "default"
        explicit_route_mode = (
            requested_route_mode
            if requested_route_mode != "default"
            else planner_route_mode
            if planner_route_mode in {"driving", "transit", "walking", "bicycling"}
            else ""
        )
        requested_route_strategy = str(route_strategy or "default").strip().lower()
        planner_route_strategy = str(planned_route_strategy or "default").strip().lower()
        if requested_route_strategy not in {
            "default", "time_then_cost", "least_time", "least_cost",
        }:
            requested_route_strategy = "default"
        explicit_route_strategy = (
            requested_route_strategy
            if requested_route_strategy != "default"
            else planner_route_strategy
            if planner_route_strategy in {"time_then_cost", "least_time", "least_cost"}
            else ""
        )
        should_use_current_location = bool(
            browser_current_location
            and (use_current_location_as_origin or planned_route_uses_current_location)
            and not str(origin_query or "").strip()
        )
        if (
            (use_current_location_as_origin or planned_route_uses_current_location)
            and not browser_current_location
            and not str(origin_query or "").strip()
        ):
            return _clarification_action(
                conversation_id,
                title="需要路线起点",
                prompt="浏览器当前位置未授权或已经过期。请先在地图卡片授权定位，或直接填写起点。",
                fields=[{
                    "id": "route_origin",
                    "label": "从哪里出发？",
                    "type": "text",
                    "required": True,
                    "options": [],
                    "placeholder": "例如：吉林大学前卫南区",
                }],
            )
        route_operation_deadline = asyncio.get_running_loop().time() + 58.0
        radius = max(500, min(20_000, int(nearby_radius_meters or 5_000)))
        state = await _load_state()
        learning = state.setdefault("route_preference_learning", {
            "mode_counts": {},
            "strategy_counts": {},
        })
        learned_route_mode = (
            _learned_route_preference(
                learning,
                "mode_counts",
                {"driving", "transit", "walking", "bicycling"},
            )
            if map_learn_route_preferences
            else ""
        )
        learned_route_strategy = (
            _learned_route_preference(
                learning,
                "strategy_counts",
                {"time_then_cost", "least_time", "least_cost"},
            )
            if map_learn_route_preferences
            else ""
        )
        selected_route_mode = (
            explicit_route_mode or learned_route_mode or map_preferred_route_mode
        )
        selected_route_strategy = (
            explicit_route_strategy or learned_route_strategy or map_route_strategy
        )
        candidates = state.setdefault("place_candidates", {})
        for event in (state.get("schedules") or {}).values():
            extra = event.get("extra") if isinstance(event, dict) and isinstance(event.get("extra"), dict) else {}
            place = extra.get("place") if isinstance(extra, dict) else None
            if isinstance(place, dict) and str(place.get("place_id") or ""):
                candidates[str(place["place_id"])] = place

        def unresolved_place_card(
            endpoint_id: str,
            endpoint_label: str,
            query: str,
            near_query: str = "",
            *,
            timed_out: bool = False,
        ) -> str:
            qualifier = (
                f"（{near_query}附近 {radius} 米内）"
                if str(near_query or "").strip()
                else ""
            )
            evidence_state = (
                "在本次时间预算内没有足够证据核实"
                if timed_out
                else "没有足够证据确认"
            )
            return _clarification_action(
                conversation_id,
                title=f"请确认{endpoint_label}",
                prompt=(
                    f"地点服务{evidence_state}“{query}”{qualifier}。"
                    "可能是名称有误、存在同名地点或缺少城市，请补充更完整名称。"
                ),
                fields=[{
                    "id": (
                        f"{endpoint_id}_"
                        f"{hashlib.sha256(str(query).encode()).hexdigest()[:6]}"
                    ),
                    "label": f"{endpoint_label}的正确名称或城市是什么？",
                    "type": "text",
                    "required": True,
                    "options": [],
                    "placeholder": f"例如：城市 + {query}",
                }],
            )

        async def resolve(
            endpoint_id: str,
            endpoint_label: str,
            query: str,
            near_query: str,
        ) -> tuple[dict[str, Any] | None, str | None]:
            clean_query = str(query or "").strip()
            clean_near = str(near_query or "").strip()
            if clean_query == "__browser_current_location__":
                return copy.deepcopy(browser_current_location), None
            if not clean_query:
                raise ValueError(f"{endpoint_label}地点不能为空")
            if clean_near:
                selected_anchor = _selected_place_candidate(
                    clean_near,
                    candidates,
                )
                anchors = (
                    [selected_anchor]
                    if selected_anchor is not None
                    else await _search_places_metered(
                        map_key, clean_near, city=city or "全国", limit=5,
                    )
                )
                if not anchors:
                    return None, unresolved_place_card(
                        endpoint_id,
                        endpoint_label,
                        clean_query,
                        clean_near,
                    )
                anchor = anchors[0]
                if len(anchors) > 1:
                    return None, _clarification_action(
                        conversation_id,
                        title="请选择附近参照地点",
                        prompt=(
                            f"腾讯地点服务查到多个“{clean_near}”，候选已按相关度排序。"
                            f"请先选择用于查找{endpoint_label}“{clean_query}”的参照地点。"
                        ),
                        fields=[_place_choice_field(
                            f"{endpoint_id}_anchor",
                            "附近搜索以哪个地点为参照？",
                            anchors,
                        )],
                    )
                matches = await _search_places_nearby_metered(
                    map_key,
                    clean_query,
                    anchor,
                    radius_meters=radius,
                    limit=6,
                )
            else:
                matches = _rank_verified_workspace_matches(
                    clean_query,
                    candidates,
                    city or "全国",
                    limit=6,
                )
                reused_workspace_candidates = bool(matches)
                if not matches:
                    matches = await _search_places_metered(
                        map_key, clean_query, city=city or "全国", limit=6,
                    )
                    reused_workspace_candidates = False
            if clean_near:
                reused_workspace_candidates = False
            if not matches:
                return None, unresolved_place_card(
                    endpoint_id,
                    endpoint_label,
                    clean_query,
                    clean_near,
                )
            matches = _prioritize_provider_candidates_for_city(
                matches,
                city or "全国",
            )
            if not reused_workspace_candidates:
                for match in matches:
                    place_id = str(match.get("place_id") or "").strip()
                    if place_id:
                        candidates[place_id] = match
            if len(candidates) > 200:
                state["place_candidates"] = dict(list(candidates.items())[-200:])

            # A brand near an anchor commonly has several legitimate branches.
            # Even when one branch has the exact bare brand name, choosing it
            # silently would be arbitrary; let the user pick from real nearby
            # candidates instead.
            if clean_near and len(matches) > 1:
                field = _place_choice_field(
                    endpoint_id,
                    f"请选择具体{endpoint_label}",
                    matches,
                )
                return None, _clarification_action(
                    conversation_id,
                    title="请选择具体地点",
                    prompt=(
                        f"查到多个位于“{clean_near}”附近的“{clean_query}”，候选已按相关度排序。"
                        f"请选择具体{endpoint_label}，提交后我会继续规划。"
                    ),
                    fields=[field],
                )
            if len(matches) > 1:
                decision, selected, _reason = await _place_resolution_with_provider_review(
                    place_disambiguation_model,
                    clean_query,
                    matches,
                    context=endpoint_label,
                    enabled=provider_place_review_enabled,
                    timeout_seconds=min(8.0, map_search_timeout),
                )
                if decision == "auto_use" and isinstance(selected, dict):
                    return selected, None
                field = _place_choice_field(
                    endpoint_id,
                    f"请选择具体{endpoint_label}",
                    matches,
                )
                return None, _clarification_action(
                    conversation_id,
                    title="请选择具体地点",
                    prompt=(
                        f"查到多个符合“{clean_query}”的地点，候选已按相关度返回。"
                        f"请选择具体{endpoint_label}，提交后我会继续规划。"
                    ),
                    fields=[field],
                )
            return matches[0], None

        requested_stops: list[tuple[str, str]] = []
        if ordered_stops:
            minimum_stops = 1 if should_use_current_location else 2
            if (
                not isinstance(ordered_stops, list)
                or not minimum_stops <= len(ordered_stops) <= map_route_stop_limit
            ):
                raise ValueError(
                    f"有序行程必须包含 {minimum_stops} 到 {map_route_stop_limit} 个地点；"
                    "可在设置的“地图与路线”中调整上限"
                )
            for index, raw_stop in enumerate(ordered_stops, 1):
                if isinstance(raw_stop, BaseModel):
                    raw_stop = raw_stop.model_dump()
                if not isinstance(raw_stop, dict):
                    raise ValueError(f"第 {index} 个行程地点格式无效")
                query = str(raw_stop.get("query") or "").strip()
                near_query = str(raw_stop.get("near_query") or "").strip()
                if not query:
                    raise ValueError(f"第 {index} 个行程地点不能为空")
                requested_stops.append((query, near_query))
        else:
            requested_stops = [
                (str(origin_query or "").strip(), str(origin_near_query or "").strip()),
                (str(destination_query or "").strip(), str(destination_near_query or "").strip()),
            ]
        model_stop_count = len(requested_stops)
        requested_stops = preserve_planned_route_stops(
            requested_stops,
            planned_route_stops,
            route_user_message,
        )
        if should_use_current_location:
            requested_stops = [
                ("__browser_current_location__", ""),
                *[item for item in requested_stops if item[0]],
            ]
        if len(requested_stops) > map_route_stop_limit:
            raise ValueError(
                f"当前地图设置允许单条路线最多 {map_route_stop_limit} 个地点，"
                "请减少站点或在设置中提高上限"
            )
        logging.info(
            "route stop handoff planner=%s tool_model=%s selected=%s",
            len(planned_route_stops or []),
            model_stop_count,
            len(requested_stops),
        )
        if (not city or city == "全国") and str(planned_route_city or "").strip():
            city = str(planned_route_city).strip()[:80]

        route_search_semaphore = asyncio.Semaphore(map_parallelism)
        resolution_timeout = max(
            3.0,
            min(
                map_search_timeout + 12.0,
                route_operation_deadline - asyncio.get_running_loop().time() - 9.0,
            ),
        )

        async def resolve_indexed(
            index: int, query: str, near_query: str,
        ) -> tuple[dict[str, Any] | None, str | None]:
            endpoint_id, endpoint_label = (
                ("route_origin", "起点") if index == 1
                else ("route_destination", "终点") if index == len(requested_stops)
                else (f"route_stop_{index}", f"第 {index} 站")
            )

            async def resolve_with_capacity():
                async with route_search_semaphore:
                    return await resolve(
                        endpoint_id, endpoint_label, query, near_query,
                    )

            try:
                # The deadline includes time waiting for a search slot. This
                # keeps a large stop list inside the route-wide 58 s budget.
                return await asyncio.wait_for(
                    resolve_with_capacity(),
                    timeout=resolution_timeout,
                )
            except TimeoutError:
                return None, unresolved_place_card(
                    endpoint_id,
                    endpoint_label,
                    query,
                    near_query,
                    timed_out=True,
                )

        resolution_results = await asyncio.gather(*(
            resolve_indexed(index, query, near_query)
            for index, (query, near_query) in enumerate(requested_stops, 1)
        ))
        card_city = (
            _normalized_place_name(city)
            if city and _normalized_place_name(city) not in {"全国", "中国"}
            else _provider_city_consensus([
                place
                for place, _clarification in resolution_results
                if isinstance(place, dict)
            ])
        )
        if card_city:
            resolution_results = [
                (
                    place,
                    _prioritize_clarification_options_for_city(
                        clarification,
                        candidates,
                        card_city,
                    )
                    if clarification
                    else None,
                )
                for place, clarification in resolution_results
            ]

        unresolved_cards = [
            clarification
            for _place, clarification in resolution_results
            if clarification
        ]
        if unresolved_cards:
            await _save_state(state)
            return _merge_clarification_actions(
                conversation_id,
                unresolved_cards,
            )

        resolved_stops: list[dict[str, Any]] = []
        for index, (place, clarification) in enumerate(resolution_results, 1):
            endpoint = (
                "起点" if index == 1
                else "终点" if index == len(requested_stops)
                else f"第 {index} 站"
            )
            if not place:
                raise ValueError(f"{endpoint}没有完成核实")
            if (
                resolved_stops
                and str(resolved_stops[-1].get("place_id") or "")
                == str(place.get("place_id") or "")
            ):
                raise ValueError(f"{endpoint}和上一站解析成了同一个地点，请选择不同地点")
            resolved_stops.append(place)

        remaining_route_time = route_operation_deadline - asyncio.get_running_loop().time()
        if remaining_route_time <= 1:
            raise TimeoutError(
                "路线规划总耗时已接近 60 秒上限，请减少站点或在设置中选择快速档"
            )
        route = await load_route_cache(
            store,
            user_id,
            resolved_stops,
            False,
            mode=selected_route_mode,
            strategy=selected_route_strategy,
            near_time_tolerance_minutes=map_near_time_tolerance,
        )
        if route is None:
            try:
                route = await asyncio.wait_for(
                    _plan_route_metered(
                        map_key,
                        resolved_stops,
                        optimize=False,
                        mode=selected_route_mode,
                        strategy=selected_route_strategy,
                        near_time_tolerance_minutes=map_near_time_tolerance,
                    ),
                    # The selected mode comes from the explicit request, semantic
                    # plan, or user setting—in that order.
                    timeout=remaining_route_time,
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    "路线规划超过 60 秒上限，请减少站点或在设置中选择快速档"
                ) from exc
            await save_route_cache(
                store,
                user_id,
                resolved_stops,
                False,
                route,
                mode=selected_route_mode,
                strategy=selected_route_strategy,
                near_time_tolerance_minutes=map_near_time_tolerance,
            )
        provider_places = route.get("places")
        if isinstance(provider_places, list) and len(provider_places) == len(resolved_stops):
            current_resolution = list(resolved_stops)
            resolved_stops = [
                copy.deepcopy(item)
                for item in provider_places
                if isinstance(item, dict)
            ]
            # A cached road route is keyed by canonical provider place ids and
            # intentionally ignores how the user spelled a stop. Preserve the
            # current lookup's Tencent-backed correction evidence when cached
            # normalized places replace this turn's resolved candidates.
            if len(resolved_stops) == len(current_resolution):
                for resolved, current in zip(resolved_stops, current_resolution):
                    correction = current.get("query_correction")
                    if isinstance(correction, dict):
                        resolved["query_correction"] = copy.deepcopy(correction)
                    else:
                        resolved.pop("query_correction", None)
            await save_route_cache(
                store,
                user_id,
                resolved_stops,
                False,
                route,
                mode=selected_route_mode,
                strategy=selected_route_strategy,
                near_time_tolerance_minutes=map_near_time_tolerance,
            )
        distance_meters = float(route.get("distance_meters") or 0)
        duration_seconds = float(route.get("duration_seconds") or 0)
        query_corrections = [
            copy.deepcopy(place.get("query_correction"))
            for place in resolved_stops
            if isinstance(place.get("query_correction"), dict)
        ]
        for place in resolved_stops:
            if not place.get("ephemeral"):
                candidates[str(place["place_id"])] = place
        route_plan_id = "routeplan-" + hashlib.sha256(
            (
                "|".join(str(place.get("place_id") or "") for place in resolved_stops)
                + f":{time.time_ns()}"
            ).encode()
        ).hexdigest()[:16]
        persisted_route_stops = [
            (
                {
                    "place_id": str(place.get("place_id") or ""),
                    "name": str(place.get("name") or ""),
                    "provider": str(place.get("provider") or "browser"),
                    "ephemeral": True,
                }
                if place.get("ephemeral")
                else copy.deepcopy(place)
            )
            for place in resolved_stops
        ]
        route_plan = {
            "id": route_plan_id,
            "created_at": int(time.time()),
            "ordered_stops": persisted_route_stops,
            "implicit_browser_origin": should_use_current_location,
            "query_corrections": query_corrections,
            "distance_meters": round(distance_meters),
            "duration_seconds": round(duration_seconds),
            "mode": selected_route_mode,
            "strategy": selected_route_strategy,
            "selection": copy.deepcopy(route.get("selection") or {}),
            "legs": [
                _route_plan_leg_summary(leg, selected_route_mode)
                for leg in (route.get("legs") or [])
                if isinstance(leg, dict)
            ][:11],
            "calendar_hint": str(planned_route_calendar_hint or "").strip()[:240],
        }
        state["latest_route_plan"] = route_plan
        route_plans = state.setdefault("route_plans", {})
        route_plans[route_plan_id] = copy.deepcopy(route_plan)
        state["route_plans"] = dict(sorted(
            (
                (plan_id, plan)
                for plan_id, plan in route_plans.items()
                if isinstance(plan, dict) and str(plan.get("id") or "") == plan_id
            ),
            key=lambda item: int(item[1].get("created_at") or 0),
            reverse=True,
        )[:8])
        map_action = new_action(
            "map_recommendation",
            {
                "title": f"{resolved_stops[0].get('name') or '起点'} → {resolved_stops[-1].get('name') or '终点'}",
                "action_text": "在地图中查看这条路线",
                "places": resolved_stops,
                "route_plan_id": route_plan_id,
                "route_mode": selected_route_mode,
                "route_strategy": selected_route_strategy,
                "preference_signal": (
                    {
                        **({"mode": explicit_route_mode} if explicit_route_mode else {}),
                        **(
                            {"strategy": explicit_route_strategy}
                            if explicit_route_strategy else {}
                        ),
                    }
                    if map_learn_route_preferences
                    and (explicit_route_mode or explicit_route_strategy)
                    else {}
                ),
                "show_route": True,
                # The route remains independently useful. When Calendar is
                # enabled, the same durable route card can explicitly start a
                # second turn that reuses this verified route and prepares a
                # separate confirmation proposal.
                "calendar_offer": bool(
                    calendar_skill_id
                    and (
                        enabled_skills is None
                        or calendar_skill_id in enabled_skills
                    )
                ),
            },
            requires_confirmation=False,
        )
        put_action(state, map_action)
        await _save_state(state)
        return json.dumps({
            "ui_action": "map_action",
            "action": map_action,
            "route_plan_id": route_plan_id,
            "origin": resolved_stops[0],
            "destination": resolved_stops[-1],
            "ordered_stops": resolved_stops,
            "route": {
                "provider": route.get("provider"),
                "mode": route.get("mode") or "driving",
                "distance_meters": round(distance_meters),
                "distance_kilometers": round(distance_meters / 1000, 1),
                "duration_seconds": round(duration_seconds),
                "duration_minutes": max(1, round(duration_seconds / 60)),
                "fare": route.get("fare") or {},
                "transit": route.get("transit") or {},
                "selection": route.get("selection") or {},
            },
            "evidence_contract": {
                "strict": True,
                "aggregate_only": [
                    "route.distance_meters",
                    "route.distance_kilometers",
                    "route.duration_seconds",
                    "route.duration_minutes",
                    "route.transit.walking_distance_meters",
                ],
                "permitted_transit_segment_fields": [
                    "line", "vehicle", "geton", "getoff", "station_count",
                ],
                "unknown_fields": [
                    "operating_hours",
                    "service_days",
                    "service_frequency",
                    "travel_direction",
                    "roads",
                    "entrance_rules",
                    "walking_segment_distances",
                    "alternative_lines",
                ],
                "instruction": (
                    "Only claims directly represented by the route object are "
                    "grounded. Aggregate-only values must never be assigned to "
                    "one leg. Unknown fields must not be inferred or mentioned."
                ),
            },
            "response_constraint": (
                f"距离和耗时来自按用户指定顺序核实的 {len(resolved_stops)} 个地点之间的真实道路路线；"
                f"交通方式为 {selected_route_mode}；"
                f"路线策略为 {selected_route_strategy}，由腾讯返回候选并按"
                f"{map_near_time_tolerance} 分钟的时间相近容差选择；"
                + (
                    "query_corrections 是腾讯建议服务返回的唯一候选证据，回答应简短说明按 Provider 名称规划；"
                    if query_corrections else ""
                )
                + "必须按 ordered_stops 原顺序描述各站，绝不能重新排序；"
                "回答必须使用这里的数值，不得改用网页估算、直线距离或模型猜测。"
                "公交 transit.walking_distance_meters 是全程接驳步行合计，不是任一单段距离；"
                "只有 transit.segments 中的 line、vehicle、geton、getoff、station_count 可以"
                "作为公交分段事实。未返回的运营时段、线路方向、班次、途经道路、入口规则和"
                "步行分段距离不得补写；证据不足时只报告聚合值并引导查看地图卡。"
            ),
        }, ensure_ascii=False)

    return plan_route_between_places
