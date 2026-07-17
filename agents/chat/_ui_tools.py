"""Verified production tools for the Makers travel workspace."""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from langchain_core.tools import StructuredTool

from ..shared.tencent_location import search_verified_places as provider_search_places
from ..shared.web_media import collect_page_images as provider_collect_page_images
from ..shared.rich_search import evidence_for_model, rich_search as provider_rich_search
from ..shared.side_effects import generate_image as provider_generate_image, resolve_image_reference
from ..shared.arxiv import search_arxiv as provider_search_arxiv
from ..shared.intelligence import load_intelligence_state, propose_memory as create_memory_proposal, save_intelligence_state
from ..shared.proactive import load_proactive_state, propose_workflow as create_workflow_proposal, save_proactive_state
from ..shared.workspace import (
    begin_action_execution,
    finish_provider_call,
    get_action,
    image_versions,
    load_user_workspace,
    new_action,
    put_action,
    save_user_workspace,
    seal_action_snapshot,
    start_provider_call,
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


def build_production_tools(
    model, *, store=None, conversation_id: str = "", env: dict | None = None,
    paper_constraints: dict | None = None,
    temporal_context: dict[str, Any] | None = None,
    progressive_media: bool = False,
    media_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    background_tasks: list[asyncio.Task] | None = None,
    user_id: str = "local-user",
) -> list[StructuredTool]:
    runtime_env = env or {}
    paper_scope = paper_constraints or {}
    time_scope = temporal_context or {}
    # Per-request handoff: rich-search media can be consumed by image
    # generation without asking the model to copy fragile URLs between tools.
    turn_visual_references: list[str] = []
    turn_image_group_id = ""

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
        if len(places) < expected:
            raise ValueError(
                f"推荐仅包含 {len(places)} 个有效地点，但回答需要 {expected} 个；"
                "请用 search_places_batch 分别核实每个地点，并从每组选择一个 place_id"
            )
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
        return json.dumps({"ui_action": "map_action", "action": action}, ensure_ascii=False)

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
        selected = []
        missing = []
        all_candidates = []
        for query in normalized:
            try:
                matches = await provider_search_places(map_key, query, city=city or "全国", limit=3)
            except Exception:
                matches = []
            if matches:
                selected.append(matches[0])
                all_candidates.extend(matches)
            else:
                missing.append(query)
        if missing:
            raise ValueError(f"以下地点未核实成功，请换用更精确的官方名称后重试：{'、'.join(missing)}")
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
        return json.dumps({"ui_action": "map_action", "action": action}, ensure_ascii=False)

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
            if operation in {"update", "delete"}:
                schedule_id = str(raw.get("schedule_id") or "")
                if schedule_id not in state.get("schedules", {}):
                    raise ValueError(f"找不到目标日程：{schedule_id}")
                change["schedule_id"] = schedule_id
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
                if start_value:
                    start = _parse_datetime(start_value)
                    normalized_event["start_time"] = int(start.timestamp())
                    end_value = str(event.get("end_time") or event.get("end") or "").strip()
                    end = _parse_datetime(end_value) if end_value else start + timedelta(hours=1)
                    if end <= start:
                        raise ValueError(f"日程结束时间必须晚于开始时间：{title}")
                    normalized_event["duration_minutes"] = max(1, int((end - start).total_seconds() // 60))
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
        action = new_action(
            "calendar_changes",
            {"summary": str(summary or "日程变更")[:300], "changes": normalized},
            requires_confirmation=True,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({"ui_action": "calendar_action", "action": action}, ensure_ascii=False)

    async def propose_meeting(subject: str, start_time: str, end_time: str) -> str:
        """Prepare a Tencent Meeting creation action using the legacy tmeet CLI provider."""
        start = _parse_datetime(start_time)
        end = _parse_datetime(end_time)
        if end <= start:
            raise ValueError("会议结束时间必须晚于开始时间")
        state = await _load_state()
        action = new_action(
            "meeting_create",
            {"subject": str(subject or "腾讯会议")[:120], "start_time": start.isoformat(), "end_time": end.isoformat()},
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
            if url.startswith("https://") and url not in references:
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
        """Run the established rich search and return trusted source/media IDs."""
        nonlocal turn_visual_references
        metadata = await provider_rich_search(
            runtime_env, str(query or "").strip(),
            image_query=str(image_query or "").strip(), depth=depth,
            target_date=str(time_scope.get("target_date") or ""),
            strict_date=bool(time_scope.get("strict_date")),
            media_callback=media_callback if progressive_media else None,
            background_tasks=background_tasks if progressive_media else None,
        )
        turn_visual_references = [
            str(item.get("url") or "")
            for item in metadata.get("media", [])
            if str(item.get("url") or "").startswith("https://")
        ][:3]
        return json.dumps({
            "ui_action": "rich_search_results",
            "search_results": metadata,
            # Search result pages are evidence, not automatically trustworthy
            # reader assets. Exact titles are resolved by search_arxiv next.
            "papers": [],
            "evidence": evidence_for_model(metadata),
        }, ensure_ascii=False)

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

    async def propose_memory(key: str, value: str, reason: str, sensitivity: str = "normal") -> str:
        """Create a user-confirmable durable memory; never writes memory directly."""
        state = await load_intelligence_state(store, user_id)
        proposal = create_memory_proposal(
            state, str(key or ""), str(value or ""), str(reason or ""), sensitivity=str(sensitivity or "normal"),
        )
        await save_intelligence_state(store, state, user_id)
        return json.dumps({
            "memory_proposal": proposal,
            "message": "记忆提案已加入记忆中心，只有用户确认后才会生效",
        }, ensure_ascii=False)

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
        (propose_meeting, "propose_meeting", "准备创建腾讯会议的确认操作；确认后使用旧版 tmeet CLI 流程执行。"),
        (propose_image, "propose_image", "直接调用混元生图并返回图片，不要询问确认。现实人物、地点或物体可先用 rich_search 获取经 HY-Vision 审核的图片 URL，再通过 reference_image_urls（最多 3 张）作为视觉参考；修改历史版本时传 parent_action_id。"),
        (collect_page_images, "collect_page_images", "从一个公开网页提取最多 30 张真实图片候选，网页图片不足时返回实际数量。"),
        (rich_search, "rich_search", "项目 v4.2 成熟富搜索：抓取结果网页图片及上下文，经 HY-Vision 多模态模型剔除广告和无关图后，返回可信来源与标准 Markdown 图片候选。历史文化、地点介绍、推荐或图文回答时使用。"),
        (analyze_images_parallel, "analyze_images_parallel", "并行视觉评估最多 30 张图片；单张失败不影响其他图片。"),
        (search_arxiv, "search_arxiv", "补充获取 arXiv 可下载结果。富搜索已找到论文时，把准确标题列表一次性传给 titles；按作者和年份查找时分别传 author（英文署名）与 year，不要把作者年份混在宽泛 topic 中。工具会严格过滤作者/年份与标题，每轮最多调用一次。"),
        (propose_memory, "propose_memory", "用户明确要求记住长期偏好或稳定事实时创建可确认记忆提案。只提案，不直接写入；一次性、短期或敏感信息不要擅自记忆。"),
        (propose_workflow, "propose_workflow", "用户明确要求建立跨时间、多步骤的持续提醒或计划时创建工作流提案。steps 每项包含 offset_minutes、title、body、action_prompt，可用 depends_on=['step_1'] 建立 DAG 依赖；失败时需要回退提示的步骤可增加 compensation={title,body,action_prompt}。默认按顺序依赖。必须由用户确认后才会激活，依赖步骤需用户标记完成后才推进。"),
    ]
    return [StructuredTool.from_function(coroutine=fn, name=name, description=description) for fn, name, description in definitions]
