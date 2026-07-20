"""Fixed owner identity for the personal Makers deployment; not an Agent route."""

from __future__ import annotations

from typing import Any

from .workspace import USER_WORKSPACE_ID


def require_user(_ctx: Any) -> dict[str, Any]:
    return {
        "user_id": USER_WORKSPACE_ID,
        "username": "local-user",
        "roles": ["owner"],
        "system": False,
    }


def scoped_conversation_id(ctx: Any, user_id: str, conversation_id: str | None = None) -> str:
    raw = str(conversation_id if conversation_id is not None else getattr(ctx, "conversation_id", "") or "")
    if not raw or len(raw) > 180:
        raise ValueError("无效会话 ID")
    return raw
