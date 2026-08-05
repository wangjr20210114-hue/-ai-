"""Lightweight reconnect state for one Maker-owned chat run."""

from .._infrastructure.makers.conversation_repository import (
    public_chat_run,
    read_chat_run,
)
from .._infrastructure.makers.identity import require_user, scoped_conversation_id
from .._infrastructure.makers.presentation_repository import (
    load_presentation_snapshot,
)
from .._infrastructure.http import error
from .._application.i18n import normalize_language, text


async def handler(ctx):
    identity = require_user(ctx)
    response_language = normalize_language((ctx.request.body or {}).get("response_language"))
    raw_conversation_id = str(
        (ctx.request.body or {}).get("conversation_id")
        or ctx.conversation_id
        or ""
    )
    if not raw_conversation_id:
        return error(text("request.conversation_header_required", response_language))
    conversation_id = scoped_conversation_id(
        ctx,
        str(identity["user_id"]),
        raw_conversation_id,
    )
    run = await read_chat_run(ctx.store, conversation_id)
    public_run = public_chat_run(run)
    presentation = None
    if public_run and public_run.get("status") in {"running", "cancel_requested"}:
        presentation = await load_presentation_snapshot(
            getattr(ctx.store, "langgraph_store", None),
            conversation_id,
            str(public_run.get("run_id") or ""),
        )
        if (
            isinstance(presentation, dict)
            and str(presentation.get("client_message_id") or "")
            != str(public_run.get("client_message_id") or "")
        ):
            presentation = None
    return {"run": public_run, "presentation": presentation}
