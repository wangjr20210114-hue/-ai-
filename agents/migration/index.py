"""Authenticated one-time SQLite bundle importer; disabled unless explicitly configured."""

from __future__ import annotations

import hmac

from .._shared.auth import require_user, scoped_conversation_id
from .._shared.http import error
from .._shared.legacy_migration import import_message_batch, import_state_bundle, validate_export_id


def _header(ctx, name: str) -> str:
    headers = getattr(getattr(ctx, "request", None), "headers", None)
    try:
        return str(headers.get(name) or headers.get(name.lower()) or "")
    except AttributeError:
        return ""


def _authorize(ctx) -> None:
    expected = str((ctx.env or {}).get("LEGACY_IMPORT_SECRET") or "")
    supplied = _header(ctx, "x-yuanbao-migration-secret")
    if len(expected) < 32 or not supplied or not hmac.compare_digest(expected, supplied):
        raise ValueError("旧数据导入未启用或迁移密钥无效")


async def handler(ctx):
    try:
        _authorize(ctx)
        identity = require_user(ctx)
        user_id = str(identity["user_id"])
        body = ctx.request.body or {}
        operation = str(body.get("operation") or "")
        export_id = validate_export_id(body.get("export_id"))
        if operation == "import_state":
            result = await import_state_bundle(
                ctx.store.langgraph_store, user_id, export_id, body.get("state") or {},
            )
            return result, 409 if result.get("status") == "conflict" else 200
        if operation == "import_messages":
            raw_conversation_id = str(body.get("conversation_id") or "")
            if not raw_conversation_id:
                raise ValueError("缺少 conversation_id")
            conversation_id = scoped_conversation_id(ctx, user_id, raw_conversation_id)
            result = await import_message_batch(
                ctx.store,
                ctx.store.langgraph_store,
                user_id=user_id,
                export_id=export_id,
                conversation_id=conversation_id,
                messages=body.get("messages") or [],
                title=str(body.get("title") or ""),
            )
            return result, 409 if result.get("status") == "reconciliation_required" else 200
        raise ValueError("不支持的迁移操作")
    except ValueError as exc:
        return error(str(exc))
