"""Stop endpoint — abort a running conversation."""

async def handler(ctx):
    target = ctx.request.body.get("conversation_id") or ""
    result = ctx.utils.abortActiveRun(target)
    return {
        "status": "aborted" if result.aborted else "idle",
        "conversation_id": result.conversation_id,
        "run_id": result.run_id,
    }
