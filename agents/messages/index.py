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
    latest_travel_plan = None
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
        item = {
            "id": str(_value(message, "id", "") or f"checkpoint-{index}"),
            "role": role,
            "content": content,
            "ts": index,
        }
        if role == "ai":
            additional = _value(message, "additional_kwargs", {}) or {}
            if isinstance(additional, dict):
                search_results = additional.get("search_results")
                if isinstance(search_results, dict) and search_results.get("total"):
                    item["searchResults"] = search_results
                follow_ups = additional.get("follow_ups")
                if isinstance(follow_ups, list) and follow_ups:
                    item["followUps"] = [
                        str(question)[:80] for question in follow_ups[:3] if question
                    ]
                map_places = additional.get("map_places")
                if isinstance(map_places, list) and map_places:
                    item["mapPlaces"] = [
                        place for place in map_places[:12] if isinstance(place, dict)
                    ]
                travel_plan = additional.get("travel_plan")
                if isinstance(travel_plan, dict):
                    schedules = travel_plan.get("schedules")
                    if isinstance(schedules, list):
                        latest_travel_plan = {
                            **travel_plan,
                            "schedules": [
                                schedule for schedule in schedules if isinstance(schedule, dict)
                            ],
                        }
        result.append(item)
    response = {"messages": result}
    if latest_travel_plan is not None:
        response["travel_plan"] = latest_travel_plan
        response["schedules"] = latest_travel_plan["schedules"]
    return response
