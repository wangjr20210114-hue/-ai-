"""Verified production tools for the Makers travel workspace."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Literal
from urllib.parse import urlparse

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from .._shared.tencent_location import (
    plan_verified_route as provider_plan_route,
    search_places as provider_search_place_candidates,
    search_verified_places as provider_search_places,
    search_verified_places_nearby as provider_search_places_nearby,
)
from .._shared.web_media import collect_page_images as provider_collect_page_images
from .._shared.rich_search import evidence_for_model, rich_search as provider_rich_search
from .._shared.data_version import namespace as data_namespace
from .._shared.side_effects import generate_image as provider_generate_image, resolve_image_reference
from .._shared.arxiv import search_arxiv as provider_search_arxiv
from .._shared.proactive import load_proactive_state, propose_workflow as create_workflow_proposal, save_proactive_state
from .._shared.workspace import (
    begin_action_execution,
    calendar_change_warnings,
    finish_provider_call,
    get_action,
    image_versions,
    load_user_workspace,
    meeting_action_payload,
    new_action,
    put_action,
    save_user_workspace,
    seal_action_snapshot,
    start_provider_call,
    validate_calendar_change_window,
)


class ClarificationFieldInput(BaseModel):
    """Strong schema shown to the model for every clarification field."""

    id: str = Field(description="Stable semantic field id derived from the unresolved part of the user's request")
    label: str = Field(
        description=(
            "Short user-visible question grounded in the current request, recent dialogue, "
            "or a directly relevant safe memory; never invent a generic profile question"
        ),
    )
    type: Literal["single", "multi", "boolean", "text", "date", "time", "datetime"] = Field(
        description=(
            "Interaction type. Prefer single/multi for finite choices, boolean for yes/no, "
            "date for a missing date, time when the date is already known, datetime when both "
            "are missing, and text only when the answer cannot be enumerated."
        ),
    )
    required: bool = Field(default=True, description="Whether the user must answer this field")
    options: list[str] = Field(
        default_factory=list,
        description="Two to eight natural-language options for single or multi; empty for other types",
    )
    placeholder: str = Field(
        default="",
        description="Short example only for a text field; do not use it for choices or dates",
    )


def _parse_datetime(value: str) -> datetime:
    normalized = str(value or "").strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
    return str(content or "")


def _clarification_action(
    conversation_id: str,
    *,
    title: str,
    prompt: str,
    fields: list[dict[str, Any]],
) -> str:
    prompt_id = hashlib.sha256(
        f"{conversation_id}:{time.time_ns()}:{title}".encode()
    ).hexdigest()[:16]
    return json.dumps({
        "ui_action": "clarification_action",
        "clarification": {
            "id": f"clarify-{prompt_id}",
            "title": str(title).strip()[:120],
            "prompt": str(prompt).strip()[:300],
            "fields": fields[:8],
        },
    }, ensure_ascii=False)


def _normalized_place_name(value: Any) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", str(value or "").lower()))


def _place_choice_field(field_id: str, label: str, places: list[dict[str, Any]]) -> dict[str, Any]:
    options = []
    for place in places[:6]:
        distance = place.get("distance_to_anchor_meters")
        distance_text = f" · 距参照地点约 {max(1, round(float(distance)))} 米" if isinstance(distance, (int, float)) else ""
        option = f"{place.get('name') or '未命名地点'}｜{place.get('address') or '地址未提供'}{distance_text}"
        if option not in options:
            options.append(option[:240])
    return {
        "id": field_id,
        "label": label,
        "type": "single",
        "required": True,
        "options": options,
    }


async def verify_place_queries_parallel(
    provider: Callable[..., Awaitable[list[dict[str, Any]]]],
    map_key: str,
    queries: list[str],
    *,
    city: str = "全国",
    timeout_seconds: float = 10.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Verify independent model-selected places concurrently, preserving query order."""
    timeout = max(3.0, min(15.0, float(timeout_seconds)))

    async def verify(query: str) -> tuple[str, list[dict[str, Any]]]:
        try:
            matches = await asyncio.wait_for(
                provider(map_key, query, city=city or "全国", limit=3),
                timeout=timeout,
            )
        except Exception:
            matches = []
        return query, matches

    results = await asyncio.gather(*(verify(query) for query in queries))
    selected: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    missing: list[str] = []
    for query, matches in results:
        if matches:
            selected.append(matches[0])
            all_candidates.extend(matches)
        else:
            missing.append(query)
    return selected, all_candidates, missing


def build_production_tools(
    model, *, store=None, conversation_id: str = "", env: dict | None = None,
    paper_constraints: dict | None = None,
    temporal_context: dict[str, Any] | None = None,
    progressive_media: bool = False,
    media_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    background_tasks: list[asyncio.Task] | None = None,
    user_id: str = "local-user",
    initial_visual_references: list[str] | None = None,
    media_enabled: bool = True,
    planned_search_query: str = "",
    planned_image_query: str = "",
    search_cache_ttl_seconds: int = 86_400,
    search_cache_identity: str = "",
    search_result_limit: int = 8,
    search_image_limit: int = 2,
    parallel_image_search: bool = True,
    enabled_skills: set[str] | None = None,
) -> list[StructuredTool]:
    runtime_env = env or {}
    paper_scope = paper_constraints or {}
    time_scope = temporal_context or {}
    # Per-request handoff: rich-search media can be consumed by image
    # generation without asking the model to copy fragile URLs between tools.
    turn_visual_references: list[str] = [
        str(item) for item in (initial_visual_references or [])
        if str(item).startswith(("https://", "data:image/"))
    ][:3]
    turn_image_group_id = ""
    rich_search_task: asyncio.Task | None = None
    rich_search_invocations = 0
    rich_search_provider_calls = 0

    async def _load_state() -> dict[str, Any]:
        return await load_user_workspace(store, conversation_id, user_id)

    async def _save_state(state: dict[str, Any]) -> dict[str, Any]:
        return await save_user_workspace(store, state, user_id)

    async def search_places(query: str, city: str = "全国", limit: int = 10) -> str:
        """Search and verify real map places; returns stable place IDs and coordinates."""
        places = await provider_search_places(
            str(runtime_env.get("TENCENT_MAP_SERVER_KEY") or runtime_env.get("TENCENT_MAP_KEY") or runtime_env.get("VITE_TENCENT_MAP_KEY") or ""),
            query,
            city=city,
            limit=max(1, min(20, int(limit))),
        )
        state = await _load_state()
        candidates = state.setdefault("place_candidates", {})
        for place in places:
            candidates[str(place["place_id"])] = place
        # Keep the short-lived candidate set bounded even in a long conversation.
        if len(candidates) > 200:
            state["place_candidates"] = dict(list(candidates.items())[-200:])
        await _save_state(state)
        return json.dumps({"places": places, "count": len(places)}, ensure_ascii=False)

    async def search_places_batch(queries: list[str], city: str = "全国", limit_per_query: int = 3) -> str:
        """Verify every named destination independently and retain every candidate ID."""
        normalized = []
        seen_queries = set()
        for raw_query in queries or []:
            query = str(raw_query or "").strip()
            if query and query not in seen_queries:
                seen_queries.add(query)
                normalized.append(query)
        if not 1 <= len(normalized) <= 12:
            raise ValueError("批量地点查询必须包含 1 到 12 个独立地点名称")

        map_key = str(runtime_env.get("TENCENT_MAP_SERVER_KEY") or runtime_env.get("TENCENT_MAP_KEY") or runtime_env.get("VITE_TENCENT_MAP_KEY") or "")
        groups = []
        all_places = []
        seen_ids = set()
        # Sequential calls are intentional: the compliant public fallback has a
        # conservative rate limit, while Tencent calls are still fast enough.
        for query in normalized:
            try:
                places = await provider_search_places(
                    map_key,
                    query,
                    city=city,
                    limit=max(1, min(5, int(limit_per_query))),
                )
                groups.append({"query": query, "places": places})
            except Exception as exc:
                places = []
                groups.append({"query": query, "places": [], "error": str(exc)[:200]})
            for place in places:
                place_id = str(place["place_id"])
                if place_id not in seen_ids:
                    seen_ids.add(place_id)
                    all_places.append(place)

        state = await _load_state()
        candidates = state.setdefault("place_candidates", {})
        for place in all_places:
            candidates[str(place["place_id"])] = place
        if len(candidates) > 200:
            state["place_candidates"] = dict(list(candidates.items())[-200:])
        await _save_state(state)
        return json.dumps(
            {
                "groups": groups,
                "places": all_places,
                "verified_query_count": sum(bool(group.get("places")) for group in groups),
            },
            ensure_ascii=False,
        )

    async def recommend_nearby_places_on_map(
        anchor_query: str,
        query: str,
        city: str = "全国",
        radius_meters: int = 2_000,
        strict_radius: bool = False,
        limit: int = 5,
        title: str = "",
        action_text: str = "",
    ) -> str:
        """Find a category near one verified anchor and prepare a map Action.

        The anchor is resolved from the Makers user workspace first, including
        verified places attached to schedules. Only a missing anchor reaches
        the location provider. Nearby discovery itself is one Tencent boundary
        query rather than a web search plus repeated relative-name lookups.
        """
        clean_anchor_query = str(anchor_query or "").strip()
        clean_query = str(query or "").strip()
        if not clean_anchor_query:
            raise ValueError("附近搜索缺少参照地点")
        if not clean_query:
            raise ValueError("附近搜索缺少要查找的地点类别")

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

        normalized_anchor = _normalized_place_name(clean_anchor_query)

        def anchor_score(place: dict[str, Any]) -> tuple[float, int]:
            normalized_name = _normalized_place_name(place.get("name"))
            if not normalized_anchor or not normalized_name:
                return (0.0, 0)
            if normalized_name == normalized_anchor:
                return (4.0, len(normalized_name))
            if normalized_anchor in normalized_name:
                return (3.0 + len(normalized_anchor) / max(1, len(normalized_name)), len(normalized_name))
            if normalized_name in normalized_anchor:
                return (2.0 + len(normalized_name) / max(1, len(normalized_anchor)), len(normalized_name))
            return (0.0, 0)

        ranked_stored = sorted(
            ((anchor_score(place), index, place) for index, place in enumerate(stored_places)),
            key=lambda item: (-item[0][0], item[1]),
        )
        anchor = ranked_stored[0][2] if ranked_stored and ranked_stored[0][0][0] > 0 else None

        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )
        if anchor is None:
            anchors = await provider_search_place_candidates(
                map_key,
                clean_anchor_query,
                city=city or "全国",
                limit=5,
            )
            exact = [
                place for place in anchors
                if _normalized_place_name(place.get("name")) == normalized_anchor
            ]
            anchor = exact[0] if len(exact) == 1 else (anchors[0] if anchors else None)
        if anchor is None:
            raise ValueError(f"没有核实到参照地点“{clean_anchor_query}”")

        requested_radius = max(300, min(20_000, int(radius_meters or 2_000)))
        # A model sometimes invents an overly narrow radius even though the
        # user only said "nearby". Keep the product default stable unless the
        # model marks a distance explicitly stated by the user as strict.
        radius = requested_radius if strict_radius else max(2_000, requested_radius)
        bounded_limit = max(1, min(10, int(limit or 5)))
        places = await provider_search_places_nearby(
            map_key,
            clean_query,
            anchor,
            radius_meters=radius,
            limit=bounded_limit,
            accept_category_results=True,
        )
        logging.info(
            "nearby place lookup anchor=%s query=%s radius=%s strict=%s results=%s",
            str(anchor.get("name") or clean_anchor_query)[:120],
            clean_query[:120],
            radius,
            bool(strict_radius),
            len(places),
        )
        if not places:
            raise ValueError(
                f"没有在“{anchor.get('name') or clean_anchor_query}”附近 {radius} 米内"
                f"核实到“{clean_query}”"
            )

        candidates = state.setdefault("place_candidates", {})
        candidates[str(anchor["place_id"])] = anchor
        for place in places:
            candidates[str(place["place_id"])] = place
        if len(candidates) > 200:
            state["place_candidates"] = dict(list(candidates.items())[-200:])

        natural_title = str(title or f"{anchor.get('name') or clean_anchor_query}附近的{clean_query}")[:120]
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
            "anchor": anchor,
            "places": places,
            "verified_place_count": len(places),
            "radius_meters": radius,
            "response_constraint": (
                f"已基于“{anchor.get('name') or clean_anchor_query}”的核实坐标，"
                f"在 {radius} 米范围内找到 {len(places)} 个真实地点。"
                "正文只使用这些地点及其 distance_to_anchor_meters；不要补写未核实地点、评分或营业时间。"
            ),
        }, ensure_ascii=False)

    async def plan_route_between_places(
        origin_query: str,
        destination_query: str,
        city: str = "全国",
        origin_near_query: str = "",
        destination_near_query: str = "",
        nearby_radius_meters: int = 5_000,
    ) -> str:
        """Resolve two real POIs and calculate a verified driving route.

        When an endpoint is described relative to another place, pass the POI
        name as *_query and its anchor as *_near_query. For example:
        destination_query="锦江之星", destination_near_query="北京301医院".
        """
        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )
        radius = max(500, min(20_000, int(nearby_radius_meters or 5_000)))

        async def resolve(
            endpoint: str,
            query: str,
            near_query: str,
        ) -> tuple[dict[str, Any] | None, str | None]:
            clean_query = str(query or "").strip()
            clean_near = str(near_query or "").strip()
            if not clean_query:
                raise ValueError(f"{endpoint}地点不能为空")
            if "附近" in clean_query and not clean_near:
                raise ValueError(
                    f"{endpoint}包含相对位置，请把要找的地点与参照地点分开传入；"
                    "不要把“附近”复合条件当成一个普通地点名"
                )
            if clean_near:
                try:
                    anchors = await provider_search_place_candidates(
                        map_key, clean_near, city=city or "全国", limit=5,
                    )
                except Exception:
                    anchors = await provider_search_places(
                        map_key, clean_near, city=city or "全国", limit=5,
                    )
                if not anchors:
                    raise ValueError(f"没有核实到{endpoint}参照地点“{clean_near}”")
                anchor_exact = [
                    item for item in anchors
                    if _normalized_place_name(item.get("name")) == _normalized_place_name(clean_near)
                ]
                anchor = anchor_exact[0] if len(anchor_exact) == 1 else anchors[0]
                matches = await provider_search_places_nearby(
                    map_key,
                    clean_query,
                    anchor,
                    radius_meters=radius,
                    limit=6,
                )
            else:
                matches = await provider_search_places(
                    map_key, clean_query, city=city or "全国", limit=6,
                )
            if not matches:
                qualifier = f"（{clean_near}附近 {radius} 米内）" if clean_near else ""
                raise ValueError(f"没有核实到{endpoint}“{clean_query}”{qualifier}")

            # A brand near an anchor commonly has several legitimate branches.
            # Even when one branch has the exact bare brand name, choosing it
            # silently would be arbitrary; let the user pick from real nearby
            # candidates instead.
            if clean_near and len(matches) > 1:
                field = _place_choice_field(
                    f"route_{'origin' if endpoint == '起点' else 'destination'}",
                    f"请选择具体{endpoint}",
                    matches,
                )
                return None, _clarification_action(
                    conversation_id,
                    title="请选择具体地点",
                    prompt=f"查到多个位于“{clean_near}”附近的“{clean_query}”。为避免算错距离，请先选择具体{endpoint}。",
                    fields=[field],
                )
            exact = [
                item for item in matches
                if _normalized_place_name(item.get("name")) == _normalized_place_name(clean_query)
            ]
            if len(exact) == 1:
                return exact[0], None
            if len(matches) > 1:
                field = _place_choice_field(
                    f"route_{'origin' if endpoint == '起点' else 'destination'}",
                    f"请选择具体{endpoint}",
                    matches,
                )
                return None, _clarification_action(
                    conversation_id,
                    title="请选择具体地点",
                    prompt=f"查到多个符合“{clean_query}”的地点。为避免算错距离，请先选择具体{endpoint}。",
                    fields=[field],
                )
            return matches[0], None

        origin, origin_clarification = await resolve("起点", origin_query, origin_near_query)
        if origin_clarification:
            return origin_clarification
        destination, destination_clarification = await resolve(
            "终点", destination_query, destination_near_query,
        )
        if destination_clarification:
            return destination_clarification
        if not origin or not destination:
            raise ValueError("起点或终点没有完成核实")
        if str(origin.get("place_id") or "") == str(destination.get("place_id") or ""):
            raise ValueError("起点和终点解析成了同一个地点，请选择不同地点")

        route = await provider_plan_route(map_key, [origin, destination], optimize=False)
        state = await _load_state()
        candidates = state.setdefault("place_candidates", {})
        candidates[str(origin["place_id"])] = origin
        candidates[str(destination["place_id"])] = destination
        await _save_state(state)
        distance_meters = float(route.get("distance_meters") or 0)
        duration_seconds = float(route.get("duration_seconds") or 0)
        return json.dumps({
            "origin": origin,
            "destination": destination,
            "route": {
                "provider": route.get("provider"),
                "mode": route.get("mode") or "driving",
                "distance_meters": round(distance_meters),
                "distance_kilometers": round(distance_meters / 1000, 1),
                "duration_seconds": round(duration_seconds),
                "duration_minutes": max(1, round(duration_seconds / 60)),
                "fare": route.get("fare") or {},
            },
            "response_constraint": (
                "距离和耗时来自已核实地点之间的真实道路路线；"
                "回答必须使用这里的数值，不得改用网页估算、直线距离或模型猜测。"
            ),
        }, ensure_ascii=False)

    async def prepare_map_recommendation(
        title: str,
        place_ids: list[str],
        action_text: str,
        expected_place_count: int = 2,
    ) -> str:
        """Prepare a clickable map recommendation from verified place IDs.

        action_text is natural, contextual Chinese link copy generated for this answer.
        This tool does not change the user's map until the user clicks the action.
        """
        if not isinstance(place_ids, list) or not 1 <= len(place_ids) <= 12:
            raise ValueError("地图推荐必须包含 1 到 12 个地点 ID")
        state = await _load_state()
        candidates = state.get("place_candidates", {})
        places = []
        seen = set()
        for raw_id in place_ids:
            place_id = str(raw_id or "").strip()
            place = candidates.get(place_id)
            if place_id and place_id not in seen and isinstance(place, dict):
                seen.add(place_id)
                places.append(place)
        if not places:
            raise ValueError("推荐地点均未通过地点服务验证，不能显示到地图")
        expected = max(1, min(12, int(expected_place_count or 2)))
        action = new_action(
            "map_recommendation",
            {
                "title": str(title or "相关地点")[:120],
                "action_text": str(action_text or "在地图中看看这些地点")[:80],
                "places": places,
            },
            requires_confirmation=False,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({
            "ui_action": "map_action",
            "action": action,
            "verified_place_count": len(places),
            "requested_place_count": expected,
            "partial": len(places) < expected,
        }, ensure_ascii=False)

    async def recommend_places_on_map(
        queries: list[str],
        city: str,
        title: str,
        action_text: str,
    ) -> str:
        """Verify model-selected destinations and prepare one terminal map Action."""
        normalized = list(dict.fromkeys(str(item or "").strip() for item in queries if str(item or "").strip()))
        if not 2 <= len(normalized) <= 12:
            raise ValueError("地图推荐需要模型提供 2 到 12 个独立地点名称")
        map_key = str(runtime_env.get("TENCENT_MAP_SERVER_KEY") or runtime_env.get("TENCENT_MAP_KEY") or runtime_env.get("VITE_TENCENT_MAP_KEY") or "")
        selected, all_candidates, missing = await verify_place_queries_parallel(
            provider_search_places,
            map_key,
            normalized,
            city=city or "全国",
            timeout_seconds=float(runtime_env.get("PLACE_LOOKUP_TIMEOUT_SECONDS") or 5),
        )
        if not selected:
            raise ValueError("所有候选地点都未通过真实地点服务核实，不能生成地图")
        state = await _load_state()
        candidates = state.setdefault("place_candidates", {})
        for place in all_candidates:
            candidates[str(place["place_id"])] = place
        action = new_action(
            "map_recommendation",
            {
                "title": str(title or f"{city}推荐地点")[:120],
                "action_text": str(action_text or "在地图中查看这些地点")[:80],
                "places": selected,
            },
            requires_confirmation=False,
        )
        put_action(state, action)
        await _save_state(state)
        verified_count = len(selected)
        requested_count = len(normalized)
        response_constraint = (
            f"实际核实成功 {verified_count}/{requested_count} 个地点；正文只能声称地图显示了 {verified_count} 个。"
        )
        if missing:
            response_constraint += f" 未核实且不得放入地图：{'、'.join(missing)}。"
        return json.dumps({
            "ui_action": "map_action",
            "action": action,
            "verified_place_count": verified_count,
            "requested_place_count": requested_count,
            "partial": bool(missing),
            "unverified_queries": missing,
            "response_constraint": response_constraint,
        }, ensure_ascii=False)

    async def propose_calendar_changes(summary: str, changes: list[dict]) -> str:
        """Prepare create/update/delete changes; the calendar is mutated only after UI confirmation."""
        if not isinstance(changes, list) or not 1 <= len(changes) <= 24:
            raise ValueError("日程变更数量必须在 1 到 24 项之间")
        state = await _load_state()
        candidates = state.get("place_candidates", {})
        normalized = []
        for raw in changes:
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
                    raise ValueError("当前日程已变化，旧日程 ID 已失效；请根据本轮系统提供的当前日程标题和时间重新匹配后再提案")
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
                normalized_event: dict[str, Any] = {}
                if title:
                    normalized_event["title"] = title
                end_value = str(event.get("end_time") or event.get("end") or "").strip()
                if start_value:
                    start = _parse_datetime(start_value)
                    normalized_event["start_time"] = int(start.timestamp())
                    end = _parse_datetime(end_value) if end_value else start + timedelta(hours=1)
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
                place_id = str(event.get("place_id") or event.get("location_place_id") or "").strip()
                location_text = str(event.get("location") or "").strip()
                if location_text and not place_id:
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
                            or _normalized_place_name(candidate.get("name")) in normalized_location
                        )
                    ]
                    if len(matched) == 1:
                        place_id = str(matched[0][0])
                    elif len(matched) > 1:
                        raise ValueError(f"“{location_text}”对应多个已核实地点，请先选择具体地点")
                    else:
                        raise ValueError(f"“{location_text}”必须先通过 search_places 选择真实地点")
                if place_id:
                    place = candidates.get(place_id)
                    if not isinstance(place, dict):
                        raise ValueError(f"地点 ID 未通过本轮地点搜索验证：{place_id}")
                    normalized_event["place"] = place
                    normalized_event["location"] = place.get("address") or place.get("name")
                change["event"] = normalized_event
            normalized.append(change)
        validate_calendar_change_window(state, normalized)
        warnings = calendar_change_warnings(state, normalized)
        action = new_action(
            "calendar_changes",
            {"summary": str(summary or "日程变更")[:300], "changes": normalized, "warnings": warnings},
            requires_confirmation=True,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({"ui_action": "calendar_action", "action": action}, ensure_ascii=False)

    async def propose_meeting(subject: str = "", start_time: str = "", end_time: str = "") -> str:
        """Prepare an editable Tencent Meeting action, preserving missing user details."""
        state = await _load_state()
        action = new_action(
            "meeting_create",
            meeting_action_payload(state, subject, start_time, end_time),
            requires_confirmation=True,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({"ui_action": "side_effect_action", "action": action}, ensure_ascii=False)

    async def propose_image(
        prompt: str,
        parent_action_id: str = "",
        reference_image_urls: list[str] | None = None,
    ) -> str:
        """Generate an image immediately, optionally editing one prior generated version."""
        nonlocal turn_image_group_id
        clean_prompt = str(prompt or "").strip()[:2000]
        if not clean_prompt:
            raise ValueError("生图提示词不能为空")
        state = await _load_state()
        parent = state.get("actions", {}).get(str(parent_action_id or ""))
        references: list[str] = []
        group_id = ""
        if isinstance(parent, dict) and parent.get("kind") == "image_generate":
            parent_payload = parent.get("payload") or {}
            parent_result = parent.get("result") or {}
            reference_url = await resolve_image_reference(parent_result)
            if reference_url.startswith(("https://", "data:image/")):
                references.append(reference_url)
            group_id = str(parent_payload.get("group_id") or parent.get("id") or "")
        elif turn_image_group_id:
            group_id = turn_image_group_id
        for raw_url in reference_image_urls or []:
            url = str(raw_url or "").strip()
            if url.startswith(("https://", "data:image/")) and url not in references:
                references.append(url)
            if len(references) >= 3:
                break
        if not group_id and not references:
            references.extend(turn_visual_references[:3])
        action = new_action(
            "image_generate",
            {
                "prompt": clean_prompt,
                "parent_action_id": str(parent_action_id or ""),
                "group_id": group_id,
                "reference_image_urls": references,
            },
            requires_confirmation=False,
        )
        action["payload"]["group_id"] = group_id or action["id"]
        seal_action_snapshot(action)
        if not turn_image_group_id:
            turn_image_group_id = str(action["payload"]["group_id"])
        now = int(datetime.now().timestamp())
        begin_action_execution(action, owner=f"chat:{action['id']}", now=now)
        put_action(state, action)
        start_provider_call(state, action, now)
        state = await _save_state(state)
        result = await provider_generate_image(runtime_env, clean_prompt, references, user_id=user_id)
        state = await _load_state()
        current = get_action(state, action["id"])
        finish_provider_call(state, current, result, int(datetime.now().timestamp()))
        if result.get("ok"):
            current["result"]["versions"] = image_versions(state, str(current["payload"]["group_id"]))
        state = await _save_state(state)
        action = state["actions"][action["id"]]
        return json.dumps({"ui_action": "side_effect_action", "action": action}, ensure_ascii=False)

    async def collect_page_images(page_url: str, max_images: int = 30) -> str:
        """Collect up to 30 real image candidates from one public HTML page."""
        images = await provider_collect_page_images(page_url, max_images)
        return json.dumps({"page_url": page_url, "images": images, "count": len(images)}, ensure_ascii=False)

    async def rich_search(query: str, image_query: str = "", depth: str = "standard") -> str:
        """Run one planner-shaped rich search per turn, with a persistent result cache."""
        nonlocal rich_search_task, rich_search_invocations
        rich_search_invocations += 1
        if rich_search_task is None:
            clean_query = str(planned_search_query or query or "").strip()[:500]
            clean_image_query = str(planned_image_query or image_query or "").strip()[:500] if media_enabled else ""
            if not clean_query:
                raise ValueError("富搜索查询不能为空")
            clean_depth = depth if depth in {"basic", "standard", "deep"} else "standard"
            target_date = str(time_scope.get("target_date") or "")
            strict_date = bool(time_scope.get("strict_date"))
            cache_input = json.dumps(
                {
                    # Increment whenever cached search metadata semantics change
                    # so an older text-only entry cannot mask new rich media.
                    # Invalidate pre-vision-review entries that can only
                    # restore text/source metadata and therefore make a
                    # previously rich news answer appear permanently
                    # text-only after the media fallback change.
                    "pipeline_version": 5,
                    "identity": re.sub(r"\s+", " ", str(search_cache_identity or clean_query)).strip().casefold()[:4000],
                    "depth": clean_depth,
                    "target_date": target_date,
                    "strict_date": strict_date,
                    "media": media_enabled,
                    "result_limit": search_result_limit,
                    "image_limit": search_image_limit,
                    "parallel_image_search": parallel_image_search,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            cache_key = hashlib.sha256(cache_input.encode("utf-8")).hexdigest()
            cache_namespace = data_namespace("search_cache", str(user_id or "local-user"))

            async def run_once() -> str:
                nonlocal turn_visual_references, rich_search_provider_calls
                metadata = None
                stale_metadata = None
                stale_age = 0
                if store is not None:
                    try:
                        cached_item = await store.aget(cache_namespace, cache_key)
                        cached = cached_item.get("value") if isinstance(cached_item, dict) else getattr(cached_item, "value", None)
                        cached_at = int((cached or {}).get("cached_at") or 0) if isinstance(cached, dict) else 0
                        candidate = cached.get("metadata") if isinstance(cached, dict) else None
                        if cached_at and isinstance(candidate, dict):
                            stale_age = max(0, int(time.time()) - cached_at)
                            stale_metadata = candidate
                            if stale_age <= max(0, int(search_cache_ttl_seconds)):
                                metadata = candidate
                                metadata = {
                                    **metadata,
                                    "media_pending": False,
                                    "cache_hit": True,
                                    "cache_age_seconds": stale_age,
                                }
                                logging.info("rich_search cache_hit key=%s media=%s", cache_key[:12], media_enabled)
                    except Exception:
                        # Search must remain available when the optional cache is unavailable.
                        metadata = None
                if metadata is None:
                    logging.info("rich_search provider_call key=%s media=%s", cache_key[:12], media_enabled)
                    try:
                        async def publish_enriched_media(enriched: dict[str, Any]) -> None:
                            completed = {**enriched, "cache_hit": False, "media_pending": False}
                            if store is not None:
                                try:
                                    await store.aput(cache_namespace, cache_key, {
                                        "cached_at": int(time.time()),
                                        "metadata": completed,
                                    })
                                except Exception:
                                    pass
                            if media_callback is not None:
                                await media_callback(completed)

                        rich_search_provider_calls += 1
                        metadata = await provider_rich_search(
                            runtime_env,
                            clean_query,
                            image_query=clean_image_query,
                            depth=clean_depth,
                            target_date=target_date,
                            strict_date=strict_date,
                            media_callback=publish_enriched_media if progressive_media and media_enabled else None,
                            background_tasks=background_tasks if progressive_media and media_enabled else None,
                            include_media=media_enabled,
                            result_limit=search_result_limit,
                            image_limit=search_image_limit,
                            parallel_queries=parallel_image_search,
                        )
                        metadata = {**metadata, "cache_hit": False}
                    except Exception:
                        stale_limit = max(3600, int(search_cache_ttl_seconds) * 4)
                        if isinstance(stale_metadata, dict) and stale_age <= stale_limit:
                            metadata = {
                                **stale_metadata,
                                "media_pending": False,
                                "cache_hit": True,
                                "stale_cache_hit": True,
                                "cache_age_seconds": stale_age,
                            }
                            logging.warning(
                                "rich_search stale_cache_hit key=%s age=%s",
                                cache_key[:12], stale_age,
                            )
                        else:
                            raise
                    if (
                        store is not None
                        and not metadata.get("media_pending")
                        and not metadata.get("stale_cache_hit")
                    ):
                        try:
                            await store.aput(cache_namespace, cache_key, {
                                "cached_at": int(time.time()),
                                "metadata": metadata,
                            })
                        except Exception:
                            pass
                reviewed_references = [
                    str(item.get("url") or "")
                    for item in metadata.get("media", [])
                    if str(item.get("url") or "").startswith("https://")
                ][:3]
                turn_visual_references = list(dict.fromkeys([*turn_visual_references, *reviewed_references]))[:3]
                return json.dumps({
                    "ui_action": "rich_search_results",
                    "search_results": metadata,
                    "papers": [],
                    "evidence": evidence_for_model(metadata),
                }, ensure_ascii=False)

            rich_search_task = asyncio.create_task(run_once())
        serialized = await rich_search_task
        result = json.loads(serialized)
        metadata = result.get("search_results") if isinstance(result, dict) else None
        if isinstance(metadata, dict):
            search_config = metadata.get("search_config")
            if not isinstance(search_config, dict):
                search_config = {}
            metadata["search_config"] = {
                **search_config,
                "turn_tool_invocations": rich_search_invocations,
                "turn_provider_calls": rich_search_provider_calls,
            }
            logging.info(
                "rich_search turn_audit conversation=%s invocations=%s provider_calls=%s cache_hit=%s",
                conversation_id,
                rich_search_invocations,
                rich_search_provider_calls,
                bool(metadata.get("cache_hit")),
            )
        return json.dumps(result, ensure_ascii=False)

    async def analyze_images_parallel(image_urls: list[str], goal: str) -> str:
        """Evaluate up to 30 images in small isolated concurrent batches."""
        image_urls = list(dict.fromkeys(str(url) for url in image_urls))[:30]
        if not image_urls:
            raise ValueError("至少需要一个图片 URL")
        for url in image_urls:
            if urlparse(url).scheme not in {"http", "https"}:
                raise ValueError("图片 URL 必须使用 http 或 https")
        semaphore = asyncio.Semaphore(4)

        async def inspect(index: int, image_url: str) -> dict:
            async with semaphore:
                try:
                    response = await asyncio.wait_for(
                        model.ainvoke([{"role": "user", "content": [
                            {"type": "text", "text": f"视觉评估目标：{goal}\n简洁返回画面内容、相关性和是否建议采用。"},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ]}]),
                        timeout=45,
                    )
                    return {"index": index, "url": image_url, "analysis": _message_text(getattr(response, "content", ""))[:1200], "ok": True}
                except Exception as exc:
                    return {"index": index, "url": image_url, "analysis": "", "ok": False, "error": str(exc)[:200]}

        results = await asyncio.gather(*(inspect(index, url) for index, url in enumerate(image_urls)))
        return json.dumps({"ui_action": "image_analysis", "analyses": results}, ensure_ascii=False)

    async def search_arxiv(
        topic: str = "",
        limit: int = 5,
        titles: list[str] | None = None,
        author: str = "",
        year: int = 0,
    ) -> str:
        """Search structured academic papers from arXiv."""
        clean_topic = str(topic or "").strip()[:240]
        clean_titles = [str(title).strip()[:240] for title in (titles or []) if str(title).strip()][:8]
        clean_author = str(paper_scope.get("author") or author or "").strip()[:160]
        clean_year = int(paper_scope.get("year") or year or 0)
        requested_limit = int(paper_scope.get("limit") or 0)
        if requested_limit:
            limit = min(max(1, int(limit or requested_limit)), requested_limit)
        if not clean_topic and not clean_titles and not clean_author:
            raise ValueError("论文主题、准确标题或作者至少需要一项")
        papers = await provider_search_arxiv(clean_topic, limit, clean_titles, clean_author, clean_year)
        return json.dumps({"ui_action": "paper_results", "papers": papers, "topic": clean_topic}, ensure_ascii=False)

    async def propose_workflow(title: str, steps: list[dict[str, Any]], reason: str) -> str:
        """Create a user-confirmable persistent multi-step workflow."""
        state = await load_proactive_state(store, user_id)
        mode = str((state.get("preferences") or {}).get("autonomy_mode") or "propose")
        if mode not in {"propose", "low_risk_auto"}:
            raise ValueError("当前主动权限只允许观察或提醒；请先在主动提醒设置中允许提案")
        workflow = create_workflow_proposal(
            state, title=title, steps=steps, reason=reason, now=int(time.time()),
        )
        await save_proactive_state(store, state, user_id)
        return json.dumps({
            "workflow_proposal": workflow,
            "message": "工作流提案已加入主动提醒中心，只有用户确认后才会激活",
        }, ensure_ascii=False)

    async def ask_user_clarification(
        title: str,
        prompt: str,
        fields: list[ClarificationFieldInput],
    ) -> str:
        """Present one compact, structured clarification card instead of prose interrogation."""
        allowed = {"single", "multi", "boolean", "text", "date", "time", "datetime"}
        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(fields or []):
            if isinstance(raw, BaseModel):
                raw = raw.model_dump()
            if not isinstance(raw, dict):
                continue
            field_type = str(raw.get("type") or "text").strip().lower()
            options = list(dict.fromkeys(
                str(option).strip()[:120]
                for option in (raw.get("options") or [])
                if str(option).strip()
            ))[:8]
            # Enforce the product-wide interaction hierarchy even if a model
            # asks for a text box while already supplying finite choices.
            if len(options) >= 2 and field_type not in {"single", "multi"}:
                field_type = "single"
            if field_type not in allowed:
                field_type = "single" if len(options) >= 2 else "text"
            field_id = re.sub(r"[^a-zA-Z0-9_-]", "-", str(raw.get("id") or f"field-{index + 1}"))[:48] or f"field-{index + 1}"
            label = str(raw.get("label") or "请补充").strip()[:80]
            item: dict[str, Any] = {
                "id": field_id,
                "label": label,
                "type": field_type,
                "required": bool(raw.get("required", True)),
            }
            if field_type in {"single", "multi"}:
                if len(options) < 2:
                    continue
                item["options"] = options
            elif field_type == "text":
                item["placeholder"] = str(raw.get("placeholder") or "请填写").strip()[:120]
            normalized.append(item)
            if len(normalized) >= 8:
                break
        if not normalized:
            raise ValueError("至少需要一个有效的澄清字段")
        return _clarification_action(
            conversation_id,
            title=str(title or "请补充几个信息"),
            prompt=str(prompt or "为了更准确地帮你处理，请选择或补充以下信息。"),
            fields=normalized,
        )

    definitions = [
        (search_places, "search_places", "使用腾讯地点服务搜索真实地点，返回可安全用于地图和日程的 place_id。推荐地点、景点、餐馆或含地点日程前必须调用。"),
        (search_places_batch, "search_places_batch", "多地点推荐必须使用：把每个地点作为独立 query 核实，并从每组选择一个最匹配的真实 place_id。"),
        (recommend_nearby_places_on_map, "recommend_nearby_places_on_map", "用户要找某个已知地点、当前位置或日程地点附近的餐馆、早餐店、酒店、商店、景点等真实地点时使用。传入完整明确的 anchor_query 与要找的类别 query；工具优先复用 Makers 工作区和日程中已核实的参照地点坐标，再调用腾讯位置附近检索，并一次生成地图 Action。用户没有明确距离时不要自行缩小 radius_meters，保持默认 2000 米且 strict_radius=false；只有用户明确说“X 米内”时才传该距离并设 strict_radius=true。不要先用 rich_search 发现地点，也不要把“某地附近某类别”拼成普通 search_places 查询。"),
        (plan_route_between_places, "plan_route_between_places", "查询两个真实地点之间的道路距离、驾车耗时或费用时必须使用。工具会自行核实起终点并调用真实路线服务，禁止先用网页搜索估算距离。若地点形如“301医院附近的锦江之星”，把 destination_query 传“锦江之星”、destination_near_query 传“北京301医院”；多个候选会自动生成单选卡让用户选择。"),
        (prepare_map_recommendation, "prepare_map_recommendation", "从已核实的真实 ID 生成可点击地图推荐；多地点推荐必须传 expected_place_count 和每组各一个 ID，数量不足时继续核实。只准备 Action，不直接更新地图。"),
        (recommend_places_on_map, "recommend_places_on_map", "模型驱动的多地点推荐组合工具：根据用户目标自行给出 2-12 个具体地点名称、城市、自然地图标题和自然链接文案；工具逐个核实并准备最终地图 Action。用户指定数量时 queries 必须严格等于该数量。"),
        (propose_calendar_changes, "propose_calendar_changes", "必须用此工具准备日程新增、更新或删除提案并生成确认卡；不要只在正文里口头询问。格式示例：changes=[{operation:'create',event:{title:'游览北海公园',start_time:'2026-07-16T09:00:00+08:00',end_time:'2026-07-16T10:00:00+08:00',place_id:'地点工具返回的ID'}}]。更新/删除还要传 schedule_id。用户点击确认前不会真正写入。"),
        (propose_meeting, "propose_meeting", "准备可编辑的腾讯会议确认卡；即使主题、开始时间或结束时间不完整也要调用本工具，把未知值留空，不要在正文中连续追问多个条件。确认卡会让用户逐项补齐、检查冲突并确认，之后才由后台通过腾讯会议官方 MCP Skill 执行。"),
        (propose_image, "propose_image", "直接调用混元生图并返回图片，不要询问确认。现实人物、地点或物体可先用 rich_search 获取经 HY-Vision 审核的图片 URL，再通过 reference_image_urls（最多 3 张）作为视觉参考；修改历史版本时传 parent_action_id。"),
        (collect_page_images, "collect_page_images", "从一个公开网页提取最多 30 张真实图片候选，网页图片不足时返回实际数量。"),
        (rich_search, "rich_search", "项目 v4.2 富搜索。搜索前的独立 LLM 规划器已经合并本轮事实查询，并判断图片是否有助于理解；同一轮无论怎样改写参数都只执行一次 Provider 搜索。"),
        (analyze_images_parallel, "analyze_images_parallel", "并行视觉评估最多 30 张图片；单张失败不影响其他图片。"),
        (search_arxiv, "search_arxiv", "补充获取 arXiv 可下载结果。富搜索已找到论文时，把准确标题列表一次性传给 titles；按作者和年份查找时分别传 author（英文署名）与 year，不要把作者年份混在宽泛 topic 中。工具会严格过滤作者/年份与标题，每轮最多调用一次。"),
        (propose_workflow, "propose_workflow", "用户明确要求建立跨时间、多步骤的持续提醒或计划时创建工作流提案。steps 每项包含 offset_minutes、title、body、action_prompt，可用 depends_on=['step_1'] 建立 DAG 依赖；失败时需要回退提示的步骤可增加 compensation={title,body,action_prompt}。默认按顺序依赖。必须由用户确认后才会激活，依赖步骤需用户标记完成后才推进。"),
        (ask_user_clarification, "ask_user_clarification", "所有问答场景统一的必要信息收集入口。只有缺少该字段会阻断所有安全有用的回答，或无法唯一确定真实副作用对象时才能调用；“知道后更好”、可选偏好和用户尚未决定都不得调用，应直接在正文给出 2–3 套带假设与取舍的方案。这条边界适用于所有主题，禁止套用固定画像问题。本轮最多调用一次并只收最少必要字段；能由当前上下文、已核实结果、其他字段或安全默认值推导出的字段不得再问。有限候选优先 single/multi，能用是/否表达就用 boolean，只缺日期用 date、日期已知只缺时刻用 time、两者都缺才用 datetime，仅答案无法枚举时用 text。卡片提交后由前端自动把答案作为对话补充信息继续推理，不要要求用户再次发送，也不要重复询问已提交字段。"),
    ]
    meeting_ready = bool(str(runtime_env.get("TENCENT_MEETING_TOKEN") or "").strip())
    if not meeting_ready:
        definitions = [definition for definition in definitions if definition[1] != "propose_meeting"]
    active = enabled_skills if enabled_skills is not None else {
        "web-search", "vision", "image-studio", "maps", "calendar",
        "proactive-agent", "paper-reading", "tencent-meeting",
    }
    active = set(active)
    if "calendar" not in active:
        active.discard("tencent-meeting")
    tool_skills = {
        "search_places": "maps",
        "search_places_batch": "maps",
        "recommend_nearby_places_on_map": "maps",
        "plan_route_between_places": "maps",
        "prepare_map_recommendation": "maps",
        "recommend_places_on_map": "maps",
        "propose_calendar_changes": "calendar",
        "propose_meeting": "tencent-meeting",
        "propose_image": "image-studio",
        "collect_page_images": "web-search",
        "rich_search": "web-search",
        "analyze_images_parallel": "vision",
        "search_arxiv": "paper-reading",
        "propose_workflow": "proactive-agent",
        "ask_user_clarification": "core",
    }
    definitions = [definition for definition in definitions if tool_skills.get(definition[1]) == "core" or tool_skills.get(definition[1]) in active]
    return [StructuredTool.from_function(coroutine=fn, name=name, description=description) for fn, name, description in definitions]
