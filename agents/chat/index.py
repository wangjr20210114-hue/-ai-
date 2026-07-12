"""Chat agent — LangGraph + SSE streaming on EdgeOne Makers.

POST /chat
Body: { "message": "..." }
Streams: SSE (ai_response, tool_call, tool_result, ping, error_message)
"""

import asyncio
import time
from ._llm import get_model
from ._graph import build_graph
from ._tools import search_web, search_images


SYSTEM_PROMPT = (
    "你是元宝主动式 Agent，一个智能助手。"
    "用 Markdown 格式回复。"
    "不要在回答中提及搜索、参考信息、来源等内部过程。"
    "当用户问需要实时信息的问题时，使用 search_web 工具搜索。"
    "当用户想看图片时，使用 search_images 工具。"
    "回答中出现的图片使用 Markdown 语法 ![描述](url) 插入。"
)


async def handler(ctx):
    body = ctx.request.body or {}
    message = body.get("message") or body.get("text") or ""
    if not message:
        return {"error": "'message' is required"}, 400

    model = get_model(ctx.env)

    # Tools: ours + platform
    custom_tools = [search_web, search_images]
    platform_tools = []
    if ctx.tools:
        try:
            from langchain_core.tools import tool as _tool_base
            platform_tools = ctx.tools.to_langchain_tools(_tool_base)
        except Exception:
            pass
    all_tools = custom_tools + platform_tools

    # LangGraph adapters from EdgeOne
    checkpointer = getattr(ctx.store, "langgraph_checkpointer", None)
    lg_store = getattr(ctx.store, "langgraph_store", None)

    graph = build_graph(model, all_tools, checkpointer=checkpointer, store=lg_store)

    async def gen():
        try:
            # Build messages: system + history + current
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            try:
                history = await ctx.store.get_messages(ctx.conversation_id, limit=40)
                if history:
                    msgs = ctx.store.to_openai_input(history)
                    messages.extend(msgs[-40:])
            except Exception:
                pass
            messages.append({"role": "user", "content": message})

            # Persist user message
            try:
                await ctx.store.append_message(ctx.conversation_id, "user", message)
            except Exception:
                pass

            # Stream LangGraph events
            full = ""
            last_ping = time.time()
            async for event in graph.astream(
                {"messages": messages},
                config={"configurable": {"thread_id": ctx.conversation_id}},
                stream_mode="messages",
            ):
                if ctx.request.signal.is_set():
                    break

                # Heartbeat every 5s
                now = time.time()
                if now - last_ping >= 5:
                    yield ctx.utils.sse({"type": "ping", "ts": int(now * 1000)})
                    last_ping = now

                msg, _meta = event
                # AI text
                if hasattr(msg, "content") and msg.content and not getattr(msg, "tool_calls", None):
                    content = msg.content
                    if isinstance(content, str):
                        full += content
                        yield ctx.utils.sse({"type": "ai_response", "content": content})

                # Tool calls
                elif hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        yield ctx.utils.sse({
                            "type": "tool_call",
                            "name": tc.get("name", ""),
                            "args": tc.get("args", {}),
                        })

                # Tool results
                elif hasattr(msg, "type") and msg.type == "tool":
                    yield ctx.utils.sse({
                        "type": "tool_result",
                        "name": getattr(msg, "name", ""),
                        "content": str(msg.content)[:500] if msg.content else "",
                    })

            # Store assistant response
            if full:
                try:
                    await ctx.store.append_message(ctx.conversation_id, "assistant", full)
                except Exception:
                    pass

        except Exception as e:
            if not ctx.request.signal.is_set():
                yield ctx.utils.sse({"type": "error_message", "content": str(e)})
        yield b"data: [DONE]\n\n"

    return ctx.utils.stream_sse(gen())
