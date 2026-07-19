"""Append chat messages through the native Makers Python Conversation Store.

The Node and Python Makers runtimes can both read records written in the
platform's raw message format. Keeping writes on the Agent side avoids wrapping
message records in the Node generic-store envelope before Python reads them.
"""

from __future__ import annotations

from .._shared.auth import require_user, scoped_conversation_id
from .._shared.http import error
from .._shared.makers_conversation import ensure_conversation_title


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    raw_conversation_id = getattr(ctx, "conversation_id", "")
    if not raw_conversation_id:
        return error("makers-conversation-id header is required")
    conversation_id = scoped_conversation_id(ctx, user_id, raw_conversation_id)
    body = ctx.request.body or {}
    content = body.get("content") if isinstance(body.get("content"), str) else ""
    role = "assistant" if body.get("role") == "ai" else str(body.get("role") or "")
    if role not in {"user", "assistant", "system"} or not content:
        return error("Invalid conversation message")
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    message_id = await ctx.store.append_message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        user_id=user_id,
        metadata={
            **metadata,
            "client_message_id": str(metadata.get("id") or ""),
            "source": "yuanbao-web",
            "owner_user_id": user_id,
        },
    )
    if role == "user" and hasattr(ctx.store, "get_conversation") and hasattr(ctx.store, "update_conversation"):
        await ensure_conversation_title(ctx.store, conversation_id, content, user_id)
    return {"message_id": str(message_id)}
