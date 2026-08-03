"""Trusted nearby-place operation backed by provider adapters."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
from typing import Any

from ..._application.workspace.service import new_action, put_action
from .route_resolution import (
    _clarification_action,
    _normalized_place_name,
    _place_choice_field,
    _place_option_label,
    _selected_place_candidate,
)


def build_nearby_operation(
    *,
    _load_state,
    _save_state,
    _search_places_metered,
    _search_places_nearby_metered,
    browser_current_location,
    conversation_id,
    map_place_result_limit,
    map_search_timeout,
    runtime_env,
):
    async def recommend_nearby_places_on_map(
        anchor_query: str,
        query: str,
        anchor_queries: list[str] | None = None,
        use_current_location_as_anchor: bool = False,
        city: str = "全国",
        radius_meters: int = 2_000,
        strict_radius: bool = False,
        limit: int = 5,
        title: str = "",
        action_text: str = "",
    ) -> str:
        """Find a category near one or more verified anchors and prepare a map Action.

        Put the first or only anchor in anchor_query. When the user names
        alternative anchors, also put every alternative in anchor_queries; the
        tool keeps successful groups even if another anchor returns no result.
        Anchors are resolved from the Makers user workspace first, including
        verified places attached to schedules. Only a missing anchor reaches
        the location provider. Each nearby lookup is one Tencent boundary query
        rather than a web search plus repeated relative-name lookups.
        """
        requested_anchor_queries = list(dict.fromkeys(
            str(value or "").strip()
            for value in [anchor_query, *(anchor_queries or [])]
            if str(value or "").strip()
        ))
        current_location_requested = bool(use_current_location_as_anchor)
        clean_anchor_queries = requested_anchor_queries
        if current_location_requested:
            clean_anchor_queries.insert(0, "__browser_current_location__")
        clean_query = str(query or "").strip()
        if not clean_anchor_queries:
            raise ValueError("附近搜索缺少参照地点")
        if len(clean_anchor_queries) > 4:
            raise ValueError("一次附近搜索最多支持 4 个备选参照地点")
        if not clean_query:
            raise ValueError("附近搜索缺少要查找的地点类别")
        if current_location_requested and browser_current_location is None:
            if len(clean_anchor_queries) == 1:
                return _clarification_action(
                    conversation_id,
                    title="需要附近搜索的起点",
                    prompt=(
                        "浏览器没有提供当前位置。请填写你所在的区域或附近地标，"
                        "提交后我会自动继续查找，不需要重新描述需求。"
                    ),
                    fields=[{
                        "id": "nearby_anchor",
                        "label": "你现在在哪里？",
                        "type": "text",
                        "required": True,
                        "options": [],
                        "placeholder": "例如：北京市海淀区中关村，或吉林大学前卫南区",
                    }],
                )
            # Keep explicit alternative anchors useful even when the browser
            # branch is unavailable. The response reports only anchors that
            # were actually resolved and never claims a current-position scan.
            clean_anchor_queries = [
                value
                for value in clean_anchor_queries
                if value != "__browser_current_location__"
            ]

        state = await _load_state()
        stored_places: list[dict[str, Any]] = []
        seen_stored_ids: set[str] = set()

        def remember_stored(place: Any) -> None:
            if not isinstance(place, dict):
                return
            place_id = str(place.get("place_id") or "").strip()
            if (
                not place_id
                or place_id in seen_stored_ids
                or not isinstance(place.get("latitude"), (int, float))
                or not isinstance(place.get("longitude"), (int, float))
            ):
                return
            seen_stored_ids.add(place_id)
            stored_places.append(place)

        # Schedules are intentional user state, so their verified place is a
        # stronger anchor than a stale search candidate from an older turn.
        for event in (state.get("schedules") or {}).values():
            if not isinstance(event, dict):
                continue
            extra = event.get("extra") if isinstance(event.get("extra"), dict) else {}
            remember_stored(extra.get("place"))
        for place in (state.get("place_candidates") or {}).values():
            remember_stored(place)

        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )

        async def resolve_anchor(clean_anchor_query: str) -> dict[str, Any] | None:
            if clean_anchor_query == "__browser_current_location__":
                return copy.deepcopy(browser_current_location)
            selected_anchor = _selected_place_candidate(
                clean_anchor_query,
                state.get("place_candidates") or {},
            )
            if selected_anchor is not None:
                return selected_anchor
            normalized_anchor = _normalized_place_name(clean_anchor_query)
            exact_stored = [
                place for place in stored_places
                if normalized_anchor
                and normalized_anchor in {
                    _normalized_place_name(place.get("name")),
                    _normalized_place_name(_place_option_label(place)),
                }
            ]
            if len(exact_stored) == 1:
                return exact_stored[0]
            anchors = await _search_places_metered(
                map_key,
                clean_anchor_query,
                city=city or "全国",
                limit=5,
            )
            if len(anchors) == 1:
                return anchors[0]
            if anchors:
                return {
                    "_ambiguous_candidates": anchors,
                    "_query": clean_anchor_query,
                }
            return None

        search_deadline = asyncio.get_running_loop().time() + map_search_timeout
        try:
            resolved_anchors = await asyncio.wait_for(
                asyncio.gather(*(
                    resolve_anchor(clean_anchor_query)
                    for clean_anchor_query in clean_anchor_queries
                )),
                timeout=map_search_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"参照地点搜索超过 {round(map_search_timeout)} 秒；请减少地点数量或使用快速档"
            ) from exc
        ambiguous_anchors = [
            (index, item)
            for index, item in enumerate(resolved_anchors)
            if isinstance(item, dict)
            and isinstance(item.get("_ambiguous_candidates"), list)
        ]
        if ambiguous_anchors:
            candidates = state.setdefault("place_candidates", {})
            for resolved_anchor in resolved_anchors:
                if not isinstance(resolved_anchor, dict):
                    continue
                candidate_items = (
                    resolved_anchor.get("_ambiguous_candidates")
                    if isinstance(
                        resolved_anchor.get("_ambiguous_candidates"), list
                    )
                    else [resolved_anchor]
                )
                for candidate in candidate_items:
                    if not isinstance(candidate, dict):
                        continue
                    place_id = str(candidate.get("place_id") or "").strip()
                    if place_id:
                        candidates[place_id] = candidate
            if len(candidates) > 200:
                state["place_candidates"] = dict(
                    list(candidates.items())[-200:]
                )
            await _save_state(state)
            return _clarification_action(
                conversation_id,
                title="请选择附近搜索的参照地点",
                prompt=(
                    "地点服务返回了多个候选，已按腾讯地图相关度排序。"
                    "请选择与原目标一致的地点后，我会继续附近搜索。"
                ),
                fields=[
                    _place_choice_field(
                        f"anchor_{index}",
                        str(item.get("_query") or "参照地点"),
                        item["_ambiguous_candidates"],
                    )
                    for index, item in ambiguous_anchors
                ],
            )

        requested_radius = max(300, min(20_000, int(radius_meters or 2_000)))
        # A model sometimes invents an overly narrow radius even though the
        # user only said "nearby". Keep the product default stable unless the
        # model marks a distance explicitly stated by the user as strict.
        radius = requested_radius if strict_radius else max(2_000, requested_radius)
        bounded_limit = max(1, min(map_place_result_limit, int(limit or 5)))

        async def lookup_nearby(
            clean_anchor_query: str,
            anchor: dict[str, Any] | None,
        ) -> dict[str, Any]:
            display_anchor_query = (
                "当前位置"
                if clean_anchor_query == "__browser_current_location__"
                else clean_anchor_query
            )
            if anchor is None:
                return {
                    "anchor_query": display_anchor_query,
                    "anchor": None,
                    "places": [],
                    "error": f"没有核实到参照地点“{display_anchor_query}”",
                }
            try:
                found = await _search_places_nearby_metered(
                    map_key,
                    clean_query,
                    anchor,
                    radius_meters=radius,
                    limit=bounded_limit,
                )
                places = [{
                    **place,
                    "nearby_anchor_query": display_anchor_query,
                    "nearby_anchor_name": str(anchor.get("name") or display_anchor_query),
                    "nearby_anchor_place_id": str(anchor.get("place_id") or ""),
                } for place in found]
                logging.info(
                    "nearby place lookup anchor=%s query=%s radius=%s strict=%s results=%s",
                    str(anchor.get("name") or display_anchor_query)[:120],
                    clean_query[:120],
                    radius,
                    bool(strict_radius),
                    len(places),
                )
                return {
                    "anchor_query": display_anchor_query,
                    "anchor": anchor,
                    "places": places,
                    "error": "",
                }
            except Exception as exc:
                logging.warning(
                    "nearby place lookup failed anchor=%s query=%s error=%s",
                    display_anchor_query[:120],
                    clean_query[:120],
                    exc,
                )
                return {
                    "anchor_query": display_anchor_query,
                    "anchor": anchor,
                    "places": [],
                    "error": str(exc)[:200],
                }

        remaining = search_deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(
                f"附近地点搜索超过 {round(map_search_timeout)} 秒；请减少地点数量或使用快速档"
            )
        try:
            groups = await asyncio.wait_for(
                asyncio.gather(*(
                    lookup_nearby(clean_anchor_query, anchor)
                    for clean_anchor_query, anchor in zip(clean_anchor_queries, resolved_anchors)
                )),
                timeout=remaining,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"附近地点搜索超过 {round(map_search_timeout)} 秒；请减少地点数量或使用快速档"
            ) from exc
        places: list[dict[str, Any]] = []
        seen_place_ids: set[str] = set()
        max_group_size = max((len(group["places"]) for group in groups), default=0)
        # Interleave groups so every successful alternative remains represented
        # when the combined map reaches the user-selected result cap.
        for index in range(max_group_size):
            for group in groups:
                if index >= len(group["places"]):
                    continue
                place = group["places"][index]
                place_id = str(place.get("place_id") or "")
                if not place_id or place_id in seen_place_ids:
                    continue
                seen_place_ids.add(place_id)
                places.append(place)
                if len(places) >= map_place_result_limit:
                    break
            if len(places) >= map_place_result_limit:
                break
        if not places:
            anchors_text = "、".join(
                "“当前位置”" if value == "__browser_current_location__" else f"“{value}”"
                for value in clean_anchor_queries
            )
            raise ValueError(
                f"没有在{anchors_text}附近 {radius} 米内核实到“{clean_query}”"
            )

        candidates = state.setdefault("place_candidates", {})
        for anchor in resolved_anchors:
            if anchor is not None:
                candidates[str(anchor["place_id"])] = anchor
        for place in places:
            candidates[str(place["place_id"])] = place
        if len(candidates) > 200:
            state["place_candidates"] = dict(list(candidates.items())[-200:])

        anchor_names = [
            str(group["anchor"].get("name") or group["anchor_query"])
            for group in groups
            if group["anchor"] is not None
        ]
        natural_title = str(
            title or f"{'、'.join(anchor_names or clean_anchor_queries)}附近的{clean_query}"
        )[:120]
        action = new_action(
            "map_recommendation",
            {
                "title": natural_title,
                "action_text": str(action_text or "在地图中查看附近地点")[:80],
                "places": places,
            },
            requires_confirmation=False,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({
            "ui_action": "map_action",
            "action": action,
            "anchor": next((anchor for anchor in resolved_anchors if anchor is not None), None),
            "anchors": [anchor for anchor in resolved_anchors if anchor is not None],
            "groups": groups,
            "places": places,
            "verified_place_count": len(places),
            "radius_meters": radius,
            "response_constraint": (
                f"已基于 {len([anchor for anchor in resolved_anchors if anchor is not None])} 个"
                f"参照地点的核实坐标，在 {radius} 米范围内合并找到 {len(places)} 个真实地点。"
                "每个地点的 nearby_anchor_name 表示其对应参照点；正文只使用这些地点及其"
                " distance_to_anchor_meters，不要补写未核实地点、评分或营业时间。"
            ),
        }, ensure_ascii=False)

    return recommend_nearby_places_on_map
