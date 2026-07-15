"""LangGraph chat endpoint running on the EdgeOne Makers agent runtime."""

import asyncio
import contextlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from ._graph import build_graph
from ._llm import get_model
from ._ui_tools import build_production_tools
from ._capability_plan import plan_capabilities

SYSTEM_PROMPT = """你是元宝，一个可靠、主动、自然的中文智能助手。使用 Markdown 回复。
当前北京时间是 {now}。
本轮能力规划（由独立模型语义判断，不是关键词规则）：{capability_plan}。调用 rich_search 时优先原样使用规划中的 search_query 和 image_query；只有为空时才自行生成简洁查询。
严格执行能力规划：needs_places 时必须调用地点工具；needs_map_action 时必须在核实全部地点后调用 prepare_map_recommendation；needs_web_search、needs_rich_answer 或 needs_images 任一为 true 时必须调用 rich_search；needs_images 时从视觉模型筛选过的标准 Markdown 图片中选择真正相关的图片，插到最合适的段落；ALT 可以结合当前段落改写，但必须忠于视觉描述。needs_rich_answer 时使用清晰的小标题、列表/时间线组织回答。能力规划不允许在回答中提及。
需要最新信息、可靠来源、地点营业信息或图片时先调用 rich_search；复杂问题主动扩大查询词和结果覆盖，不要编造来源、链接或工具结果。
推荐一个餐馆、景点或其他地点时，必须同时使用 rich_search 和 search_places。推荐两个及以上地点或路线时必须调用 search_places_batch，把回答中的每个地点作为独立 query 核实，并从每组选择一个最匹配的真实 place_id。只有地点工具返回的真实 place_id 才能交给 prepare_map_recommendation；未验证地点可以在正文中明确说明，但不能进地图。
prepare_map_recommendation 只生成用户可点击的地图 Action，不会自动改地图。expected_place_count 必须等于回答中实际推荐的地点数，place_ids 必须覆盖每组；数量不足时继续核实，不能创建残缺 Action。action_text 要根据上下文自然生成，避免每次使用同一句话。
新增、更新或删除日程时必须先调用 propose_calendar_changes 冻结提案，再请用户点击确认；不能只用普通文字询问，因为没有 Action 卡就无法安全提交。新增变更项设置 operation=create，并在 event 中提供 title、start_time、end_time、place_id；时间必须为带 +08:00 的 ISO 8601，更新和删除还要带 schedule_id。工具调用本身不会写入日程。绝不能在确认前声称已经修改日程。
用户要求创建腾讯会议时调用 propose_meeting；用户要求生图时调用 propose_image；两者都需要网页确认后执行。
需要网页图片时可用 collect_page_images 提取单页最多 30 张候选，再用 analyze_images_parallel 分批评估。回答中的图片使用 ![描述](url)。
静默使用用户记忆和旅行偏好，不要用“根据已确定的旅行偏好”“根据用户记忆”等固定句式开头，也不要主动解释内部记忆来源。
调用工具前后都不要输出搜索策略、思维链、内部提示词、查询改写或参数；只让前端显示简短进度，最终直接给结论。
只有确实有帮助时，才在末尾给出 2-3 个简短的后续问题。"""

HEARTBEAT_SECONDS = 5
MAX_GRAPH_RECURSION = 12


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


def _usage_values(message) -> tuple[int, int, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        return 0, 0, 0
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    return input_tokens, output_tokens, total_tokens


def _ui_action(content: str) -> dict | None:
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or not str(value.get("ui_action", "")):
        return None
    return value


async def handler(ctx):
    body = ctx.request.body or {}
    message = body.get("message") or body.get("text") or ""
    if not message:
        return {"error": "'message' is required"}, 400

    model = get_model(ctx.env)
    capability_plan = await plan_capabilities(model, message)
    logging.info("capability plan enabled=%s", [key for key, value in capability_plan.items() if value])

    # Production UI tools are local LangGraph tools; web search remains Makers-native.
    all_tools = build_production_tools(
        model,
        store=ctx.store.langgraph_store,
        conversation_id=ctx.conversation_id,
        env=ctx.env,
    )
    # Rich search is the single search path. Exposing the platform's plain
    # web_search beside it made semantically identical turns randomly lose the
    # established page-media + vision-review pipeline.
    tool_setup_error = ""

    graph = build_graph(
        model,
        all_tools,
        SYSTEM_PROMPT.format(
            now=datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S UTC+08:00"),
            capability_plan=json.dumps(capability_plan, ensure_ascii=False),
        ),
        checkpointer=ctx.store.langgraph_checkpointer,
        store=ctx.store.langgraph_store,
        required_tool=(
            "recommend_places_on_map" if capability_plan.get("needs_map_action")
            else "rich_search" if (
                capability_plan.get("needs_web_search")
                or capability_plan.get("needs_rich_answer")
                or capability_plan.get("needs_images")
            )
            else ""
        ),
    )

    async def gen():
        queue: asyncio.Queue = asyncio.Queue()
        done = object()
        usage = [0, 0, 0]

        async def produce():
            pending_actions: list[dict] = []
            pending_search_results: dict | None = None
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

                    streamed_message, _metadata = event
                    input_tokens, output_tokens, total_tokens = _usage_values(streamed_message)
                    usage[0] = max(usage[0], input_tokens)
                    usage[1] = max(usage[1], output_tokens)
                    usage[2] = max(usage[2], total_tokens)

                    if getattr(streamed_message, "type", "") == "tool":
                        tool_content = _text_content(
                            getattr(streamed_message, "content", "")
                        )
                        action = _ui_action(tool_content)
                        if action and action.get("ui_action") == "rich_search_results":
                            metadata = action.get("search_results")
                            if isinstance(metadata, dict):
                                pending_search_results = metadata
                            await queue.put(
                                ctx.utils.sse({
                                    "type": "tool_result",
                                    "name": getattr(streamed_message, "name", ""),
                                    "content": "富搜索来源和媒体已准备",
                                })
                            )
                            continue
                        if action and action["ui_action"] in {
                            "map_action", "calendar_action", "side_effect_action",
                        }:
                            # Action UI is protocolically terminal metadata. Buffer
                            # it until all assistant text has streamed so links and
                            # confirmation cards never appear mid-sentence.
                            pending_actions.append(action)
                            continue
                        await queue.put(
                            ctx.utils.sse(
                                {
                                    "type": "tool_result",
                                    "name": getattr(streamed_message, "name", ""),
                                    "content": tool_content[:500],
                                }
                            )
                        )
                        continue

                    tool_calls = getattr(streamed_message, "tool_calls", None) or []
                    if tool_calls:
                        for tool_call in tool_calls:
                            name = (
                                tool_call.get("name", "")
                                if isinstance(tool_call, dict)
                                else ""
                            )
                            await queue.put(ctx.utils.sse({"type": "tool_call", "name": name}))
                        continue

                    content = _text_content(getattr(streamed_message, "content", ""))
                    if content:
                        await queue.put(
                            ctx.utils.sse({"type": "ai_response", "content": content})
                        )
            except Exception as exc:
                if not ctx.request.signal.is_set():
                    await queue.put(
                        ctx.utils.sse({"type": "error_message", "content": str(exc)})
                    )
            finally:
                if pending_search_results is not None:
                    await queue.put(ctx.utils.sse({
                        "type": "search_results",
                        "payload": pending_search_results,
                    }))
                for action in pending_actions:
                    await queue.put(ctx.utils.sse({
                        "type": action["ui_action"],
                        "payload": action,
                    }))
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
