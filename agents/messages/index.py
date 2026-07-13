"""Read the latest LangGraph checkpoint for frontend conversation hydration."""


def _value(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return ""


async def handler(ctx):
    conversation_id = ctx.conversation_id
    if not conversation_id:
        return {"error": "makers-conversation-id header is required"}, 400

    config = {"configurable": {"thread_id": conversation_id}}
    checkpoint_tuple = await ctx.store.langgraph_checkpointer.aget_tuple(config)
    if checkpoint_tuple is None:
        return {"messages": []}

    checkpoint = _value(checkpoint_tuple, "checkpoint", {}) or {}
    channel_values = checkpoint.get("channel_values", {}) if isinstance(checkpoint, dict) else {}
    stored_messages = (
        channel_values.get("messages", []) if isinstance(channel_values, dict) else []
    )

    result = []
    for index, message in enumerate(stored_messages):
        message_type = str(_value(message, "type", _value(message, "role", "")))
        role = {
            "human": "user",
            "user": "user",
            "ai": "ai",
            "assistant": "ai",
        }.get(message_type)
        content = _text(_value(message, "content", ""))
        if not role or not content:
            continue
        result.append(
            {
                "id": str(_value(message, "id", "") or f"checkpoint-{index}"),
                "role": role,
                "content": content,
                "ts": index,
            }
        )
    return {"messages": result}
