"""Controller for cancellation delegated to the Makers Agent runtime."""

from .._infrastructure.makers.identity import require_user, scoped_conversation_id
from .._infrastructure.http import error
from .._infrastructure.makers.conversation_repository import discard_chat_turn
from .._application.i18n import normalize_language, text

async def handler(ctx):
    identity = require_user(ctx)
    body = ctx.request.body or {}
    response_language = normalize_language(body.get("response_language"))
    raw_target = str(body.get("conversation_id") or "")
    if not raw_target:
        return error(text("request.conversation_id_required", response_language))
    target = scoped_conversation_id(ctx, str(identity["user_id"]), raw_target)
    requested_client_id = str(body.get("client_message_id") or "")
    stored, active = await discard_chat_turn(
        ctx.store,
        target,
        client_message_id=requested_client_id,
    )
    # Active Makers runs are keyed by the incoming public conversation id.
    # Only abort when the requested client turn still owns that run; a delayed
    # offline cancellation must never kill the next queued turn.
    result = (
        ctx.utils.abortActiveRun(raw_target)
        if active
        else None
    )
    return {
        "status": (
            "aborted"
            if active or bool(getattr(result, "aborted", False))
            else "discarded"
            if requested_client_id
            else "idle"
        ),
        "conversation_id": raw_target,
        "run_id": getattr(result, "run_id", None) or stored.get("run_id") or None,
        "client_message_id": requested_client_id or stored.get("client_message_id") or None,
    }
