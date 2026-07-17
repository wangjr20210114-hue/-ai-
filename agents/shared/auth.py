"""Trusted user scope for optional EdgeOne JWT multi-user mode."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from typing import Any

from .workspace import USER_WORKSPACE_ID


def _header(ctx: Any, name: str) -> str:
    headers = getattr(getattr(ctx, "request", None), "headers", None)
    if headers is None:
        return ""
    try:
        value = headers.get(name) or headers.get(name.lower())
    except AttributeError:
        value = ""
    return str(value or "")


def _cookie(value: str, name: str) -> str:
    for item in value.split(";"):
        key, _, content = item.strip().partition("=")
        if key == name:
            return content
    return ""


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_jwt(token: str, secret: str, now: int | None = None) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3 or not secret:
        raise ValueError("无效登录凭证")
    try:
        header = json.loads(_decode(parts[0]))
        payload = json.loads(_decode(parts[1]))
    except Exception as exc:
        raise ValueError("无效登录凭证") from exc
    if header.get("alg") != "HS256":
        raise ValueError("不支持的登录凭证算法")
    expected = hmac.new(secret.encode("utf-8"), f"{parts[0]}.{parts[1]}".encode("ascii"), hashlib.sha256).digest()
    try:
        signature = _decode(parts[2])
    except Exception as exc:
        raise ValueError("无效登录凭证签名") from exc
    if not hmac.compare_digest(expected, signature):
        raise ValueError("登录凭证签名错误")
    timestamp = int(now or time.time())
    if int(payload.get("exp") or 0) <= timestamp or int(payload.get("iat") or timestamp + 1) > timestamp + 60:
        raise ValueError("登录凭证已过期")
    user_id = str(payload.get("sub") or "")
    if not re.fullmatch(r"[0-9a-fA-F-]{16,64}", user_id):
        raise ValueError("登录凭证缺少可信用户")
    return payload


def require_user(ctx: Any, *, allow_system: bool = False) -> dict[str, Any]:
    env = getattr(ctx, "env", {}) or {}
    if str(env.get("AUTH_MODE") or "single_user") != "multi_user":
        return {"user_id": USER_WORKSPACE_ID, "username": "local-user", "roles": ["owner"], "system": False}
    if allow_system:
        expected = str(env.get("PROACTIVE_SCHEDULE_SECRET") or "")
        supplied = _header(ctx, "x-yuanbao-system-secret")
        scoped_user = _header(ctx, "x-yuanbao-user-id")
        if expected and hmac.compare_digest(expected, supplied) and re.fullmatch(r"[0-9a-fA-F-]{16,64}", scoped_user):
            return {"user_id": scoped_user, "username": "system", "roles": ["system"], "system": True}
    token = _cookie(_header(ctx, "cookie"), "jwt_token")
    payload = verify_jwt(token, str(env.get("JWT_SECRET") or ""))
    roles = payload.get("roles") if isinstance(payload.get("roles"), list) else ["user"]
    if "user" not in roles and "admin" not in roles:
        raise ValueError("当前身份没有使用 Agent 的权限")
    return {
        "user_id": str(payload["sub"]),
        "username": str(payload.get("username") or ""),
        "roles": [str(role) for role in roles],
        "system": False,
    }


def scoped_conversation_id(ctx: Any, user_id: str, conversation_id: str | None = None) -> str:
    raw = str(conversation_id if conversation_id is not None else getattr(ctx, "conversation_id", "") or "")
    env = getattr(ctx, "env", {}) or {}
    if str(env.get("AUTH_MODE") or "single_user") != "multi_user":
        return raw
    if not raw or len(raw) > 180 or raw.startswith("tenant:"):
        raise ValueError("无效会话 ID")
    return f"tenant:{user_id}:{raw}"
