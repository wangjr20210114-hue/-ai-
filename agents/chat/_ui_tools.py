"""Verified production tools for the Makers travel workspace."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from langchain_core.tools import StructuredTool

from .._shared.tencent_location import search_verified_places as provider_search_places
from .._shared.web_media import collect_page_images as provider_collect_page_images
from .._shared.rich_search import evidence_for_model, rich_search as provider_rich_search
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
    new_action,
    put_action,
    save_user_workspace,
    seal_action_snapshot,
    start_provider_call,
    validate_calendar_change_window,
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

    async def propose_meeting(subject: str, start_time: str, end_time: str) -> str:
        """Prepare a confirmed Tencent Meeting action for the official MCP Skill."""
        start = _parse_datetime(start_time)
        end = _parse_datetime(end_time)
        if end <= start:
            raise ValueError("会议结束时间必须晚于开始时间")
        state = await _load_state()
        meeting_change = [{"operation": "create", "event": {
            "title": str(subject or "腾讯会议")[:120],
            "start_time": int(start.timestamp()),
            "duration_minutes": max(1, int((end - start).total_seconds() // 60)),
            "category": "meeting",
        }}]
        validate_calendar_change_window(state, meeting_change)
        warnings = calendar_change_warnings(state, meeting_change)
        action = new_action(
            "meeting_create",
            {"subject": str(subject or "腾讯会议")[:120], "start_time": start.isoformat(), "end_time": end.isoformat(), "warnings": warnings},
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
        nonlocal rich_search_task
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
            cache_namespace = ("yuanbao_search_cache_v1", str(user_id or "local-user"))

            async def run_once() -> str:
                nonlocal turn_visual_references
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
        return await rich_search_task

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

    definitions = [
        (search_places, "search_places", "使用腾讯地点服务搜索真实地点，返回可安全用于地图和日程的 place_id。推荐地点、景点、餐馆或含地点日程前必须调用。"),
        (search_places_batch, "search_places_batch", "多地点推荐必须使用：把每个地点作为独立 query 核实，并从每组选择一个最匹配的真实 place_id。"),
        (prepare_map_recommendation, "prepare_map_recommendation", "从已核实的真实 ID 生成可点击地图推荐；多地点推荐必须传 expected_place_count 和每组各一个 ID，数量不足时继续核实。只准备 Action，不直接更新地图。"),
        (recommend_places_on_map, "recommend_places_on_map", "模型驱动的多地点推荐组合工具：根据用户目标自行给出 2-12 个具体地点名称、城市、自然地图标题和自然链接文案；工具逐个核实并准备最终地图 Action。用户指定数量时 queries 必须严格等于该数量。"),
        (propose_calendar_changes, "propose_calendar_changes", "必须用此工具准备日程新增、更新或删除提案并生成确认卡；不要只在正文里口头询问。格式示例：changes=[{operation:'create',event:{title:'游览北海公园',start_time:'2026-07-16T09:00:00+08:00',end_time:'2026-07-16T10:00:00+08:00',place_id:'地点工具返回的ID'}}]。更新/删除还要传 schedule_id。用户点击确认前不会真正写入。"),
        (propose_meeting, "propose_meeting", "准备创建腾讯会议的确认操作；用户确认后由后台通过腾讯会议官方 MCP Skill 执行。"),
        (propose_image, "propose_image", "直接调用混元生图并返回图片，不要询问确认。现实人物、地点或物体可先用 rich_search 获取经 HY-Vision 审核的图片 URL，再通过 reference_image_urls（最多 3 张）作为视觉参考；修改历史版本时传 parent_action_id。"),
        (collect_page_images, "collect_page_images", "从一个公开网页提取最多 30 张真实图片候选，网页图片不足时返回实际数量。"),
        (rich_search, "rich_search", "项目 v4.2 富搜索。搜索前的独立 LLM 规划器已经合并本轮事实查询，并判断图片是否有助于理解；同一轮无论怎样改写参数都只执行一次 Provider 搜索。"),
        (analyze_images_parallel, "analyze_images_parallel", "并行视觉评估最多 30 张图片；单张失败不影响其他图片。"),
        (search_arxiv, "search_arxiv", "补充获取 arXiv 可下载结果。富搜索已找到论文时，把准确标题列表一次性传给 titles；按作者和年份查找时分别传 author（英文署名）与 year，不要把作者年份混在宽泛 topic 中。工具会严格过滤作者/年份与标题，每轮最多调用一次。"),
        (propose_workflow, "propose_workflow", "用户明确要求建立跨时间、多步骤的持续提醒或计划时创建工作流提案。steps 每项包含 offset_minutes、title、body、action_prompt，可用 depends_on=['step_1'] 建立 DAG 依赖；失败时需要回退提示的步骤可增加 compensation={title,body,action_prompt}。默认按顺序依赖。必须由用户确认后才会激活，依赖步骤需用户标记完成后才推进。"),
    ]
    legacy_meeting_ready = all(str(runtime_env.get(key) or "").strip() for key in (
        "TENCENT_MEETING_SECRET_ID", "TENCENT_MEETING_SECRET_KEY", "TENCENT_MEETING_APP_ID",
        "TENCENT_MEETING_SDK_ID", "TENCENT_MEETING_USER_ID",
    ))
    meeting_ready = bool(str(runtime_env.get("TENCENT_MEETING_TOKEN") or "").strip()) or legacy_meeting_ready
    if not meeting_ready:
        definitions = [definition for definition in definitions if definition[1] != "propose_meeting"]
    return [StructuredTool.from_function(coroutine=fn, name=name, description=description) for fn, name, description in definitions]
