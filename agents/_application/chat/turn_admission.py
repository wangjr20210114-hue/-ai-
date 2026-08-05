"""Admission boundary for one chat turn.

This module owns request normalization, Maker run ownership and durable user
message indexing.  The turn orchestrator receives one immutable context and
can focus on planning/execution/presentation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from ..i18n import language_instruction, normalize_language, text
from .turn_policy import (
    normalize_browser_current_location,
    normalize_browser_location_request,
    run_cancelled,
)
from .turn_protocol import (
    clarification_answer_value,
    clarification_response_answers,
    clarification_response_id,
    should_persist_user_message,
)
from ..._infrastructure.http import error
from ..._infrastructure.makers.conversation_repository import (
    RUNNING_STATES,
    ensure_conversation_title,
    is_stale,
    read_chat_run,
    write_chat_run,
)
from ..._infrastructure.makers.identity import (
    conversation_index_user_id,
    require_user,
    scoped_conversation_id,
)
from ..._infrastructure.makers.request_context import request_id_for_turn
from ..._infrastructure.makers.presentation_repository import (
    delete_presentation_snapshot,
)


@dataclass(frozen=True, slots=True)
class AdmittedTurn:
    identity: dict[str, Any]
    user_id: str
    raw_conversation_id: str
    conversation_id: str
    body: dict[str, Any]
    message: str
    clarification_id: str
    current_clarification_answers: list[dict[str, Any]]
    silent_clarification: bool
    direct_public_answer: str
    response_language: str
    response_language_instruction: str
    browser_current_location: dict[str, Any] | None
    browser_location_request: str
    current_location_context: str
    run_id: str
    reference_images: list[str]
    run_state: dict[str, Any]


async def admit_turn(ctx) -> tuple[AdmittedTurn | None, Any | None]:
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    raw_conversation_id = str(getattr(ctx, "conversation_id", "") or "")
    conversation_id = scoped_conversation_id(ctx, user_id, raw_conversation_id)
    body = ctx.request.body or {}
    message = str(body.get("message") or body.get("text") or "")
    if not message:
        requested_language = normalize_language(body.get("response_language"))
        return None, error(text("chat.message_required", requested_language))

    clarification_id = clarification_response_id(body)
    answers = clarification_response_answers(body)
    manual_location = clarification_answer_value(body, "manual_location")
    response_language = normalize_language(body.get("response_language"))
    direct_public_answer = text(
        "chat.manual_location_answer",
        response_language,
        location=manual_location,
    ) if manual_location else ""
    browser_current_location = normalize_browser_current_location(
        body.get("current_location"),
        response_language=response_language,
    )
    browser_location_request = normalize_browser_location_request(
        body.get("location_request")
    )
    current_location_context = text(
        "chat.location_context.available",
        response_language,
    ) if browser_current_location else text(
        "chat.location_context.unavailable",
        response_language,
        request_state=browser_location_request,
    )

    previous_run = await read_chat_run(ctx.store, conversation_id)
    allow_after_stop = bool(body.get("_allow_after_stop"))
    if is_stale(previous_run):
        await write_chat_run(
            ctx.store,
            conversation_id,
            run_id=str((previous_run or {}).get("run_id") or ""),
            status="failed",
            error=text("chat.previous_run_timed_out", response_language),
        )
    elif isinstance(previous_run, dict) and previous_run.get("status") in RUNNING_STATES:
        if previous_run.get("status") == "cancel_requested":
            await write_chat_run(
                ctx.store,
                conversation_id,
                run_id=str(previous_run.get("run_id") or ""),
                status="cancelled",
            )
        elif allow_after_stop:
            raw_target = str(getattr(ctx, "conversation_id", "") or conversation_id)
            try:
                ctx.utils.abortActiveRun(raw_target)
            except Exception:
                logging.exception(
                    "maker abort retry failed conversation=%s", conversation_id
                )
            await write_chat_run(
                ctx.store,
                conversation_id,
                run_id=str(previous_run.get("run_id") or ""),
                status="cancelled",
            )
        else:
            return None, error(
                text("chat.conversation_busy", response_language),
                409,
            )

    if isinstance(previous_run, dict) and previous_run.get("run_id"):
        # Keep at most one completed recovery projection per conversation.
        # The committed LangGraph checkpoint remains the durable history.
        await delete_presentation_snapshot(
            getattr(ctx.store, "langgraph_store", None),
            conversation_id,
            str(previous_run.get("run_id") or ""),
        )

    if should_persist_user_message(body):
        try:
            await ctx.store.append_message(
                conversation_id=conversation_id,
                role="user",
                content=message,
                user_id=conversation_index_user_id(user_id),
                metadata={
                    "client_message_id": str(body.get("client_message_id") or ""),
                    "client_conversation_id": raw_conversation_id,
                    "source": "yuanbao-chat",
                    "owner_user_id": user_id,
                    "tenant_id": str(identity["tenant_id"]),
                },
            )
            await ensure_conversation_title(
                ctx.store,
                conversation_id,
                message,
                user_id,
                tenant_id=str(identity["tenant_id"]),
                client_conversation_id=raw_conversation_id,
            )
        except Exception:
            logging.exception(
                "native conversation append failed conversation=%s", conversation_id
            )

    run_id = request_id_for_turn(ctx)
    admitted_run = await write_chat_run(
        ctx.store,
        conversation_id,
        run_id=run_id,
        status="running",
        client_message_id=str(body.get("client_message_id") or ""),
    )
    if run_cancelled(admitted_run):
        return None, error(
            text("chat.conversation_busy", response_language),
            409,
        )
    reference_images = [
        str(item)
        for item in (body.get("reference_images") or [])
        if isinstance(item, str)
        and re.match(r"^data:image/(?:jpeg|png|webp);base64,", item, re.I)
        and len(item) <= 1_800_000
    ][:3]
    return AdmittedTurn(
        identity=identity,
        user_id=user_id,
        raw_conversation_id=raw_conversation_id,
        conversation_id=conversation_id,
        body=body,
        message=message,
        clarification_id=clarification_id,
        current_clarification_answers=answers,
        silent_clarification=bool(clarification_id),
        direct_public_answer=direct_public_answer,
        response_language=response_language,
        response_language_instruction=language_instruction(response_language),
        browser_current_location=browser_current_location,
        browser_location_request=browser_location_request,
        current_location_context=current_location_context,
        run_id=run_id,
        reference_images=reference_images,
        run_state=admitted_run,
    ), None
