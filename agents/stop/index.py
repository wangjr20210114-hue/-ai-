"""Stop endpoint — abort a running conversation."""

from .._shared.auth import require_user, scoped_conversation_id

async def handler(ctx):
    identity = require_user(ctx)
    raw_target = ctx.request.body.get("conversation_id") or ""
    target = scoped_conversation_id(ctx, str(identity["user_id"]), raw_target)
    result = ctx.utils.abortActiveRun(target)
    return {
        "status": "aborted" if result.aborted else "idle",
        "conversation_id": raw_target,
        "run_id": result.run_id,
    }
