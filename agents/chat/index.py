"""LangGraph chat endpoint running on the EdgeOne Makers agent runtime."""

import asyncio
import contextlib
import json
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage

from ._graph import build_graph
from ._llm import get_model
from ._rich_search import create_rich_search_tool, search_meta_from_tool_content
from ._travel import (
    analyze_travel_request,
    build_itinerary,
    contains_internal_tool_protocol,
    deterministic_places_answer,
    enrich_itinerary_places,
    ground_itinerary_answer_date,
    ensure_itinerary_in_answer,
    itinerary_prompt,
    load_profile,
    load_recent_conversation,
    looks_like_travel,
    merge_profile,
    places_prompt,
    profile_prompt,
    save_itinerary,
    search_places,
)

SYSTEM_PROMPT = (
    "你是元宝，一个可靠、主动、简洁的中文智能助手。使用标准 Markdown 回复。"
    "对实质性问题优先调用平台提供的 web_search；工具会返回网页、公众号、百科等来源，"
    "以及与来源绑定的图片、视频和正文摘要。先排除广告、低质量和与用户问题无关的候选。"
    "只引用工具返回的真实来源 URL。只在媒体与当前段落高度相关时插入："
    "图片使用 ![准确描述](media中的原始URL)，视频使用 [视频：标题](media中的原始URL)。"
    "地点、旅行、人物、产品或教程问题存在高度相关媒体时，通常选择 1-3 个穿插到对应段落。"
    "不要输出内部媒体 ID，不要使用 [[image:...]]，不要猜测或改写媒体 URL。"
    "回答正文到结论即结束，禁止在正文中输出‘你还可以问’‘后续问题’‘猜你想问’等追问建议；"
    "追问建议由系统在正文之外单独生成和展示。"
)

HEARTBEAT_SECONDS = 5
MAX_GRAPH_RECURSION = 8

INLINE_FOLLOW_UP_SECTION = re.compile(
    r"(?:^|\n)\s{0,3}(?:#{1,6}\s*)?"
    r"(?:后续(?:问题|追问)|延伸问题|接下来(?:可以|还可以)问|猜你想(?:继续)?问|"
    r"你可能还想问|你还可以(?:继续)?问|可继续追问)"
    r"\s*[:：]?\s*(?:\n|$)",
    re.IGNORECASE,
)


def _text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _strip_inline_follow_up_section(content: str) -> str:
    """Keep UI follow-up suggestions out of the answer and checkpoint."""

    match = INLINE_FOLLOW_UP_SECTION.search(content)
    return content[:match.start()].rstrip() if match else content


def _usage_values(message) -> tuple[int, int, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        return 0, 0, 0
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    return input_tokens, output_tokens, total_tokens


async def _generate_follow_ups(model, user_message: str, answer: str) -> list[str]:
    """Generate UI-only follow-ups; these are never appended to answer Markdown."""

    if not answer.strip():
        return []
    prompt = (
        "基于用户问题和助手回答，生成恰好 3 个用户最可能继续追问的简短问题。"
        "问题应具体、互不重复、可直接作为用户输入。只返回 JSON 字符串数组，不要标题、编号或解释。\n\n"
        f"用户问题：{user_message[:1000]}\n\n助手回答：{answer[:6000]}"
    )
    try:
        response = await asyncio.wait_for(
            model.ainvoke([
                SystemMessage(content="你只负责生成对话界面的可点击追问建议。"),
                HumanMessage(content=prompt),
            ]),
            timeout=45,
        )
        raw = _text_content(getattr(response, "content", ""))
        match = re.search(r"\[[\s\S]*\]", raw)
        value = json.loads(match.group(0)) if match else []
    except Exception:
        return []
    follow_ups: list[str] = []
    for item in value if isinstance(value, list) else []:
        question = re.sub(r"^\s*(?:[-*]|\d+[.、])\s*", "", str(item)).strip()
        if not question or question in follow_ups:
            continue
        follow_ups.append(question[:80])
        if len(follow_ups) == 3:
            break
    return follow_ups if len(follow_ups) == 3 else []


async def _persist_follow_ups(
    graph,
    config: dict,
    follow_ups: list[str],
    answer: str,
    map_places: list[dict] | None = None,
    itinerary: dict | None = None,
) -> None:
    """Persist UI metadata on the last AI message for deterministic refresh."""

    try:
        state = await graph.aget_state(config)
        messages = (getattr(state, "values", {}) or {}).get("messages", [])
        last_ai = next(
            (item for item in reversed(messages) if getattr(item, "type", "") == "ai"),
            None,
        )
        if last_ai is None:
            return
        additional = {
            **(getattr(last_ai, "additional_kwargs", {}) or {}),
            "follow_ups": follow_ups,
        }
        if map_places:
            additional["map_places"] = map_places[:12]
        if itinerary:
            additional["travel_plan"] = {
                key: itinerary.get(key)
                for key in (
                    "schema_version",
                    "id",
                    "city",
                    "start_date",
                    "days",
                    "tentative_date",
                    "schedules",
                )
            }
        updated = last_ai.model_copy(update={
            "content": _strip_inline_follow_up_section(answer),
            "additional_kwargs": additional,
        })
        await graph.aupdate_state(config, {"messages": [updated]})
    except Exception:
        # Buttons still work in the active response even if optional metadata
        # persistence is unavailable in an older runtime adapter.
        pass


async def handler(ctx):
    body = ctx.request.body or {}
    message = body.get("message") or body.get("text") or ""
    if not message:
        return {"error": "'message' is required"}, 400

    model = get_model(ctx.env)
    user_id = str(body.get("user_id") or ctx.conversation_id or "anonymous")

    # Reuse Makers-provided tools; no self-hosted search proxy or manual token flow.
    structured_tool = None
    platform_tools_by_name = {}
    tool_setup_error = ""
    if ctx.tools and body.get("web_search") is not False:
        try:
            from langchain_core.tools import StructuredTool

            platform_tools = list(
                ctx.tools.to_langchain_tools(
                    StructuredTool,
                    names=["web_search", "browser_fetch", "browser_evaluate"],
                )
            )
            structured_tool = StructuredTool
            platform_tools_by_name = {tool.name: tool for tool in platform_tools}
        except Exception as exc:
            tool_setup_error = f"平台工具初始化失败：{exc}"

    async def gen():
        queue: asyncio.Queue = asyncio.Queue()
        done = object()
        usage = [0, 0, 0]

        profile = await load_profile(ctx.store.langgraph_store, user_id)
        travel_analysis = {}
        travel_places = []
        map_places_for_ui = []
        itinerary = None
        travel_context = profile_prompt(profile)
        if looks_like_travel(str(message)):
            yield ctx.utils.sse({
                "type": "search_progress",
                "stage": "place_intent",
                "message": "正在结合记忆识别目的地和旅行偏好…",
            })
            recent_context = await load_recent_conversation(
                ctx.store.langgraph_checkpointer,
                ctx.conversation_id,
            )
            travel_analysis = await analyze_travel_request(
                model,
                str(message),
                profile,
                recent_context=recent_context,
            )
            memory_updates = travel_analysis.get("memory_updates")
            if isinstance(memory_updates, dict) and memory_updates:
                profile = await merge_profile(
                    ctx.store.langgraph_store,
                    user_id,
                    memory_updates,
                    source_conversation_id=ctx.conversation_id,
                )
            city = str(travel_analysis.get("city") or "")
            query = str(travel_analysis.get("query") or "景点")
            if city:
                yield ctx.utils.sse({
                    "type": "search_progress",
                    "stage": "place_database",
                    "message": f"正在地点专库检索 {city} · {query}，未命中时自动切换腾讯地图…",
                })
                requested_limit = max(
                    int(travel_analysis.get("count") or 6),
                    int(travel_analysis.get("days") or 1) * 3
                    if travel_analysis.get("wants_itinerary") else 1,
                )
                travel_places = await search_places(
                    ctx.env,
                    city=city,
                    query=query,
                    category=str(travel_analysis.get("category") or "other"),
                    limit=min(requested_limit, 20),
                )
                travel_places = await enrich_itinerary_places(
                    ctx.env,
                    travel_analysis,
                    profile,
                    travel_places,
                )
                yield ctx.utils.sse({
                    "type": "search_progress",
                    "stage": "place_results",
                    "message": (
                        f"地点检索完成：找到 {len(travel_places)} 个可验证地点，正在个性化排序…"
                        if travel_places else
                        "地点专库和腾讯地图暂未命中，继续使用联网资料补充。"
                    ),
                })
            travel_context = profile_prompt(profile) + "\n" + places_prompt(travel_analysis, travel_places)
            if travel_places and travel_analysis.get("wants_itinerary"):
                itinerary = build_itinerary(user_id, travel_analysis, travel_places, profile)
                confirmed_schedules = await save_itinerary(
                    ctx.store.langgraph_store,
                    user_id,
                    itinerary,
                )
                # Only announce records that were successfully read back from
                # the same store used by the calendar snapshot endpoint.
                itinerary["schedules"] = confirmed_schedules
                travel_context += itinerary_prompt(itinerary)
                map_places_for_ui = [
                    {
                        "id": (schedule.get("extra") or {}).get("place_id") or schedule.get("id"),
                        "name": schedule.get("title"),
                        "address": schedule.get("location"),
                        "lat": (schedule.get("extra") or {}).get("lat"),
                        "lng": (schedule.get("extra") or {}).get("lng"),
                        "source": (schedule.get("extra") or {}).get("place_source"),
                    }
                    for schedule in itinerary.get("schedules", [])[:12]
                    if isinstance(schedule, dict)
                ]
                yield ctx.utils.sse({
                    "type": "travel_plan",
                    "plan": itinerary,
                    "schedules": itinerary["schedules"],
                })
            elif travel_places:
                map_places_for_ui = [
                    {
                        "id": place.get("id"),
                        "name": place.get("name"),
                        "address": place.get("address"),
                        "lat": place.get("lat"),
                        "lng": place.get("lng"),
                        "source": place.get("source"),
                    }
                    for place in travel_places[:12]
                ]
            if map_places_for_ui:
                yield ctx.utils.sse({
                    "type": "map_places",
                    "title": f"{city}行程地点" if itinerary else f"{city}推荐地点",
                    "places": map_places_for_ui,
                })

        async def report_search_progress(event):
            await queue.put(ctx.utils.sse({"type": "search_progress", **event}))

        all_tools = []
        if structured_tool is not None and platform_tools_by_name.get("web_search"):
            all_tools = [
                create_rich_search_tool(
                    structured_tool,
                    platform_tools_by_name["web_search"],
                    platform_tools_by_name.get("browser_fetch"),
                    platform_tools_by_name.get("browser_evaluate"),
                    vision_model=model,
                    progress=report_search_progress,
                )
            ]
        graph = build_graph(
            model,
            [] if travel_places else all_tools,
            SYSTEM_PROMPT
            + (
                "\n\n本轮已经由系统完成地点检索，未向你提供任何工具。"
                "禁止尝试调用 web_search 或输出任何 tool_call 标记；"
                + (
                    "把下方已落库行程作为不可更改的事实，自由、自然地回答用户。"
                    "回答必须完整包含正式行程及其日期时间，并说明已经写入右侧日历；"
                    "除此之外不要套固定模板，可以充分补充游玩理由、节奏、交通、美食和注意事项。"
                    if itinerary
                    else "直接根据下方可验证地点回答，并说明地点已显示在右侧地图；不得声称写入了日历。"
                )
                if travel_places else ""
            )
            + "\n\n旅行记忆与地点上下文：\n"
            + travel_context,
            checkpointer=ctx.store.langgraph_checkpointer,
            store=ctx.store.langgraph_store,
        )

        async def produce():
            answer_chunks: list[str] = []
            if tool_setup_error:
                await queue.put(
                    ctx.utils.sse({"type": "error_message", "content": tool_setup_error})
                )
            try:
                config = {
                    "configurable": {"thread_id": ctx.conversation_id},
                    "recursion_limit": MAX_GRAPH_RECURSION,
                }
                async for event in graph.astream(
                    {"messages": [{"role": "user", "content": message}]},
                    config=config,
                    stream_mode="messages",
                ):
                    if ctx.request.signal.is_set():
                        break

                    streamed_message, event_metadata = event
                    input_tokens, output_tokens, total_tokens = _usage_values(streamed_message)
                    usage[0] = max(usage[0], input_tokens)
                    usage[1] = max(usage[1], output_tokens)
                    usage[2] = max(usage[2], total_tokens)

                    # Nested vision-review model chunks belong to the internal
                    # media safety gate and must never appear in the user answer.
                    message_type = getattr(streamed_message, "type", "")
                    graph_node = (
                        event_metadata.get("langgraph_node", "")
                        if isinstance(event_metadata, dict)
                        else ""
                    )
                    if graph_node == "prefetch" and message_type != "tool":
                        continue
                    event_tags = (
                        event_metadata.get("tags", [])
                        if isinstance(event_metadata, dict)
                        else []
                    )
                    if "internal_vision_review" in event_tags:
                        continue

                    if message_type == "tool":
                        raw_tool_content = getattr(streamed_message, "content", "")
                        search_meta = search_meta_from_tool_content(raw_tool_content)
                        tool_event = {
                            "type": "tool_result",
                            "name": getattr(streamed_message, "name", ""),
                            "content": (
                                f"找到 {search_meta['total']} 个来源、"
                                f"{len(search_meta['media'])} 个媒体候选"
                                if search_meta
                                else _text_content(raw_tool_content)[:500]
                            ),
                        }
                        if search_meta:
                            tool_event["search_results"] = search_meta
                        await queue.put(
                            ctx.utils.sse(tool_event)
                        )
                        continue

                    tool_calls = getattr(streamed_message, "tool_calls", None) or []
                    if tool_calls:
                        for tool_call in tool_calls:
                            if not isinstance(tool_call, dict):
                                continue
                            name = tool_call.get("name", "")
                            # Deterministic prefetch already emitted detailed live
                            # progress while it was running; do not overwrite it
                            # with a late generic tool_call event.
                            if str(tool_call.get("id") or "").startswith("prefetch-"):
                                continue
                            await queue.put(ctx.utils.sse({"type": "tool_call", "name": name}))
                        continue

                    content = _text_content(getattr(streamed_message, "content", ""))
                    if content:
                        answer_chunks.append(content)
                        if not travel_places:
                            await queue.put(
                                ctx.utils.sse({"type": "ai_response", "content": content})
                            )
                if not ctx.request.signal.is_set():
                    answer = _strip_inline_follow_up_section("".join(answer_chunks))
                    if travel_places:
                        if itinerary:
                            answer = ensure_itinerary_in_answer(
                                answer,
                                travel_analysis,
                                travel_places,
                                itinerary,
                            )
                        elif not answer.strip() or contains_internal_tool_protocol(answer):
                            answer = deterministic_places_answer(
                                travel_analysis,
                                travel_places,
                                itinerary,
                            )
                        answer = ground_itinerary_answer_date(answer, itinerary)
                        await queue.put(
                            ctx.utils.sse({"type": "ai_response", "content": answer})
                        )
                    follow_ups = await _generate_follow_ups(
                        model,
                        str(message),
                        answer,
                    )
                    await _persist_follow_ups(
                        graph,
                        config,
                        follow_ups,
                        answer,
                        map_places_for_ui,
                        itinerary,
                    )
                    if follow_ups:
                        await queue.put(
                            ctx.utils.sse({"type": "follow_ups", "items": follow_ups})
                        )
            except Exception as exc:
                if not ctx.request.signal.is_set():
                    await queue.put(
                        ctx.utils.sse({"type": "error_message", "content": str(exc)})
                    )
            finally:
                await queue.put(done)

        producer = asyncio.create_task(produce())
        try:
            while not ctx.request.signal.is_set():
                try:
                    frame = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield ctx.utils.sse(
                        {"type": "ping", "ts": int(time.time() * 1000)}
                    )
                    continue
                if frame is done:
                    break
                yield frame
        finally:
            if not producer.done():
                producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer

        if any(usage):
            yield ctx.utils.sse(
                {
                    "type": "usage",
                    "input_tokens": usage[0],
                    "output_tokens": usage[1],
                    "total_tokens": usage[2] or usage[0] + usage[1],
                }
            )
        yield b"data: [DONE]\n\n"

    return ctx.utils.stream_sse(gen())
