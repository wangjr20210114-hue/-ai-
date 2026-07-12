"""Get conversation messages from EdgeOne store — for page refresh persistence."""

import json


async def handler(ctx):
    body = ctx.request.body or {}
    conv_id = body.get("conversation_id") or ""
    if not conv_id:
        return {"error": "conversation_id required"}, 400

    store = getattr(ctx, "agent", None)
    if store:
        store = store.store
    else:
        store = getattr(ctx, "store", None)

    if not store:
        return {"messages": []}

    try:
        msgs = await store.get_messages(conv_id, limit=100)
        result = []
        for m in msgs or []:
            result.append({
                "id": m.get("id") or m.get("message_id", ""),
                "role": m.get("role", "user"),
                "content": m.get("content", ""),
                "ts": m.get("created_at", 0),
            })
        return {"messages": result}
    except Exception as e:
        return {"messages": [], "error": str(e)}
