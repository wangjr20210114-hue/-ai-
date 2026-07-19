"""Stop endpoint — delegate cancellation to the Makers Agent runtime."""

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
    return {
        "status": "aborted" if result.aborted or active else "idle",
        "conversation_id": raw_target,
        "run_id": result.run_id or (stored.get("run_id") if isinstance(stored, dict) else None),
    }
