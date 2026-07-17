"""Thin WebSocket transport for interactive Agent events.

This module owns connection lifecycle and protocol validation only. Intent
classification, planning, execution, persistence, model calls, and side effects
live in application/agent/skill layers.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from agent.context import AgentContext
from agent.executor import AgentExecutor
from agent.orchestrator import AgentOrchestrator
from application.agent_application_service import AgentApplicationService
from database.repositories.conversation_repo import (
    DEFAULT_CONVERSATION_ID,
    ensure_local_identity,
    get_conversation,
    history_lines,
)
from models.schemas import WSMessage
from security.local_auth import require_websocket_token

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_application(websocket: WebSocket) -> AgentApplicationService:
    state = websocket.app.state
    executor = AgentExecutor(
        registry=state.skill_registry,
        runtime=state.agent_runtime,
        handlers={},
        notifications=state.notification_service,
        usage=state.usage_service,
        cancellations=state.run_cancellation_service,
    )
    orchestrator = AgentOrchestrator(
        registry=state.skill_registry,
        runtime=state.agent_runtime,
        handlers={},
        executor=executor,
        action_service=state.action_service,
        intent_router=state.intent_router,
    )
    return AgentApplicationService(runtime=state.agent_runtime, orchestrator=orchestrator)


async def _send(websocket: WebSocket, message_type: str, payload: dict[str, Any] | None = None) -> None:
    await websocket.send_text(
        WSMessage(type=message_type, payload=payload or {}).model_dump_json()
    )


@router.websocket("/ws/{conversation_id}")
async def ws_endpoint(websocket: WebSocket, conversation_id: str) -> None:
    token_protocol = await require_websocket_token(websocket)
    if token_protocol is None:
        return
    await ensure_local_identity()
    if conversation_id == "local-user":
        conversation_id = DEFAULT_CONVERSATION_ID
    if await get_conversation(conversation_id) is None:
        await websocket.close(code=1008, reason="conversation not found")
        return

    await websocket.accept(subprotocol=token_protocol or None)
    await _send(
        websocket,
        "ack",
        {"user_id": "local-user", "conversation_id": conversation_id},
    )
    history = await history_lines(conversation_id)
    application = _build_application(websocket)
    context = AgentContext(session_id=conversation_id, history=history)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = WSMessage.model_validate_json(raw)
            except ValidationError:
                await _send(websocket, "error", {"message": "消息格式无效", "error_type": "validation_error"})
                continue

            if message.type == "ping":
                await _send(websocket, "pong")
                continue
            if message.type != "user_activity":
                await _send(
                    websocket,
                    "error",
                    {"message": f"不支持的消息类型：{message.type}", "error_type": "unsupported_message_type"},
                )
                continue

            text = str(message.payload.get("text") or "").strip()
            if not text:
                continue
            history.append(f"用户: {text}")
            await _send(websocket, "chat_thinking", {})
            try:
                await application.handle_user_message(
                    conversation_id=conversation_id,
                    text=text,
                    websocket=websocket,
                    context=context,
                    payload=message.payload,
                    client_message_id=message.payload.get("message_id")
                    or message.payload.get("client_message_id"),
                )
            except Exception as error:  # boundary guard; services persist detailed failures
                logger.exception("unexpected websocket application failure")
                try:
                    await _send(
                        websocket,
                        "error",
                        {
                            "message": f"处理失败：{type(error).__name__}: {error}",
                            "error_type": type(error).__name__,
                        },
                    )
                except Exception:
                    return
    except WebSocketDisconnect:
        logger.info("websocket disconnected: conversation=%s", conversation_id)
