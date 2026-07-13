"""LangGraph chat endpoint running on the EdgeOne Makers agent runtime."""

import asyncio
import contextlib
import time

from ._graph import build_graph
from ._llm import get_model

SYSTEM_PROMPT = (
    "你是元宝，一个可靠、主动、简洁的中文智能助手。使用 Markdown 回复。"
    "需要最新信息、可靠来源或图片时，优先调用平台提供的 web_search 工具；"
    "不要编造来源、链接或工具结果。回答图片时使用 ![描述](url)。"
    "只有确实有帮助时，才在末尾给出 2-3 个简短的后续问题。"
)

HEARTBEAT_SECONDS = 5
MAX_GRAPH_RECURSION = 8


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


async def handler(ctx):
    body = ctx.request.body or {}
    message = body.get("message") or body.get("text") or ""
    if not message:
        return {"error": "'message' is required"}, 400

    model = get_model(ctx.env)

    # Reuse Makers-provided tools; no self-hosted search proxy or manual token flow.
    all_tools = []
    tool_setup_error = ""
    if ctx.tools and body.get("web_search") is not False:
        try:
            from langchain_core.tools import StructuredTool

            all_tools = list(
                ctx.tools.to_langchain_tools(StructuredTool, names=["web_search"])
            )
        except Exception as exc:
            tool_setup_error = f"平台工具初始化失败：{exc}"

    graph = build_graph(
        model,
        all_tools,
        SYSTEM_PROMPT,
        checkpointer=ctx.store.langgraph_checkpointer,
        store=ctx.store.langgraph_store,
    )

    async def gen():
        queue: asyncio.Queue = asyncio.Queue()
        done = object()
        usage = [0, 0, 0]

        async def produce():
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
                        await queue.put(
                            ctx.utils.sse(
                                {
                                    "type": "tool_result",
                                    "name": getattr(streamed_message, "name", ""),
                                    "content": _text_content(
                                        getattr(streamed_message, "content", "")
                                    )[:500],
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
