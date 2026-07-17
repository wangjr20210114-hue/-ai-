"""Persistent single-user bootstrap, conversations, and messages API."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database.repositories.conversation_repo import (
    DEFAULT_CONVERSATION_ID,
    LOCAL_USER_ID,
    create_conversation,
    ensure_local_identity,
    get_conversation,
    list_conversations,
    list_messages,
    save_message,
)

router = APIRouter(prefix="/api", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    title: str = "新会话"


class SaveMessageRequest(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    role: Literal["user", "ai", "system"]
    content: str = Field(max_length=1_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ts: float | None = None


def _ui_message(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    return {
        **metadata,
        "id": item["id"],
        "role": item["role"],
        "content": item["content"],
        "ts": item["created_at"] * 1000,
        "streaming": False,
    }


@router.get("/bootstrap")
async def bootstrap(conversation_id: str = DEFAULT_CONVERSATION_ID) -> dict[str, Any]:
    await ensure_local_identity()
    conversation = await get_conversation(conversation_id)
    if conversation is None:
        conversation_id = DEFAULT_CONVERSATION_ID
        conversation = await get_conversation(conversation_id)
    messages = [_ui_message(item) for item in await list_messages(conversation_id)]
    return {
        "user": {"id": LOCAL_USER_ID, "display_name": "我", "timezone": "Asia/Shanghai"},
        "conversation": conversation,
        "messages": messages,
    }


@router.get("/conversations")
async def get_conversations() -> dict[str, Any]:
    return {"conversations": await list_conversations()}


@router.post("/conversations")
async def post_conversation(request: CreateConversationRequest) -> dict[str, Any]:
    return {"conversation": await create_conversation(request.title)}


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str) -> dict[str, Any]:
    if await get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"messages": [_ui_message(item) for item in await list_messages(conversation_id)]}


@router.post("/conversations/{conversation_id}/messages")
async def post_message(conversation_id: str, request: SaveMessageRequest) -> dict[str, Any]:
    try:
        item = await save_message(
            conversation_id,
            request.id,
            request.role,
            request.content,
            request.metadata,
            request.ts / 1000 if request.ts else None,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"message": _ui_message(item)}
