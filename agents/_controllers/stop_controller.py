"""Controller for cancellation delegated to the Makers Agent runtime."""

import asyncio

from .._infrastructure.makers.identity import require_user, scoped_conversation_id
from .._infrastructure.http import error
from .._infrastructure.makers.conversation_repository import discard_chat_turn
from .._application.i18n import normalize_language, text
from .._application.intelligence.service import (
    discard_turn_intelligence,
    load_intelligence_state,
    save_intelligence_state,
)
from .._infrastructure.makers.data_version import namespace as data_namespace
from .._application.proactive.service import (
    discard_proactive_source,
    load_proactive_state,
    save_proactive_state,
)


async def _discard_turn_derived_state(ctx, user_id: str, conversation_id: str, client_id: str) -> None:
    """Remove optional state that may have raced an explicit stop request."""
    store = getattr(ctx.store, "langgraph_store", None)
    if store is None or not client_id:
        return
    try:
        namespace = data_namespace("message_meta", conversation_id)
        intelligence, proactive, item = await asyncio.gather(
            load_intelligence_state(store, user_id),
            load_proactive_state(store, user_id),
            store.aget(namespace, "latest_extras"),
        )
        writes = []
        if discard_turn_intelligence(intelligence, client_id):
            writes.append(save_intelligence_state(store, intelligence, user_id))
        if discard_proactive_source(proactive, client_id):
            writes.append(save_proactive_state(store, proactive, user_id))
        value = (
            item.get("value")
            if isinstance(item, dict)
            else getattr(item, "value", None)
        )
        if (
            isinstance(value, dict)
            and str(value.get("client_message_id") or "") == client_id
        ):
            if hasattr(store, "adelete"):
                writes.append(store.adelete(namespace, "latest_extras"))
            else:
                writes.append(store.aput(namespace, "latest_extras", {}))
        if writes:
            await asyncio.gather(*writes)
    except Exception:
        # Cancellation itself must remain available when an optional cleanup
        # is temporarily unavailable on an older Maker store.
        pass


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
    resolved_client_id = str(
        requested_client_id or stored.get("client_message_id") or ""
    )
    # Active Makers runs are keyed by the incoming public conversation id.
    # Only abort when the requested client turn still owns that run; a delayed
    # offline cancellation must never kill the next queued turn.
    result = (
        ctx.utils.abortActiveRun(raw_target)
        if active
        else None
    )
    # Maker Store reads and writes above are batched so the acknowledgement
    # remains quick without weakening the guarantee that stopped content is
    # absent from memory, proactive state and cached presentation extras.
    await _discard_turn_derived_state(
        ctx,
        str(identity["user_id"]),
        target,
        resolved_client_id,
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
        "client_message_id": resolved_client_id or None,
    }
