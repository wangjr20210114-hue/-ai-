"""Trusted place lookup Component operations."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from .map_runtime import MapProviderRuntime
from .route_resolution import (
    _clarification_action,
    _normalized_place_name,
    _place_choice_field,
    _place_option_label,
    _place_resolution_with_provider_review,
    _selected_place_candidate,
    verify_place_queries_parallel,
)
from ..._application.workspace.service import new_action, put_action


StateLoader = Callable[[], Awaitable[dict[str, Any]]]
StateSaver = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class PlaceOperations:
    """Expose verified place operations over one shared Maps runtime."""

    def __init__(
        self,
        *,
        runtime_env: dict[str, Any],
        conversation_id: str,
        browser_current_location: dict[str, Any] | None,
        map_runtime: MapProviderRuntime,
        load_state: StateLoader,
        save_state: StateSaver,
        place_disambiguation_model: Any,
        planned_calendar_place_resolution: bool,
        provider_place_review_enabled: bool,
        place_result_limit: int,
        route_stop_limit: int,
        parallelism: int,
        search_timeout: float,
    ) -> None:
        self._runtime_env = runtime_env
        self._conversation_id = conversation_id
        self._browser_current_location = browser_current_location
        self._map_runtime = map_runtime
        self._load_state = load_state
        self._save_state = save_state
        self._place_disambiguation_model = place_disambiguation_model
        self._planned_calendar_place_resolution = (
            planned_calendar_place_resolution
        )
        self._provider_place_review_enabled = provider_place_review_enabled
        self._place_result_limit = place_result_limit
        self._route_stop_limit = route_stop_limit
        self._parallelism = parallelism
        self._search_timeout = search_timeout

    def _map_key(self) -> str:
        return str(
            self._runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or self._runtime_env.get("TENCENT_MAP_KEY")
            or self._runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )

    async def get_current_location(self) -> str:
        """Describe the fresh browser location through Tencent reverse geocoding."""
        if self._browser_current_location is None:
            return _clarification_action(
                self._conversation_id,
                title="需要你的位置",
                prompt=(
                    "浏览器没有提供当前位置。你可以在浏览器设置中允许定位后重试，"
                    "也可以填写大致位置，我会用它继续附近推荐或路线规划。"
                ),
                fields=[{
                    "id": "manual_location",
                    "label": "你目前所在的位置或出发地",
                    "type": "text",
                    "required": True,
                    "options": [],
                    "placeholder": "例如：北京市海淀区中关村，或吉林大学前卫南区",
                }],
            )
        try:
            resolved = await self._map_runtime.reverse_geocode(
                self._map_key(),
                self._browser_current_location,
            )
        except Exception as exc:
            logging.warning(
                "reverse geocode current location failed error=%s",
                exc,
            )
            raise ValueError(
                "腾讯地图暂时无法把当前位置解析为地址，请稍后重试"
            ) from exc
        return json.dumps({
            "location_available": True,
            "location": resolved,
            "accuracy_meters": self._browser_current_location.get(
                "accuracy_meters"
            ),
            "response_constraint": (
                "只说明腾讯逆地址解析返回的地址、行政区和附近地标；"
                "不得输出经纬度，不得声称定位精度高于浏览器 accuracy_meters，"
                "也不得把本次位置写入日程或长期记忆。"
            ),
        }, ensure_ascii=False)

    async def search_places(
        self,
        query: str,
        city: str = "全国",
        limit: int = 10,
        purpose: Literal["browse", "calendar"] = "browse",
    ) -> str:
        """Search real places; calendar mode enforces auto/choose/fill resolution."""
        effective_purpose = (
            "calendar"
            if self._planned_calendar_place_resolution
            else purpose
        )
        state = await self._load_state()
        candidates = state.setdefault("place_candidates", {})
        selected_option = (
            _selected_place_candidate(query, candidates)
            or next(
                (
                    place
                    for place in candidates.values()
                    if isinstance(place, dict)
                    and _normalized_place_name(_place_option_label(place))
                    == _normalized_place_name(query)
                ),
                None,
            )
        )
        if effective_purpose == "calendar" and isinstance(
            selected_option,
            dict,
        ):
            return json.dumps({
                "places": [selected_option],
                "count": 1,
                "resolution": {
                    "decision": "auto_use",
                    "reason": "user_selected_verified_candidate",
                    "selected_place_id": selected_option.get("place_id"),
                },
            }, ensure_ascii=False)
        places = await self._map_runtime.search_places(
            self._map_key(),
            query,
            city=city,
            limit=max(1, min(self._place_result_limit, int(limit))),
        )
        for place in places:
            candidates[str(place["place_id"])] = place
        if len(candidates) > 200:
            state["place_candidates"] = dict(
                list(candidates.items())[-200:]
            )
        await self._save_state(state)
        if effective_purpose != "calendar":
            return json.dumps(
                {"places": places, "count": len(places)},
                ensure_ascii=False,
            )
        decision, selected, reason = (
            await _place_resolution_with_provider_review(
                self._place_disambiguation_model,
                query,
                places,
                context="calendar place lookup",
                enabled=self._provider_place_review_enabled,
                timeout_seconds=min(8.0, self._search_timeout),
            )
        )
        if decision == "auto_use" and isinstance(selected, dict):
            return json.dumps({
                "places": [selected],
                "count": 1,
                "resolution": {
                    "decision": decision,
                    "reason": reason,
                    "selected_place_id": selected.get("place_id"),
                },
            }, ensure_ascii=False)
        if decision == "choose":
            return _clarification_action(
                self._conversation_id,
                title="请选择日程地点",
                prompt=(
                    f"查到多个符合“{query}”的真实地点，候选已按腾讯地图相关度排序。"
                    "请选择要写入日程的地点，提交后我会继续安排。"
                ),
                fields=[_place_choice_field(
                    "calendar_place",
                    "日程安排在哪个地点？",
                    places,
                )],
            )
        return _clarification_action(
            self._conversation_id,
            title="请补充日程地点",
            prompt=f"地点服务没有足够证据确认“{query}”。请填写更完整的名称或城市。",
            fields=[{
                "id": "calendar_place",
                "label": "日程的正确地点是什么？",
                "type": "text",
                "required": True,
                "options": [],
                "placeholder": f"例如：城市 + {query}",
            }],
        )

    async def search_places_batch(
        self,
        queries: list[str],
        city: str = "全国",
        limit_per_query: int = 3,
    ) -> str:
        """Verify every named destination independently and retain every candidate ID."""
        normalized = []
        seen_queries = set()
        for raw_query in queries or []:
            query = str(raw_query or "").strip()
            if query and query not in seen_queries:
                seen_queries.add(query)
                normalized.append(query)
        if not 1 <= len(normalized) <= self._route_stop_limit:
            raise ValueError(
                f"批量地点查询必须包含 1 到 {self._route_stop_limit} 个独立地点名称；"
                "可在设置的“地图与路线”中调整上限"
            )

        groups = []
        all_places = []
        seen_ids = set()
        semaphore = asyncio.Semaphore(self._parallelism)

        async def search_one(query: str) -> dict[str, Any]:
            try:
                async with semaphore:
                    places = await self._map_runtime.search_places(
                        self._map_key(),
                        query,
                        city=city,
                        limit=max(
                            1,
                            min(
                                self._place_result_limit,
                                int(limit_per_query),
                            ),
                        ),
                    )
                return {"query": query, "places": places}
            except Exception as exc:
                return {
                    "query": query,
                    "places": [],
                    "error": str(exc)[:200],
                }

        try:
            groups = await asyncio.wait_for(
                asyncio.gather(
                    *(search_one(query) for query in normalized)
                ),
                timeout=self._search_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"批量地点搜索超过 {round(self._search_timeout)} 秒；"
                "请减少地点数量或在设置中选择快速档"
            ) from exc
        for group in groups:
            places = group.get("places") or []
            for place in places:
                place_id = str(place["place_id"])
                if place_id not in seen_ids:
                    seen_ids.add(place_id)
                    all_places.append(place)

        state = await self._load_state()
        candidates = state.setdefault("place_candidates", {})
        for place in all_places:
            candidates[str(place["place_id"])] = place
        if len(candidates) > 200:
            state["place_candidates"] = dict(
                list(candidates.items())[-200:]
            )
        await self._save_state(state)
        return json.dumps(
            {
                "groups": groups,
                "places": all_places,
                "verified_query_count": sum(
                    bool(group.get("places"))
                    for group in groups
                ),
            },
            ensure_ascii=False,
        )

    async def prepare_map_recommendation(
        self,
        title: str,
        place_ids: list[str],
        action_text: str,
        expected_place_count: int = 2,
    ) -> str:
        """Prepare a clickable map recommendation from verified place IDs."""
        if (
            not isinstance(place_ids, list)
            or not 1 <= len(place_ids) <= self._place_result_limit
        ):
            raise ValueError(
                f"地图推荐必须包含 1 到 {self._place_result_limit} 个地点 ID；"
                "可在设置的“地图与路线”中调整候选数量"
            )
        state = await self._load_state()
        candidates = dict(state.get("place_candidates", {}))
        for event in (state.get("schedules") or {}).values():
            extra = (
                event.get("extra")
                if isinstance(event, dict)
                and isinstance(event.get("extra"), dict)
                else {}
            )
            place = extra.get("place") if isinstance(extra, dict) else None
            if isinstance(place, dict) and str(place.get("place_id") or ""):
                candidates[str(place["place_id"])] = place
        places = []
        seen = set()
        for raw_id in place_ids:
            place_id = str(raw_id or "").strip()
            place = candidates.get(place_id)
            if (
                place_id
                and place_id not in seen
                and isinstance(place, dict)
            ):
                seen.add(place_id)
                places.append(place)
        if not places:
            raise ValueError("推荐地点均未通过地点服务验证，不能显示到地图")
        expected = max(
            1,
            min(
                self._place_result_limit,
                int(expected_place_count or 2),
            ),
        )
        action = new_action(
            "map_recommendation",
            {
                "title": str(title or "相关地点")[:120],
                "action_text": str(
                    action_text or "在地图中看看这些地点"
                )[:80],
                "places": places,
            },
            requires_confirmation=False,
        )
        put_action(state, action)
        await self._save_state(state)
        return json.dumps({
            "ui_action": "map_action",
            "action": action,
            "verified_place_count": len(places),
            "requested_place_count": expected,
            "partial": len(places) < expected,
        }, ensure_ascii=False)

    async def recommend_places_on_map(
        self,
        queries: list[str],
        city: str,
        title: str,
        action_text: str,
    ) -> str:
        """Verify model-selected destinations and prepare one map Action."""
        normalized = list(dict.fromkeys(
            str(item or "").strip()
            for item in queries
            if str(item or "").strip()
        ))
        if not 2 <= len(normalized) <= self._place_result_limit:
            raise ValueError(
                f"地图推荐需要模型提供 2 到 {self._place_result_limit} 个独立地点名称；"
                "可在设置的“地图与路线”中调整候选数量"
            )
        selected, all_candidates, missing = (
            await verify_place_queries_parallel(
                self._map_runtime.search_places,
                self._map_key(),
                normalized,
                city=city or "全国",
                timeout_seconds=float(
                    self._runtime_env.get(
                        "PLACE_LOOKUP_TIMEOUT_SECONDS"
                    )
                    or 5
                ),
            )
        )
        if not selected:
            raise ValueError(
                "所有候选地点都未通过真实地点服务核实，不能生成地图"
            )
        state = await self._load_state()
        candidates = state.setdefault("place_candidates", {})
        for place in all_candidates:
            candidates[str(place["place_id"])] = place
        action = new_action(
            "map_recommendation",
            {
                "title": str(title or f"{city}推荐地点")[:120],
                "action_text": str(
                    action_text or "在地图中查看这些地点"
                )[:80],
                "places": selected,
            },
            requires_confirmation=False,
        )
        put_action(state, action)
        await self._save_state(state)
        verified_count = len(selected)
        requested_count = len(normalized)
        response_constraint = (
            f"实际核实成功 {verified_count}/{requested_count} 个地点；"
            f"正文只能声称地图显示了 {verified_count} 个。"
        )
        if missing:
            response_constraint += (
                f" 未核实且不得放入地图：{'、'.join(missing)}。"
            )
        return json.dumps({
            "ui_action": "map_action",
            "action": action,
            "verified_place_count": verified_count,
            "requested_place_count": requested_count,
            "partial": bool(missing),
            "unverified_queries": missing,
            "response_constraint": response_constraint,
        }, ensure_ascii=False)
