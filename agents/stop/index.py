"""Stop endpoint — delegate cancellation to the Makers Agent runtime."""

import asyncio

from .._shared.auth import require_user, scoped_conversation_id
from .._shared.http import error
from .._shared.makers_conversation import RUNNING_STATES, read_chat_run, write_chat_run

async def handler(ctx):
    identity = require_user(ctx)
    raw_target = str((ctx.request.body or {}).get("conversation_id") or "")
    if not raw_target:
        return error("conversation_id is required")
    target = scoped_conversation_id(ctx, str(identity["user_id"]), raw_target)
    stored = await read_chat_run(ctx.store, target)
    active = isinstance(stored, dict) and stored.get("status") in RUNNING_STATES
    if active:
        await write_chat_run(
            ctx.store,
            target,
            run_id=str(stored.get("run_id") or ""),
            status="cancel_requested",
        )
    # Active Makers runs are keyed by the incoming, public conversation id.
    result = ctx.utils.abortActiveRun(raw_target)
    latest = await read_chat_run(ctx.store, target)
    if active:
        # abortActiveRun closes the subscriber first. The chat generator then
        # cancels its LangGraph producer and publishes the terminal marker.
        # Wait briefly so a deliberate next send cannot share a thread with
        # the old producer and have its checkpoint overwritten.
        for _ in range(40):
            if not (
                isinstance(latest, dict)
                and latest.get("status") in RUNNING_STATES
            ):
                break
            await asyncio.sleep(0.1)
            latest = await read_chat_run(ctx.store, target)
    status = str((latest or {}).get("status") or "")
    if not active and result.aborted and status not in {"cancelled", "completed", "failed"}:
        await write_chat_run(
            ctx.store,
            target,
            run_id=str(result.run_id or (stored.get("run_id") if isinstance(stored, dict) else "")),
            status="cancelled",
        )
        status = "cancelled"
    return {
        "status": (
            "cancelled"
            if status == "cancelled"
            else "cancel_requested"
            if status == "cancel_requested"
            else "idle"
        ),
        "conversation_id": raw_target,
        "run_id": result.run_id or (stored.get("run_id") if isinstance(stored, dict) else None),
    }
