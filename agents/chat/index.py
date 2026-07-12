"""Chat agent — fast LangGraph SSE on EdgeOne Makers."""

import time
from ._llm import get_model
from ._graph import build_graph
from ._tools import search_images

SYSTEM_PROMPT = (
    "你是元宝，一个智能助手。用 Markdown 回复。"
    "当用户需要图片时，使用 search_images 工具。回答中的图片用 ![描述](url) 插入。"
    "结束回复后，在最后一行用 --- 分隔，然后给出 2-3 个用户可能想问的后续问题。"
)


async def handler(ctx):
    body = ctx.request.body or {}
    message = body.get("message") or body.get("text") or ""
    if not message:
        return {"error": "'message' is required"}, 400

    model = get_model(ctx.env)

    # Tools: custom (images) + platform (web_search)
    all_tools = [search_images]
    if ctx.tools:
        try:
            from langchain_core.tools import tool as _tool_base
            all_tools = all_tools + ctx.tools.to_langchain_tools(_tool_base)
        except Exception:
            pass

    checkpointer = getattr(ctx.store, "langgraph_checkpointer", None)
    lg_store = getattr(ctx.store, "langgraph_store", None)
    graph = build_graph(model, all_tools, checkpointer=checkpointer, store=lg_store)

    async def gen():
        full = ""
        try:
            # Persist user message
            try:
                await ctx.store.append_message(ctx.conversation_id, "user", message)
            except Exception:
                pass

            # Stream
            messages = [{"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": message}]
            async for event in graph.astream(
                {"messages": messages},
                config={"configurable": {"thread_id": ctx.conversation_id}},
                stream_mode="messages",
            ):
                if ctx.request.signal.is_set():
                    break

                msg_t, _meta = event

                if hasattr(msg_t, "content") and msg_t.content and not getattr(msg_t, "tool_calls", None):
                    c = msg_t.content
                    if isinstance(c, str):
                        full += c
                        yield ctx.utils.sse({"type": "ai_response", "content": c})

                elif hasattr(msg_t, "tool_calls") and msg_t.tool_calls:
                    for tc in msg_t.tool_calls:
                        yield ctx.utils.sse({"type": "tool_call", "name": tc.get("name", "")})

                elif hasattr(msg_t, "type") and msg_t.type == "tool":
                    yield ctx.utils.sse({"type": "tool_result", "name": getattr(msg_t, "name", "")})

            # Save response
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
